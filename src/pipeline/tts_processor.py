import json
import re
from collections import Counter
from pathlib import Path

from src.core.interfaces import TTSProvider, TTSResult
from src.core.models import Script, ScriptSegment, WordTiming
from src.pipeline.timing_engine import TimingEngine
from src.utils.logger import setup_logger
from src.utils.audio import get_audio_duration


class TTSProcessor:
    def __init__(self, tts_provider: TTSProvider, config: dict, debug: bool = False, level=None):
        self.tts_provider = tts_provider
        self.config = config
        self.timing_engine = TimingEngine(debug=debug, level=level)
        self.logger = setup_logger(__name__, debug=debug, level=level)

    def process_audio(self, script: Script, date: str, content=None) -> Script:
        """Synthesize audio for all segments, compute timings, validate."""
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

            cached_result = self._load_cached_tts(audio_path, timings_path)

            if cached_result is not None:
                if not self._validate_tts_consistency(segment, cached_result, idx):
                    self.logger.info(f"  Re-synthesizing segment {idx} due to text mismatch...")
                    Path(audio_path).unlink(missing_ok=True)
                    Path(timings_path).unlink(missing_ok=True)
                    result = self._synthesize_and_save(segment, audio_path, timings_path)
                else:
                    result = cached_result
            elif Path(audio_path).exists():
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

        self.timing_engine.compute_timeline(script)
        self.timing_engine.set_scene_element_times(script)
        self.timing_engine.validate_segment_duration(script)
        return script

    def _load_cached_tts(self, audio_path: str, timings_path: str) -> TTSResult | None:
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

    def _validate_tts_consistency(
        self,
        segment: ScriptSegment,
        result: TTSResult,
        idx: int
    ) -> bool:
        if not result.word_timings:
            return True

        timings_text = "".join(wt.text for wt in result.word_timings)

        def _normalize(s: str) -> str:
            return re.sub(r'[\s　，。？！""''；．]', '', s)

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
