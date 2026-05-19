import subprocess
import time
from pathlib import Path
from typing import List, Optional

from src.core.interfaces import ContentFetcher, LLMProvider, TTSProvider, Renderer
from src.core.models import ContentPackage, Script, ScriptSegment
from src.providers.renderer.remotion_props import regenerate_preview_props
from src.pipeline.content_preparer import ContentPreparer
from src.pipeline.content_hydrator import merge_enrichment_into_content
from src.pipeline.script_writer import ScriptWriter
from src.pipeline.timing_engine import TimingEngine
from src.pipeline.tts_processor import TTSProcessor
from src.pipeline.translation_manager import TranslationManager
from src.pipeline.report_generator import ReportGenerator
from src.pipeline.comment_analyzer import CommentAnalyzer
from src.pipeline.comment_judge import CommentJudge
from src.pipeline.prefilter import Prefilter
from src.utils.logger import setup_logger


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
        self.comment_judge = CommentJudge(
            llm_provider, config, comment_analyzer=self.comment_analyzer, debug=debug
        )
        self.prefilter = Prefilter(llm_provider, config, debug=debug)
        timing_cfg = config.get("timing", {})
        self._timing = TimingEngine(
            segment_gap=float(timing_cfg.get("segment_gap", 0.0)),
            story_gap=float(timing_cfg.get("story_gap", 0.0)),
            debug=debug,
        )

    def run(
        self, date: str, steps: Optional[List[str]] = None, force: bool = False
    ) -> None:
        # Core pipeline: fetch → enrich → script → produce
        # Standalone: render, preview, editor, sync_preview
        _ALL_STEPS = [
            "fetch",
            "enrich",
            "script",
            "produce",
            "render",
            "preview",
            "editor",
            "sync_preview",
        ]

        if steps is None:
            steps = [
                s for s in _ALL_STEPS if s not in ("render", "editor", "sync_preview")
            ]
        else:
            # Exclude standalone steps from expansion — they don't need prior steps
            _standalone = {"editor", "render", "preview", "sync_preview"}
            pipeline_steps = [
                s for s in steps if s in _ALL_STEPS and s not in _standalone
            ]
            if pipeline_steps:
                max_idx = max(_ALL_STEPS.index(s) for s in pipeline_steps)
                steps = _ALL_STEPS[: max_idx + 1] + [
                    s for s in steps if s in _standalone
                ]
            else:
                steps = [s for s in steps if s in _ALL_STEPS]

        t_start = time.monotonic()
        self.logger.info(
            f"Running pipeline, date={date}, steps={steps}, product=daily_brief"
        )

        content = None
        script = None

        # ── fetch ──────────────────────────────────────────────────
        if "fetch" in steps:
            content = self._step_fetch(date)
        else:
            try:
                content = self.content_preparer.load_content(date)
            except FileNotFoundError:
                self.logger.info("Content not found, fetching anyway...")
                content = self._step_fetch(date)

        # ── enrich (prefilter + enrichment) ────────────────────────
        if "enrich" in steps:
            content = self._step_enrich(content, date)
            # Stop pipeline if any items need manual HTML download
            if content and any(
                item.enrichment_source in ("fetch_failed", "extraction_failed")
                for item in content.items
            ):
                self.logger.warning(
                    "Pipeline stopped: some items need manual intervention. "
                    "Re-run after placing HTML files in downloaded_pages/."
                )
                return

        # ── script (analyze + script generation) ───────────────────
        if "script" in steps:
            script = self._step_script(content, date)
        else:
            try:
                script = self.script_writer.load_script(date)
            except FileNotFoundError:
                self.logger.info("Script not found, generating anyway...")
                script = self._step_script(content, date)

        # ── produce (translate + tts) ──────────────────────────────
        if "produce" in steps:
            content, script = self._step_produce(content, script, date)

        # ── standalone steps ───────────────────────────────────────
        if "sync_preview" in steps:
            self._step_sync_preview(script, date, content)

        if "preview" in steps:
            self._step_preview(script, date, content)

        if "editor" in steps:
            self._step_editor(date)

        if "render" in steps:
            self._step_render(script, date, content, force=force)

        # Save transcript
        if script and ("script" in steps or "produce" in steps):
            self.script_writer.save_transcript(script, date, content)

        elapsed = time.monotonic() - t_start
        self.report_generator.generate(date, steps, elapsed, content, script)

        self.logger.info("Pipeline completed")

    # ── Core Steps ────────────────────────────────────────────────

    def _step_fetch(self, date: str):
        self.logger.info("Step: Fetch content")
        if self.dry_run:
            self.logger.info("Dry run: skipping fetch")
            from src.core.models import ContentPackage

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
        # Sub-step 1: prefilter
        self.logger.info("Step: Enrich — prefilter stories by tech relevance")
        if not self.dry_run:
            content = self.prefilter.filter(content, date)
            self.content_preparer.save_content(content, date)

        # Sub-step 2: fetch comments (only for stories that survived prefilter)
        self.logger.info("Step: Enrich — fetch comments")
        if not self.dry_run:
            content = self.content_fetcher.fetch_comments(content, date)
            self.content_preparer.save_content(content, date)

        # Sub-step 3: enrichment
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

        # Gate: check for items that need manual HTML download
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

        self.content_preparer.save_content(content, date)
        return content

    def _step_script(self, content, date: str):
        # Sub-step 1: analyze comments
        self.logger.info("Step: Script — analyze comments")
        if not self.dry_run:
            content = self.comment_analyzer.analyze(content, date)
            self.comment_judge.judge(content, date)
            self.content_preparer.save_content(content, date)

        # Sub-step 2: generate script
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
                        estimated_duration=10.0,
                    )
                ],
            )

        script = self.script_writer.write(content)
        self.script_writer.save_script(script, date)
        return script

    def _step_produce(self, content, script, date: str):
        # Sub-step 1: translate
        self.logger.info("Step: Produce — translate titles and comments")
        if not self.dry_run:
            content, script = self.translation_manager.translate(content, script, date)
            self.script_writer.save_script(script, date)

        # Sub-step 2: tts
        self.logger.info("Step: Produce — synthesize audio")
        if self.dry_run:
            self.logger.info("Dry run: skipping TTS")
            for seg in script.segments:
                seg.actual_duration = seg.estimated_duration
                seg.audio_path = ""
            self._timing.compute_timeline(script)
            return content, script

        script = self.tts_processor.process_audio(script, date, content)
        self.script_writer.save_script(script, date)
        return content, script

    # ── Standalone Steps ──────────────────────────────────────────

    def _step_sync_preview(self, script: Script, date: str, content=None) -> None:
        self.logger.info("Step: Sync Preview Props")
        if self.dry_run:
            self.logger.info("Dry run: skipping sync_preview")
            return
        regenerate_preview_props(date, self.config, logger=self.logger)

    def _step_preview(self, script: Script, date: str, content=None) -> None:
        self.logger.info("Step: Preview (Remotion Studio)")
        if self.dry_run:
            self.logger.info("Dry run: skipping preview")
            return

        if content is None:
            try:
                content = self.content_preparer.load_content(date)
            except FileNotFoundError:
                self.logger.info(
                    "Content not found for preview, scene elements may be incomplete"
                )

        self._merge_enrichment_images(content, date)

        audio_dir = f"data/{date}/audio"
        self.logger.info("Opening Remotion Studio at http://localhost:3000")
        self.logger.info(
            "Check the preview, then press Ctrl+C to stop and proceed to render."
        )
        self.renderer.preview(script, audio_dir, content, date=date)

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

    def _merge_enrichment_images(self, content: ContentPackage, date: str) -> None:
        """Apply enrichment/editor overlay before preview or render."""
        merge_enrichment_into_content(content, date, logger=self.logger)

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

        self._merge_enrichment_images(content, date)

        if force:
            self._clear_render_cache(date)

        output_path = f"data/{date}/output.mp4"
        audio_dir = f"data/{date}/audio"
        self.renderer.render(script, audio_dir, output_path, content, date=date)

    def _clear_render_cache(self, date: str) -> None:
        """Delete chunk cache and output file to force a full re-render."""
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
