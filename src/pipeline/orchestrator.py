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

    def run(self, date: str, steps: Optional[List[str]] = None) -> None:
        if steps is None:
            steps = ["fetch", "enrich", "script", "translate", "tts", "render"]

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

        self.logger.info("Pipeline completed")

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
        return content

    def _step_translate(self, content, script, date: str):
        """Translate titles + referenced comments. Checkpointed.

        Runs after script generation so we know which comments are referenced
        in story cards. Updates both content (title_cn) and script (dashboard
        title_translation, viewpoint quote_cn) in place.
        """
        self.logger.info("Step: Translate titles and comments")
        if self.dry_run:
            self.logger.info("Dry run: skipping translation")
            return content, script

        translations_path = Path(f"data/{date}/translations.json")

        # Checkpoint: reuse cached translations
        if translations_path.exists():
            self.logger.info(f"  Loading cached translations from {translations_path}")
            with open(translations_path, "r", encoding="utf-8") as f:
                translations = json.load(f)
            for key, value in translations.items():
                if key.startswith("title_"):
                    idx = int(key.split("_", 1)[1])
                    if idx < len(content.items):
                        content.items[idx].title_cn = value
            self._apply_translations_to_script(script, content, translations)
            self.content_preparer.save_content(content, date)
            self.script_writer.save_script(script, date)
            return content, script

        # 1. Translate all titles
        content = self.llm_provider.translate_titles(content, "translate.md")

        # 2. Collect referenced comments from story_scan cards
        comment_refs = self._collect_comment_refs(script)

        # 3. Translate only the referenced comments
        comment_translations = {}
        if comment_refs:
            comment_translations = self.llm_provider.translate_comments(content, comment_refs)

        # 4. Build checkpoint and apply to script
        translations = {}
        for idx, item in enumerate(content.items):
            if item.title_cn:
                translations[f"title_{idx}"] = item.title_cn
        translations.update(comment_translations)

        if translations:
            translations_path.parent.mkdir(parents=True, exist_ok=True)
            with open(translations_path, "w", encoding="utf-8") as f:
                json.dump(translations, f, ensure_ascii=False, indent=2)
            self.logger.info(f"  Saved {len(translations)} translations to {translations_path}")

        self._apply_translations_to_script(script, content, translations)

        self.content_preparer.save_content(content, date)
        self.script_writer.save_script(script, date)

        return content, script

    @staticmethod
    def _collect_comment_refs(script) -> dict:
        """Collect {key: quote_text} from story_scan viewpoints.

        Keys are "comment_{story_idx}_{comment_idx}", values are the LLM-extracted
        quote snippets (≤50 chars English) that need translation.
        """
        refs = {}
        for seg in script.segments:
            if seg.segment_type != "story_scan":
                continue
            for elem in seg.scene_elements:
                if elem.element_type != "story_scan_card":
                    continue
                story_idx = elem.props.get("story_index")
                if story_idx is None:
                    continue
                for vp in elem.props.get("viewpoints", []):
                    ci = vp.get("comment_index")
                    quote = vp.get("quote", "")
                    if ci is not None and quote:
                        key = f"comment_{story_idx}_{ci}"
                        refs[key] = quote
        return refs

    @staticmethod
    def _apply_translations_to_script(script, content, translations: dict) -> None:
        """Apply translations to script: dashboard title_cn and viewpoint quote_cn."""
        for seg in script.segments:
            if seg.segment_type == "dashboard":
                for elem in seg.scene_elements:
                    if elem.element_type == "dashboard_card":
                        for entry in elem.props.get("entries", []):
                            story_idx = entry.get("story_index")
                            if story_idx is not None and story_idx < len(content.items):
                                entry["title_translation"] = content.items[story_idx].title_cn
            elif seg.segment_type == "story_scan":
                for elem in seg.scene_elements:
                    if elem.element_type == "story_scan_card":
                        story_idx = elem.props.get("story_index")
                        for vp in elem.props.get("viewpoints", []):
                            ci = vp.get("comment_index")
                            if ci is not None and story_idx is not None:
                                key = f"comment_{story_idx}_{ci}"
                                if key in translations:
                                    vp["quote_cn"] = translations[key]

    def _step_script(self, content, date: str):
        self.logger.info("=" * 50)
        self.logger.info("Step: Generate script (daily_brief)")
        self.logger.info(f"Date: {date}, Stories: {len(content.items)}")
        self.logger.info(f"Model: {self.config.get('llm', {}).get('model', 'unknown')}")
        self.logger.info(f"Expected LLM calls: R1a={len(content.items)} + R2={len(content.items)} = {len(content.items) * 2}")
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

            # Dashboard visual needs to be longer than its short narration audio
            if segment.segment_type == "dashboard":
                segment.actual_duration = max(segment.estimated_duration, result.duration)
            segment.audio_path = audio_path

            if result.word_timings:
                segment.meta["word_timings"] = [
                    {"text": wt.text, "start_time": wt.start_time, "end_time": wt.end_time}
                    for wt in result.word_timings
                ]
                segment.meta["timing_level"] = result.timing_level

        self._compute_timeline(script)
        self._set_scene_element_times(script)
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

    def _set_scene_element_times(self, script: Script) -> None:
        """Set scene_element start_time/end_time based on actual audio duration.

        For combined segments (story_scan) with word_timings and
        sub_segment_char_ranges, each element's times are derived from the
        actual TTS word timings that fall within its sub-segment's char range.
        Falls back to proportional layout when word_timings are unavailable.
        """
        for seg in script.segments:
            # Dashboard has a fixed visual duration longer than its short narration audio;
            # skip time remapping so element start/end stay as set in script_writer.
            if seg.segment_type == "dashboard":
                continue
            duration = seg.actual_duration or seg.estimated_duration
            if duration <= 0:
                continue

            char_ranges = seg.meta.get("sub_segment_char_ranges")
            word_timings_raw = seg.meta.get("word_timings", [])

            if char_ranges and word_timings_raw and seg.scene_elements:
                # Index-based: map each sub-segment's char range to its
                # actual time span in word_timings.
                sub_times = self._map_char_ranges_to_times(
                    seg.audio_text, char_ranges, word_timings_raw, duration
                )
                for i, elem in enumerate(seg.scene_elements):
                    idx = elem.sub_segment_index if elem.sub_segment_index is not None else i
                    if idx < len(sub_times):
                        elem.start_time = sub_times[idx][0]
                        elem.end_time = sub_times[idx][1]
                    else:
                        elem.start_time = 0.0
                        elem.end_time = duration
            elif word_timings_raw and seg.scene_elements:
                # char_ranges missing (e.g. loaded from cache) but we have
                # word_timings — synthesize char_ranges from audio_text length
                # and sub_segment_estimated_durations so we can still map to
                # real TTS times instead of doing a naive proportional split.
                sub_est = seg.meta.get("sub_segment_estimated_durations")
                n = len(seg.scene_elements)
                if sub_est and n > 0 and seg.audio_text:
                    total_est = sum(sub_est)
                    text_len = len(seg.audio_text)
                    synthetic_ranges = []
                    char_offset = 0
                    for est in sub_est[:n]:
                        share = est / total_est if total_est > 0 else 1.0 / n
                        char_end = min(text_len, char_offset + int(round(share * text_len)))
                        if char_end <= char_offset:
                            char_end = char_offset + 1
                        synthetic_ranges.append((char_offset, char_end))
                        char_offset = char_end
                    # Pin last range to end of text
                    if synthetic_ranges:
                        synthetic_ranges[-1] = (synthetic_ranges[-1][0], text_len)
                    sub_times = self._map_char_ranges_to_times(
                        seg.audio_text, synthetic_ranges, word_timings_raw, duration
                    )
                    for i, elem in enumerate(seg.scene_elements):
                        idx = elem.sub_segment_index if elem.sub_segment_index is not None else i
                        if idx < len(sub_times):
                            elem.start_time = sub_times[idx][0]
                            elem.end_time = sub_times[idx][1]
                        else:
                            elem.start_time = 0.0
                            elem.end_time = duration
                else:
                    # No estimated durations — synthesize even-char split
                    # from audio_text so we can still leverage TTS word_timings
                    # for per-element alignment (better than even time split).
                    if n > 0 and seg.audio_text:
                        text_len = len(seg.audio_text)
                        chars_per = text_len // n
                        synthetic_ranges = []
                        char_offset = 0
                        for i in range(n):
                            ce = char_offset + (chars_per if i < n - 1 else text_len - char_offset)
                            if ce <= char_offset:
                                ce = char_offset + 1
                            synthetic_ranges.append((char_offset, ce))
                            char_offset = ce
                        sub_times = self._map_char_ranges_to_times(
                            seg.audio_text, synthetic_ranges, word_timings_raw, duration
                        )
                        for i, elem in enumerate(seg.scene_elements):
                            idx = elem.sub_segment_index if elem.sub_segment_index is not None else i
                            if idx < len(sub_times):
                                elem.start_time = sub_times[idx][0]
                                elem.end_time = sub_times[idx][1]
                            else:
                                elem.start_time = 0.0
                                elem.end_time = duration
                    else:
                        for i, elem in enumerate(seg.scene_elements):
                            per = duration / n if n > 0 else duration
                            elem.start_time = i * per
                            elem.end_time = (i + 1) * per
            else:
                # No word_timings at all — proportional layout by estimated durations
                sub_est = seg.meta.get("sub_segment_estimated_durations")
                if sub_est and len(seg.scene_elements) > 0:
                    total_est = sum(sub_est)
                    if total_est <= 0:
                        n = len(seg.scene_elements)
                        per = duration / n if n > 0 else duration
                        for i, elem in enumerate(seg.scene_elements):
                            elem.start_time = i * per
                            elem.end_time = (i + 1) * per
                    else:
                        offset = 0.0
                        for est, elem in zip(sub_est, seg.scene_elements):
                            actual = est * duration / total_est
                            elem.start_time = offset
                            elem.end_time = offset + actual
                            offset += actual
                        for i in range(len(sub_est), len(seg.scene_elements)):
                            seg.scene_elements[i].start_time = offset
                            seg.scene_elements[i].end_time = duration
                else:
                    for elem in seg.scene_elements:
                        elem.start_time = 0.0
                        elem.end_time = duration

    @staticmethod
    def _map_char_ranges_to_times(
        audio_text: str,
        char_ranges: list,
        word_timings_raw: list,
        duration: float,
    ) -> list:
        """Map sub-segment char ranges to (start_time, end_time) from word_timings.

        Each word_timing has a cumulative char offset derived from its text
        position in audio_text. We assign each word to the sub-segment whose
        char range contains it, then derive per-sub-segment time spans.
        """
        # Build a list of (char_offset, start_time, end_time) for each word.
        # Use str.find() to locate each word's actual position in audio_text.
        # Cumulative len() would drift because edge_tts word tokens omit spaces
        # and other characters present in the original text.
        word_entries = []
        search_pos = 0
        for wt in word_timings_raw:
            text = wt.get("text", "")
            idx = audio_text.find(text, search_pos)
            if idx >= 0:
                word_entries.append((idx, wt["start_time"], wt["end_time"]))
                search_pos = idx + len(text)
            else:
                # Word not in audio_text (edge_tts normalization) — fall back
                word_entries.append((search_pos, wt["start_time"], wt["end_time"]))
                search_pos += len(text)

        if not word_entries:
            # No timings: fall back to even split
            n = len(char_ranges)
            per = duration / n if n > 0 else duration
            return [(i * per, (i + 1) * per) for i in range(n)]

        # For each sub-segment, find the first and last word that falls
        # within its char range.
        sub_times = []
        for cs, ce in char_ranges:
            first_time = None
            last_time = None
            for char_off, st, et in word_entries:
                if cs <= char_off < ce:
                    if first_time is None:
                        first_time = st
                    last_time = et
            if first_time is None:
                # No words in this range — placeholder, will be filled below
                sub_times.append((0.0, 0.0))
            else:
                sub_times.append((first_time, last_time))

        # Handle zero-duration entries: fall back to proportional split
        n = len(char_ranges)
        per = duration / n if n > 0 else duration
        for i in range(len(sub_times)):
            if sub_times[i][0] == 0.0 and sub_times[i][1] == 0.0:
                sub_times[i] = (i * per, (i + 1) * per)

        # Pin first/last to segment boundaries
        if sub_times:
            sub_times[0] = (0.0, sub_times[0][1])
            if sub_times[-1][1] < duration:
                sub_times[-1] = (sub_times[-1][0], duration)

        # Fill visual gaps by extending the previous card, not pulling the
        # next card forward.  Preserves real TTS start times so cards don't
        # appear before their audio.
        for i in range(1, len(sub_times)):
            if sub_times[i][0] > sub_times[i - 1][1]:
                sub_times[i - 1] = (sub_times[i - 1][0], sub_times[i][0])

        return sub_times

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
