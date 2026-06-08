import re
from typing import Any, Dict, List

from src.core.models import ScriptSegment


MAX_DISPLAY_CUE_CHARS = 28
MIN_MERGE_CUE_CHARS = 8


def build_cues(segment: ScriptSegment, duration: float, logger) -> List[Dict[str, Any]]:
    """Build subtitle cues.

    Priority: per-card cues (story_scan segments) > auto-split by sentence length.
    """
    if segment.cues:
        logger.debug(f"Using aligned cues: {len(segment.cues)} cues")
        return _normalize_existing_cues(segment.cues)

    logger.debug(f"Using auto-split cues: duration={duration:.2f}s")
    return _split_into_cues(segment.audio_text, duration)


def _normalize_existing_cues(cues) -> List[Dict[str, Any]]:
    """Keep aligned cue timing, but split any cue that is too long for display."""
    normalized: List[Dict[str, Any]] = []
    for cue in cues:
        text = str(cue.text or "").strip()
        start = float(cue.start_time or 0)
        end = float(cue.end_time or 0)
        duration = max(0.0, end - start)
        if not text or duration <= 0:
            continue

        parts = _split_text_for_display(text)
        if len(parts) <= 1:
            normalized.append({"text": text, "start_time": start, "end_time": end})
            continue

        total_chars = sum(len(part) for part in parts)
        current = start
        for part in parts:
            char_ratio = len(part) / total_chars if total_chars > 0 else 1.0 / len(parts)
            part_duration = duration * char_ratio
            normalized.append(
                {
                    "text": part,
                    "start_time": round(current, 3),
                    "end_time": round(current + part_duration, 3),
                }
            )
            current += part_duration
        normalized[-1]["end_time"] = end

    return normalized


def _split_into_cues(text: str, duration: float) -> List[Dict[str, Any]]:
    if not text or duration <= 0:
        return []

    text = re.sub(r"<[^>]+>", "", text).strip()
    if not text:
        return []

    final = _split_text_for_display(text)

    if not final:
        return [{"text": text, "start_time": 0.0, "end_time": duration}]

    total_chars = sum(len(s) for s in final)
    cues: List[Dict[str, Any]] = []
    current_time = 0.0
    for s in final:
        char_ratio = len(s) / total_chars if total_chars > 0 else 1.0 / len(final)
        cue_duration = duration * char_ratio
        cues.append(
            {
                "text": s,
                "start_time": round(current_time, 3),
                "end_time": round(current_time + cue_duration, 3),
            }
        )
        current_time += cue_duration

    if cues:
        cues[-1]["end_time"] = duration

    return cues


def _split_text_for_display(text: str) -> List[str]:
    text = re.sub(r"<[^>]+>", "", text).strip()
    if not text:
        return []

    sentences = re.split(r"(?<=[。！？；\.\!\?;])", text)
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return [text]

    merged: List[str] = []
    for s in sentences:
        if merged and len(merged[-1]) < MIN_MERGE_CUE_CHARS:
            merged[-1] = merged[-1] + s
        else:
            merged.append(s)

    final: List[str] = []
    for s in merged:
        if len(s) > MAX_DISPLAY_CUE_CHARS:
            parts = re.split(r"(?<=[，,、：:——-])", s)
            parts = [p.strip() for p in parts if p.strip()]
            buf = ""
            for part in parts:
                if len(part) > MAX_DISPLAY_CUE_CHARS:
                    if buf:
                        final.append(buf)
                        buf = ""
                    final.extend(_chunk_long_text(part, MAX_DISPLAY_CUE_CHARS))
                elif buf and len(buf) + len(part) > MAX_DISPLAY_CUE_CHARS:
                    final.append(buf)
                    buf = part
                else:
                    buf = buf + part
            if buf:
                final.append(buf)
        else:
            final.append(s)

    return final or [text]


def _chunk_long_text(text: str, max_chars: int) -> List[str]:
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]
