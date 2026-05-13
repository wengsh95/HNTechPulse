from src.core.models import Script
from src.utils.logger import setup_logger


class TimingEngine:

    def __init__(self, segment_gap: float = 0.0, story_gap: float = 0.0,
                 debug: bool = False, level=None):
        self.segment_gap = segment_gap
        self.story_gap = story_gap
        self.logger = setup_logger(__name__, debug=debug, level=level)

    def compute_timeline(self, script: Script) -> Script:
        current_time = 0.0
        for i, seg in enumerate(script.segments):
            if seg.actual_duration is None:
                seg.actual_duration = seg.estimated_duration

            if i > 0:
                gap = self.story_gap if seg.segment_type == "story_scan" else self.segment_gap
                current_time += gap

            seg.start_time = current_time
            seg.end_time = current_time + seg.actual_duration
            current_time = seg.end_time

        script.total_duration = current_time
        return script

    def set_scene_element_times(self, script: Script) -> None:
        """Set scene_element start_time/end_time based on actual audio duration.

        Falls back to proportional layout using sub_segment_estimated_durations.
        """
        for seg in script.segments:
            if seg.segment_type == "dashboard":
                # Dashboard has a single dashboard_card spanning the full segment duration.
                # No per-element timing needed — the card uses segment start/end directly.
                duration = seg.actual_duration or seg.estimated_duration
                for elem in seg.scene_elements:
                    elem.start_time = 0.0
                    elem.end_time = duration
                continue

            if seg.segment_type == "story_scan":
                elem_durations = [
                    elem.props.get("audio_duration")
                    for elem in seg.scene_elements
                ]
                if any(d is not None for d in elem_durations):
                    current = 0.0
                    for elem, dur in zip(seg.scene_elements, elem_durations):
                        d = dur if dur is not None else 0.0
                        elem.start_time = current
                        elem.end_time = current + d
                        current += d
                    continue

            duration = seg.actual_duration or seg.estimated_duration
            if duration <= 0:
                continue

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
