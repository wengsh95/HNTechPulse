import json
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import List, Optional, Tuple

from src.core.interfaces import (
    ContentFetcher,
    LLMProvider,
    TTSProvider,
    Renderer,
    ImageGeneratorProvider,
)
from src.core.models import ContentPackage, Script
from src.pipeline.agent_decision import AgentDecisionEngine
from src.pipeline.agent_io import append_agent_event, write_artifact_manifest
from src.pipeline.agent_variants import (
    promote_variant_script,
    write_variants_index,
)
from src.pipeline.comment import CommentAnalyzer, CommentJudge, CommentRefiner
from src.pipeline.agent_state import AgentState, BLOCK_INSUFFICIENT_CONTEXT
from src.pipeline.content_io import ContentPreparer
from src.pipeline.pipeline_progress import PipelineProgress
from src.pipeline.prefilter import Prefilter
from src.providers.renderer.binary_finder import find_npx
from src.pipeline.report_generator import ReportGenerator
from src.pipeline.script import ScriptWriter
from src.pipeline.timing_engine import TimingEngine
from src.pipeline.transcript_generator import save_transcript
from src.pipeline.translation_manager import TranslationManager
from src.pipeline.tts_processor import TTSProcessor
from src.utils.logger import setup_logger


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
    "translate_comments",
    "synthesize_audio",
    "title",
    "cover_image",
    "cover_thumbnail",
    "publish_guide",
    "prepare_render",
]
OPTIONAL_PRODUCTION_STEPS = {"cover_image", "cover_thumbnail", "publish_guide"}
CORE_PIPELINE_STEPS = [
    step for step in PIPELINE_STEPS if step not in OPTIONAL_PRODUCTION_STEPS
]
STANDALONE_STEPS = {"render", "preview"}
ALL_STEPS = PIPELINE_STEPS + ["render", "preview"]
DEFAULT_STEPS = CORE_PIPELINE_STEPS

# Steps that need `script` in memory (consume from `write_script` or disk).
SCRIPT_CONSUMING_STEPS = frozenset(
    {
        "translate_comments",
        "synthesize_audio",
        "title",
        "cover_image",
        "cover_thumbnail",
        "publish_guide",
        "prepare_render",
        "render",
    }
)

# Steps that mutate `script`; trigger transcript save.
SCRIPT_MUTATING_STEPS = frozenset(
    {
        "write_script",
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

    if "cover_thumbnail" in optional_requested and "cover_image" not in optional_requested:
        optional_requested = ["cover_image", *optional_requested]

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
        self.report_generator = ReportGenerator(debug=debug, level=log_level)
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
            if self.agent_mode and self.allow_degraded_enrichment:
                self._mark_degraded_enrichment(failed_items)
            else:
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

        # ── 9. translate_comments ─────────────────────────────────────────
        if "translate_comments" in steps:
            with self._tracked_step("translate_comments"):
                content, script = self._step_translate_comments(content, script, date)

        # ── 10. synthesize_audio ──────────────────────────────────────────
        if "synthesize_audio" in steps:
            with self._tracked_step("synthesize_audio"):
                script = self._step_synthesize_audio(content, script, date)

        # ── 11. title ─────────────────────────────────────────────────────
        if "title" in steps:
            with self._tracked_step("title"):
                script = self._step_title(content, script, date)

        # ── 12. cover_image ───────────────────────────────────────────────
        if "cover_image" in steps:
            with self._tracked_step("cover_image"):
                self._step_cover_image(content, script, date)

        # ── 13. cover_thumbnail ───────────────────────────────────────────
        if "cover_thumbnail" in steps:
            with self._tracked_step("cover_thumbnail"):
                self._step_cover_thumbnail(content, script, date)

        # ── 14. publish_guide ─────────────────────────────────────────────
        if "publish_guide" in steps:
            with self._tracked_step("publish_guide"):
                self._step_publish_guide(content, script, date)

        # ── 15. prepare_render ────────────────────────────────────────────
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

        elapsed = self._progress.elapsed()
        self.report_generator.generate(date, steps, elapsed, content, script)
        if self._agent_state:
            self._agent_state.finish_run()

        self.logger.info("Pipeline completed")

    # ── Step implementations ─────────────────────────────────────────────

    def _step_fetch(self, date: str) -> ContentPackage:
        self.logger.info("Step: Fetch content")
        if self.dry_run:
            self.logger.info("Dry run: skipping fetch")
            return ContentPackage(date=date, items=[])

        hn_cfg = self.config.get("hn", {})
        fetch_count = hn_cfg.get("target_stories_count", 30)
        content = self.content_fetcher.fetch(
            date,
            num_deep_dive=0,
            num_brief=fetch_count,
        )
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
            download_dir = Path(f"data/{date}/downloaded_pages")
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

        analysis_path = Path(f"data/{date}/comment_analysis.json")
        if analysis_path.exists():
            self.logger.info(f"  Comment analysis already done at {analysis_path}")
            return content

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

        judgement_path = Path(f"data/{date}/comment_judgement.json")
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
        num_brief = min(
            self.config.get("pipeline", {}).get("target_story_count", 10),
            len(content.items),
        )
        self.logger.info(
            f"Expected script LLM calls: story_scan={num_brief} "
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

    def _step_title(
        self, content: ContentPackage, script: Optional[Script], date: str
    ) -> Optional[Script]:
        self.logger.info("Step: Title — generate video title/description/tags")
        if script is None:
            self.logger.warning("Script not loaded; skipping title generation")
            return script

        cache_path = Path(f"data/{date}/title.json")
        if cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            self.logger.info(f"  Loaded cached title from {cache_path}")
            script.title = cached.get("title", script.title)
            script.description = cached.get("description", script.description)
            script.tags = cached.get("tags", script.tags)
            script.cover_subtitle = cached.get("cover_subtitle", script.cover_subtitle)
            return script

        if self.dry_run:
            self.logger.info("Dry run: skipping title generation")
            return script

        highlight_entries = self._extract_highlight_entries(script, content)

        context = {
            "highlight_entries": json.dumps(
                highlight_entries, ensure_ascii=False, indent=2
            ),
            "date": date,
        }
        result = self.llm_provider.complete_prompt(
            "prompts/title.md",
            context,
            label="title",
            expect_json=True,
            model=self.llm_provider.fast_model,
            temperature=self.llm_provider.fast_temperature,
        )
        script.title = (result.get("title") or "").strip() or "HN每日观察"
        script.description = (
            result.get("description") or ""
        ).strip() or f"每日快讯 - {date}"
        script.tags = list(result.get("tags") or [])
        script.cover_subtitle = (result.get("cover_subtitle") or "").strip()

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(
                {
                    "title": script.title,
                    "title_candidates": result.get("title_candidates") or [],
                    "description": script.description,
                    "cover_subtitle": (result.get("cover_subtitle") or "").strip(),
                    "tags": script.tags,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        write_artifact_manifest(
            cache_path,
            step="title",
            date=date,
            inputs={
                "script_segment_count": len(script.segments),
                "content_item_count": len(content.items),
            },
            config=self.config,
        )
        self.script_writer.save_script(script, date)
        return script

    def _step_cover_image(
        self, content: ContentPackage, script: Optional[Script], date: str
    ) -> None:
        self.logger.info("Step: Cover image — generate AI image for cover")
        bg_path = Path(f"data/{date}/cover_bg.png")
        props_path = Path(f"data/{date}/cover_props.json")
        # CoverThumbnail composition in Remotion is 1920x1080 (16:9); the
        # generated image must match, otherwise objectFit:cover crops the
        # editorial illustration. The provider's config default may differ,
        # so we override explicitly here.
        cover_aspect_ratio = "16:9"

        if bg_path.exists() and props_path.exists():
            self.logger.info(f"  Cover image already done at {bg_path}")
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

            try:
                self.image_generator.generate(
                    cover_prompt, str(bg_path), aspect_ratio=cover_aspect_ratio
                )
            except (ValueError, RuntimeError, OSError) as e:
                self.logger.warning(
                    f"Image generation failed ({type(e).__name__}: {e})"
                )
                return

        title = script.title if script else "HN每日观察"
        # 封面副文：cover_subtitle 优先（格式/长度见 prompts/title.md cover_subtitle 段），fallback 到 description 截断
        if script is None:
            subtitle = date
        elif script.cover_subtitle:
            subtitle = script.cover_subtitle
        elif script.description:
            subtitle = script.description[:40] + (
                "…" if len(script.description) > 40 else ""
            )
        else:
            subtitle = date
        date_label = date

        props_path.parent.mkdir(parents=True, exist_ok=True)
        props_path.write_text(
            json.dumps(
                {
                    "backgroundImage": bg_path.name,
                    "title": title,
                    "subtitle": subtitle,
                    "dateLabel": date_label,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        write_artifact_manifest(
            props_path,
            step="cover_image",
            date=date,
            inputs={
                "background": str(bg_path).replace("\\", "/"),
                "title": title,
                "subtitle": subtitle,
            },
            config=self.config,
        )

        remotion_dir = Path("src/providers/renderer/remotion")
        public_bg = remotion_dir / "public" / bg_path.name
        public_bg.parent.mkdir(parents=True, exist_ok=True)
        try:
            same_file = public_bg.samefile(bg_path)
        except FileNotFoundError:
            same_file = False
        if not same_file:
            shutil.copy2(bg_path, public_bg)

        self.logger.info(f"  Cover image written to {bg_path}")

    def _step_cover_thumbnail(
        self, content: ContentPackage, script: Optional[Script], date: str
    ) -> None:
        self.logger.info(
            "Step: Cover thumbnail — render Remotion still with title overlay"
        )
        cover_path = Path(f"data/{date}/cover.png")
        bg_path = Path(f"data/{date}/cover_bg.png")
        props_path = Path(f"data/{date}/cover_props.json")

        if cover_path.exists():
            self.logger.info(f"  Cover thumbnail already exists at {cover_path}")
            return

        if not bg_path.exists() or not props_path.exists():
            self.logger.error(
                "  cover_thumbnail requires cover_bg.png and cover_props.json; "
                "run --steps cover_image first"
            )
            return

        if self.dry_run:
            self.logger.info("Dry run: skipping cover thumbnail render")
            return

        npx_path = find_npx()
        if not npx_path:
            self.logger.error(
                "npx not found — install Node.js or set PATH to include npx"
            )
            return

        remotion_dir = Path("src/providers/renderer/remotion")
        output_abs = cover_path.resolve()
        cmd = [
            npx_path,
            "remotion",
            "still",
            "CoverThumbnail",
            f"--props={props_path.resolve()}",
            "--frame=0",
            f"--output={output_abs}",
        ]
        try:
            result = subprocess.run(
                cmd,
                cwd=str(remotion_dir),
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.stdout:
                self.logger.info(f"  [remotion] {result.stdout.strip()}")
            self.logger.info(f"  Cover thumbnail written to {cover_path}")
        except subprocess.CalledProcessError as e:
            self.logger.error(
                f"Cover render failed (exit={e.returncode}):\n"
                f"  stderr: {(e.stderr or '').strip()}\n"
                f"  stdout: {(e.stdout or '').strip()}"
            )
        except subprocess.TimeoutExpired as e:
            self.logger.error(f"Cover render timed out after 120s: {e}")
        except FileNotFoundError as e:
            self.logger.error(f"npx not found: {e}")

    def _step_publish_guide(
        self, content: ContentPackage, script: Optional[Script], date: str
    ) -> None:
        self.logger.info(
            "Step: Publish guide — generate human-facing publish checklist"
        )
        guide_path = Path(f"data/{date}/publish_guide.md")

        if guide_path.exists():
            self.logger.info(f"  Publish guide already exists at {guide_path}")
            return

        if self.dry_run:
            self.logger.info("Dry run: skipping publish guide generation")
            return

        items_payload = [
            {
                "title_cn": item.title_cn or item.title,
                "title": item.title,
                "editor_angle": item.editor_angle or item.dek or "",
                "category": item.category or "",
                "keywords": item.keywords or [],
                "score": item.score,
                "comment_count": item.comment_count,
            }
            for item in content.items
        ]
        context = {
            "script_title": script.title if script else "HN每日观察",
            "script_description": script.description if script else "",
            "items_json": json.dumps(items_payload, ensure_ascii=False, indent=2),
            "date": date,
        }
        text = self.llm_provider.complete_prompt(
            "prompts/publish_guide.md",
            context,
            label="publish_guide",
            expect_json=False,
            model=self.llm_provider.fast_model,
            temperature=self.llm_provider.fast_temperature,
        )

        guide_path.parent.mkdir(parents=True, exist_ok=True)
        guide_path.write_text(text, encoding="utf-8")
        write_artifact_manifest(
            guide_path,
            step="publish_guide",
            date=date,
            inputs={
                "content_item_count": len(content.items),
                "script_title": script.title if script else "",
            },
            config=self.config,
        )
        self.logger.info(f"  Publish guide written to {guide_path}")

    def _step_prepare_render(
        self, content: ContentPackage, script: Optional[Script], date: str
    ) -> None:
        self.logger.info("Step: Prepare render — write props.json and copy assets")
        if script is None:
            self.logger.warning("Script not loaded; skipping prepare_render")
            return

        if self.dry_run:
            self.logger.info("Dry run: skipping prepare_render")
            return

        audio_dir = f"data/{date}/audio"
        props_path = Path("src/providers/renderer/remotion/public/props.json")
        before_mtime = props_path.stat().st_mtime if props_path.exists() else None
        self.renderer.write_props(script, audio_dir, content, date=date)
        after_mtime = props_path.stat().st_mtime if props_path.exists() else None
        if props_path.exists() and after_mtime != before_mtime:
            write_artifact_manifest(
                props_path,
                step="prepare_render",
                date=date,
                inputs={
                    "script_title": script.title,
                    "segment_count": len(script.segments),
                    "audio_dir": audio_dir,
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
                self.logger.error("Script not found; cannot render")
                return

        if content is None:
            try:
                content = self.content_preparer.load_content(date)
            except FileNotFoundError:
                self.logger.info(
                    "Content not found for render, scene elements may be incomplete"
                )

        if force:
            self._clear_render_cache(date)

        output_path = f"data/{date}/output.mp4"
        audio_dir = f"data/{date}/audio"
        self.renderer.render(script, audio_dir, output_path, content, date=date)

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

        audio_dir = f"data/{date}/audio"
        self.logger.info("Opening Remotion Studio at http://localhost:3000")
        self.logger.info(
            "Check the preview, then press Ctrl+C to stop and proceed to render."
        )
        self.renderer.preview(script, audio_dir, content, date=date)

    # ── Helpers ─────────────────────────────────────────────────────────

    def _clear_render_cache(self, date: str) -> None:
        remotion_dir = Path("src/providers/renderer/remotion")
        chunk_dir = remotion_dir / "out" / "chunks"
        if chunk_dir.exists():
            import shutil

            shutil.rmtree(chunk_dir)
            self.logger.info(f"Cleared all chunk caches: {chunk_dir}")

        output_path = Path(f"data/{date}/output.mp4")
        if output_path.exists():
            output_path.unlink()
            self.logger.info(f"Deleted output: {output_path}")

    def _refresh_variant_outputs(self, date: str) -> None:
        base = Path(f"data/{date}")
        if not base.exists():
            return
        deleted: list[str] = []
        paths = [
            base / "script.json",
            base / "script.json.manifest.json",
            base / "agent_decision.json",
            base / "agent_variant_decision.json",
            base / "selected_variant.json",
        ]
        for path in paths:
            if path.exists() and path.is_file():
                path.unlink()
                deleted.append(str(path).replace("\\", "/"))

        variants_dir = base / "variants"
        if variants_dir.exists() and variants_dir.is_dir():
            shutil.rmtree(variants_dir)
            deleted.append(str(variants_dir).replace("\\", "/"))

        segments_dir = base / "segments"
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
        self.logger.info(f"  Save each page as HTML to: data/{date}/downloaded_pages/")
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
