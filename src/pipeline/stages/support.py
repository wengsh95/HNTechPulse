"""Cross-stage runtime helpers used by the orchestrator."""

import shutil
from typing import Optional

from src.core.models import ContentPackage, Script
from src.pipeline.agent_io import append_agent_event
from src.pipeline.paths import (
    agent_path,
    date_root,
    pipeline_path,
    raw_downloaded_pages_dir,
)
from src.pipeline.stages.context import OrchestratorContext


class SupportStageMixin(OrchestratorContext):
    """Keep cache refresh and degraded-run helpers out of stage code."""

    def _refresh_variant_outputs(self, date: str) -> None:
        base = date_root(date)
        if not base.exists():
            return
        deleted: list[str] = []
        script_path = pipeline_path(date, "script.json")
        paths = [
            script_path,
            script_path.with_name(script_path.name + ".manifest.json"),
            agent_path(date, "agent_decision.json"),
            agent_path(date, "agent_variant_decision.json"),
            agent_path(date, "script_lock.json"),
        ]
        for path in paths:
            if path.exists() and path.is_file():
                path.unlink()
                deleted.append(str(path).replace("\\", "/"))

        variants_dir = base / "pipeline" / "variants"
        if variants_dir.exists() and variants_dir.is_dir():
            shutil.rmtree(variants_dir)
            deleted.append(str(variants_dir).replace("\\", "/"))

        segments_dir = base / "pipeline" / "segments"
        if segments_dir.exists() and segments_dir.is_dir():
            for pattern in (
                "story_scan_item*.json",
                "story_scan_item*.json.tmp",
            ):
                for path in segments_dir.glob(pattern):
                    if path.is_file():
                        path.unlink()
                        deleted.append(str(path).replace("\\", "/"))

        if deleted:
            self.logger.info(
                f"Refresh script/variant caches: deleted {len(deleted)} item(s)"
            )
            append_agent_event(
                date,
                "variants_refreshed",
                deleted_count=len(deleted),
                deleted=deleted,
            )

    def _print_enrich_failure_guidance(self, failed_items: list) -> None:
        date = self._progress.date
        steps = self._progress.steps
        self.logger.info("")
        self.logger.info("=" * 60)
        self.logger.info(f"  {len(failed_items)} item(s) need manual download.")
        self.logger.info(
            f"  Save each page as HTML to: {raw_downloaded_pages_dir(date)}/"
        )
        self.logger.info("  Then re-run:")
        self.logger.info(
            f"    uv run python main.py --date {date} --steps {','.join(steps)}"
        )
        self.logger.info("=" * 60)

    def _mark_degraded_enrichment(self, failed_items: list) -> None:
        self.logger.warning(
            "Agent mode: continuing with degraded enrichment for "
            f"{len(failed_items)} item(s)"
        )
        for item in failed_items:
            if not item.editor_angle:
                item.editor_angle = item.dek or item.title or ""
            if not item.dek:
                item.dek = item.title or ""
            if item.key_points is None:
                item.key_points = []
            if item.keywords is None:
                item.keywords = []
            if not item.category:
                item.category = "unknown"
            if not item.why_it_matters:
                item.why_it_matters = item.editor_angle or item.title or ""
        if self._workflow is not None:
            degraded_items = [
                {
                    "story_id": str(item.source_id),
                    "title": item.title or "",
                    "reason": "enrichment_failed",
                    "continued": True,
                }
                for item in failed_items
            ]
            self._workflow.update_metadata(degraded_items=degraded_items)

    def _insufficient_context_items(self, items: list) -> list[dict]:
        min_comments = int(
            self.config.get("agent", {}).get("min_comments_for_discussion_only", 5)
        )
        blocked = []
        for item in items:
            has_article = bool(item.article_text or item.article_summary)
            comments = [c for c in item.comments if (c.content or "").strip()]
            if has_article or len(comments) >= min_comments:
                continue
            blocked.append(
                {
                    "story_id": str(item.source_id),
                    "title": item.title or "",
                    "url": item.url or "",
                    "reason": "article_unavailable_and_too_few_comments",
                    "comment_count": len(comments),
                    "min_comments_required": min_comments,
                }
            )
        return blocked

    def _extract_highlight_entries(
        self, script: Optional[Script], content: ContentPackage
    ) -> list[dict]:
        """Pull highlight entries from the opening cover card."""
        if script and script.segments:
            opening = script.segments[0]
            for elem in opening.scene_elements:
                if elem.element_type == "cover_card":
                    entries = elem.props.get("highlight_entries")
                    if entries:
                        return list(entries)

        self.logger.warning("No highlight_entries found, using content items fallback")
        return [
            {
                "rank": i + 1,
                "story_index": i,
                "original_title": item.title,
                "title_translation": item.title_cn or item.title,
                "editor_angle": item.editor_angle or item.dek or "",
                "why_it_matters": "",
                "signal": "",
                "category": item.category or "",
                "keywords": item.keywords or [],
                "score": item.score,
                "comment_count": item.comment_count,
                "coverage_tier": "focus",
                "presentation_mode": "deep",
                "section": "",
            }
            for i, item in enumerate(content.items[:3])
        ]
