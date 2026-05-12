import re
from typing import Any, Dict, List

from src.core.models import WordTiming


def build_cues(segment: "ScriptSegment", duration: float, logger) -> List[Dict[str, Any]]:
    """Build subtitle cues from TTS word timings or auto-split.

    Priority: real TTS word_timings > auto-split by punctuation.
    """
    word_timings_raw = segment.meta.get("word_timings", [])
    if word_timings_raw:
        word_timings = [
            WordTiming(text=wt["text"], start_time=wt["start_time"], end_time=wt["end_time"])
            for wt in word_timings_raw
        ]
        timing_level = segment.meta.get("timing_level", "word")
        logger.debug(
            f"Using real TTS timings: {timing_level} level, {len(word_timings)} timings"
        )
        if timing_level == "sentence":
            return _build_cues_from_sentence_timings(word_timings, duration)
        else:
            return _build_cues_from_word_timings(word_timings, duration)

    logger.debug(f"Using auto-split cues: duration={duration:.2f}s")
    return _split_into_cues(segment.audio_text, duration)


def _build_cues_from_sentence_timings(
    sentence_timings: List["WordTiming"], duration: float
) -> List[Dict[str, Any]]:
    if not sentence_timings:
        return []

    cues: List[Dict[str, Any]] = []
    for st in sentence_timings:
        cues.append({
            "text": st.text,
            "start_time": round(st.start_time, 3),
            "end_time": round(st.end_time, 3),
        })

    if cues:
        cues[0]["start_time"] = 0.0
        cues[-1]["end_time"] = duration

    return cues


def _build_cues_from_word_timings(
    word_timings: List["WordTiming"], duration: float
) -> List[Dict[str, Any]]:
    if not word_timings:
        return []

    sentence_breaks = set("。！？.!?")
    clause_breaks = set("，,、：:;；")

    cues: List[Dict[str, Any]] = []
    current_words: List["WordTiming"] = []
    current_text_parts: List[str] = []

    def flush():
        if not current_words:
            return
        text = "".join(current_text_parts)
        cues.append({
            "text": text,
            "start_time": round(current_words[0].start_time, 3),
            "end_time": round(current_words[-1].end_time, 3),
        })

    for wt in word_timings:
        current_words.append(wt)
        current_text_parts.append(wt.text)

        last_char = wt.text[-1] if wt.text else ""
        if last_char in sentence_breaks:
            flush()
            current_words = []
            current_text_parts = []
        elif last_char in clause_breaks and len("".join(current_text_parts)) > 20:
            flush()
            current_words = []
            current_text_parts = []

    if current_words:
        flush()

    if cues:
        cues[0]["start_time"] = 0.0
        cues[-1]["end_time"] = duration

    return cues


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
