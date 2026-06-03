import subprocess
from pathlib import Path
from typing import List, Optional

from src.core.interfaces import ContentFetcher, LLMProvider, TTSProvider, Renderer
from src.core.models import ContentPackage, Script, ScriptSegment
from src.pipeline.comment import CommentAnalyzer, CommentJudge, CommentRefiner
from src.pipeline.content_io import ContentPreparer, merge_enrichment_into_content
from src.pipeline.pipeline_progress import PipelineProgress
from src.pipeline.prefilter import Prefilter
from src.pipeline.html_preview import generate as generate_html_preview
from src.pipeline.html_preview import import_selections
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
PIPELINE_STEPS = ["fetch", "enrich", "script", "produce"]
STANDALONE_STEPS = {"render", "editor", "html_preview"}
ALL_STEPS = PIPELINE_STEPS + ["render", "editor", "html_preview"]
DEFAULT_STEPS = PIPELINE_STEPS


def _resolve_steps(requested: List[str]) -> List[str]:
    """Expand requested steps to include all prerequisites."""
    valid = [s for s in requested if s in ALL_STEPS]
    if not valid:
        return []

    pipeline_requested = [s for s in valid if s in PIPELINE_STEPS]
    standalone_requested = [s for s in valid if s in STANDALONE_STEPS]

    if pipeline_requested:
        max_idx = max(PIPELINE_STEPS.index(s) for s in pipeline_requested)
        return PIPELINE_STEPS[: max_idx + 1] + standalone_requested
    return standalone_requested


class Orchestrator:
    def __init__(
        self,
        config: dict,
        content_fetcher: ContentFetcher,
        llm_provider: LLMProvider,
        tts_provider: TTSProvider,
        renderer: Renderer,
        article_enricher=None,
        debug: bool = False,
        dry_run: bool = False,
    ):
        self.config = config
        self.content_fetcher = content_fetcher
        self.llm_provider = llm_provider
        self.tts_provider = tts_provider
        self.renderer = renderer
        self.article_enricher = article_enricher
        self.debug = debug
        self.dry_run = dry_run
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
        self._progress.print_execution_summary(force=force)

        content = None
        script = None

        if "fetch" in steps:
            with self._progress.step("fetch"):
                content = self._step_fetch(date)
        else:
            try:
                content = self.content_preparer.load_content(date)
            except FileNotFoundError:
                self.logger.info("Content not found, fetching anyway...")
                with self._progress.step("fetch"):
                    content = self._step_fetch(date)

        if "enrich" in steps:
            with self._progress.step("enrich"):
                content = self._step_enrich(content, date)
                failed_items = [
                    item
                    for item in content.items
                    if item.enrichment_source in ("fetch_failed", "extraction_failed")
                ]
                if failed_items:
                    self.logger.warning(
                        f"Pipeline stopped: {len(failed_items)}/{len(content.items)} "
                        "items could not be fetched. "
                        "Re-run after placing HTML files in downloaded_pages/."
                    )
                    self._print_enrich_failure_guidance(failed_items)
                    return

        if "script" in steps:
            with self._progress.step("script"):
                script = self._step_script(content, date)
        else:
            try:
                script = self.script_writer.load_script(date)
            except FileNotFoundError:
                self.logger.info("Script not found, generating anyway...")
                with self._progress.step("script"):
                    script = self._step_script(content, date)

        if "produce" in steps:
            with self._progress.step("produce"):
                content, script = self._step_produce(content, script, date)

        if "editor" in steps:
            with self._progress.step("editor"):
                self._step_editor(date)

        if "html_preview" in steps:
            with self._progress.step("html_preview"):
                self._step_html_preview(date)

        if "render" in steps:
            with self._progress.step("render"):
                self._step_render(script, date, content, force=force)

        if script and ("script" in steps or "produce" in steps):
            save_transcript(script, date, content, logger=self.logger)

        elapsed = self._progress.elapsed()
        self.report_generator.generate(date, steps, elapsed, content, script)

        self.logger.info("Pipeline completed")

    def _step_fetch(self, date: str):
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

    def _step_enrich(self, content, date: str):
        self.logger.info("Step: Enrich — prefilter stories by tech relevance")
        if not self.dry_run:
            content = self.prefilter.filter(content, date)
            self.content_preparer.save_content(content, date)

        self.logger.info("Step: Enrich — fetch comments")
        if not self.dry_run:
            content = self.content_fetcher.fetch_comments(content, date)
            self.content_preparer.save_content(content, date)

        self.logger.info("Step: Enrich — fetch article content and extract metadata")
        if self.dry_run:
            self.logger.info("Dry run: skipping enrichment")
            return content
        if self.article_enricher is None:
            self.logger.info("Article enricher not configured, skipping")
            return content
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
            return content

        self.logger.info("Step: Enrich — translate titles")
        if not self.dry_run:
            content = self.llm_provider.translate_titles(content, "translate.md")

        self.content_preparer.save_content(content, date)
        return content

    def _step_script(self, content, date: str):
        self.logger.info("Step: Script — analyze comments")
        if not self.dry_run:
            content = self.comment_analyzer.analyze(content, date)
            self.comment_judge.judge(content, date)
            self.content_preparer.save_content(content, date)

        self.logger.info("=" * 50)
        self.logger.info("Step: Script — generate narration (daily_brief)")
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

        script = self.script_writer.write(content)
        self.script_writer.save_script(script, date)
        return script

    def _step_produce(self, content, script, date: str):
        self.logger.info("Step: Produce — translate titles and comments")
        if not self.dry_run:
            content, script = self.translation_manager.translate(content, script, date)
            self.script_writer.save_script(script, date)

        self.logger.info("Step: Produce — synthesize audio")
        if self.dry_run:
            self.logger.info("Dry run: skipping TTS")
            for seg in script.segments:
                seg.actual_duration = seg.duration
                seg.audio_path = ""
            self._timing.compute_timeline(script)
            return content, script

        script = self.tts_processor.process_audio(script, date, content)
        self.script_writer.save_script(script, date)
        return content, script

    def _step_editor(self, date: str) -> None:
        self.logger.info("Step: Open Streamlit Editor")
        if self.dry_run:
            self.logger.info("Dry run: skipping editor")
            return

        self.logger.info("Opening Streamlit Editor at http://localhost:8501")
        self.logger.info("Close the browser tab and press Ctrl+C to stop.")
        try:
            subprocess.run(
                [
                    "uv",
                    "run",
                    "streamlit",
                    "run",
                    "src/editor/app.py",
                    "--server.port",
                    "8501",
                ],
                check=True,
            )
        except KeyboardInterrupt:
            self.logger.info("Editor stopped.")

    def _step_html_preview(self, date: str) -> None:
        self.logger.info("Step: Generate HTML preview")
        if self.dry_run:
            self.logger.info("Dry run: skipping html preview")
            return

        result = import_selections(date)
        if result["applied"]:
            self.logger.info(
                f"Imported {result['applied']} image selections"
                + (
                    f", {result['new_images']} new images"
                    if result.get("new_images")
                    else ""
                )
            )

        output = generate_html_preview(date)
        self.logger.info(f"HTML preview: {output}")

    def _step_render(
        self, script: Script, date: str, content=None, force: bool = False
    ) -> None:
        self.logger.info("Step: Render video")
        if self.dry_run:
            self.logger.info("Dry run: skipping render")
            return

        if content is None:
            try:
                content = self.content_preparer.load_content(date)
            except FileNotFoundError:
                self.logger.info(
                    "Content not found for render, scene elements may be incomplete"
                )

        merge_enrichment_into_content(content, date, logger=self.logger)

        if force:
            self._clear_render_cache(date)

        output_path = f"data/{date}/output.mp4"
        audio_dir = f"data/{date}/audio"
        self.renderer.render(script, audio_dir, output_path, content, date=date)

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
