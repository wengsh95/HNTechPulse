import re
from typing import Any, Dict, List


def build_cues(segment: "ScriptSegment", duration: float, logger) -> List[Dict[str, Any]]:
    """Build subtitle cues.

    Priority: per-card cues (story_scan segments) > auto-split by sentence length.
    """
    if segment.cues:
        logger.debug(f"Using per-card cues: {len(segment.cues)} cues")
        return [
            {"text": c.text, "start_time": c.start_time, "end_time": c.end_time}
            for c in segment.cues
        ]

    logger.debug(f"Using auto-split cues: duration={duration:.2f}s")
    return _split_into_cues(segment.audio_text, duration)


def _split_into_cues(text: str, duration: float) -> List[Dict[str, Any]]:
    if not text or duration <= 0:
        return []

    text = re.sub(r'<[^>]+>', '', text).strip()
    if not text:
        return []

    sentences = re.split(r'(?<=[。！？；\.\!\?;])', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return [{"text": text, "start_time": 0.0, "end_time": duration}]

    merged: List[str] = []
    for s in sentences:
        if merged and len(merged[-1]) < 8:
            merged[-1] = merged[-1] + s
        else:
            merged.append(s)

    final: List[str] = []
    for s in merged:
        if len(s) > 40:
            parts = re.split(r'(?<=[，,、：:])', s)
            parts = [p.strip() for p in parts if p.strip()]
            buf = ""
            for part in parts:
                if buf and len(buf) + len(part) > 40:
                    final.append(buf)
                    buf = part
                else:
                    buf = buf + part
            if buf:
                final.append(buf)
        else:
            final.append(s)

    if not final:
        return [{"text": text, "start_time": 0.0, "end_time": duration}]

    total_chars = sum(len(s) for s in final)
    cues: List[Dict[str, Any]] = []
    current_time = 0.0
    for s in final:
        char_ratio = len(s) / total_chars if total_chars > 0 else 1.0 / len(final)
        cue_duration = duration * char_ratio
        cues.append({
            "text": s,
            "start_time": round(current_time, 3),
            "end_time": round(current_time + cue_duration, 3),
        })
        current_time += cue_duration

    if cues:
        cues[-1]["end_time"] = duration

    return cues
