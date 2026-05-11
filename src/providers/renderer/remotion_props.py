"""
Props serialization for Remotion renderer.

Converts Python Script dataclass → JSON props consumed by the React/Remotion
composition.  Handles cue building and element props expansion.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

from src.core.models import Script, ScriptSegment, WordTiming
from src.pipeline.comment_selection import (
    clean_comment_text,
    classify_comment_stance,
    select_representative_comments,
)
from src.utils.logger import setup_logger


def _is_remote_url(path: str) -> bool:
    return path.startswith(("http://", "https://"))


def _to_filename(path: str) -> str:
    """Extract bare filename from a local path or remote URL."""
    if _is_remote_url(path):
        return Path(urlparse(path).path).name
    return Path(path).name


def _safe_get_item(content, idx):
    """Return content.items[idx] if idx is a valid in-range int, else None."""
    if idx is None or not isinstance(idx, int):
        return None
    if 0 <= idx < len(content.items):
        return content.items[idx]
    return None


def _safe_get_comment(item, idx):
    """Return item.comments[idx] if idx is a valid in-range int, else None."""
    if idx is None or not isinstance(idx, int):
        return None
    if 0 <= idx < len(item.comments):
        return item.comments[idx]
    return None


# ── Element props expanders ──────────────────────────────────────────

def _expand_story_header(props, content):
    item = _safe_get_item(content, props.get("story_index"))
    if item is None:
        return None
    return {
        "story_title": item.title,
        "score": item.score or 0,
        "comments": item.comment_count or 0,
    }


def _expand_comment_card(props, content):
    item = _safe_get_item(content, props.get("story_index"))
    if item is None:
        return None
    comment = _safe_get_comment(item, props.get("comment_index"))
    if comment is None:
        return None
    return {
        "author": comment.author,
        "score": 0,
        "text": comment.content,
        "translation": "",
        "angle_label": "",
    }


def _expand_comment_bubble(props, content):
    item = _safe_get_item(content, props.get("story_index"))
    if item is None:
        return None
    comment = _safe_get_comment(item, props.get("comment_index"))
    if comment is None:
        return None
    return {
        "author": comment.author,
        "original_text": comment.content,
        "chinese_summary": "",
    }


def _expand_news_carousel_card(props, content):
    item = _safe_get_item(content, props.get("story_index"))
    if item is None:
        return None
    result = {
        "story_title": item.title,
        "score": item.score or 0,
        "comment_count": item.comment_count or 0,
        "author": "?",
        "comment_score": 0,
        "comment_text": "",
        "comment_translation": "",
    }
    comment = _safe_get_comment(item, props.get("comment_index"))
    if comment is not None:
        result["author"] = comment.author
        result["comment_text"] = comment.content
    return result


def _expand_dashboard_card(props, content):
    """Trust LLM entries, but overwrite per-entry title/score from content."""
    expanded_entries = []
    for entry in props.get("entries", []):
        expanded = dict(entry)
        item = _safe_get_item(content, entry.get("story_index"))
        if item is not None:
            expanded["original_title"] = item.title
            expanded["title_cn"] = item.title_cn or ""
            expanded["score"] = item.score or 0
            expanded["comment_count"] = item.comment_count or 0
        expanded_entries.append(expanded)
    return {"entries": expanded_entries}


def _expand_perspective_compare(props, content):
    def build_side(side):
        if not isinstance(side, dict) or "story_index" not in side or "comment_index" not in side:
            return side
        item = _safe_get_item(content, side.get("story_index"))
        if item is None:
            return side
        comment = _safe_get_comment(item, side.get("comment_index"))
        if comment is None:
            return side
        return {
            "label": side.get("label", ""),
            "text": comment.content,
            "translation": "",
        }

    return {
        "perspective_a": build_side(props.get("perspective_a", {})),
        "perspective_b": build_side(props.get("perspective_b", {})),
    }


def _expand_event_card(props, content):
    """Expand event_card element: inject story metadata, image, and keywords."""

    item = _safe_get_item(content, props.get("story_index"))
    if item is None:
        return props
    result = dict(props)
    result["story_title"] = item.title
    result["source_title"] = result.get("source_title") or item.title
    result["title_cn"] = item.title_cn or ""
    result["editor_angle"] = result.get("editor_angle") or item.title_cn or item.title
    result["event_summary"] = result.get("event_summary") or item.article_summary or item.summary or item.title_cn or item.title
    result["dek"] = result.get("dek") or result["event_summary"]
    result["key_points"] = result.get("key_points") or []
    result["why_it_matters"] = result.get("why_it_matters") or ""
    result["next_watch"] = result.get("next_watch") or ""


    # Image: support manual image_index; fall back to first local image
    image_index = props.get("image_index", 0)
    local_images = [p for p in item.article_images if not _is_remote_url(p)]
    if local_images:
        idx = max(0, min(image_index, len(local_images) - 1)) if isinstance(image_index, int) else 0
        result["image_src"] = f"images/{_to_filename(local_images[idx])}"
        result["image_type"] = "article"
    elif item.screenshot_image and not _is_remote_url(item.screenshot_image):
        result["image_src"] = f"images/{_to_filename(item.screenshot_image)}"
        result["image_type"] = "screenshot"
    elif item.logo_image and not _is_remote_url(item.logo_image):
        result["image_src"] = f"images/{_to_filename(item.logo_image)}"
        result["image_type"] = "logo"
    else:
        result["image_src"] = ""
        result["image_type"] = "article"

    # Pass through LLM keywords (set in prompt)
    if "keywords" not in result:
        result["keywords"] = []

    return result


def _expand_atmosphere_card(props, content):
    """Expand atmosphere_card: inject controversy score, ensure stance/distribution fields exist."""
    import math

    item = _safe_get_item(content, props.get("story_index"))
    if item is None:
        return props
    result = dict(props)

    # debate_focus is set by LLM in props, ensure default
    if "debate_focus" not in result:
        result["debate_focus"] = []

    # stance_distribution already set by LLM in props, just ensure it exists
    if "stance_distribution" not in result:
        result["stance_distribution"] = {}

    # Controversy score from heat/comment ratio
    score = item.score or 0
    descendants = item.comment_count or 0
    result["score"] = score
    result["comment_count"] = descendants
    if score > 0 and descendants >= 0:
        ratio = descendants / score
        capped = min(ratio, 5.0)
        if capped <= 0:
            controversy = 0.0
        else:
            controversy = min(10.0, math.log10(capped * 9 + 1) / math.log10(46) * 10)
        result["controversy_score"] = round(controversy, 1)
    else:
        result["controversy_score"] = 0.0

    return result


def _expand_quote_card(props, content):
    """Expand quote_card: inject representative comments across different stances."""
    item = _safe_get_item(content, props.get("story_index"))
    if item is None:
        return props
    result = dict(props)

    # Preserve text_cn from original LLM props (set by translation_manager)
    orig_text_cn = {}
    for q in props.get("quotes", []):
        cn = q.get("text_cn", "")
        if cn:
            orig_text_cn[q.get("text", "")] = cn

    # Prefer one high-quality comment per stance, with de-duplication.
    selected = select_representative_comments(item.comments, max_n=3)

    quotes = []
    for c in selected[:3]:
        stance = classify_comment_stance(c)
        text = clean_comment_text(c.content or "")[:300]
        text_cn = c.content_cn or orig_text_cn.get(text, "")
        quotes.append({
            "author": c.author,
            "text": text,
            "text_cn": text_cn,
            "stance": stance,
        })
    result["quotes"] = quotes
    result["next_watch"] = props.get("next_watch", "")

    return result


# Dispatch table: element_type -> expander function.
# Each expander returns an expanded props dict, or None to signal "leave props unchanged".
ELEMENT_EXPANDERS = {
    "story_header": _expand_story_header,
    "comment_card": _expand_comment_card,
    "comment_bubble": _expand_comment_bubble,
    "news_carousel_card": _expand_news_carousel_card,
    "dashboard_card": _expand_dashboard_card,
    "perspective_compare": _expand_perspective_compare,
    "event_card": _expand_event_card,
    "atmosphere_card": _expand_atmosphere_card,
    "quote_card": _expand_quote_card,
}


def expand_element_props(element_type: str, props: Dict[str, Any], content, logger) -> Dict[str, Any]:
    """Dispatch to the per-type expander; fall back to raw props on failure or unknown type."""
    if content is None:
        return props
    expander = ELEMENT_EXPANDERS.get(element_type)
    if expander is None:
        return props
    try:
        result = expander(props, content)
    except Exception as e:
        logger.info(f"Failed to expand props for {element_type}: {e}")
        return props
    return result if result is not None else props


# ── Cue building ─────────────────────────────────────────────────────

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


# ── Props sanitization ───────────────────────────────────────────────

def sanitize_props(props: Dict[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for k, v in props.items():
        if v is None:
            cleaned[k] = None
        elif isinstance(v, (str, int, float, bool)):
            cleaned[k] = v
        elif isinstance(v, dict):
            cleaned[k] = sanitize_props(v)
        elif isinstance(v, list):
            cleaned[k] = [
                sanitize_props(item) if isinstance(item, dict)
                else str(item) if not isinstance(item, (str, int, float, bool, type(None)))
                else item
                for item in v
            ]
        elif hasattr(v, "item"):
            cleaned[k] = v.item()
        elif hasattr(v, "__str__"):
            cleaned[k] = str(v)
        else:
            cleaned[k] = str(v)
    return cleaned


# ── Main serialization entry point ──────────────────────────────────

def script_to_props(
    script: Script,
    audio_dir: str,
    width: int,
    height: int,
    fps: int,
    bg_color: str,
    content=None,
    logger=None,
) -> Dict[str, Any]:
    """Convert Script dataclass → JSON-serializable dict for Remotion composition."""
    if logger is None:
        logger = setup_logger(__name__)

    segments_data: List[Dict[str, Any]] = []
    audio_path_obj = Path(audio_dir).resolve()

    for segment in script.segments:
        duration = float(segment.actual_duration or segment.estimated_duration)

        # 1. Build cues from TTS word timings or auto-split
        cues = build_cues(segment, duration, logger)

        seg_dict: Dict[str, Any] = {
            "segment_type": segment.segment_type,
            "audio_text": segment.audio_text,
            "cues": cues,
            "duration": duration,
            "start_time": float(segment.start_time or 0),
            "end_time": float(segment.end_time or 0),
            "scene_elements": [],
        }

        if segment.audio_path:
            src_audio = Path(segment.audio_path)
            if not src_audio.is_absolute():
                src_audio = audio_path_obj / src_audio
            seg_dict["audio_path"] = f"audio/{src_audio.name}"

        # 2. Expand element props and use times set by orchestrator
        expanded_count = 0
        for elem in segment.scene_elements:
            if elem.end_time <= elem.start_time:
                continue

            expanded_props = expand_element_props(elem.element_type, elem.props.copy(), content, logger)
            if expanded_props != elem.props:
                expanded_count += 1

            seg_dict["scene_elements"].append({
                "element_type": elem.element_type,
                "start_time": round(elem.start_time, 3),
                "end_time": round(elem.end_time, 3),
                "props": sanitize_props(expanded_props),
            })

        if expanded_count > 0:
            logger.debug(
                f"Expanded props for {expanded_count}/{len(segment.scene_elements)} scene elements"
            )

        segments_data.append(seg_dict)

    return {
        "width": width,
        "height": height,
        "fps": fps,
        "bgColor": bg_color,
        "title": script.title,
        "totalDuration": float(script.total_duration or 0),
        "segments": segments_data,
        "audioDir": str(Path(audio_dir).resolve()),
    }
