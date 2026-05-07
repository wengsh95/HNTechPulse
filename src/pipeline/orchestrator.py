import json
import re
from collections import Counter
from pathlib import Path
from typing import List, Optional
from dataclasses import asdict

from src.core.interfaces import ContentFetcher, LLMProvider, TTSProvider, Renderer, TTSResult
from src.core.models import Script, ScriptSegment, WordTiming
from src.pipeline.content_preparer import ContentPreparer
from src.pipeline.script_writer import ScriptWriter
from src.utils.logger import setup_logger
from src.utils.audio import get_audio_duration


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

    def run(self, date: str, steps: Optional[List[str]] = None, prompt_template: str = "", product: str = "full") -> None:
        if steps is None:
            steps = ["fetch", "enrich", "script", "tts", "render"]

        self.logger.info(f"Running pipeline, date={date}, steps={steps}, product={product}")

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
            script = self._step_script(content, prompt_template, date, product)
        else:
            try:
                script = self.script_writer.load_script(date)
            except FileNotFoundError:
                self.logger.info("Script not found, generating anyway...")
                script = self._step_script(content, prompt_template, date, product)

        if "tts" in steps:
            script = self._step_tts(script, date, content, product)

        if "preview" in steps:
            self._step_preview(script, date, content)

        if "render" in steps:
            self._step_render(script, date, content)

        # Save transcript with product-specific format
        if script and ("script" in steps or "tts" in steps):
            self.script_writer.save_transcript(script, date, content, product)

        self.logger.info("Pipeline completed")

    def _step_fetch(self, date: str):
        self.logger.info("Step: Fetch content")
        if self.dry_run:
            self.logger.info("Dry run: skipping fetch")
            from src.core.models import ContentPackage, ContentItem
            return ContentPackage(date=date, items=[])

        pipeline_cfg = self.config.get("pipeline", {})
        content = self.content_fetcher.fetch(
            date,
            num_deep_dive=pipeline_cfg.get("num_deep_dive", 1),
            num_brief=pipeline_cfg.get("num_brief", 2),
            num_quick_news=pipeline_cfg.get("num_quick_news", 7),
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
        return content

    def _step_script(self, content, prompt_template: str, date: str, product: str = "full"):
        self.logger.info("=" * 50)
        self.logger.info(f"Step: Generate script (product={product})")
        self.logger.info(f"Date: {date}, Stories: {len(content.items)}")
        self.logger.info(f"Model: {self.config.get('llm', {}).get('model', 'unknown')}")
        self.logger.info(f"Expected LLM calls: R1a={len(content.items)} + R1b=1 + R2=1 = {len(content.items) + 2}")
        self.logger.info("=" * 50)

        if self.dry_run:
            self.logger.info("Dry run: skipping script generation")
            from src.core.models import Script, ScriptSegment
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

        script = self.script_writer.write(content, prompt_template, product)
        self.script_writer.save_script(script, date)
        return script

    def _step_tts(self, script: Script, date: str, content=None, product: str = "full") -> Script:
        self.logger.info("Step: Synthesize audio")
        if self.dry_run:
            self.logger.info("Dry run: skipping TTS")
            for seg in script.segments:
                seg.actual_duration = seg.estimated_duration
                seg.audio_path = ""
            self._compute_timeline(script)
            return script

        audio_dir = Path(f"data/{date}/audio")
        audio_dir.mkdir(parents=True, exist_ok=True)

        for idx, segment in enumerate(script.segments):
            audio_path = str(audio_dir / f"segment_{idx:02d}.mp3")
            timings_path = str(audio_dir / f"segment_{idx:02d}_timings.json")

            if not (segment.audio_text or "").strip():
                self.logger.info(
                    f"  Skipping segment {idx} [{segment.segment_type}]: audio_text is empty"
                )
                Path(audio_path).unlink(missing_ok=True)
                Path(timings_path).unlink(missing_ok=True)
                segment.actual_duration = 0.0
                segment.audio_path = ""
                continue

            # Try loading cached audio + timings
            cached_result = self._load_cached_tts(audio_path, timings_path)

            if cached_result is not None:
                # Validate cached timings match current audio_text
                if not self._validate_tts_consistency(segment, cached_result, idx):
                    self.logger.info(f"  Re-synthesizing segment {idx} due to text mismatch...")
                    Path(audio_path).unlink(missing_ok=True)
                    Path(timings_path).unlink(missing_ok=True)
                    result = self._synthesize_and_save(segment, audio_path, timings_path)
                else:
                    result = cached_result
            elif Path(audio_path).exists():
                # Audio exists but no timings — must re-synthesize
                self.logger.debug(f"Audio exists but no timings, cannot validate - re-synthesizing: {audio_path}")
                Path(audio_path).unlink(missing_ok=True)
                self.logger.info(f"Synthesizing segment {idx}/{len(script.segments)}...")
                result = self._synthesize_and_save(segment, audio_path, timings_path)
            else:
                self.logger.info(f"Synthesizing segment {idx}/{len(script.segments)}...")
                result = self._synthesize_and_save(segment, audio_path, timings_path)

            segment.actual_duration = result.duration
            segment.audio_path = audio_path

            if result.word_timings:
                segment.meta["word_timings"] = [
                    {"text": wt.text, "start_time": wt.start_time, "end_time": wt.end_time}
                    for wt in result.word_timings
                ]
                segment.meta["timing_level"] = result.timing_level

        self._compute_timeline(script)
        self._validate_segment_duration(script)
        self.script_writer.save_script(script, date)
        return script

    def _load_cached_tts(self, audio_path: str, timings_path: str) -> TTSResult | None:
        """Load cached TTS result from disk. Returns None if not cached."""
        if not (Path(audio_path).exists() and Path(timings_path).exists()):
            return None

        self.logger.debug(f"Audio exists, loading: {audio_path}")
        duration = get_audio_duration(audio_path)
        try:
            with open(timings_path, "r", encoding="utf-8") as f:
                timings_data = json.load(f)
            return TTSResult(
                duration=duration,
                word_timings=[
                    WordTiming(text=wt["text"], start_time=wt["start_time"], end_time=wt["end_time"])
                    for wt in timings_data.get("word_timings", [])
                ],
                timing_level=timings_data.get("timing_level", "word")
            )
        except (json.JSONDecodeError, FileNotFoundError, KeyError):
            self.logger.debug(f"Failed to load timings, using duration only")
            return TTSResult(duration=duration)

    def _synthesize_and_save(self, segment: ScriptSegment, audio_path: str, timings_path: str) -> TTSResult:
        """Synthesize audio for a segment and save timings to disk."""
        result = self.tts_provider.synthesize(
            segment.audio_text, audio_path, segment.emotion
        )
        if result.word_timings:
            with open(timings_path, "w", encoding="utf-8") as f:
                json.dump({
                    "word_timings": [
                        {"text": wt.text, "start_time": wt.start_time, "end_time": wt.end_time}
                        for wt in result.word_timings
                    ],
                    "timing_level": result.timing_level
                }, f, ensure_ascii=False, indent=2)
        return result

    def _step_preview(self, script: Script, date: str, content = None) -> None:
        """启动 Remotion Studio 预览，确认无误后用户 Ctrl+C 退出再执行 render"""
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

    def _compute_timeline(self, script: Script) -> Script:
        current_time = 0.0
        for seg in script.segments:
            if seg.actual_duration is None:
                seg.actual_duration = seg.estimated_duration

            seg.start_time = current_time
            seg.end_time = current_time + seg.actual_duration
            current_time = seg.end_time

        script.total_duration = current_time
        return script

    # ── Post-TTS validation ──

    def _validate_tts_consistency(
        self,
        segment: ScriptSegment,
        result: TTSResult,
        idx: int
    ) -> bool:
        """Check if word_timings text roughly matches audio_text.
        Returns True if consistent, False if mismatch detected."""
        if not result.word_timings:
            return True

        timings_text = "".join(wt.text for wt in result.word_timings)

        def _normalize(s: str) -> str:
            return re.sub(r'[\s　，。？！“”‘’；．]', '', s)

        norm_timings = _normalize(timings_text)
        norm_audio = _normalize(segment.audio_text)

        if not norm_timings or not norm_audio:
            return True

        def _bigrams(s: str) -> Counter:
            return Counter(s[i:i+2] for i in range(len(s)-1))

        bg_timings = _bigrams(norm_timings)
        bg_audio = _bigrams(norm_audio)

        if not bg_timings or not bg_audio:
            return True

        # Multiset intersection (respects repetition)
        overlap = sum((bg_timings & bg_audio).values())
        total = min(sum(bg_timings.values()), sum(bg_audio.values()))
        similarity = overlap / total if total > 0 else 0

        THRESHOLD = 0.6
        if similarity < THRESHOLD:
            self.logger.info(
                f"  TTS consistency check: segment {idx} [{segment.segment_type}] "
                f"similarity={similarity:.2f} < {THRESHOLD}, "
                f"will re-synthesize"
            )
            return False
        return True

    def _validate_segment_duration(self, script: Script) -> list:
        """Flag segments where actual_duration is significantly shorter than estimated.
        Returns list of (index, ratio) tuples for short segments."""
        RATIO_THRESHOLD = 0.6
        short_segments = []

        for idx, seg in enumerate(script.segments):
            if seg.actual_duration and seg.estimated_duration and seg.estimated_duration > 0:
                ratio = seg.actual_duration / seg.estimated_duration
                seg.meta["duration_ratio"] = round(ratio, 2)
                if ratio < RATIO_THRESHOLD and seg.segment_type not in ("opening", "closing", "dashboard"):
                    self.logger.info(
                        f"  Duration check: segment {idx} [{seg.segment_type}] "
                        f"actual={seg.actual_duration:.1f}s vs estimated={seg.estimated_duration:.1f}s "
                        f"(ratio={ratio:.2f} < {RATIO_THRESHOLD})"
                    )
                    short_segments.append((idx, ratio))

        if short_segments:
            total_actual = sum(s.actual_duration or 0 for s in script.segments)
            total_estimated = sum(s.estimated_duration for s in script.segments)
            self.logger.info(
                f"  {len(short_segments)} segments are significantly shorter than estimated. "
                f"Total actual: {total_actual:.1f}s vs estimated: {total_estimated:.1f}s. "
                f"Consider re-running script generation with stronger word count constraints."
            )

        return short_segments
