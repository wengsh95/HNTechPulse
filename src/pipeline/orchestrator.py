import time
from pathlib import Path
from typing import List, Optional

from src.core.interfaces import ContentFetcher, LLMProvider, TTSProvider, Renderer
from src.core.models import Script, ScriptSegment
from src.pipeline.content_preparer import ContentPreparer
from src.pipeline.script_writer import ScriptWriter
from src.pipeline.timing_engine import TimingEngine
from src.pipeline.tts_processor import TTSProcessor
from src.pipeline.translation_manager import TranslationManager
from src.pipeline.report_generator import ReportGenerator
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
        dry_run: bool = False
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
        self.script_writer = ScriptWriter(config, llm_provider, self.content_preparer, debug=debug)
        self.tts_processor = TTSProcessor(tts_provider, config, debug=debug, level=log_level)
        self.translation_manager = TranslationManager(llm_provider, self.content_preparer, config, debug=debug, level=log_level)
        self.report_generator = ReportGenerator(debug=debug, level=log_level)
        self._timing = TimingEngine(debug=debug)

    def run(self, date: str, steps: Optional[List[str]] = None) -> None:
        if steps is None:
            steps = ["fetch", "enrich", "script", "translate", "tts", "render"]

        t_start = time.monotonic()
        self.logger.info(f"Running pipeline, date={date}, steps={steps}, product=daily_brief")

        content = None
        script = None

        if "fetch" in steps:
            content = self._step_fetch(date)
        else:
            try:
                content = self.content_preparer.load_content(date)
            except FileNotFoundError:
                self.logger.info("Content not found, fetching anyway...")
                content = self._step_fetch(date)

        if "enrich" in steps:
            content = self._step_enrich(content, date)

        if "script" in steps:
            script = self._step_script(content, date)
        else:
            try:
                script = self.script_writer.load_script(date)
            except FileNotFoundError:
                self.logger.info("Script not found, generating anyway...")
                script = self._step_script(content, date)

        if "translate" in steps:
            content, script = self._step_translate(content, script, date)

        if "tts" in steps:
            script = self._step_tts(script, date, content)

        if "preview" in steps:
            self._step_preview(script, date, content)

        if "render" in steps:
            self._step_render(script, date, content)

        # Save transcript
        if script and ("script" in steps or "tts" in steps):
            self.script_writer.save_transcript(script, date, content)

        elapsed = time.monotonic() - t_start
        self.report_generator.generate(date, steps, elapsed, content, script)

        self.logger.info("Pipeline completed")

    def _compute_timeline(self, script: Script) -> Script:
        return self._timing.compute_timeline(script)

    def _set_scene_element_times(self, script: Script) -> None:
        self._timing.set_scene_element_times(script)

    def _step_fetch(self, date: str):
        self.logger.info("Step: Fetch content")
        if self.dry_run:
            self.logger.info("Dry run: skipping fetch")
            from src.core.models import ContentPackage, ContentItem
            return ContentPackage(date=date, items=[])

        pipeline_cfg = self.config.get("pipeline", {})
        num_brief_items = pipeline_cfg.get("num_brief_items", 6)
        content = self.content_fetcher.fetch(
            date,
            num_deep_dive=0,
            num_brief=num_brief_items,
            num_quick_news=0,
        )
        self.content_preparer.save_content(content, date)
        return content

    def _step_enrich(self, content, date: str):
        self.logger.info("Step: Enrich content")
        if self.dry_run:
            self.logger.info("Dry run: skipping enrichment")
            return content
        if self.article_enricher is None:
            self.logger.info("Article enricher not configured, skipping")
            return content
        content = self.article_enricher.enrich(content, date)
        self.content_preparer.save_content(content, date)

        # Gate: check for items needing manual override
        failed_items = [
            item for item in content.items
            if item.enrichment_source in ("none", "error")
        ]
        if failed_items:
            override_path = Path(f"data/{date}/manual_override.json")
            self.logger.warning(
                f"{len(failed_items)} items need manual override — "
                f"edit {override_path} then re-run pipeline"
            )
            for i, item in enumerate(failed_items, 1):
                title = (item.title or "")[:50]
                reason = item.enrichment_source
                self.logger.info(f"  [{reason}] {title}")

            # If running interactively (TTY), pause for user to edit
            import sys
            if sys.stdin.isatty():
                try:
                    print(f"\n  Edit: {override_path}")
                    print("  Fill in article_text for each item, then press Enter to continue...")
                    input()

                    # Reload manual overrides after user edits
                    overridden = self.article_enricher._load_manual_overrides(content, date)
                    if overridden:
                        self.logger.info(f"Loaded {len(overridden)} manual overrides after user edit")
                        self.content_preparer.save_content(content, date)
                except EOFError:
                    self.logger.info("Non-interactive terminal, skipping manual override pause")

        return content

    def _step_translate(self, content, script, date: str):
        self.logger.info("Step: Translate titles and comments")
        if self.dry_run:
            self.logger.info("Dry run: skipping translation")
            return content, script

        content, script = self.translation_manager.translate(content, script, date)
        self.script_writer.save_script(script, date)
        return content, script

    def _step_script(self, content, date: str):
        self.logger.info("=" * 50)
        self.logger.info("Step: Generate script (daily_brief)")
        self.logger.info(f"Date: {date}, Stories: {len(content.items)}")
        self.logger.info(f"Model: {self.config.get('llm', {}).get('model', 'unknown')}")
        self.logger.info(f"Expected LLM calls: R1a={len(content.items)} + R2={len(content.items)} = {len(content.items) * 2}")
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
                        emotion="energetic"
                    )
                ]
            )

        script = self.script_writer.write(content)
        self.script_writer.save_script(script, date)
        return script

    def _step_tts(self, script: Script, date: str, content=None) -> Script:
        self.logger.info("Step: Synthesize audio")
        if self.dry_run:
            self.logger.info("Dry run: skipping TTS")
            for seg in script.segments:
                seg.actual_duration = seg.estimated_duration
                seg.audio_path = ""
            self._timing.compute_timeline(script)
            return script

        script = self.tts_processor.process_audio(script, date, content)
        self.script_writer.save_script(script, date)
        return script

    def _step_preview(self, script: Script, date: str, content = None) -> None:
        self.logger.info("Step: Preview (Remotion Studio)")
        if self.dry_run:
            self.logger.info("Dry run: skipping preview")
            return

        if content is None:
            try:
                content = self.content_preparer.load_content(date)
            except FileNotFoundError:
                self.logger.info("Content not found for preview, scene elements may be incomplete")

        audio_dir = f"data/{date}/audio"
        self.logger.info("Opening Remotion Studio at http://localhost:3000")
        self.logger.info("Check the preview, then press Ctrl+C to stop and proceed to render.")
        self.renderer.preview(script, audio_dir, content)

    def _step_render(self, script: Script, date: str, content = None) -> None:
        self.logger.info("Step: Render video")
        if self.dry_run:
            self.logger.info("Dry run: skipping render")
            return

        if content is None:
            try:
                content = self.content_preparer.load_content(date)
            except FileNotFoundError:
                self.logger.info("Content not found for render, scene elements may be incomplete")

        output_path = f"data/{date}/output.mp4"
        audio_dir = f"data/{date}/audio"
        self.renderer.render(script, audio_dir, output_path, content, date=date)
