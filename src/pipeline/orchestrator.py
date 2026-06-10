import json
import re
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
from src.pipeline.agent_io import (
    append_agent_event,
    file_sha256,
    stable_hash,
    write_artifact_manifest,
)
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
from src.pipeline.script import ScriptWriter
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


def _format_mmss(seconds: float | int | None) -> str:
    total = max(0, int(round(float(seconds or 0))))
    return f"{total // 60:02d}:{total % 60:02d}"


def _script_chapter_payload(script: Optional[Script]) -> dict:
    if script is None:
        return {"total_duration": "00:00", "chapters": []}
    chapters = []
    for segment in script.segments:
        label = {
            "opening": "开场",
            "story_scan": "逐条速览",
            "closing": "收尾",
        }.get(segment.segment_type, segment.segment_type)
        text = normalize_cjk_mixed_spacing(segment.audio_text or "")
        chapters.append(
            {
                "start": _format_mmss(segment.start_time),
                "end": _format_mmss(segment.end_time),
                "label": label,
                "summary": text[:90],
            }
        )
    return {
        "total_duration": _format_mmss(script.total_duration),
        "chapters": chapters,
    }


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

    if (
        "cover_thumbnail" in optional_requested
        and "cover_image" not in optional_requested
    ):
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

        analysis_path = Path(f"data/{date}/comment_analysis.json")
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
            return script

        if self.dry_run:
            self.logger.info("Dry run: skipping title generation")
            return script

        focus_story, comment_analysis = self._build_focus_story_input(
            script, content, date
        )

        context = {
            "focus_story_json": json.dumps(focus_story, ensure_ascii=False, indent=2),
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

        # Enforce a reasonable length cap on title candidates.
        # The prompt asks for ≤30 visual chars; we allow up to 35 len()
        # to accommodate English product names that are wider than CJK.
        title_candidates = [
            _downgrade_unsupported_publish_claims(str(c))
            for c in (result.get("title_candidates") or [])
            if c
        ]
        chosen = _downgrade_unsupported_publish_claims(result.get("title") or "")

        TITLE_IDEAL_MIN, TITLE_HARD_MAX = 8, 40

        def _fits(c: str) -> bool:
            return TITLE_IDEAL_MIN <= len(c) <= TITLE_HARD_MAX

        original_chosen_len = len(chosen)
        valid_candidates = [c for c in title_candidates if _fits(c)]
        if not _fits(chosen):
            if valid_candidates:
                chosen = min(valid_candidates, key=len)
                self.logger.info(
                    f"  LLM's `title` field was {original_chosen_len} chars; "
                    f"picked shortest valid candidate: {chosen!r}"
                )
            else:
                if title_candidates:
                    self.logger.warning(
                        f"  All {len(title_candidates)} title candidates out of range "
                        f"(lengths: {[len(c) for c in title_candidates]}). "
                        f"Truncating shortest to {TITLE_HARD_MAX} chars."
                    )
                    shortest = min(title_candidates, key=len)
                    chosen = shortest[:TITLE_HARD_MAX]
                else:
                    self.logger.warning(
                        "  LLM returned no title_candidates. "
                        f"Using fallback title ({len(chosen)} chars)."
                    )
        kept_candidates = [chosen] + [
            c for c in title_candidates if c != chosen and _fits(c)
        ]

        script.title = chosen or "HN每日观察"
        script.description = (
            _clean_publish_description(
                _downgrade_unsupported_publish_claims(result.get("description") or "")
            )
            or f"每日快讯 - {date}"
        )
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

        atomic_write_json(
            cache_path,
            {
                "title": script.title,
                "title_candidates": kept_candidates,
                "description": script.description,
                "cover_title": script.cover_title,
                "cover_tags": script.cover_tags,
                "cover_subtitle": script.cover_subtitle,
                "tags": script.tags,
            },
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

        title = (
            script.cover_title
            if script and script.cover_title
            else script.title
            if script
            else "HN每日观察"
        )
        cover_tags = script.cover_tags[:2] if script and script.cover_tags else []
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

        atomic_write_json(
            props_path,
            {
                "backgroundImage": bg_path.name,
                "title": title,
                "subtitle": subtitle,
                "tags": cover_tags,
                "dateLabel": date_label,
            },
        )
        write_artifact_manifest(
            props_path,
            step="cover_image",
            date=date,
            inputs={
                "background": str(bg_path).replace("\\", "/"),
                "title": title,
                "subtitle": subtitle,
                "tags": cover_tags,
            },
            config=self.config,
        )

        # Mirror the cover background into the per-date Remotion runtime dir
        # so the source tree stays clean. The renderer also points
        # --public-dir here when rendering.
        public_bg = Path(f"data/{date}/remotion/public") / bg_path.name
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
            raise FileNotFoundError(
                "  cover_thumbnail requires cover_bg.png and cover_props.json; "
                "run --steps cover_image first"
            )

        if self.dry_run:
            self.logger.info("Dry run: skipping cover thumbnail render")
            return

        npx_path = find_npx()
        if not npx_path:
            raise FileNotFoundError(
                "npx not found; install Node.js or set PATH to include npx"
            )

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
            f"--public-dir={Path(f'data/{date}/remotion/public').resolve()}",
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
            raise RuntimeError(
                f"Cover render failed (exit={e.returncode}):\n"
                f"  stderr: {(e.stderr or '').strip()}\n"
                f"  stdout: {(e.stdout or '').strip()}"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"Cover render timed out after 120s: {e}") from e
        except FileNotFoundError as e:
            raise FileNotFoundError(f"npx not found: {e}") from e
        if not cover_path.exists() or cover_path.stat().st_size <= 0:
            raise RuntimeError(
                f"Cover render did not produce a valid file: {cover_path}"
            )

    def _step_publish_guide(
        self, content: ContentPackage, script: Optional[Script], date: str
    ) -> None:
        self.logger.info(
            "Step: Publish guide — generate human-facing publish checklist"
        )
        guide_path = Path(f"data/{date}/publish_guide.md")
        title_path = Path(f"data/{date}/title.json")
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
                "keywords": item.keywords or [],
                "score": item.score,
                "comment_count": item.comment_count,
            }
            for item in content.items
        ]
        context = {
            "script_title": title_payload.get("title")
            or (script.title if script else "HN每日观察"),
            "script_description": title_payload.get("description")
            or (script.description if script else ""),
            "script_runtime": json.dumps(
                _script_chapter_payload(script), ensure_ascii=False, indent=2
            ),
            "items_json": json.dumps(items_payload, ensure_ascii=False, indent=2),
            "date": date,
        }
        manifest_context = {
            **context,
            "prompt_hash": file_sha256(Path("prompts/publish_guide.md")),
        }
        manifest_path = guide_path.with_suffix(guide_path.suffix + ".manifest.json")
        manifest = None
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                manifest = None
        if (
            guide_path.exists()
            and isinstance(manifest, dict)
            and manifest.get("input_hash") == stable_hash(manifest_context)
        ):
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

    def _step_prepare_render(
        self, content: ContentPackage, script: Optional[Script], date: str
    ) -> None:
        self.logger.info("Step: Prepare render — write props.json and copy assets")
        if script is None:
            raise ValueError("Script not loaded; cannot prepare render")

        if self.dry_run:
            self.logger.info("Dry run: skipping prepare_render")
            return

        audio_dir = f"data/{date}/audio"
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

        output_path = f"data/{date}/output.mp4"
        audio_dir = f"data/{date}/audio"
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

        audio_dir = f"data/{date}/audio"
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
        # Match the new per-date runtime layout: data/{date}/remotion/chunks.
        chunk_dir = Path(f"data/{date}/remotion/chunks")
        if chunk_dir.exists() and not any(
            str(p).startswith(str(remotion_dir))
            for p in self.renderer.cache_paths(date)
        ):
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
