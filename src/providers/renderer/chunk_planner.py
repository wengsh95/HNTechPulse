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
    chunks = [(start, end, label) for start, end, label in chunks if start < end]

    # Extend last chunk to cover total_frames
    if chunks:
        last_start, last_end, last_label = chunks[-1]
        if last_end < total_frames - 1:
            chunks[-1] = (last_start, total_frames - 1, last_label)

    return chunks


def compute_segment_chunks_seconds(
    script: Script, total_duration: float
) -> List[Tuple[float, float, str]]:
    """Same as compute_segment_chunks but returns seconds directly.

    Returns list of (start_sec, end_sec, label) tuples. Use this when you
    need chunk boundaries in seconds (e.g. for filtering scene_spec JSON
    where the HyperFrames renderer stores times as seconds).
    """
    if total_duration <= 0:
        return []

    chunks_sec: List[Tuple[float, float, str]] = []
    story_idx = 0

    for seg in script.segments:
        seg_start = float(seg.start_time or 0)
        seg_end = float(seg.end_time or 0)

        if seg.segment_type == "story_scan" and seg.scene_elements:
            for elem in seg.scene_elements:
                abs_start = seg_start + float(elem.start_time or 0)
                abs_end = seg_start + float(elem.end_time or 0)
                if abs_start < abs_end:
                    chunks_sec.append((abs_start, abs_end, f"story_{story_idx}"))
                story_idx += 1
        else:
            if seg_end > seg_start:
                chunks_sec.append((seg_start, seg_end, seg.segment_type or "segment"))

    # Align boundaries: each chunk ends exactly at the next chunk's start
    for i in range(len(chunks_sec) - 1):
        next_start = chunks_sec[i + 1][0]
        chunks_sec[i] = (chunks_sec[i][0], next_start, chunks_sec[i][2])

    # Drop zero-length chunks
    chunks_sec = [(s, e, lbl) for s, e, lbl in chunks_sec if e > s]

    # Extend last chunk to cover total_duration
    if chunks_sec:
        last_start, last_end, last_label = chunks_sec[-1]
        if last_end < total_duration:
            chunks_sec[-1] = (last_start, total_duration, last_label)

    return chunks_sec
