from typing import List, Optional

from src.core.interfaces import (
    ContentFetcher,
    LLMProvider,
    TTSProvider,
    Renderer,
    ImageGeneratorProvider,
)
from src.core.models import ContentPackage, Script
from src.pipeline.agent_decision import AgentDecisionEngine
from src.pipeline.agent_io import append_agent_event
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
)
from src.pipeline.pipeline_progress import PipelineProgress
from src.pipeline.prefilter import Prefilter
from src.pipeline.stages import (
    EditorialStageMixin,
    PackagingStageMixin,
    ProductionStageMixin,
    ResearchStageMixin,
    ScriptStageMixin,
    SupportStageMixin,
    TitleCoverStageMixin,
    WorkflowLifecycleMixin,
)
from src.pipeline.script import ScriptWriter
from src.pipeline.timing_engine import TimingEngine
from src.pipeline.transcript_generator import save_transcript
from src.pipeline.translation_manager import TranslationManager
from src.pipeline.tts_processor import TTSProcessor
from src.utils.logger import setup_logger


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
    TitleCoverStageMixin,
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
