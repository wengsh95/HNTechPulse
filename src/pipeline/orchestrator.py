import io
import json
import os
import re
import shutil
import subprocess
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
from src.pipeline.comment import CommentAnalyzer, CommentJudge, CommentRefiner
from src.workflow import (
    BLOCK_MANUAL_DOWNLOAD,
    BLOCK_MANUAL_IMAGE_SELECTION,
    BLOCK_INSUFFICIENT_CONTEXT,
    BLOCK_MANUAL_SCRIPT_REVIEW,
    VIDEO_PIPELINE_STEPS,
    WorkflowMachine,
    write_image_selection_tasks,
    write_manual_download_tasks,
)
from src.pipeline.content_io import ContentPreparer
from src.pipeline.human_review import (
    generate_script_review_page,
    script_approval_is_current,
)
from src.pipeline.paths import (
    agent_path,
    date_root,
    pipeline_path,
    publish_path,
    raw_downloaded_pages_dir,
    render_path,
    render_remotion_dir,
    render_root,
)
from src.pipeline.pipeline_progress import PipelineProgress
from src.pipeline.prefilter import Prefilter
from src.pipeline.stages import (
    ProductionStageMixin,
    ResearchStageMixin,
    WorkflowLifecycleMixin,
)
from src.pipeline.subtitle_planner import prepare_subtitles
from src.pipeline.storyboard import apply_storyboard
from src.pipeline.storyboard_draft import draft_storyboard
from src.pipeline.quick_news import draft_quick_news
from src.pipeline.story_images import prepare_story_images
from src.pipeline.video_structure import prepare_video_structure
from src.providers.renderer.binary_finder import find_npx
from src.pipeline.script import ScriptWriter, apply_subtitle_revisions
from src.pipeline.script.io import (
    apply_audio_manifest,
    audio_manifest_is_usable,
    load_audio_manifest,
    save_audio_manifest,
    load_script_lock,
    script_audio_input_hash,
    script_editorial_hash,
)
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


def _normalize_cover_variants(raw: Any) -> list[dict[str, Any]]:
    """Normalize the cover copy emitted by the title/editorial LLM call.

    Cover copy uses the same focus story and comment analysis as the title, so
    it is cheaper and more coherent to ask for both in one structured response.
    Keep this parser deliberately tolerant: older cached title artifacts may
    not contain ``cover_variants`` and will fall back to the single cover text.
    """
    if not isinstance(raw, list):
        return []

    variants: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        title = _downgrade_unsupported_publish_claims(
            str(entry.get("cover_title") or "")
        ).strip()
        if not title:
            continue
        subtitle = normalize_cjk_mixed_spacing(
            str(entry.get("cover_subtitle") or "")
        ).strip()
        tags = [
            normalize_cjk_mixed_spacing(str(tag)).strip()
            for tag in (entry.get("cover_tags") or [])
            if str(tag).strip()
        ][:2]
        highlights = [
            normalize_cjk_mixed_spacing(str(word)).strip()
            for word in (entry.get("cover_highlights") or [])
            if str(word).strip()
        ][:4]
        variants.append(
            {
                "title": title,
                "subtitle": subtitle,
                "tags": tags,
                "highlights": highlights,
            }
        )
    return variants[:COVER_VARIANT_COUNT]


def _normalize_cover_prompt(raw: Any) -> str:
    """Keep a cached image prompt bounded and safe for the image provider."""
    text = str(raw or "").strip()
    if not text:
        return ""
    text = text[:1200].rstrip(" ,.;。；")
    safety_suffix = (
        "No logos, no text, no watermarks, no brand references, no horizontal bars, "
        "no vertical bars, no UI elements, no header bars, no footer bars."
    )
    if safety_suffix.lower() not in text.lower():
        text = f"{text}, {safety_suffix}"
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


# The workflow registry is the single source of truth for the order and the
# default managed chain.
VIDEO_PIPELINE_ORDER = list(VIDEO_PIPELINE_STEPS)
STANDALONE_STEPS = {"render", "preview"}
PIPELINE_STEPS = [step for step in VIDEO_PIPELINE_STEPS if step not in STANDALONE_STEPS]
OPTIONAL_PRODUCTION_STEPS = {
    "write_script",
    "draft_quick_news",
    "prepare_story_images",
    "human_review",
    "title",
    "prepare_render",
    "cover_image",
    "cover_thumbnail",
    "draft_storyboard",
    "apply_storyboard",
    "prepare_subtitles",
    # TTS is a render-side branch only (prepare_render needs audio_dir +
    # actual_duration); title/cover/publish do not depend on it, so it is
    # optional rather than a forced core prerequisite of write_script.
    "synthesize_audio",
}
CORE_PIPELINE_STEPS = [
    step for step in PIPELINE_STEPS if step not in OPTIONAL_PRODUCTION_STEPS
]
ALL_STEPS = PIPELINE_STEPS + ["render", "preview"]
_VALID_STEPS = set(ALL_STEPS)
DEFAULT_STEPS = list(VIDEO_PIPELINE_STEPS)

# Number of cover text variants generated for manual selection (shared background).
COVER_VARIANT_COUNT = 3

# Steps that need `script` in memory (consume from `write_script` or disk).
SCRIPT_CONSUMING_STEPS = frozenset(
    {
        "human_review",
        "draft_quick_news",
        "prepare_story_images",
        "prepare_subtitles",
        "synthesize_audio",
        "title",
        "cover_image",
        "cover_thumbnail",
        "draft_storyboard",
        "apply_storyboard",
        "prepare_render",
        "render",
    }
)

# Steps that mutate `script`; trigger transcript save.
SCRIPT_MUTATING_STEPS = frozenset(
    {
        "write_script",
        "draft_quick_news",
        "prepare_story_images",
        "human_review",
        "prepare_subtitles",
        "synthesize_audio",
        "title",
        "apply_storyboard",
    }
)

# Any production work after copy review must use the exact script version a
# human approved. The resolver injects ``human_review`` even for a direct
# render recovery, so manually edited copy cannot bypass the checkpoint.
HUMAN_REVIEW_PROTECTED_STEPS = frozenset(
    {
        "title",
        "cover_image",
        "cover_thumbnail",
        "draft_storyboard",
        "apply_storyboard",
        "prepare_subtitles",
        "synthesize_audio",
        "prepare_render",
        "render",
        "preview",
    }
)


def _resolve_steps(requested: List[str]) -> List[str]:
    """Expand requested steps to include all prerequisites."""
    invalid = [s for s in requested if s not in _VALID_STEPS]
    if invalid:
        raise ValueError(
            "Unknown pipeline step(s): "
            + ", ".join(invalid)
            + ". Use the canonical workflow steps."
        )
    valid = list(requested)
    if not valid:
        return []

    core_requested = [s for s in valid if s in CORE_PIPELINE_STEPS]
    optional_requested = [s for s in valid if s in OPTIONAL_PRODUCTION_STEPS]
    standalone_requested = [s for s in valid if s in STANDALONE_STEPS]

    resolved: list[str] = []
    if core_requested:
        max_idx = max(CORE_PIPELINE_STEPS.index(s) for s in core_requested)
        resolved.extend(CORE_PIPELINE_STEPS[: max_idx + 1])

    if (
        "cover_thumbnail" in optional_requested
        and "cover_image" not in optional_requested
    ):
        optional_requested = ["cover_image", *optional_requested]

    # prepare_render needs audio synthesis, but it is itself a downstream step.
    # An explicit prepare_render/render recovery must not expand back through
    # the editorial chain and overwrite a manually edited script.
    if (
        "prepare_render" in optional_requested
        and "synthesize_audio" not in optional_requested
    ):
        optional_requested = ["synthesize_audio", *optional_requested]

    # Subtitle selection is a local-agent prerequisite for every video-side
    # audio/render recovery. It never expands into the editorial chain.
    if (
        any(
            step in optional_requested
            for step in ("synthesize_audio", "prepare_render")
        )
        and "prepare_subtitles" not in optional_requested
    ):
        optional_requested = ["prepare_subtitles", *optional_requested]

    for step in optional_requested:
        if step not in resolved:
            resolved.append(step)

    for step in standalone_requested:
        if step not in resolved:
            resolved.append(step)

    if (
        HUMAN_REVIEW_PROTECTED_STEPS.intersection(resolved)
        and "human_review" not in resolved
    ):
        resolved.append("human_review")

    # Reorder the final set by the real pipeline order so a video run always
    # synthesizes audio before prepare_render.
    if any(
        step in resolved
        for step in (
            "prepare_subtitles",
            "synthesize_audio",
            "prepare_render",
            "render",
        )
    ):
        ordered = [step for step in VIDEO_PIPELINE_ORDER if step in resolved]
    else:
        ordered = [step for step in PIPELINE_STEPS if step in resolved]
    ordered.extend(step for step in standalone_requested if step not in ordered)
    return ordered


class Orchestrator(WorkflowLifecycleMixin, ResearchStageMixin, ProductionStageMixin):
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
        refresh_selection: bool = False,
        refresh_script: bool = False,
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
        self.refresh_selection = refresh_selection
        self.refresh_script = refresh_script
        self._workflow: WorkflowMachine | None = None
        self._workflow_completed_steps: set[str] = set()
        self._workflow_expected_steps: dict[str, set[str]] = {}
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

    def run(
        self, date: str, steps: Optional[List[str]] = None, force: bool = False
    ) -> None:
        if steps is None:
            steps = DEFAULT_STEPS
        else:
            steps = _resolve_steps(steps)

        self._progress = PipelineProgress(steps, date, self.config)
        if self.agent_mode and not self.dry_run:
            self._prepare_workflow(date, steps)
            append_agent_event(date, "run_started", steps=steps)
        if (
            self.agent_mode
            and not self.dry_run
            and (self.refresh_variants or self.refresh_selection or self.refresh_script)
            and "write_script" in steps
        ):
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
                insufficient = self._insufficient_context_items(failed_items)
                if insufficient:
                    self._workflow_block(
                        "enrich_articles",
                        BLOCK_INSUFFICIENT_CONTEXT,
                        items=insufficient,
                    )
                else:
                    task_file = write_manual_download_tasks(date, failed_items)
                    self._workflow_block(
                        "enrich_articles",
                        BLOCK_MANUAL_DOWNLOAD,
                        items=[
                            {
                                "story_id": str(item.source_id),
                                "title": item.title or "",
                                "url": item.url or "",
                            }
                            for item in failed_items
                        ],
                        task_file=str(task_file).replace("\\", "/"),
                    )
                self._print_enrich_failure_guidance(failed_items)
                return
            else:
                self._print_enrich_failure_guidance(failed_items)
                return

        pending_image_selections = getattr(
            self.article_enricher, "pending_image_selections", []
        )
        if pending_image_selections and self.agent_mode:
            task_file = write_image_selection_tasks(date, pending_image_selections)
            self._workflow_block(
                "enrich_articles",
                BLOCK_MANUAL_IMAGE_SELECTION,
                items=pending_image_selections,
                task_file=str(task_file).replace("\\", "/"),
            )
            self.logger.warning(
                "%d image selections need agent confirmation before continuing.",
                len(pending_image_selections),
            )
            return

        # ── 5. source-context gate ───────────────────────────────────────
        skip_source_gate = bool(failed_items and self.allow_degraded_enrichment)
        if (
            self.agent_mode
            and content is not None
            and "enrich_articles" in steps
            and not skip_source_gate
        ):
            decision = self.agent_decision.evaluate_source_context(content, date)
            if not decision.should_continue:
                self._workflow_block(
                    "enrich_articles",
                    decision.blocked_reason or BLOCK_INSUFFICIENT_CONTEXT,
                    items=decision.blocked_items or [],
                )
                return

        # ── 6. judge_comments ─────────────────────────────────────────────
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
                    self._workflow_block(
                        "write_script",
                        decision.blocked_reason or "low_decision_confidence",
                        items=decision.blocked_items or [],
                    )
                    return
        elif SCRIPT_CONSUMING_STEPS & set(steps):
            try:
                script = self.script_writer.load_script(
                    date,
                    with_audio=any(
                        step in steps for step in ("prepare_render", "render")
                    )
                    and "synthesize_audio" not in steps,
                )
            except FileNotFoundError:
                self.logger.warning(
                    "Script not found on disk; downstream steps may fail"
                )

        # ── 9. draft_quick_news + structure + comment translations ───────
        if "draft_quick_news" in steps:
            with self._tracked_step("draft_quick_news"):
                script = self._step_draft_quick_news(
                    script,
                    date,
                    content=content,
                )

        # ── 10. prepare_story_images ──────────────────────────────────────
        if "prepare_story_images" in steps:
            with self._tracked_step("prepare_story_images"):
                image_result = self._step_prepare_story_images(script, content, date)
            if image_result.pending and self.agent_mode:
                task_file = write_image_selection_tasks(date, image_result.pending)
                self._workflow_block(
                    "prepare_story_images",
                    BLOCK_MANUAL_IMAGE_SELECTION,
                    items=image_result.pending,
                    task_file=str(task_file).replace("\\", "/"),
                )
                self.logger.warning(
                    "%d stories need confirmed images before continuing.",
                    len(image_result.pending),
                )
                return

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

        # ── 15. draft_storyboard ─────────────────────────────────────────
        if "draft_storyboard" in steps:
            with self._tracked_step("draft_storyboard"):
                self._step_draft_storyboard(script, date)

        # ── 16. human_review ──────────────────────────────────────────────
        if "human_review" in steps:
            with self._tracked_step("human_review"):
                approved, review_page = self._step_human_review(
                    script, date, content=content
                )
            if not approved:
                review_items = [
                    {
                        "review_page": str(review_page).replace("\\", "/"),
                        "approval_file": str(
                            agent_path(date, "script_approval.json")
                        ).replace("\\", "/"),
                        "approve_command": (
                            "uv run python scripts/agent_run.py "
                            f"--date {date} --approve-script"
                        ),
                    }
                ]
                self._workflow_block(
                    "human_review",
                    BLOCK_MANUAL_SCRIPT_REVIEW,
                    items=review_items,
                )
                self.logger.warning(
                    "Human script review required before downstream production: %s",
                    review_page,
                )
                return

        # ── 17. apply_storyboard ─────────────────────────────────────────
        if "apply_storyboard" in steps:
            with self._tracked_step("apply_storyboard"):
                script = self._step_apply_storyboard(script, date)

        # ── 19. prepare_subtitles ─────────────────────────────────────────
        if "prepare_subtitles" in steps:
            with self._tracked_step("prepare_subtitles"):
                script = self._step_prepare_subtitles(script, date)

        # ── 20. synthesize_audio ──────────────────────────────────────────
        if "synthesize_audio" in steps:
            with self._tracked_step("synthesize_audio"):
                script = self._step_synthesize_audio(content, script, date)

        # ── 21. prepare_render (+ publish guide) ──────────────────────────
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

        if script and SCRIPT_MUTATING_STEPS & set(steps) and not self.dry_run:
            save_transcript(script, date, content, logger=self.logger)

        if self._workflow is not None:
            self._workflow.update_metadata(
                execution_status="complete",
                current_pipeline_step=None,
            )
            append_agent_event(
                date,
                "run_finished",
                status=self._workflow.status_report().get("status"),
                steps=steps,
            )

        self.logger.info("Pipeline completed")

    # ── Step implementations ─────────────────────────────────────────────

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

    def _step_write_script(self, content: ContentPackage, date: str) -> Script:
        lock = load_script_lock(date)
        if not (self.refresh_script or self.refresh_variants):
            script_path = pipeline_path(date, "script.json")
            if lock:
                existing = self.script_writer.load_script(date)
                expected_hash = lock.get("script_hash")
                current_hash = script_editorial_hash(existing)
                if expected_hash and expected_hash != current_hash:
                    raise RuntimeError(
                        "script.json changed after the last editorial lock. "
                        "Continue from a downstream step, or pass --refresh-script "
                        "to intentionally regenerate the script."
                    )
            elif self.agent_mode and script_path.exists():
                raise RuntimeError(
                    "Existing script.json has no script_lock.json. "
                    "Continue from a downstream step, or pass --refresh-script "
                    "to intentionally regenerate the script."
                )
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

    def _apply_comment_translations(
        self,
        content: ContentPackage,
        script: Optional[Script],
        date: str,
        *,
        save_script: bool = True,
    ) -> Tuple[ContentPackage, Optional[Script]]:
        self.logger.info("  Translating selected comments")
        if self.dry_run:
            self.logger.info("Dry run: skipping comment translation")
            return content, script

        if script is None:
            self.logger.warning("Script not loaded; skipping comment translation")
            return content, script

        content, script = self.translation_manager.translate(content, script, date)
        if save_script:
            self.script_writer.save_script(script, date)
        return content, script

    def _step_synthesize_audio(
        self, content: ContentPackage, script: Optional[Script], date: str
    ) -> Optional[Script]:
        self.logger.info("Step: Synthesize audio — TTS")
        if script is None:
            self.logger.warning("Script not loaded; skipping audio synthesis")
            return script

        audio_manifest_path = pipeline_path(date, "audio_manifest.json")
        audio_inputs = {
            "audio_input_hash": script_audio_input_hash(script),
            "segment_count": len(script.segments),
        }

        if self.dry_run:
            self.logger.info("Dry run: skipping TTS")
            for seg in script.segments:
                seg.actual_duration = seg.duration
                seg.audio_path = ""
            self._timing.compute_timeline(script)
            return script

        if is_artifact_fresh(audio_manifest_path, audio_inputs):
            manifest = load_audio_manifest(date)
            if manifest is not None and audio_manifest_is_usable(
                manifest, expected_segment_count=len(script.segments)
            ):
                self.logger.info(
                    "  Audio manifest matches current script; skipping TTS"
                )
                return apply_audio_manifest(script, manifest)
            self.logger.info("  Audio manifest is incomplete; regenerating TTS")

        script = self.tts_processor.process_audio(script, date, content)
        save_audio_manifest(script, date, config=self.config)
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
        cover_variants = _normalize_cover_variants(result.get("cover_variants"))
        cover_prompt = _normalize_cover_prompt(result.get("cover_prompt"))
        if not cover_variants and script.cover_title:
            # Keep the title step useful even when an older/cheaper model omits
            # the optional variants field. The cover stage can still render a
            # coherent single candidate without another LLM round trip.
            cover_variants = [
                {
                    "title": script.cover_title,
                    "subtitle": script.cover_subtitle,
                    "tags": script.cover_tags,
                    "highlights": script.cover_highlights,
                }
            ]

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
                "cover_variants": cover_variants,
                "cover_prompt": cover_prompt,
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
            "Step: Cover image — generate AI image + cached cover text variants"
        )
        bg_path = render_path(date, "cover_bg.png")
        # CoverThumbnail composition in Remotion is 1920x1080 (16:9); the
        # generated image must match, otherwise objectFit:cover crops the
        # editorial illustration. The provider's config default may differ,
        # so we override explicitly here.
        cover_aspect_ratio = "16:9"

        # Single-cover fallback text from the title step, used when a model
        # omits the optional multi-angle field.
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

        cover_prompt = self._load_title_cover_prompt(date)
        if not cover_prompt:
            cover_prompt = (
                "A bold editorial illustration about technology and software, "
                "abstract central metaphor, no logos, no text."
            )
        cover_prompt_hash = stable_hash(cover_prompt)
        cover_cfg = self.config.get("image_generator", {})
        candidate_count = max(
            1,
            int(
                os.environ.get("HN_COVER_CANDIDATES")
                or cover_cfg.get("candidate_count", 1)
                or 1
            ),
        )
        cover_bg_inputs = {
            "prompt_hash": cover_prompt_hash,
            "aspect_ratio": cover_aspect_ratio,
            "candidate_count": candidate_count,
        }
        bg_is_fresh = is_artifact_fresh(bg_path, cover_bg_inputs)

        variants = self._load_title_cover_variants(date)
        fallback_variant = {
            "title": fallback_title,
            "subtitle": fallback_subtitle,
            "tags": fallback_tags,
            "highlights": fallback_highlights,
        }
        if not variants:
            variants = [fallback_variant]
        while len(variants) < COVER_VARIANT_COUNT:
            variants.append(dict(fallback_variant))
        variants = variants[:COVER_VARIANT_COUNT]
        variant_hash = stable_hash(variants)

        # The title step now owns cover copy generation. Include its normalized
        # output in the props manifest so a title refresh invalidates stale
        # cover text without requiring another cover-specific LLM call.
        variant_paths = [
            render_path(date, f"cover_props_v{i}.json")
            for i in range(1, COVER_VARIANT_COUNT + 1)
        ]
        if bg_is_fresh and all(
            is_artifact_fresh(
                path,
                {
                    "background": bg_path.name,
                    "variant_index": index,
                    "title_cover_variants_hash": variant_hash,
                    "cover_prompt_hash": cover_prompt_hash,
                },
            )
            for index, path in enumerate(variant_paths, start=1)
        ):
            self.logger.info("  Cover image + variants already done; skipping")
            self._mirror_cover_bg(date, bg_path)
            return

        if self.dry_run:
            self.logger.info("Dry run: skipping cover image generation")
            return

        if not bg_is_fresh:
            if self.image_generator is None:
                if not bg_path.exists():
                    self.logger.warning(
                        "No image_generator configured — cover step will be skipped. "
                        "Set image_generator.enabled=true in config to enable."
                    )
                    return
                self.logger.warning(
                    "No image_generator configured — keeping existing cover background."
                )
            else:
                # The title/editorial call already has the same story and comment
                # context. Reuse its cached visual prompt instead of making a
                # second LLM request with an almost identical input.
                candidate_seeds = [1001, 2002, 3003, 4004, 5005, 6006, 7007, 8008]

                # Generate N candidates with different seeds for manual layout
                # selection. Each candidate is written as cover_bg_v{i}.png. The
                # first candidate also becomes the canonical cover_bg.png so
                # downstream cover_thumbnail keeps working unchanged.
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

            if bg_path.exists():
                write_artifact_manifest(
                    bg_path,
                    step="cover_image",
                    date=date,
                    inputs=cover_bg_inputs,
                    config=self.config,
                )

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
                inputs={
                    "background": bg_path.name,
                    "variant_index": i,
                    "title_cover_variants_hash": variant_hash,
                    "cover_prompt_hash": cover_prompt_hash,
                },
                config=self.config,
            )

        self._mirror_cover_bg(date, bg_path)
        self.logger.info(
            f"  Cover image + {min(len(variants), COVER_VARIANT_COUNT)} variant(s) "
            f"written ({bg_path.name})"
        )

    def _load_title_cover_variants(self, date: str) -> list[dict[str, Any]]:
        """Load cover copy emitted by the title step, if present.

        The tolerant fallback is intentional for pre-consolidation artifacts:
        once ``title.md`` changes, its manifest becomes stale and the title
        step will rewrite the cache with the new field.
        """
        title_path = publish_path(date, "title.json")
        if not title_path.exists():
            return []
        try:
            payload = json.loads(title_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(payload, dict):
            return []
        return _normalize_cover_variants(payload.get("cover_variants"))

    def _load_title_cover_prompt(self, date: str) -> str:
        """Load the visual prompt emitted with title metadata, if present."""
        title_path = publish_path(date, "title.json")
        if not title_path.exists():
            return ""
        try:
            payload = json.loads(title_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ""
        if not isinstance(payload, dict):
            return ""
        return _normalize_cover_prompt(payload.get("cover_prompt"))

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

        # Collect the generated text variants.
        text_variants = [
            render_path(date, f"cover_props_v{i}.json")
            for i in range(1, COVER_VARIANT_COUNT + 1)
        ]
        text_variants = [p for p in text_variants if p.exists()]
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

                # b1_t1 is the canonical cover.
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

    def _write_publish_guide(
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
