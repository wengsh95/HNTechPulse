from pathlib import Path
from typing import List, Optional

from src.core.interfaces import ContentFetcher, LLMProvider
from src.core.models import Script, ScriptSegment
from src.pipeline.content_preparer import ContentPreparer
from src.pipeline.script_writer import ScriptWriter
from src.pipeline.timing_engine import TimingEngine
from src.pipeline.translation_manager import TranslationManager
from src.pipeline.comment_analyzer import CommentAnalyzer
from src.pipeline.comment_judge import CommentJudge
from src.pipeline.prefilter import Prefilter
from src.pipeline.html_generator import HtmlGenerator
from src.utils.logger import setup_logger


class Orchestrator:
    def __init__(
        self,
        config: dict,
        content_fetcher: ContentFetcher,
        llm_provider: LLMProvider,
        article_enricher=None,
        debug: bool = False,
        dry_run: bool = False,
    ):
        self.config = config
        self.content_fetcher = content_fetcher
        self.llm_provider = llm_provider
        self.article_enricher = article_enricher
        self.debug = debug
        self.dry_run = dry_run
        log_level = config.get("logging", {}).get("level")
        self.logger = setup_logger(__name__, debug=debug, level=log_level)

        self.content_preparer = ContentPreparer(config, debug=debug)
        self.script_writer = ScriptWriter(
            config, llm_provider, self.content_preparer, debug=debug
        )
        self.translation_manager = TranslationManager(
            llm_provider, self.content_preparer, config, debug=debug, level=log_level
        )
        self.comment_analyzer = CommentAnalyzer(config, debug=debug)
        self.comment_judge = CommentJudge(
            llm_provider, config, comment_analyzer=self.comment_analyzer, debug=debug
        )
        self.prefilter = Prefilter(llm_provider, config, debug=debug)
        self.html_generator = HtmlGenerator(debug=debug, level=log_level)
        timing_cfg = config.get("timing", {})
        self._timing = TimingEngine(
            segment_gap=float(timing_cfg.get("segment_gap", 0.0)),
            story_gap=float(timing_cfg.get("story_gap", 0.0)),
            debug=debug,
        )

    def run(self, date: str, steps: Optional[List[str]] = None) -> None:
        _ALL_STEPS = [
            "fetch",
            "enrich",
            "script",
            "translate",
            "html",
        ]

        if steps is None:
            steps = [s for s in _ALL_STEPS if s != "html"]
        else:
            _standalone = {
                "html",
            }
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
            if content and any(
                item.enrichment_source in ("fetch_failed", "extraction_failed")
                for item in content.items
                if item.enrichment_source not in ("skipped", "none", "manual_override")
            ):
                self.logger.warning(
                    "Some items could not be fetched automatically. "
                    "Continuing anyway..."
                )

        # ── script (analyze + script generation) ───────────────────
        if "script" in steps:
            script = self._step_script(content, date)
        else:
            try:
                script = self.script_writer.load_script(date)
            except FileNotFoundError:
                self.logger.info("Script not found, generating anyway...")
                script = self._step_script(content, date)

        # ── translate ─────────────────────────────────────────────
        if "translate" in steps:
            content, script = self._step_translate(content, script, date)

        # ── standalone steps ────────────────────────────────────────
        if "html" in steps:
            self._step_html(content, script, date)

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
                        estimated_duration=10.0,
                    )
                ],
            )

        script = self.script_writer.write(content)
        self.script_writer.save_script(script, date)
        return script

    def _step_translate(self, content, script, date: str):
        self.logger.info("Step: Translate titles and comments")
        if not self.dry_run:
            content, script = self.translation_manager.translate(content, script, date)
            self.script_writer.save_script(script, date)
        return content, script

    # ── Standalone Steps ──────────────────────────────────────────

    def _step_html(self, content, script, date: str) -> None:
        self.logger.info("Step: Generate HTML document")
        if self.dry_run:
            self.logger.info("Dry run: skipping HTML generation")
            return
        if content is None:
            try:
                content = self.content_preparer.load_content(date)
            except FileNotFoundError:
                self.logger.error("Content not found, cannot generate HTML")
                return
        if script is None:
            try:
                script = self.script_writer.load_script(date)
            except FileNotFoundError:
                self.logger.error("Script not found, cannot generate HTML")
                return
        self.html_generator.generate(content, script, date)
