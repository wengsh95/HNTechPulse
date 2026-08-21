"""Editorial shaping and human-review stages."""

import json
from pathlib import Path
from typing import Optional

from src.core.models import ContentPackage, Script
from src.pipeline.agent_io import file_sha256, stable_hash, write_artifact_manifest
from src.pipeline.agent_variants import sync_selected_variant_snapshot
from src.pipeline.human_review import (
    generate_script_review_page,
    script_approval_is_current,
)
from src.pipeline.paths import date_root, pipeline_path
from src.pipeline.quick_news import draft_quick_news
from src.pipeline.script import apply_subtitle_revisions
from src.pipeline.story_images import prepare_story_images
from src.pipeline.storyboard import apply_storyboard
from src.pipeline.storyboard_draft import draft_storyboard
from src.pipeline.subtitle_planner import prepare_subtitles
from src.pipeline.video_structure import prepare_video_structure
from src.utils.atomic_io import atomic_write_json


class EditorialStageMixin:
    """Apply editorial shaping, review, storyboard, and image preparation."""

    def _step_prepare_subtitles(
        self, script: Optional[Script], date: str
    ) -> Optional[Script]:
        self.logger.info("Step: Prepare subtitles — local agent selection")
        if script is None:
            raise ValueError("Script not loaded; cannot prepare subtitles")
        if self.dry_run:
            self.logger.info("Dry run: skipping subtitle selection")
            return script

        plan = prepare_subtitles(script, date, config=self.config)
        self.script_writer.save_script(script, date)
        self.logger.info(
            "  Agent selected %d subtitle changes across %d entries",
            plan["changed_count"],
            len(plan["entries"]),
        )
        return script

    def _step_human_review(
        self,
        script: Optional[Script],
        date: str,
        *,
        content: Optional[ContentPackage] = None,
    ) -> tuple[bool, Path]:
        self.logger.info("Step: Human review — require approval for current script")
        if script is None:
            raise ValueError("Script not loaded; cannot prepare human review")

        review_page = date_root(date) / "review" / "script_review.html"
        if self.dry_run:
            self.logger.info("Dry run: skipping human review gate")
            return True, review_page

        # Automatic copy review is part of preparing the human-review packet.
        self._auto_review_script(content, script, date)

        review_page = generate_script_review_page(
            script,
            date,
            config=self.config,
        )
        approved = script_approval_is_current(date, script)
        if approved:
            self.logger.info("  Current script has human approval")
        else:
            self.logger.info("  Review page ready: %s", review_page)
        return approved, review_page

    def _step_apply_storyboard(
        self, script: Optional[Script], date: str
    ) -> Optional[Script]:
        self.logger.info("Step: Apply storyboard — select Remotion shot templates")
        if script is None:
            raise ValueError("Script not loaded; cannot apply storyboard")
        if self.dry_run:
            self.logger.info("Dry run: skipping storyboard application")
            return script

        script, application = apply_storyboard(script, date, logger=self.logger)
        if application is not None and application.changed_count:
            self.script_writer.save_script(script, date)
        return script

    def _step_draft_storyboard(self, script: Optional[Script], date: str) -> None:
        self.logger.info("Step: Draft storyboard — agent shot selection")
        if script is None:
            raise ValueError("Script not loaded; cannot draft storyboard")
        if self.dry_run:
            self.logger.info("Dry run: skipping storyboard draft")
            return
        draft_storyboard(
            script,
            date,
            llm_provider=self.llm_provider,
            config=self.config,
            logger=self.logger,
        )

    def _step_draft_quick_news(
        self,
        script: Optional[Script],
        date: str,
        *,
        content: Optional[ContentPackage] = None,
    ) -> Optional[Script]:
        self.logger.info("Step: Draft quick news — agent selection")
        if script is None:
            raise ValueError("Script not loaded; cannot draft quick news")
        if self.dry_run:
            self.logger.info("Dry run: skipping quick-news draft")
            return script
        draft_quick_news(
            script,
            date,
            llm_provider=self.llm_provider,
            config=self.config,
            logger=self.logger,
        )
        # The quick-news segment is the final script shape mutation before
        # image preparation. Normalize all story roles and translate the exact
        # selected comments in this same tracked editorial step.
        self._normalize_video_structure(script, date)
        if content is not None:
            _, translated_script = self._apply_comment_translations(
                content, script, date, save_script=False
            )
            script = translated_script or script
        self.script_writer.save_script(script, date)
        return script

    def _step_prepare_story_images(
        self,
        script: Optional[Script],
        content: Optional[ContentPackage],
        date: str,
    ):
        self.logger.info("Step: Prepare story images — one image per story")
        if script is None:
            raise ValueError("Script not loaded; cannot prepare story images")
        if self.dry_run:
            return prepare_story_images(script, content, date, agent_mode=False)
        result = prepare_story_images(
            script,
            content,
            date,
            fetcher=getattr(self.article_enricher, "fetcher", None),
            agent_mode=self.agent_mode,
            config=self.config,
            logger=self.logger,
        )
        if result.changed:
            self.script_writer.save_script(script, date)
        return result

    def _normalize_video_structure(
        self, script: Optional[Script], date: str
    ) -> Optional[Script]:
        self.logger.info("Step: Normalize video structure — headline/focus/quick roles")
        if script is None:
            raise ValueError("Script not loaded; cannot normalize video structure")
        if self.dry_run:
            return script
        result = prepare_video_structure(
            script, date, config=self.config, logger=self.logger
        )
        if result.changed:
            self.script_writer.save_script(script, date)
        return script

    def _build_focus_story_input(
        self, script: Script, content: ContentPackage, date: str
    ) -> tuple[dict, dict]:
        """Build focus-story metadata and analyzed comment lanes for title."""
        highlight_entries = self._extract_highlight_entries(script, content)
        if highlight_entries:
            story_idx = highlight_entries[0].get("story_index", 0)
            if isinstance(story_idx, int) and 0 <= story_idx < len(content.items):
                focus = content.items[story_idx]
            else:
                focus = content.items[0]
        elif content.items:
            focus = content.items[0]
        else:
            return {}, {}

        focus_story = {
            "source_id": focus.source_id or "",
            "title": focus.title,
            "title_cn": focus.title_cn or "",
            "url": focus.url or "",
            "editor_angle": focus.editor_angle or "",
            "why_it_matters": focus.why_it_matters or "",
            "category": focus.category or "",
            "score": focus.score or 0,
            "comment_count": focus.comment_count or 0,
            "article_summary": focus.article_summary or "",
            "key_points": focus.key_points or [],
        }

        from src.pipeline.comment.judge import judgement_cache_path

        jp = judgement_cache_path(date)
        comment_analysis: dict = {}
        if jp.exists():
            try:
                jdata = json.loads(jp.read_text(encoding="utf-8"))
                sid = str(focus.source_id or "")
                story = (jdata.get("stories") or {}).get(sid)
                if story is None:
                    for _, candidate in (jdata.get("stories") or {}).items():
                        if str(candidate.get("story_id", "")) == sid:
                            story = candidate
                            break
                if story:
                    lanes = {}
                    for lane_name in (
                        "representative",
                        "detail",
                        "color",
                        "counterpoint",
                    ):
                        entries = [
                            {
                                "stance": entry.get("stance", ""),
                                "claim": entry.get("claim", ""),
                                "role": entry.get("role", ""),
                                "quote_score": entry.get("quote_score", 0),
                            }
                            for entry in (story.get("comment_lanes") or {}).get(
                                lane_name, []
                            )
                            or []
                        ]
                        if entries:
                            lanes[lane_name] = entries
                    comment_analysis = {
                        "discussion_mode": story.get("discussion_mode", ""),
                        "discussion_summary": story.get("discussion_summary", ""),
                        "lanes": lanes,
                        "quote_candidates": [
                            {
                                "stance": entry.get("stance", ""),
                                "claim": entry.get("claim", ""),
                                "quote_score": entry.get("quote_score", 0),
                            }
                            for entry in (story.get("quote_candidates") or [])[:10]
                        ],
                    }
            except (json.JSONDecodeError, OSError, ImportError):
                pass

        return focus_story, comment_analysis

    def _auto_review_script(
        self, content: ContentPackage, script: Optional[Script], date: str
    ) -> Optional[Script]:
        self.logger.info("  Automatic script review — LLM quality audit + auto-revise")
        if script is None:
            self.logger.warning("Script not loaded; skipping script review")
            return script

        segment = next(
            (s for s in script.segments if s.segment_type == "story_scan"), None
        )
        sub_texts = (
            segment.meta.get("sub_segment_subtitle_texts") if segment else None
        ) or []
        if not sub_texts:
            self.logger.info("  No story_scan sub-segments to review; skipping")
            return script

        cache_path = pipeline_path(date, "script_review.json")

        def _apply(revisions: dict[int, list[str]]) -> None:
            changed, warnings = apply_subtitle_revisions(script, revisions)
            for warning in warnings:
                self.logger.info(f"  Review: {warning}")
            self.logger.info(f"  Review: applied {changed} subtitle revision(s)")

        current_hash = stable_hash(sub_texts)
        if cache_path.exists():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                cached = {}
            if cached.get("result_subsegments_hash") == current_hash:
                self.logger.info("  Script already matches cached review; skipping")
                return script

        if self.dry_run:
            self.logger.info("Dry run: skipping script review")
            return script

        payload = [
            {"index": i, "subtitle_texts": texts} for i, texts in enumerate(sub_texts)
        ]
        context = {
            "subsegments_json": json.dumps(payload, ensure_ascii=False, indent=2),
            "date": date,
        }
        try:
            result = self.llm_provider.complete_prompt(
                "prompts/script_review.md",
                context,
                label="human_review_auto",
                expect_json=True,
                max_tokens=16384,
                model=self.llm_provider.fast_model,
                temperature=self.llm_provider.fast_temperature,
            )
        except Exception as e:
            self.logger.warning(
                f"  Script review LLM call failed ({type(e).__name__}: {e}); "
                f"leaving script unchanged"
            )
            return script

        revisions = self._parse_review_revisions(result, len(sub_texts))
        _apply(revisions)

        result_segment = next(
            (s for s in script.segments if s.segment_type == "story_scan"), None
        )
        result_texts = (
            result_segment.meta.get("sub_segment_subtitle_texts")
            if result_segment
            else sub_texts
        )
        atomic_write_json(
            cache_path,
            {
                "revisions": [
                    {"index": i, "subtitle_texts": texts}
                    for i, texts in sorted(revisions.items())
                ],
                "overall_assessment": str(result.get("overall_assessment") or ""),
                "result_subsegments_hash": stable_hash(result_texts),
            },
        )
        write_artifact_manifest(
            cache_path,
            step="human_review_auto",
            date=date,
            inputs={
                "source_subsegments_hash": current_hash,
                "prompt_hash": file_sha256(Path("prompts/script_review.md")),
                "date": date,
            },
            config=self.config,
        )
        self.script_writer.save_script(script, date)
        if self.agent_mode:
            sync_selected_variant_snapshot(date, script)
        return script

    @staticmethod
    def _parse_review_revisions(
        result: dict, sub_segment_count: int
    ) -> dict[int, list[str]]:
        """Validate review output into ``{index: [subtitle texts]}``."""
        revisions: dict[int, list[str]] = {}
        for entry in result.get("revisions") or []:
            if not isinstance(entry, dict):
                continue
            idx = entry.get("index")
            texts = entry.get("subtitle_texts")
            if not isinstance(idx, int) or idx < 0 or idx >= sub_segment_count:
                continue
            if not isinstance(texts, list):
                continue
            cleaned = [str(text).strip() for text in texts if str(text).strip()]
            if cleaned:
                revisions[idx] = cleaned
        return revisions
