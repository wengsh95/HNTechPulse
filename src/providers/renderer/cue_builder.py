from typing import Any, Dict, List

from src.core.models import ScriptSegment


def build_cues(segment: ScriptSegment, duration: float, logger) -> List[Dict[str, Any]]:
    """Build subtitle cues.

    Subtitle segmentation is authored upstream by the LLM through
    ``subtitle_texts`` and then preserved by TTS alignment. The renderer should
    not guess sentence boundaries as a fallback, because punctuation in version
    numbers and product names is easy to split incorrectly.
    """
    if segment.cues:
        logger.debug(f"Using aligned cues: {len(segment.cues)} cues")
        return _normalize_existing_cues(segment.cues)

    logger.debug(f"Using whole-segment cue fallback: duration={duration:.2f}s")
    return _split_into_cues(segment.audio_text, duration)


def _normalize_existing_cues(cues) -> List[Dict[str, Any]]:
    """Sanitize existing cues without changing their authored boundaries."""
    normalized: List[Dict[str, Any]] = []
    for cue in cues:
        text = _strip_html(str(cue.text or "")).strip()
        start = float(cue.start_time or 0)
        end = float(cue.end_time or 0)
        if not text or end <= start:
            continue
        normalized.append({"text": text, "start_time": start, "end_time": end})
    return normalized


def _split_into_cues(text: str, duration: float) -> List[Dict[str, Any]]:
    if not text or duration <= 0:
        return []

    text = _strip_html(text).strip()
    if not text:
        return []

    return [{"text": text, "start_time": 0.0, "end_time": duration}]


def _strip_html(text: str) -> str:
    in_tag = False
    out: list[str] = []
    for ch in text:
        if ch == "<":
            in_tag = True
            continue
        if ch == ">":
            in_tag = False
            continue
        if not in_tag:
            out.append(ch)
    return "".join(out)
