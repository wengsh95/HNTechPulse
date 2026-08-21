import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, List, Optional

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
from src.pipeline.paths import (
    agent_path,
    publish_path,
    render_path,
    render_remotion_dir,
)
from src.pipeline.pipeline_progress import PipelineProgress
from src.pipeline.prefilter import Prefilter
from src.pipeline.stages import (
    COVER_VARIANT_COUNT,
    EditorialStageMixin,
    PackagingStageMixin,
    ProductionStageMixin,
    ResearchStageMixin,
    ScriptStageMixin,
    SupportStageMixin,
    WorkflowLifecycleMixin,
)
from src.pipeline.script import ScriptWriter
from src.pipeline.timing_engine import TimingEngine
from src.pipeline.transcript_generator import save_transcript
from src.pipeline.translation_manager import TranslationManager
from src.pipeline.tts_processor import TTSProcessor
from src.utils.atomic_io import atomic_write_json
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


class Orchestrator(
    WorkflowLifecycleMixin,
    ResearchStageMixin,
    ScriptStageMixin,
    EditorialStageMixin,
    PackagingStageMixin,
    SupportStageMixin,
    ProductionStageMixin,
):
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
