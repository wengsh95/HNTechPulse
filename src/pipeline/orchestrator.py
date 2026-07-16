import io
import json
import os
import re
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any, List, Optional, Tuple

from src.core.interfaces import (
    ContentFetcher,
    LLMProvider,
    TTSProvider,
    Renderer,
    ImageGeneratorProvider,
)
from src.core.models import ContentPackage, Script
from src.pipeline.agent_decision import AgentDecisionEngine
from src.pipeline.agent_io import (
    append_agent_event,
    file_sha256,
    is_artifact_fresh,
    stable_hash,
    write_artifact_manifest,
)
from src.pipeline.agent_variants import (
    promote_variant_script,
    sync_selected_variant_snapshot,
    write_variants_index,
)
from src.pipeline.publish_guide_inputs import publish_guide_manifest_inputs
from src.pipeline.xhs_guide_inputs import xhs_guide_manifest_inputs
from src.pipeline.comment import CommentAnalyzer, CommentJudge, CommentRefiner
from src.pipeline.agent_state import AgentState, BLOCK_INSUFFICIENT_CONTEXT
from src.pipeline.content_io import ContentPreparer
from src.pipeline.paths import (
    agent_path,
    date_root,
    pipeline_audio_dir,
    pipeline_path,
    publish_path,
    raw_downloaded_pages_dir,
    render_path,
    render_remotion_dir,
    render_root,
)
from src.pipeline.pipeline_progress import PipelineProgress
from src.pipeline.prefilter import Prefilter
from src.providers.renderer.binary_finder import find_npx
from src.pipeline.script import ScriptWriter, apply_subtitle_revisions
from src.pipeline.timing_engine import TimingEngine
from src.pipeline.transcript_generator import save_transcript
from src.pipeline.translation_manager import TranslationManager
from src.pipeline.tts_processor import TTSProcessor
from src.utils.atomic_io import atomic_write_json, atomic_write_text
from src.utils.logger import setup_logger
from src.utils.text import normalize_cjk_mixed_spacing


_PUBLISH_DISCUSSION_CLICHES = (
    "你怎么看，欢迎在评论区聊聊。",
    "欢迎在评论区聊聊。",
    "欢迎评论区聊聊。",
    "你怎么看？",
    "你怎么看。",
)


def _clean_publish_description(text: str, max_len: int = 130) -> str:
    """Keep generated publishing copy dense enough for Bilibili metadata."""
    text = normalize_cjk_mixed_spacing(str(text or "")).strip()
    for phrase in _PUBLISH_DISCUSSION_CLICHES:
        text = text.replace(phrase, "")
    text = text.replace("；", "。").replace(";", "。")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_len:
        return text

    parts = re.findall(r"[^。！？!?]+[。！？!?]?", text)
    kept: list[str] = []
    total = 0
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if kept and total + len(part) > max_len:
            break
        kept.append(part)
        total += len(part)
    compacted = "".join(kept).strip()
    if compacted:
        return compacted
    return text[:max_len].rstrip("，。！？；：,.!?;: ")


def _downgrade_unsupported_publish_claims(text: str) -> str:
    """Tone down recurring high-conflict copy that overstates source facts."""
    text = normalize_cjk_mixed_spacing(str(text or ""))
    replacements = {
        "先掉链子": "先多等100毫秒",
        "先掉线": "延迟先升高",
        "掉线": "延迟升高",
        "断网": "延迟升高",
        "砍掉P2P": "改了P2P路径",
        "砍掉 P2P": "改了 P2P 路径",
        "一刀砍": "改动",
        "20225个Instagram账号": "超2万个Instagram账号",
        "20225个账号": "超2万个账号",
        "20225 个账号": "超2万个账号",
        "20225个": "超2万个",
        "先遭殃": "延迟升高",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _ensure_all_stories_in_description(
    description: str,
    focus_story: dict,
    other_stories: list[dict],
) -> str:
    """Append any story not already mentioned in the description."""

    # Story-skew key terms: if none of these appear in desc, the story is missing.
    # Each story gets its own list derived from title_cn + editor_angle.
    def _story_keywords(story: dict) -> set[str]:
        src = normalize_cjk_mixed_spacing(
            (story.get("title_cn") or "") + " " + (story.get("editor_angle") or "")
        )
        tokens = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", src))
        # Remove super-generic brand tokens that the focus story also owns
        generic = {"苹果", "macbook", "ipad", "mac", "iphone"}
        return {t for t in tokens if t not in generic}

    def _story_mentioned(desc: str, story: dict) -> bool:
        keywords = _story_keywords(story)
        if not keywords:
            return True  # can't detect, don't append noise
        desc_lower = normalize_cjk_mixed_spacing(desc).lower()
        return any(kw.lower() in desc_lower for kw in keywords)

    def _compact_line(story: dict) -> str:
        editor = story.get("editor_angle") or ""
        summary = (story.get("article_summary") or "")[:120]
        return normalize_cjk_mixed_spacing(editor or summary)

    extra_lines = []
    for story in other_stories:
        if not _story_mentioned(description, story):
            line = _compact_line(story)
            if line:
                extra_lines.append(line)

    if not extra_lines:
        return description

    return description.rstrip("。；; ") + "。" + "。".join(extra_lines) + "。"


def _format_mmss(seconds: float | int | None) -> str:
    total = max(0, int(round(float(seconds or 0))))
    return f"{total // 60:02d}:{total % 60:02d}"


# Ordered pipeline steps with their prerequisites.
# Each step depends on all steps listed before it (linear chain),
# except standalone steps which have no prerequisites.
PIPELINE_STEPS = [
    "fetch",
    "prefilter",
    "fetch_comments",
    "enrich_articles",
    "translate_titles",
    "analyze_comments",
    "judge_comments",
    "write_script",
    "review_script",
    "translate_comments",
    "synthesize_audio",
    "title",
    "cover_image",
    "cover_thumbnail",
    "publish_guide",
    "xhs_guide",
    "prepare_render",
]
OPTIONAL_PRODUCTION_STEPS = {
    "cover_image",
    "cover_thumbnail",
    "publish_guide",
    "xhs_guide",
    # TTS is a render-side branch only (prepare_render needs audio_dir +
    # actual_duration); title/cover/publish/xhs do not depend on it, so it is
    # optional rather than a forced core prerequisite of write_script.
    "synthesize_audio",
}
CORE_PIPELINE_STEPS = [
    step for step in PIPELINE_STEPS if step not in OPTIONAL_PRODUCTION_STEPS
]
STANDALONE_STEPS = {"render", "preview"}
ALL_STEPS = PIPELINE_STEPS + ["render", "preview"]
DEFAULT_STEPS = CORE_PIPELINE_STEPS

# Number of cover text variants generated for manual selection (shared background).
COVER_VARIANT_COUNT = 3

# Steps that need `script` in memory (consume from `write_script` or disk).
SCRIPT_CONSUMING_STEPS = frozenset(
    {
        "review_script",
        "translate_comments",
        "synthesize_audio",
        "title",
        "cover_image",
        "cover_thumbnail",
        "publish_guide",
        "xhs_guide",
        "prepare_render",
        "render",
    }
)

# Steps that mutate `script`; trigger transcript save.
SCRIPT_MUTATING_STEPS = frozenset(
    {
        "write_script",
        "review_script",
        "translate_comments",
        "synthesize_audio",
        "title",
    }
)


def _resolve_steps(requested: List[str]) -> List[str]:
    """Expand requested steps to include all prerequisites."""
    valid = [s for s in requested if s in ALL_STEPS]
    if not valid:
        return []

    core_requested = [s for s in valid if s in CORE_PIPELINE_STEPS]
    optional_requested = [s for s in valid if s in OPTIONAL_PRODUCTION_STEPS]
    standalone_requested = [s for s in valid if s in STANDALONE_STEPS]

    resolved = []
    if core_requested:
        max_idx = max(CORE_PIPELINE_STEPS.index(s) for s in core_requested)
        resolved.extend(CORE_PIPELINE_STEPS[: max_idx + 1])

    if (
        "cover_thumbnail" in optional_requested
        and "cover_image" not in optional_requested
    ):
        optional_requested = ["cover_image", *optional_requested]

    # prepare_render needs audio (audio_dir + actual_duration); auto-pull
    # synthesize_audio so video flows stay correct without listing it by hand.
    # prepare_render may enter via core expansion, so check the resolved set.
    if "prepare_render" in resolved and "synthesize_audio" not in resolved:
        optional_requested = ["synthesize_audio", *optional_requested]

    for step in optional_requested:
        if step not in resolved:
            resolved.append(step)

    for step in standalone_requested:
        if step not in resolved:
            resolved.append(step)
    return resolved


class Orchestrator:
    def __init__(
        self,
        config: dict,
        content_fetcher: ContentFetcher,
        llm_provider: LLMProvider,
        tts_provider: TTSProvider,
        renderer: Renderer,
        article_enricher=None,
        image_generator: Optional[ImageGeneratorProvider] = None,
        debug: bool = False,
        dry_run: bool = False,
        agent_mode: bool = False,
        allow_degraded_enrichment: bool = False,
        refresh_variants: bool = False,
    ):
        self.config = config
        self.content_fetcher = content_fetcher
        self.llm_provider = llm_provider
        self.tts_provider = tts_provider
        self.renderer = renderer
        self.article_enricher = article_enricher
        self.image_generator = image_generator
        self.debug = debug
        self.dry_run = dry_run
        self.agent_mode = agent_mode
        self.allow_degraded_enrichment = allow_degraded_enrichment
        self.refresh_variants = refresh_variants
        self._agent_state: Optional[AgentState] = None
        log_level = config.get("logging", {}).get("level")
        self.logger = setup_logger(__name__, debug=debug, level=log_level)

        self.content_preparer = ContentPreparer(config, debug=debug)
        self.script_writer = ScriptWriter(
            config, llm_provider, self.content_preparer, debug=debug
        )
        self.tts_processor = TTSProcessor(
            tts_provider, config, debug=debug, level=log_level
        )
        self.translation_manager = TranslationManager(
            llm_provider, self.content_preparer, config, debug=debug, level=log_level
        )
        self.comment_analyzer = CommentAnalyzer(config, debug=debug)
        self.comment_refiner = CommentRefiner(llm_provider, config, debug=debug)
        self.comment_judge = CommentJudge(
            llm_provider,
            config,
            comment_analyzer=self.comment_analyzer,
            comment_refiner=self.comment_refiner,
            debug=debug,
        )
        self.agent_decision = AgentDecisionEngine(config)
        self.prefilter = Prefilter(llm_provider, config, debug=debug)
        timing_cfg = config.get("timing", {})
        self._timing = TimingEngine(
            segment_gap=float(timing_cfg.get("segment_gap", 0.0)),
            debug=debug,
        )

    @contextmanager
    def _tracked_step(self, name: str):
        if self._agent_state:
            self._agent_state.start_step(name)
        try:
            with self._progress.step(name):
                yield
        except Exception as e:
            if self._agent_state:
                self._agent_state.fail_step(name, e)
            raise
        else:
            if self._agent_state:
                self._agent_state.complete_step(name)

    def run(
        self, date: str, steps: Optional[List[str]] = None, force: bool = False
    ) -> None:
        if steps is None:
            steps = DEFAULT_STEPS
        else:
            steps = _resolve_steps(steps)

        self._progress = PipelineProgress(steps, date, self.config)
        self._agent_state = (
            AgentState(date, steps, self.config) if self.agent_mode else None
        )
        if self._agent_state:
            self._agent_state.start_run()
        if self.agent_mode and self.refresh_variants and "write_script" in steps:
            self._refresh_variant_outputs(date)
        self._progress.print_execution_summary(force=force)

        content: Optional[ContentPackage] = None
        script: Optional[Script] = None

        # ── 1. fetch ──────────────────────────────────────────────────────
        if "fetch" in steps:
            with self._tracked_step("fetch"):
                content = self._step_fetch(date)
        else:
            try:
                content = self.content_preparer.load_content(date)
            except FileNotFoundError:
                self.logger.info("Content not found, fetching anyway...")
                with self._tracked_step("fetch"):
                    content = self._step_fetch(date)

        # ── 2. prefilter ──────────────────────────────────────────────────
        if "prefilter" in steps:
            with self._tracked_step("prefilter"):
                content = self._step_prefilter(content, date)

        # ── 3. fetch_comments ─────────────────────────────────────────────
        if "fetch_comments" in steps:
            with self._tracked_step("fetch_comments"):
                content = self._step_fetch_comments(content, date)

        # ── 4. enrich_articles ────────────────────────────────────────────
        failed_items: list = []
        if "enrich_articles" in steps:
            with self._tracked_step("enrich_articles"):
                content, failed_items = self._step_enrich_articles(content, date)
        if failed_items:
            # --allow-degraded-enrichment works in both agent and non-agent modes:
            # mark missing article_text as degraded and keep the rest of the chain
            # running with whatever context is available.
            if self.allow_degraded_enrichment:
                self._mark_degraded_enrichment(failed_items)
            elif self.agent_mode:
                if self._agent_state:
                    insufficient = self._insufficient_context_items(failed_items)
                    if insufficient:
                        self._agent_state.block(
                            "enrich_articles",
                            BLOCK_INSUFFICIENT_CONTEXT,
                            items=insufficient,
                        )
                    else:
                        self._agent_state.block_for_manual_files(
                            "enrich_articles", failed_items
                        )
                self._print_enrich_failure_guidance(failed_items)
                return
            else:
                self._print_enrich_failure_guidance(failed_items)
                return

        # ── 5. translate_titles ───────────────────────────────────────────
        skip_source_gate = bool(failed_items and self.allow_degraded_enrichment)
        if (
            self.agent_mode
            and content is not None
            and "enrich_articles" in steps
            and not skip_source_gate
        ):
            decision = self.agent_decision.evaluate_source_context(content, date)
            if not decision.should_continue:
                if self._agent_state:
                    self._agent_state.block(
                        "enrich_articles",
                        decision.blocked_reason or BLOCK_INSUFFICIENT_CONTEXT,
                        items=decision.blocked_items or [],
                    )
                return

        if "translate_titles" in steps:
            with self._tracked_step("translate_titles"):
                content = self._step_translate_titles(content, date)

        # ── 6. analyze_comments ───────────────────────────────────────────
        if "analyze_comments" in steps:
            with self._tracked_step("analyze_comments"):
                content = self._step_analyze_comments(content, date)

        # ── 7. judge_comments ─────────────────────────────────────────────
        if "judge_comments" in steps:
            with self._tracked_step("judge_comments"):
                content = self._step_judge_comments(content, date)

        # ── 8. write_script ───────────────────────────────────────────────
        if "write_script" in steps:
            with self._tracked_step("write_script"):
                script = self._step_write_script(content, date)
            if (
                self.agent_mode
                and script is not None
                and content is not None
                and not self.allow_degraded_enrichment
            ):
                decision = self.agent_decision.evaluate_script_quality(
                    content, script, date
                )
                if not decision.should_continue:
                    if self._agent_state:
                        self._agent_state.block(
                            "write_script",
                            decision.blocked_reason or "low_decision_confidence",
                            items=decision.blocked_items or [],
                        )
                    return
        elif SCRIPT_CONSUMING_STEPS & set(steps):
            try:
                script = self.script_writer.load_script(date)
            except FileNotFoundError:
                self.logger.warning(
                    "Script not found on disk; downstream steps may fail"
                )

        # ── 9. review_script ──────────────────────────────────────────────
        if "review_script" in steps:
            with self._tracked_step("review_script"):
                script = self._step_review_script(content, script, date)

        # ── 10. translate_comments ────────────────────────────────────────
        if "translate_comments" in steps:
            with self._tracked_step("translate_comments"):
                content, script = self._step_translate_comments(content, script, date)

        # ── 11. synthesize_audio ──────────────────────────────────────────
        if "synthesize_audio" in steps:
            with self._tracked_step("synthesize_audio"):
                script = self._step_synthesize_audio(content, script, date)

        # ── 12. title ─────────────────────────────────────────────────────
        if "title" in steps:
            with self._tracked_step("title"):
                script = self._step_title(content, script, date)

        # ── 13. cover_image ───────────────────────────────────────────────
        if "cover_image" in steps:
            with self._tracked_step("cover_image"):
                self._step_cover_image(content, script, date)

        # ── 14. cover_thumbnail ───────────────────────────────────────────
        if "cover_thumbnail" in steps:
            with self._tracked_step("cover_thumbnail"):
                self._step_cover_thumbnail(content, script, date)

        # ── 15. publish_guide ─────────────────────────────────────────────
        if "publish_guide" in steps:
            with self._tracked_step("publish_guide"):
                self._step_publish_guide(content, script, date)

        # ── 16. xhs_guide ───────────────────────────────────────────────
        if "xhs_guide" in steps:
            with self._tracked_step("xhs_guide"):
                self._step_xhs_guide(content, script, date)

        # ── 17. prepare_render ────────────────────────────────────────────
        if "prepare_render" in steps:
            with self._tracked_step("prepare_render"):
                self._step_prepare_render(content, script, date)

        # ── standalone: render ────────────────────────────────────────────
        if "render" in steps:
            with self._tracked_step("render"):
                self._step_render(script, date, content, force=force)

        # ── standalone: preview ───────────────────────────────────────────
        if "preview" in steps:
            with self._tracked_step("preview"):
                self._step_preview(script, date, content)

        if script and SCRIPT_MUTATING_STEPS & set(steps):
            save_transcript(script, date, content, logger=self.logger)

        # report.md generation disabled
        if self._agent_state:
            self._agent_state.finish_run()

        self.logger.info("Pipeline completed")

    # ── Step implementations ─────────────────────────────────────────────

    def _step_fetch(self, date: str) -> ContentPackage:
        self.logger.info("Step: Fetch content")
        if self.dry_run:
            self.logger.info("Dry run: skipping fetch")
            return ContentPackage(date=date, items=[])

        content = self.content_fetcher.fetch(date)
        self.content_preparer.save_content(content, date)
        return content

    def _step_prefilter(self, content: ContentPackage, date: str) -> ContentPackage:
        self.logger.info("Step: Prefilter — LLM tech-relevance filter")
        if self.dry_run:
            self.logger.info("Dry run: skipping prefilter")
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
    ) -> Tuple[ContentPackage, list]:
        self.logger.info("Step: Enrich articles — fetch body and extract metadata")
        if self.dry_run:
            self.logger.info("Dry run: skipping article enrichment")
            return content, []

        if self.article_enricher is None:
            self.logger.info("Article enricher not configured, skipping")
            return content, []

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
        else:
            # Always persist enrichment results back to content.json, even on
            # the happy path. Without this, downstream steps (write_script,
            # title, …) see items with editor_angle=None and crash.
            self.content_preparer.save_content(content, date)

        return content, failed_items

    def _step_translate_titles(
        self, content: ContentPackage, date: str
    ) -> ContentPackage:
        self.logger.info("Step: Translate titles — LLM batch title translation")
        if self.dry_run:
            self.logger.info("Dry run: skipping title translation")
            return content

        if all(item.title_cn for item in content.items):
            self.logger.info("  All titles already translated")
            return content

        content = self.llm_provider.translate_titles(content, "translate.md", date)
        self.content_preparer.save_content(content, date)
        return content

    def _step_analyze_comments(
        self, content: ContentPackage, date: str
    ) -> ContentPackage:
        self.logger.info("Step: Analyze comments — VADER scoring")
        if self.dry_run:
            self.logger.info("Dry run: skipping comment analysis")
            return content

        analysis_path = pipeline_path(date, "comment_analysis.json")
        if analysis_path.exists():
            # Cache hit: skip re-scoring, but still run analyze() so that
            # _load_from_cache() merges quality_score / sentiment back into
            # the in-memory comments. Without this merge, downstream
            # is_quotable_comment() filters (quality_score >= 0.22) silently
            # drop every selected comment and the rendered video has no
            # atmosphere_card quotes.
            self.logger.info(
                f"  Comment analysis cached at {analysis_path}, merging into content"
            )
        else:
            self.logger.info("  No comment analysis cache; running fresh")

        content = self.comment_analyzer.analyze(content, date)
        self.content_preparer.save_content(content, date)
        return content

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

    def _step_write_script(self, content: ContentPackage, date: str) -> Script:
        self.logger.info("=" * 50)
        self.logger.info("Step: Write script — narration generation")
        self.logger.info(f"Date: {date}, Stories: {len(content.items)}")
        self.logger.info(f"Model: {self.config.get('llm', {}).get('model', 'unknown')}")
        num_story_scan = min(
            self.config.get("pipeline", {}).get("target_story_count", 10),
            len(content.items),
        )
        self.logger.info(
            f"Expected script LLM calls: story_scan={num_story_scan} "
            f"(translations/enrichment may add separate calls)"
        )
        self.logger.info("=" * 50)

        if self.dry_run:
            self.logger.info("Dry run: skipping script generation")
            from src.core.models import ScriptSegment

            return Script(
                title="Test",
                description="Test",
                tags=[],
                segments=[
                    ScriptSegment(
                        segment_type="opening",
                        audio_text="测试音频",
                        duration=10.0,
                    )
                ],
            )

        if self.agent_mode and self._variant_count() > 1:
            return self._step_write_script_variants(content, date)

        script = self.script_writer.write(content)
        self.script_writer.save_script(script, date)
        return script

    def _variant_count(self) -> int:
        variant_cfg = self.config.get("agent", {}).get("variants", {})
        if not variant_cfg.get("enabled", False):
            return 1
        return max(1, int(variant_cfg.get("count", 1) or 1))

    def _step_write_script_variants(self, content: ContentPackage, date: str) -> Script:
        count = self._variant_count()
        self.logger.info(f"Agent variants enabled: generating {count} script variants")
        variants = self.script_writer.write_variants(content, count=count)
        decision = self.agent_decision.select_script_variant(content, variants, date)
        index_variants = [
            {
                "variant_id": variant["variant_id"],
                "label": variant["label"],
                "strategy": variant["strategy"],
                "story_indices": variant["story_indices"],
                "preview": variant["preview"],
            }
            for variant in variants
        ]
        write_variants_index(
            date,
            index_variants,
            selected_variant=decision.get("selected_variant"),
            status=decision.get("status", "generated"),
        )
        if decision.get("status") != "continue" or not decision.get("selected_variant"):
            raise RuntimeError(
                f"Agent could not select a script variant: {decision.get('blocked_reason')}"
            )
        script = promote_variant_script(date, str(decision["selected_variant"]))
        self.script_writer.save_script(script, date)
        return script

    def _step_translate_comments(
        self, content: ContentPackage, script: Optional[Script], date: str
    ) -> Tuple[ContentPackage, Optional[Script]]:
        self.logger.info("Step: Translate comments — LLM comment translation")
        if self.dry_run:
            self.logger.info("Dry run: skipping comment translation")
            return content, script

        if script is None:
            self.logger.warning("Script not loaded; skipping comment translation")
            return content, script

        content, script = self.translation_manager.translate(content, script, date)
        self.script_writer.save_script(script, date)
        return content, script

    def _step_synthesize_audio(
        self, content: ContentPackage, script: Optional[Script], date: str
    ) -> Optional[Script]:
        self.logger.info("Step: Synthesize audio — TTS")
        if script is None:
            self.logger.warning("Script not loaded; skipping audio synthesis")
            return script

        if self.dry_run:
            self.logger.info("Dry run: skipping TTS")
            for seg in script.segments:
                seg.actual_duration = seg.duration
                seg.audio_path = ""
            self._timing.compute_timeline(script)
            self.script_writer.save_script(script, date)
            return script

        script = self.tts_processor.process_audio(script, date, content)
        self.script_writer.save_script(script, date)
        return script

    def _build_focus_story_input(
        self, script: Script, content: ContentPackage, date: str
    ) -> tuple[dict, dict]:
        """Build single-story input for the title prompt: focus story metadata
        and analysed comment lanes from ``comment_judgement.json``.

        Returns ``(focus_story, comment_analysis)``.
        """
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

        # Load analysed comment data from comment_judgement.json.
        from src.pipeline.comment.judge import judgement_cache_path

        jp = judgement_cache_path(date)
        comment_analysis: dict = {}
        if jp.exists():
            try:
                jdata = json.loads(jp.read_text(encoding="utf-8"))
                sid = str(focus.source_id or "")
                story = (jdata.get("stories") or {}).get(sid)
                if story is None:
                    # Fallback: match by story_id field.
                    for _, s in (jdata.get("stories") or {}).items():
                        if str(s.get("story_id", "")) == sid:
                            story = s
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
                                "stance": e.get("stance", ""),
                                "claim": e.get("claim", ""),
                                "role": e.get("role", ""),
                                "quote_score": e.get("quote_score", 0),
                            }
                            for e in (story.get("comment_lanes") or {}).get(
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
                                "stance": e.get("stance", ""),
                                "claim": e.get("claim", ""),
                                "quote_score": e.get("quote_score", 0),
                            }
                            for e in (story.get("quote_candidates") or [])[:10]
                        ],
                    }
            except (json.JSONDecodeError, OSError, ImportError):
                pass

        return focus_story, comment_analysis

    def _step_review_script(
        self, content: ContentPackage, script: Optional[Script], date: str
    ) -> Optional[Script]:
        self.logger.info("Step: Review script — LLM quality audit + auto-revise")
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
            for w in warnings:
                self.logger.info(f"  Review: {w}")
            self.logger.info(f"  Review: applied {changed} subtitle revision(s)")

        # Idempotency: the step rewrites the very subtitle texts it reads, so we
        # cannot gate on the input hash. Instead record the post-review subtitle
        # hash; if the script on disk already matches it, the review is current.
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
                label="review_script",
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

        # Hash the post-review subtitle texts so a clean re-run short-circuits.
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
            step="review_script",
            date=date,
            inputs={
                "source_subsegments_hash": current_hash,
                "prompt_hash": file_sha256(Path("prompts/script_review.md")),
                "date": date,
            },
            config=self.config,
        )
        self.script_writer.save_script(script, date)
        # Keep the selected variant snapshot in sync with the reviewed script so
        # the publishability audit's selected_variant_promoted check compares
        # equal scripts (review rewrites script.json in place after promotion).
        if self.agent_mode:
            sync_selected_variant_snapshot(date, script)
        return script

    @staticmethod
    def _parse_review_revisions(
        result: dict, sub_segment_count: int
    ) -> dict[int, list[str]]:
        """Validate the review LLM output into ``{index: [subtitle texts]}``."""
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
            cleaned = [str(t).strip() for t in texts if str(t).strip()]
            if cleaned:
                revisions[idx] = cleaned
        return revisions

    def _step_title(
        self, content: ContentPackage, script: Optional[Script], date: str
    ) -> Optional[Script]:
        self.logger.info("Step: Title — generate video title/description/tags")
        if script is None:
            self.logger.warning("Script not loaded; skipping title generation")
            return script

        cache_path = publish_path(date, "title.json")
        focus_story, comment_analysis = self._build_focus_story_input(
            script, content, date
        )

        # Manifest inputs are the semantic identity of *what* this title was
        # written for. If the focus story or its comment lanes change between
        # runs (e.g. prefilter swaps the top-3), the cache is stale and must
        # be regenerated — even if `title.json` still exists on disk.
        manifest_inputs = {
            "focus_source_id": focus_story.get("source_id", ""),
            "focus_title": focus_story.get("title", ""),
            "focus_title_cn": focus_story.get("title_cn", ""),
            "focus_editor_angle": focus_story.get("editor_angle", ""),
            "comment_analysis_hash": stable_hash(comment_analysis),
            "prompt_hash": file_sha256(Path("prompts/title.md")),
            "date": date,
        }

        if is_artifact_fresh(cache_path, manifest_inputs):
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            self.logger.info(f"  Loaded cached title from {cache_path}")
            script.title = normalize_cjk_mixed_spacing(
                cached.get("title", script.title)
            )
            script.description = cached.get("description", script.description)
            script.tags = cached.get("tags", script.tags)
            script.cover_subtitle = normalize_cjk_mixed_spacing(
                cached.get("cover_subtitle", script.cover_subtitle)
            )
            script.cover_title = normalize_cjk_mixed_spacing(
                cached.get("cover_title", script.cover_title)
            )
            script.cover_tags = [
                normalize_cjk_mixed_spacing(str(tag))
                for tag in (cached.get("cover_tags") or script.cover_tags or [])
                if str(tag).strip()
            ][:2]
            script.cover_highlights = [
                normalize_cjk_mixed_spacing(str(word))
                for word in (
                    cached.get("cover_highlights") or script.cover_highlights or []
                )
                if str(word).strip()
            ][:4]
            return script

        if self.dry_run:
            self.logger.info("Dry run: skipping title generation")
            return script

        # Build other stories list (excluding focus)
        other_stories = []
        focus_id = focus_story.get("source_id", "")
        for item in content.items:
            if str(item.source_id) == str(focus_id):
                continue
            other_stories.append(
                {
                    "title": item.title,
                    "title_cn": item.title_cn or "",
                    "editor_angle": item.editor_angle or "",
                    "article_summary": (item.article_summary or "")[:300],
                    "key_points": (item.key_points or [])[:3],
                }
            )

        context = {
            "focus_story_json": json.dumps(focus_story, ensure_ascii=False, indent=2),
            "other_stories_json": json.dumps(
                other_stories, ensure_ascii=False, indent=2
            ),
            "comments_json": json.dumps(comment_analysis, ensure_ascii=False, indent=2),
            "date": date,
        }
        try:
            result = self.llm_provider.complete_prompt(
                "prompts/title.md",
                context,
                label="title",
                expect_json=True,
                max_tokens=16384,
                model=self.llm_provider.fast_model,
                temperature=self.llm_provider.fast_temperature,
            )
        except (ValueError, Exception) as e:
            self.logger.error(f"  Title LLM call failed: {e}")
            raise

        chosen = _downgrade_unsupported_publish_claims(result.get("title") or "")

        if chosen and len(chosen) < 8:
            self.logger.warning(
                f"  LLM's `title` field was only {len(chosen)} chars; "
                f"below minimum 8: {chosen!r}"
            )

        script.title = chosen or "HN每日观察"
        desc = (
            _clean_publish_description(
                _downgrade_unsupported_publish_claims(result.get("description") or "")
            )
            or f"每日快讯 - {date}"
        )
        # Fallback: if LLM omitted any other_story brand, append a one-liner
        # per story to guarantee every story appears in the description.
        desc = _ensure_all_stories_in_description(desc, focus_story, other_stories)
        script.description = desc
        script.tags = list(result.get("tags") or [])
        script.cover_subtitle = normalize_cjk_mixed_spacing(
            _downgrade_unsupported_publish_claims(result.get("cover_subtitle") or "")
        )
        script.cover_title = _downgrade_unsupported_publish_claims(
            result.get("cover_title") or ""
        )
        script.cover_tags = [
            normalize_cjk_mixed_spacing(str(tag))
            for tag in (result.get("cover_tags") or [])
            if str(tag).strip()
        ][:2]
        script.cover_highlights = [
            normalize_cjk_mixed_spacing(str(word))
            for word in (result.get("cover_highlights") or [])
            if str(word).strip()
        ][:4]

        atomic_write_json(
            cache_path,
            {
                "title": script.title,
                "title_candidates": [
                    c
                    for c in (result.get("title_candidates") or [script.title])
                    if isinstance(c, str) and c.strip()
                ][:4],
                "description": script.description,
                "cover_title": script.cover_title,
                "cover_tags": script.cover_tags,
                "cover_highlights": script.cover_highlights,
                "cover_subtitle": script.cover_subtitle,
                "tags": script.tags,
            },
        )
        write_artifact_manifest(
            cache_path,
            step="title",
            date=date,
            inputs=manifest_inputs,
            config=self.config,
        )
        self.script_writer.save_script(script, date)
        return script

    def _step_cover_image(
        self, content: ContentPackage, script: Optional[Script], date: str
    ) -> None:
        self.logger.info(
            "Step: Cover image — generate AI image + 3 cover text variants"
        )
        bg_path = render_path(date, "cover_bg.png")
        props_path = render_path(date, "cover_props.json")
        # CoverThumbnail composition in Remotion is 1920x1080 (16:9); the
        # generated image must match, otherwise objectFit:cover crops the
        # editorial illustration. The provider's config default may differ,
        # so we override explicitly here.
        cover_aspect_ratio = "16:9"

        # Single-cover fallback text from the title step, used when the variant
        # LLM call fails or returns fewer than COVER_VARIANT_COUNT variants.
        fallback_title = (
            script.cover_title
            if script and script.cover_title
            else script.title
            if script
            else "HN每日观察"
        )
        fallback_tags = script.cover_tags[:2] if script and script.cover_tags else []
        fallback_highlights = (
            script.cover_highlights[:4] if script and script.cover_highlights else []
        )
        # 封面副文：cover_subtitle 优先（格式/长度见 prompts/title.md cover_subtitle 段），fallback 到 description 截断
        if script is None:
            fallback_subtitle = date
        elif script.cover_subtitle:
            fallback_subtitle = script.cover_subtitle
        elif script.description:
            fallback_subtitle = script.description[:40] + (
                "…" if len(script.description) > 40 else ""
            )
        else:
            fallback_subtitle = date
        date_label = date

        # Freshness: the variant texts come from a non-deterministic LLM call,
        # so a content hash would never be stable. Like the bg image, gate the
        # variants on existence — if the bg and all variant props are present,
        # skip entirely (no LLM call). Delete the props (or clear render cache)
        # to regenerate.
        variant_paths = [
            render_path(date, f"cover_props_v{i}.json")
            for i in range(1, COVER_VARIANT_COUNT + 1)
        ]
        if bg_path.exists() and all(p.exists() for p in variant_paths):
            self.logger.info("  Cover image + variants already done; skipping")
            self._mirror_cover_bg(date, bg_path)
            return

        if self.dry_run:
            self.logger.info("Dry run: skipping cover image generation")
            return

        if not bg_path.exists():
            if self.image_generator is None:
                self.logger.warning(
                    "No image_generator configured — cover step will be skipped. "
                    "Set image_generator.enabled=true in config to enable."
                )
                return

            highlight_entries = self._extract_highlight_entries(script, content)
            context = {
                "highlight_entries": json.dumps(
                    highlight_entries, ensure_ascii=False, indent=2
                ),
            }
            try:
                result = self.llm_provider.complete_prompt(
                    "prompts/cover_prompt.md",
                    context,
                    label="cover_prompt",
                    expect_json=True,
                    model=self.llm_provider.fast_model,
                    temperature=self.llm_provider.fast_temperature,
                )
                cover_prompt = (result.get("cover_prompt") or "").strip()
            except (ValueError, RuntimeError, OSError) as e:
                self.logger.warning(
                    f"Cover prompt generation failed ({type(e).__name__}: {e}); "
                    f"using fallback static prompt. Cover will not reflect today's content."
                )
                cover_prompt = ""

            if not cover_prompt:
                cover_prompt = (
                    "A bold editorial illustration about technology and software, "
                    "abstract central metaphor, no logos, no text."
                )

            # Generate N candidates with different seeds for manual layout
            # selection. Each candidate is written as cover_bg_v{i}.png. The
            # first candidate also becomes the canonical cover_bg.png so
            # downstream cover_thumbnail keeps working unchanged.
            cover_cfg = self.config.get("image_generator", {})
            candidate_count = max(
                1,
                int(
                    os.environ.get("HN_COVER_CANDIDATES")
                    or cover_cfg.get("candidate_count", 1)
                    or 1
                ),
            )
            candidate_seeds = [1001, 2002, 3003, 4004, 5005, 6006, 7007, 8008]

            for i in range(1, candidate_count + 1):
                if i == 1:
                    candidate_path = bg_path
                else:
                    candidate_path = render_path(date, f"cover_bg_v{i}.png")
                seed = candidate_seeds[(i - 1) % len(candidate_seeds)]
                try:
                    self.image_generator.generate(
                        cover_prompt,
                        str(candidate_path),
                        aspect_ratio=cover_aspect_ratio,
                        seed=seed,
                    )
                except (ValueError, RuntimeError, OSError) as e:
                    self.logger.warning(
                        f"Cover candidate {i} image generation failed "
                        f"({type(e).__name__}: {e})"
                    )
                    continue
            if candidate_count > 1:
                self.logger.info(
                    f"  Generated {candidate_count} cover background candidates "
                    f"({bg_path.name} + cover_bg_v*.png); review and pick the best."
                )

        # Generate the cover text variants (3 editorial angles, shared bg).
        variants = self._generate_cover_variants(content, script, date)
        if not variants:
            variants = [
                {
                    "title": fallback_title,
                    "subtitle": fallback_subtitle,
                    "tags": fallback_tags,
                    "highlights": fallback_highlights,
                }
            ]

        for i, variant in enumerate(variants[:COVER_VARIANT_COUNT], start=1):
            props = {
                "backgroundImage": bg_path.name,
                "title": variant["title"],
                "subtitle": variant["subtitle"],
                "tags": variant["tags"],
                "highlights": variant["highlights"],
                "dateLabel": date_label,
            }
            variant_path = render_path(date, f"cover_props_v{i}.json")
            atomic_write_json(variant_path, props)
            write_artifact_manifest(
                variant_path,
                step="cover_image",
                date=date,
                inputs={"background": bg_path.name, "variant_index": i},
                config=self.config,
            )
            # v1 also written to the canonical cover_props.json (back-compat).
            if i == 1:
                atomic_write_json(props_path, props)
                write_artifact_manifest(
                    props_path,
                    step="cover_image",
                    date=date,
                    inputs={"background": bg_path.name, "variant_index": 1},
                    config=self.config,
                )

        self._mirror_cover_bg(date, bg_path)
        self.logger.info(
            f"  Cover image + {min(len(variants), COVER_VARIANT_COUNT)} variant(s) "
            f"written ({bg_path.name})"
        )

    def _generate_cover_variants(
        self, content: ContentPackage, script: Optional[Script], date: str
    ) -> list[dict]:
        """Generate up to COVER_VARIANT_COUNT cover text variants (3 angles).

        Returns a list of ``{title, subtitle, tags, highlights}`` dicts with
        CJK spacing normalized. Returns [] on failure so the caller can fall
        back to the single-cover text from the title step.
        """
        focus_story, comment_analysis = self._build_focus_story_input(
            script, content, date
        )
        if not focus_story:
            return []

        focus_id = focus_story.get("source_id", "")
        other_stories = []
        for item in content.items:
            if str(item.source_id) == str(focus_id):
                continue
            other_stories.append(
                {
                    "title": item.title,
                    "title_cn": item.title_cn or "",
                    "editor_angle": item.editor_angle or "",
                }
            )

        context = {
            "focus_story_json": json.dumps(focus_story, ensure_ascii=False, indent=2),
            "other_stories_json": json.dumps(
                other_stories, ensure_ascii=False, indent=2
            ),
            "comments_json": json.dumps(comment_analysis, ensure_ascii=False, indent=2),
            "date": date,
        }
        try:
            result = self.llm_provider.complete_prompt(
                "prompts/cover_variants.md",
                context,
                label="cover_variants",
                expect_json=True,
                max_tokens=4096,
                model=self.llm_provider.fast_model,
                temperature=self.llm_provider.fast_temperature,
            )
        except Exception as e:
            self.logger.warning(
                f"  Cover variants LLM call failed ({type(e).__name__}: {e}); "
                f"falling back to single cover text"
            )
            return []

        variants: list[dict] = []
        for entry in result.get("variants") or []:
            if not isinstance(entry, dict):
                continue
            title = normalize_cjk_mixed_spacing(
                str(entry.get("cover_title") or "")
            ).strip()
            if not title:
                continue
            subtitle = normalize_cjk_mixed_spacing(
                str(entry.get("cover_subtitle") or "")
            ).strip()
            tags = [
                normalize_cjk_mixed_spacing(str(t)).strip()
                for t in (entry.get("cover_tags") or [])
                if str(t).strip()
            ][:2]
            highlights = [
                normalize_cjk_mixed_spacing(str(w)).strip()
                for w in (entry.get("cover_highlights") or [])
                if str(w).strip()
            ][:4]
            variants.append(
                {
                    "title": title,
                    "subtitle": subtitle or date,
                    "tags": tags,
                    "highlights": highlights,
                }
            )
        return variants

    def _mirror_cover_bg(self, date: str, bg_path: Path) -> None:
        """Mirror the cover background into the per-date Remotion runtime dir
        so the source tree stays clean. The renderer also points --public-dir
        here when rendering."""
        public_bg = render_remotion_dir(date) / "public" / bg_path.name
        public_bg.parent.mkdir(parents=True, exist_ok=True)
        try:
            same_file = public_bg.samefile(bg_path)
        except FileNotFoundError:
            same_file = False
        if not same_file:
            shutil.copy2(bg_path, public_bg)

    def _step_cover_thumbnail(
        self, content: ContentPackage, script: Optional[Script], date: str
    ) -> None:
        self.logger.info("Step: Cover thumbnail — render 3 bg × 3 text grid (9 stills)")
        if self.dry_run:
            self.logger.info("Dry run: skipping cover thumbnail render")
            return

        render_dir = render_root(date)

        # Collect up to 3 background candidates: cover_bg.png (v1),
        # cover_bg_v2.png, cover_bg_v3.png.
        bg_candidates = sorted(
            p
            for p in (render_dir.glob("cover_bg*.png"))
            if p.name.startswith("cover_bg")
        )
        # Dedup and cap at 3.
        seen = set()
        unique_bgs = []
        for p in bg_candidates:
            if p.name not in seen:
                seen.add(p.name)
                unique_bgs.append(p)
            if len(unique_bgs) >= 3:
                break

        # Collect text variants (cover_props_v{1..N}); fall back to cover_props.json.
        text_variants = [
            render_path(date, f"cover_props_v{i}.json")
            for i in range(1, COVER_VARIANT_COUNT + 1)
        ]
        text_variants = [p for p in text_variants if p.exists()]
        if not text_variants:
            single = render_path(date, "cover_props.json")
            if single.exists():
                text_variants = [single]

        if not unique_bgs or not text_variants:
            raise FileNotFoundError(
                "  cover_thumbnail requires cover_bg*.png and cover_props_v*.json; "
                "run --steps cover_image first"
            )

        npx_path = find_npx()
        if not npx_path:
            raise FileNotFoundError(
                "npx not found; install Node.js or set PATH to include npx"
            )

        # cover_thumbnail renders via the Remotion CLI before prepare_render runs,
        # so the per-date public/fonts/ dir does not exist yet. Stage fonts now or
        # the still render 404s on every woff2 and fails.
        stage_fonts = getattr(self.renderer, "stage_fonts", None)
        if callable(stage_fonts):
            stage_fonts(date)

        n_bgs = len(unique_bgs)
        n_texts = len(text_variants)
        self.logger.info(
            f"  Rendering {n_bgs} bg(s) × {n_texts} text(s) = {n_bgs * n_texts} covers"
        )

        # Mirror every bg candidate into the per-date Remotion public dir so
        # the <Img> component can load them at render time.
        for bg_path in unique_bgs:
            self._mirror_cover_bg(date, bg_path)

        for bg_idx, bg_path in enumerate(unique_bgs, start=1):
            for t_idx, props_path in enumerate(text_variants, start=1):
                # Read text props, swap backgroundImage to current bg.
                with io.open(props_path, "r", encoding="utf-8") as f:
                    props = json.load(f)
                props["backgroundImage"] = bg_path.name

                # Write combined props file.
                combined_path = render_path(
                    date, f"cover_props_b{bg_idx}_t{t_idx}.json"
                )
                atomic_write_json(combined_path, props)

                # Render the cover.
                cover_path = publish_path(date, f"cover_b{bg_idx}_t{t_idx}.png")
                thumb_inputs = {
                    "props_hash": file_sha256(combined_path),
                    "bg_hash": file_sha256(bg_path),
                }
                if is_artifact_fresh(cover_path, thumb_inputs):
                    self.logger.info(f"  cover_b{bg_idx}_t{t_idx} already rendered")
                else:
                    self._render_cover_still(npx_path, combined_path, cover_path, date)
                    write_artifact_manifest(
                        cover_path,
                        step="cover_thumbnail",
                        date=date,
                        inputs=thumb_inputs,
                        config=self.config,
                    )

                # b1_t1 stays as canonical cover.png (back-compat).
                if bg_idx == 1 and t_idx == 1:
                    canonical = publish_path(date, "cover.png")
                    if not is_artifact_fresh(canonical, thumb_inputs):
                        shutil.copy2(cover_path, canonical)
                        write_artifact_manifest(
                            canonical,
                            step="cover_thumbnail",
                            date=date,
                            inputs=thumb_inputs,
                            config=self.config,
                        )

                # For bg 1, also write cover_v{t_idx}.png (back-compat alias for
                # the original 1-bg × 3-text layout).
                if bg_idx == 1:
                    legacy = publish_path(date, f"cover_v{t_idx}.png")
                    if not is_artifact_fresh(legacy, thumb_inputs):
                        shutil.copy2(cover_path, legacy)
                        write_artifact_manifest(
                            legacy,
                            step="cover_thumbnail",
                            date=date,
                            inputs=thumb_inputs,
                            config=self.config,
                        )

    def _render_cover_still(
        self, npx_path: str, props_path: Path, output_path: Path, date: str
    ) -> None:
        """Render a single CoverThumbnail still via the Remotion CLI."""
        remotion_dir = Path("src/providers/renderer/remotion")
        cmd = [
            npx_path,
            "remotion",
            "still",
            "CoverThumbnail",
            f"--props={props_path.resolve()}",
            "--frame=0",
            f"--output={output_path.resolve()}",
            f"--public-dir={(render_remotion_dir(date) / 'public').resolve()}",
        ]
        try:
            result = subprocess.run(
                cmd,
                cwd=str(remotion_dir),
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
            if result.stdout:
                self.logger.info(f"  [remotion] {result.stdout.strip()}")
            self.logger.info(f"  Cover thumbnail written to {output_path}")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Cover render failed (exit={e.returncode}):\n"
                f"  stderr: {(e.stderr or '').strip()}\n"
                f"  stdout: {(e.stdout or '').strip()}"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"Cover render timed out after 120s: {e}") from e
        except FileNotFoundError as e:
            raise FileNotFoundError(f"npx not found: {e}") from e
        if not output_path.exists() or output_path.stat().st_size <= 0:
            raise RuntimeError(
                f"Cover render did not produce a valid file: {output_path}"
            )

    def _step_publish_guide(
        self, content: ContentPackage, script: Optional[Script], date: str
    ) -> None:
        self.logger.info(
            "Step: Publish guide — generate human-facing publish checklist"
        )
        guide_path = publish_path(date, "publish_guide.md")
        title_path = publish_path(date, "title.json")
        title_payload = {}
        if title_path.exists():
            try:
                loaded_title = json.loads(title_path.read_text(encoding="utf-8"))
                if isinstance(loaded_title, dict):
                    title_payload = loaded_title
            except (OSError, json.JSONDecodeError):
                title_payload = {}
        items_payload = [
            {
                "title_cn": item.title_cn or item.title,
                "title": item.title,
                "editor_angle": item.editor_angle or item.dek or "",
                "category": item.category or "",
            }
            for item in content.items
        ]
        title_candidates = title_payload.get("title_candidates") or [
            title_payload.get("title") or (script.title if script else "HN每日观察")
        ]
        context = {
            "script_title": title_payload.get("title")
            or (script.title if script else "HN每日观察"),
            "title_candidates_json": json.dumps(
                title_candidates, ensure_ascii=False, indent=2
            ),
            "script_description": title_payload.get("description")
            or (script.description if script else ""),
            "items_json": json.dumps(items_payload, ensure_ascii=False, indent=2),
            "date": date,
        }
        # Freshness inputs are computed from disk via a shared helper so the
        # publishability audit derives an identical hash (otherwise the guide is
        # flagged stale forever: writer skips, audit complains).
        manifest_context = publish_guide_manifest_inputs(date)
        if is_artifact_fresh(guide_path, manifest_context):
            self.logger.info(f"  Publish guide already exists at {guide_path}")
            return

        if self.dry_run:
            self.logger.info("Dry run: skipping publish guide generation")
            return

        text = self.llm_provider.complete_prompt(
            "prompts/publish_guide.md",
            context,
            label="publish_guide",
            expect_json=False,
            model=self.llm_provider.fast_model,
            temperature=self.llm_provider.fast_temperature,
        )

        atomic_write_text(guide_path, text)
        write_artifact_manifest(
            guide_path,
            step="publish_guide",
            date=date,
            inputs=manifest_context,
            config=self.config,
        )
        self.logger.info(f"  Publish guide written to {guide_path}")

    def _step_xhs_guide(
        self, content: ContentPackage, script: Optional[Script], date: str
    ) -> None:
        self.logger.info("Step: XHS guide - generate Xiaohongshu image-text post copy")
        guide_path = publish_path(date, "xhs_guide.md")
        title_path = publish_path(date, "title.json")
        title_payload = {}
        if title_path.exists():
            try:
                loaded_title = json.loads(title_path.read_text(encoding="utf-8"))
                if isinstance(loaded_title, dict):
                    title_payload = loaded_title
            except (OSError, json.JSONDecodeError):
                title_payload = {}
        items_payload = [
            {
                "title_cn": item.title_cn or item.title,
                "title": item.title,
                "editor_angle": item.editor_angle or item.dek or "",
                "category": item.category or "",
            }
            for item in content.items
        ]
        # Pull quotable comments (with Chinese translations where available) as
        # opening hooks. comment_judgement.json keys stories by source_id;
        # translations.json keys comments as "comment_{source_id}_{comment_id}".
        quotes_payload = self._collect_xhs_quotes(date)
        context = {
            "script_title": title_payload.get("title")
            or (script.title if script else "HN每日观察"),
            "script_description": title_payload.get("description")
            or (script.description if script else ""),
            "items_json": json.dumps(items_payload, ensure_ascii=False, indent=2),
            "quotes_json": json.dumps(quotes_payload, ensure_ascii=False, indent=2),
            "date": date,
        }
        # Freshness inputs are computed from disk via a shared helper so the
        # publishability audit derives an identical hash (mirrors
        # publish_guide: writer skips, audit complains -> stale forever).
        manifest_context = xhs_guide_manifest_inputs(date)
        if is_artifact_fresh(guide_path, manifest_context):
            self.logger.info(f"  XHS guide already exists at {guide_path}")
            return

        if self.dry_run:
            self.logger.info("Dry run: skipping XHS guide generation")
            return

        text = self.llm_provider.complete_prompt(
            "prompts/xhs_guide.md",
            context,
            label="xhs_guide",
            expect_json=False,
            model=self.llm_provider.fast_model,
            temperature=self.llm_provider.fast_temperature,
        )

        atomic_write_text(guide_path, text)
        write_artifact_manifest(
            guide_path,
            step="xhs_guide",
            date=date,
            inputs=manifest_context,
            config=self.config,
        )
        self.logger.info(f"  XHS guide written to {guide_path}")

    @staticmethod
    def _collect_xhs_quotes(date: str) -> list[dict[str, Any]]:
        """Collect quotable comments + Chinese translations for the XHS guide.

        Reads comment_judgement.json (quote_candidates per story, keyed by
        source_id) and translations.json (keyed
        ``comment_{source_id}_{comment_id}``). Falls back to the original
        ``claim`` when no translation is cached. Returns at most 3 highest-scoring
        quotes per story, each tagged with the story's source_id and title so
        the prompt can attribute the hook.
        """
        judgement_path = pipeline_path(date, "comment_judgement.json")
        translations_path = pipeline_path(date, "translations.json")
        content_path = pipeline_path(date, "content.json")
        try:
            judgement = json.loads(judgement_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(judgement, dict):
            return []
        stories = judgement.get("stories") or {}
        if not isinstance(stories, dict):
            return []
        try:
            translations = json.loads(translations_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            translations = {}
        if not isinstance(translations, dict):
            translations = {}
        title_cn_by_source: dict[str, str] = {}
        try:
            content_data = json.loads(content_path.read_text(encoding="utf-8"))
            if isinstance(content_data, dict):
                for item in content_data.get("items") or []:
                    if isinstance(item, dict) and item.get("source_id"):
                        title_cn_by_source[str(item["source_id"])] = (
                            item.get("title_cn") or item.get("title") or ""
                        )
        except (OSError, json.JSONDecodeError):
            pass

        quotes: list[dict[str, Any]] = []
        for source_id, story in stories.items():
            if not isinstance(story, dict):
                continue
            candidates = story.get("quote_candidates") or []
            if not isinstance(candidates, list):
                continue
            ranked = sorted(
                (c for c in candidates if isinstance(c, dict)),
                key=lambda c: c.get("quote_score", 0) or 0,
                reverse=True,
            )[:3]
            for cand in ranked:
                comment_id = str(cand.get("comment_id") or "")
                trans_key = f"comment_{source_id}_{comment_id}"
                quote_text = translations.get(trans_key) or cand.get("claim") or ""
                if not quote_text:
                    continue
                quotes.append(
                    {
                        "source_id": source_id,
                        "story_title_cn": title_cn_by_source.get(str(source_id), ""),
                        "comment_id": comment_id,
                        "stance": cand.get("stance", ""),
                        "quote_score": cand.get("quote_score", 0),
                        "quote_cn": quote_text,
                    }
                )
        return quotes

    def _step_prepare_render(
        self, content: ContentPackage, script: Optional[Script], date: str
    ) -> None:
        self.logger.info("Step: Prepare render — write props.json and copy assets")
        if script is None:
            raise ValueError("Script not loaded; cannot prepare render")

        if self.dry_run:
            self.logger.info("Dry run: skipping prepare_render")
            return

        audio_dir = str(pipeline_audio_dir(date))
        try:
            props_path, _, _ = self.renderer.write_props(
                script, audio_dir, content, date=date
            )
        except Exception as e:
            self.logger.error(f"Renderer.write_props failed: {e}", exc_info=True)
            raise

        if not props_path or not props_path.exists() or props_path.stat().st_size <= 0:
            raise RuntimeError(
                "Renderer.write_props did not produce a valid props file"
            )

        write_artifact_manifest(
            props_path,
            step="prepare_render",
            date=date,
            inputs={
                "script_title": script.title,
                "segment_count": len(script.segments),
                "audio_dir": audio_dir,
                "renderer": type(self.renderer).__name__,
            },
            config=self.config,
        )

    def _step_render(
        self,
        script: Optional[Script],
        date: str,
        content: Optional[ContentPackage] = None,
        force: bool = False,
    ) -> None:
        self.logger.info("Step: Render video")
        if self.dry_run:
            self.logger.info("Dry run: skipping render")
            return

        if script is None:
            try:
                script = self.script_writer.load_script(date)
            except FileNotFoundError:
                raise FileNotFoundError("Script not found; cannot render")

        if content is None:
            try:
                content = self.content_preparer.load_content(date)
            except FileNotFoundError:
                self.logger.info(
                    "Content not found for render, scene elements may be incomplete"
                )

        if force:
            self._clear_render_cache(date)

        output_path = str(publish_path(date, "output.mp4"))
        audio_dir = str(pipeline_audio_dir(date))
        self.renderer.render(script, audio_dir, output_path, content, date=date)
        rendered = Path(output_path)
        if not rendered.exists() or rendered.stat().st_size <= 0:
            raise RuntimeError(
                f"Renderer did not produce a valid output file: {output_path}"
            )

    def _step_preview(
        self,
        script: Optional[Script],
        date: str,
        content: Optional[ContentPackage] = None,
    ) -> None:
        self.logger.info("Step: Preview (Remotion Studio)")
        if self.dry_run:
            self.logger.info("Dry run: skipping preview")
            return

        if script is None:
            try:
                script = self.script_writer.load_script(date)
            except FileNotFoundError:
                self.logger.error("Script not found; cannot preview")
                return

        if content is None:
            try:
                content = self.content_preparer.load_content(date)
            except FileNotFoundError:
                self.logger.info(
                    "Content not found for preview, scene elements may be incomplete"
                )

        audio_dir = str(pipeline_audio_dir(date))
        self.logger.info("Opening Remotion Studio at http://localhost:3000")
        self.logger.info(
            "Check the preview, then press Ctrl+C to stop and proceed to render."
        )
        self.renderer.preview(script, audio_dir, content, date=date)

    # ── Helpers ─────────────────────────────────────────────────────────

    def _clear_render_cache(self, date: str) -> None:
        # Renderer-specific caches (Remotion chunk dirs, HyperFrames project, etc.)
        try:
            for path in self.renderer.cache_paths(date):
                if path.exists():
                    import shutil

                    shutil.rmtree(path)
                    self.logger.info(f"Cleared renderer cache: {path}")
        except Exception as e:
            self.logger.warning(f"Failed to clear renderer cache_paths: {e}")

        # RemotionRenderer also writes chunk outputs under its own out/; covered
        # by cache_paths() above. Keep this fallback for any renderer that
        # doesn't opt in.
        remotion_dir = Path("src/providers/renderer/remotion")
        # Match the new per-date runtime layout: data/{month}/{date}/remotion/chunks.
        chunk_dir = render_remotion_dir(date) / "chunks"
        if chunk_dir.exists() and not any(
            str(p).startswith(str(remotion_dir))
            for p in self.renderer.cache_paths(date)
        ):
            import shutil

            shutil.rmtree(chunk_dir)
            self.logger.info(f"Cleared all chunk caches: {chunk_dir}")

        output_path = publish_path(date, "output.mp4")
        if output_path.exists():
            output_path.unlink()
            self.logger.info(f"Deleted output: {output_path}")

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
            agent_path(date, "selected_variant.json"),
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
                f"Refresh variants: deleted {len(deleted)} script/variant cache item(s)"
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
        if self._agent_state:
            self._agent_state.add_degraded_items(
                "enrich_articles", failed_items, "enrichment_failed"
            )

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
        """Pull the highlight_entries list from the opening cover_card.

        Falls back to the first 3 content items' titles/angles if the
        script segment doesn't contain a cover_card with entries.
        """
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
