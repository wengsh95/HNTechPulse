import math
from typing import List, Tuple

from src.core.models import Script


def compute_segment_chunks(
    script: Script, fps: int, total_frames: int
) -> List[Tuple[int, int, str]]:
    """Compute per-segment chunk boundaries for rendering.

    Returns list of (start_frame, end_frame, label) tuples.
    story_scan segments are split into one chunk per scene_element.
    """
    chunks: List[Tuple[int, int, str]] = []
    story_idx = 0

    for seg in script.segments:
        seg_start = seg.start_time or 0
        seg_end = seg.end_time or 0

        if seg.segment_type == "story_scan" and seg.scene_elements:
            for elem in seg.scene_elements:
                abs_start = seg_start + (elem.start_time or 0)
                abs_end = seg_start + (elem.end_time or 0)
                start_f = math.floor(abs_start * fps)
                end_f = min(math.ceil(abs_end * fps), total_frames - 1)
                if start_f < end_f:
                    chunks.append((start_f, end_f, f"story_{story_idx}"))
                story_idx += 1
        else:
            start_f = math.floor(seg_start * fps)
            end_f = min(math.ceil(seg_end * fps), total_frames - 1)
            if start_f < end_f:
                chunks.append((start_f, end_f, seg.segment_type))

    # Align boundaries: each chunk ends exactly one frame before the next starts
    for i in range(len(chunks) - 1):
        next_start = chunks[i + 1][0]
        chunks[i] = (chunks[i][0], next_start - 1, chunks[i][2])

    # Discard any chunk where start >= end (can happen when adjacent elements
    # overlap or share the same start frame)
    chunks = [(s, e, l) for s, e, l in chunks if s < e]

    # Extend last chunk to cover total_frames
    if chunks:
        last_start, last_end, last_label = chunks[-1]
        if last_end < total_frames - 1:
            chunks[-1] = (last_start, total_frames - 1, last_label)

    return chunks
