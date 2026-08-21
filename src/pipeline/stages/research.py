"""Research-input stages for the Hacker News video pipeline."""

import json
from typing import Any

from src.core.models import ContentPackage
from src.pipeline.agent_io import append_agent_event, utc_now
from src.pipeline.paths import agent_path, pipeline_path, raw_downloaded_pages_dir
from src.utils.atomic_io import atomic_write_json


class ResearchStageMixin:
    """Fetch, select, enrich, and judge the content package."""

    @staticmethod
    def _selection_ids(content: ContentPackage) -> list[str]:
        return [str(item.source_id) for item in content.items]

    def _load_selection_lock(self, date: str) -> dict[str, Any] | None:
        path = agent_path(date, "selection_lock.json")
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Invalid selection lock: {path}") from exc
        if not isinstance(payload, dict) or not isinstance(
            payload.get("source_ids"), list
        ):
            raise RuntimeError(f"Invalid selection lock: {path}")
        if payload.get("date") not in {None, date}:
            raise RuntimeError(f"Selection lock date mismatch: {path}")
        return payload

    def _assert_selection_lock(
        self, content: ContentPackage, date: str, lock: dict[str, Any]
    ) -> None:
        locked_ids = [str(source_id) for source_id in lock["source_ids"]]
        current_ids = self._selection_ids(content)
        if locked_ids != current_ids:
            raise RuntimeError(
                "Selection lock mismatch: the current content IDs differ from the "
                f"locked selection ({locked_ids} != {current_ids}). "
                "Use --refresh-selection explicitly to choose a new set."
            )

    def _write_selection_lock(self, content: ContentPackage, date: str) -> None:
        path = agent_path(date, "selection_lock.json")
        atomic_write_json(
            path,
            {
                "schema_version": 1,
                "date": date,
                "source_ids": self._selection_ids(content),
                "items": [
                    {
                        "source_id": str(item.source_id),
                        "title": item.title or "",
                        "url": item.url or "",
                    }
                    for item in content.items
                ],
                "created_at": utc_now(),
            },
        )
        append_agent_event(
            date,
            "selection_locked",
            source_ids=self._selection_ids(content),
        )

    def _step_fetch(self, date: str) -> ContentPackage:
        self.logger.info("Step: Fetch content")
        if self.dry_run:
            self.logger.info("Dry run: skipping fetch")
            return ContentPackage(date=date, items=[])

        if self.agent_mode and not self.refresh_selection:
            lock = self._load_selection_lock(date)
            if lock:
                try:
                    content = self.content_preparer.load_content(date)
                except FileNotFoundError as exc:
                    raise RuntimeError(
                        "Selection is locked but pipeline/content.json is missing; "
                        "restore the content artifact or use --refresh-selection."
                    ) from exc
                self._assert_selection_lock(content, date, lock)
                self.logger.info("  Selection lock found; reusing locked content")
                return content

        content = self.content_fetcher.fetch(date)
        self.content_preparer.save_content(content, date)
        return content

    def _step_prefilter(self, content: ContentPackage, date: str) -> ContentPackage:
        self.logger.info("Step: Prefilter — LLM tech-relevance filter")
        if self.dry_run:
            self.logger.info("Dry run: skipping prefilter")
            return content

        if self.agent_mode and not self.refresh_selection:
            lock = self._load_selection_lock(date)
            if lock:
                self._assert_selection_lock(content, date, lock)
                self.logger.info("  Selection lock found; skipping prefilter refresh")
                return content

        prefilter_cfg = self.config.get("prefilter", {})
        if prefilter_cfg.get("comment_preview_enabled", True):
            preview_count = int(prefilter_cfg.get("comment_preview_count", 5) or 0)
            if preview_count > 0:
                content = self.content_fetcher.fetch_comment_preview(
                    content,
                    date,
                    top_level_count=preview_count,
                )

        content = self.prefilter.filter(content, date)
        self.content_preparer.save_content(content, date)
        if self.agent_mode:
            self._write_selection_lock(content, date)
        return content

    def _step_fetch_comments(
        self, content: ContentPackage, date: str
    ) -> ContentPackage:
        self.logger.info("Step: Fetch comments — HN comments per story")
        if self.dry_run:
            self.logger.info("Dry run: skipping comment fetch")
            return content

        if all(item.comments and not item.comments_partial for item in content.items):
            self.logger.info("  Comments already attached to all items")
            return content

        content = self.content_fetcher.fetch_comments(content, date)
        self.content_preparer.save_content(content, date)
        return content

    def _step_enrich_articles(
        self, content: ContentPackage, date: str
    ) -> tuple[ContentPackage, list]:
        self.logger.info("Step: Enrich articles — fetch body and extract metadata")
        if self.dry_run:
            self.logger.info("Dry run: skipping article enrichment")
            return content, []

        if self.article_enricher is None:
            self.logger.info("Article enricher not configured, skipping")
        else:
            enriched = self.article_enricher.enrich(content, date)
            if enriched is not None:
                content = enriched

        failed_items = [
            item
            for item in content.items
            if item.enrichment_source in ("fetch_failed", "extraction_failed")
        ]

        if failed_items:
            download_dir = raw_downloaded_pages_dir(date)
            download_dir.mkdir(parents=True, exist_ok=True)
            self.logger.warning(
                f"{len(failed_items)} items could not be fetched automatically."
            )
            for item in failed_items:
                reason = item.enrichment_source
                title = (item.title or "")[:60]
                url = item.url or ""
                self.logger.info(f"  [{reason}] {item.source_id}: {title}")
                self.logger.info(f"         {url}")
            self.logger.warning(
                f"Download each page in your browser, save as HTML or PDF to:\n"
                f"    {download_dir}/\n"
                f"  File naming: {{source_id}}.html or {{source_id}}.pdf\n"
                f"  Then re-run the pipeline. It will resume from this point."
            )
            self.content_preparer.save_content(content, date)
        if not failed_items or self.allow_degraded_enrichment:
            # Persist the source/enrichment result before the title LLM call so
            # a translation failure can resume without refetching articles.
            self.content_preparer.save_content(content, date)
            # Title translation belongs to the research/enrichment boundary.
            content = self._translate_titles_in_enrichment(content, date)
            # Always persist enrichment results back to content.json, even on
            # the happy path. Without this, downstream steps (write_script,
            # title, …) see items with editor_angle=None and crash.
            self.content_preparer.save_content(content, date)

        return content, failed_items

    def _translate_titles_in_enrichment(
        self, content: ContentPackage, date: str
    ) -> ContentPackage:
        """Fill title_cn as part of the research/enrichment boundary."""
        if all(item.title_cn for item in content.items):
            self.logger.info("  All titles already translated")
            return content

        self.logger.info(
            "  Translating %d titles within enrichment (LLM batch)",
            sum(1 for item in content.items if item.title and not item.title_cn),
        )
        return self.llm_provider.translate_titles(content, "translate.md", date)

    def _step_judge_comments(
        self, content: ContentPackage, date: str
    ) -> ContentPackage:
        self.logger.info("Step: Judge comments — LLM top-15 + quote selection")
        if self.dry_run:
            self.logger.info("Dry run: skipping comment judging")
            return content

        judgement_path = pipeline_path(date, "comment_judgement.json")
        if judgement_path.exists():
            self.logger.info(f"  Comment judgement already done at {judgement_path}")
            return content

        self.comment_judge.judge(content, date)
        self.content_preparer.save_content(content, date)
        return content
