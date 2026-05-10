from typing import List

from src.core.models import Script
from src.utils.logger import setup_logger


class TimingEngine:

    def __init__(self, debug: bool = False, level=None):
        self.logger = setup_logger(__name__, debug=debug, level=level)

    def compute_timeline(self, script: Script) -> Script:
        current_time = 0.0
        for seg in script.segments:
            if seg.actual_duration is None:
                seg.actual_duration = seg.estimated_duration

            seg.start_time = current_time
            seg.end_time = current_time + seg.actual_duration
            current_time = seg.end_time

        script.total_duration = current_time
        return script

    def set_scene_element_times(self, script: Script) -> None:
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
                sub_times = self.map_char_ranges_to_times(
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
                    if synthetic_ranges:
                        synthetic_ranges[-1] = (synthetic_ranges[-1][0], text_len)
                    sub_times = self.map_char_ranges_to_times(
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
                        sub_times = self.map_char_ranges_to_times(
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
    def map_char_ranges_to_times(
        audio_text: str,
        char_ranges: list,
        word_timings_raw: list,
        duration: float,
    ) -> list:
        """Map sub-segment char ranges to (start_time, end_time) from word_timings."""
        word_entries = []
        search_pos = 0
        for wt in word_timings_raw:
            text = wt.get("text", "")
            idx = audio_text.find(text, search_pos)
            if idx >= 0:
                word_entries.append((idx, wt["start_time"], wt["end_time"]))
                search_pos = idx + len(text)
            else:
                word_entries.append((search_pos, wt["start_time"], wt["end_time"]))
                search_pos += len(text)

        if not word_entries:
            n = len(char_ranges)
            per = duration / n if n > 0 else duration
            return [(i * per, (i + 1) * per) for i in range(n)]

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
                sub_times.append((0.0, 0.0))
            else:
                sub_times.append((first_time, last_time))

        n = len(char_ranges)
        per = duration / n if n > 0 else duration
        for i in range(len(sub_times)):
            if sub_times[i][0] == 0.0 and sub_times[i][1] == 0.0:
                sub_times[i] = (i * per, (i + 1) * per)

        if sub_times:
            sub_times[0] = (0.0, sub_times[0][1])
            if sub_times[-1][1] < duration:
                sub_times[-1] = (sub_times[-1][0], duration)

        for i in range(1, len(sub_times)):
            if sub_times[i][0] > sub_times[i - 1][1]:
                sub_times[i - 1] = (sub_times[i - 1][0], sub_times[i][0])

        return sub_times

    def validate_segment_duration(self, script: Script) -> list:
        """Flag segments where actual_duration is significantly shorter than estimated."""
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
