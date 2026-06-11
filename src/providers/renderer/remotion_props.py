"""
Props serialization for Remotion renderer.

Converts Python Script dataclass → JSON props consumed by the React/Remotion
composition.  Handles cue building and element props expansion.
"""

from pathlib import Path
import json
import shutil
from typing import Any, Dict, List
from urllib.parse import urlparse

from src.core.models import Script
from src.pipeline.paths import date_root, render_path, render_remotion_dir
from src.pipeline.comment import (
    clean_comment_text,
    classify_comment_stance,
    select_quote_comments,
)
from src.pipeline.comment import (
    comment_judgement_key,
    load_comment_judgements,
)
from src.providers.renderer.cue_builder import build_cues
from src.utils.atomic_io import atomic_write_text
from src.utils.logger import setup_logger


def _is_remote_url(path: str) -> bool:
    return path.startswith(("http://", "https://"))


def _extract_domain(url: str) -> str:
    """Extract domain from URL, stripping www. prefix."""
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc or ""
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""


def _to_filename(path: str) -> str:
    """Extract bare filename from a local path or remote URL."""
    if _is_remote_url(path):
        return Path(urlparse(path).path).name
    return Path(path).name


def _validate_quote_claim(text: str, max_chars: int = 50) -> str:
    """Validate a card-facing quote claim."""
    value = clean_comment_text(str(text or "")).strip()
    if not value:
        raise ValueError("comment_lanes claim is required")
    value = " ".join(value.split())
    if len(value) > max_chars:
        raise ValueError(f"comment_lanes claim exceeds {max_chars} characters: {value}")
    return value.strip("，。；：、,.!?！？;:）)]】")


def _safe_get_item(content, idx):
    """Return content.items[idx] if idx is a valid in-range int, else None."""
    if idx is None or not isinstance(idx, int):
        return None
    if 0 <= idx < len(content.items):
        return content.items[idx]
    return None


def _resolve_item(content, props):
    """Find the ContentItem for a script element.

    The script's ``story_index`` is the position within the *script's* ranked
    list (0..N-1), not the index in ``content.items``. When ``write_script``
    drops a story from content but the script still references it, the naive
    index lookup returns the wrong item and downstream quote/keyword resolution
    silently fails (e.g. ``quotes: []`` on the atmosphere card).

    Fallback: match the props' ``source_title`` (LLM-supplied, always present
    for story-related cards) against ``content.items[i].title``. The titles
    are stable across reorders, so this finds the right item even when indices
    diverge.
    """
    if content is None or not getattr(content, "items", None):
        return None
    props = props or {}
    idx = props.get("story_index")
    item = _safe_get_item(content, idx)
    if item is not None:
        target_title = (props.get("source_title") or "").strip()
        if not target_title:
            return item
        # If story_index pointed to a real item AND its title matches props,
        # trust the index.
        if item.title and item.title.strip() == target_title:
            return item
        # Otherwise, try to find a content item whose title matches props.
        for candidate in content.items:
            if (
                candidate.title
                and candidate.title.strip() == target_title
                and target_title
            ):
                return candidate
        # No title match — fall back to the index lookup, but only if the
        # props don't carry a different title.
        return item
    # story_index was None or out of range: try title-based lookup.
    target_title = (props.get("source_title") or "").strip()
    if target_title:
        for candidate in content.items:
            if candidate.title and candidate.title.strip() == target_title:
                return candidate
    return None


def _safe_get_comment(item, idx):
    """Return item.comments[idx] if idx is a valid in-range int, else None."""
    if idx is None or not isinstance(idx, int):
        return None
    if 0 <= idx < len(item.comments):
        return item.comments[idx]
    return None


def _image_type_from_candidate(candidate: Dict[str, Any] | None, path: str) -> str:
    if candidate:
        source = str(candidate.get("source") or "").lower()
        if source in {"screenshot", "logo", "document"}:
            return source
    lowered = path.lower()
    if "screenshot" in lowered or "_screenshot" in lowered:
        return "screenshot"
    if "logo" in lowered:
        return "logo"
    return "article"


def _choose_event_image(item, image_index: Any = 0) -> tuple[str, str]:
    local_candidates = [
        c
        for c in item.image_candidates
        if isinstance(c, dict) and c.get("path") and not _is_remote_url(c["path"])
    ]

    for candidate in local_candidates:
        if candidate.get("auto_selected"):
            path = str(candidate["path"])
            return path, _image_type_from_candidate(candidate, path)

    article_paths = [p for p in item.article_images if p and not _is_remote_url(p)]
    if article_paths:
        selected_path = article_paths[0]
        candidate = next(
            (c for c in local_candidates if c.get("path") == selected_path),
            None,
        )
        return selected_path, _image_type_from_candidate(candidate, selected_path)

    if local_candidates:
        idx = (
            max(0, min(image_index, len(local_candidates) - 1))
            if isinstance(image_index, int)
            else 0
        )
        candidate = local_candidates[idx]
        path = str(candidate["path"])
        return path, _image_type_from_candidate(candidate, path)

    if item.screenshot_image and not _is_remote_url(item.screenshot_image):
        return item.screenshot_image, "screenshot"
    if item.logo_image and not _is_remote_url(item.logo_image):
        return item.logo_image, "logo"
    return "", "article"


# ── Element props expanders ──────────────────────────────────────────


def _expand_highlight_entries(entries, content):
    """Trust generated highlight entries, but overwrite title/score from content."""
    expanded_entries = []
    for entry in entries or []:
        expanded = dict(entry)
        item = _safe_get_item(content, entry.get("story_index"))
        if item is not None:
            expanded["original_title"] = item.title
            expanded["title_cn"] = item.title_cn or ""
            expanded["score"] = item.score or 0
            expanded["comment_count"] = item.comment_count or 0
        expanded_entries.append(expanded)
    return expanded_entries


def _expand_cover_card(props, content):
    """Expand opening highlight entries with content-backed fields."""
    result = dict(props)
    highlight_entries = props.get("highlight_entries", [])
    if highlight_entries:
        result["highlight_entries"] = _expand_highlight_entries(
            highlight_entries, content
        )
    return result


def _compute_score_ranks(content) -> Dict[str, int]:
    """Return a mapping from source_id to 1-based score rank (highest score = 1)."""
    if content is None or not getattr(content, "items", None):
        return {}
    scored = []
    for idx, item in enumerate(content.items):
        if item.source_id is not None and (item.score or 0) > 0:
            scored.append((item.source_id, item.score or 0, idx))
    scored.sort(key=lambda x: x[1], reverse=True)
    return {sid: rank + 1 for rank, (sid, _, _) in enumerate(scored)}


def _heat_level_from_rank(rank: int, total: int) -> str:
    """Return a human-readable heat level based on rank and total stories."""
    if total <= 1:
        return "高热度"
    if rank == 1:
        return "今日最热"
    if rank <= 3:
        return "高热度"
    if rank <= max(3, total // 2):
        return "中热度"
    return "低热度"


def _expand_event_card(props, content, score_ranks=None):
    """Expand event_card element: inject story metadata, image, and keywords."""

    item = _resolve_item(content, props)
    if item is None:
        return props
    result = dict(props)
    result["story_title"] = item.title
    result["source_title"] = result.get("source_title") or item.title
    result["title_cn"] = item.title_cn or ""
    result["editor_angle"] = item.editor_angle
    result["key_points"] = result.get("key_points") or item.key_points or []
    result["why_it_matters"] = result.get("why_it_matters") or item.why_it_matters or ""
    result["source_domain"] = _extract_domain(item.url) if item.url else ""
    result["score"] = item.score or 0
    result["comment_count"] = item.comment_count or 0

    # Heat level from pre-computed score ranks
    if score_ranks and item.source_id is not None:
        rank = score_ranks.get(item.source_id)
        total = len(score_ranks)
        if rank is not None:
            result["heat_level"] = _heat_level_from_rank(rank, total)
        else:
            result["heat_level"] = ""
    else:
        result["heat_level"] = ""

    if "keywords" not in result or not result["keywords"]:
        result["keywords"] = item.keywords or []
    if "category" not in result or not result["category"]:
        result["category"] = item.category or ""

    image_path, image_type = _choose_event_image(item, props.get("image_index", 0))
    result["image_src"] = f"images/{_to_filename(image_path)}" if image_path else ""
    result["image_type"] = image_type

    # Keywords already set above via ContentItem fallback

    return result


def _expand_atmosphere_card(props, content, logger=None):
    """Expand atmosphere_card: inject controversy score, stance/distribution, and representative quotes."""
    import math

    if logger is None:
        logger = setup_logger("remotion_props")

    item = _resolve_item(content, props)
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

    # Quotes (merged from quote_card, max 2)
    judgement = {}
    date = getattr(content, "date", "")
    if date:
        judgement = load_comment_judgements(date).get(comment_judgement_key(item), {})

    display_claims = {}
    for entries in (judgement.get("comment_lanes") or {}).values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            comment_id = entry.get("comment_id")
            try:
                claim = _validate_quote_claim(entry.get("claim") or "")
            except ValueError as exc:
                logger.warning(
                    "atmosphere_card: skipping invalid comment_lanes claim "
                    "for comment %s: %s",
                    comment_id or "<missing>",
                    exc,
                )
                continue
            if (
                comment_id is not None
                and claim
                and str(comment_id) not in display_claims
            ):
                display_claims[str(comment_id)] = claim

    selected = select_quote_comments(
        item.comments,
        selected_ids=props.get("selected_comment_ids") or [],
        judgement=judgement,
        max_n=2,
    )

    quotes = []
    for c in selected[:2]:
        stance = classify_comment_stance(c)
        source_id = str(c.source_id) if c.source_id is not None else ""
        display_text = display_claims.get(source_id)
        if not display_text:
            # Self-healing fallback: judge LLM may select a quote comment that has
            # no claim in `comment_lanes` (claim is a separate LLM field). Rather
            # than fail the whole prepare_render, synthesize a 50-char display
            # from the cleaned comment text. Remotion side then gets a usable
            # `display_text` even when the judge's `claim` field is missing.
            fallback = clean_comment_text(c.content or "").strip()
            if not fallback:
                logger.warning(
                    "atmosphere_card: skipping comment %s (no claim and empty text)",
                    source_id or "<missing>",
                )
                continue
            display_text = fallback[:50].rstrip()
            logger.info(
                "atmosphere_card: synthesized claim for comment %s from text "
                "(no comment_lanes claim): %r",
                source_id or "<missing>",
                display_text,
            )
        quotes.append(
            {
                "source_id": source_id,
                "author": c.author,
                "text": c.content or "",
                "text_cn": c.content_cn or "",
                "display_text": display_text,
                "stance": stance,
                "upvotes": c.upvotes or 0,
            }
        )
    result["quotes"] = quotes

    # Override stance_distribution and debate_focus from judgement if available
    if judgement.get("stance_distribution"):
        result["stance_distribution"] = judgement["stance_distribution"]
    if judgement.get("debate_focus"):
        result["debate_focus"] = judgement["debate_focus"]
    if judgement.get("stance_concerns"):
        result["stance_concerns"] = judgement["stance_concerns"]

    return result


def _expand_closing_card(props, content):
    """Map the closing-card raw props (signal/keywords/summary_items/takeaways)
    to the variables the closing.html composition expects.

    Closing card variables (see compositions/closing.html):
      - title          : string, big orange title
      - subtitle       : string, smaller gray subtitle
      - stories        : list of {rank, original_title, title_zh, editor_angle}
      - footer_text    : string, freeform bottom-left text
      - badge          : string, pill text in the bottom-right

    Source props (set by script/composer.py → templates.generate_fixed_closing):
      - signal         : the closing one-liner
      - keywords       : list of 3 keywords
      - summary_items  : list of {category, title, signal} (one per story)
      - takeaways      : list of closing takeaway sentences
      - totals         : {story_count, score_total, comment_total}
    """
    result = dict(props)

    signal = props.get("signal") or ""
    summary_items = props.get("summary_items") or []
    takeaways = props.get("takeaways") or []
    keywords = props.get("keywords") or []
    totals = props.get("totals") or {}

    if signal:
        title = signal
    else:
        title = "今日HN AI观察 · 回顾"

    story_count = totals.get("story_count") or len(summary_items)
    score_total = totals.get("score_total") or 0
    comment_total = totals.get("comment_total") or 0
    parts: list = []
    if story_count:
        parts.append(f"{story_count} 个故事")
    if score_total:
        parts.append(f"{score_total:,} 分")
    if comment_total:
        parts.append(f"{comment_total:,} 评论")
    subtitle = " · ".join(parts) if parts else ""

    stories: list = []
    for rank, item in enumerate(summary_items, start=1):
        if not isinstance(item, dict):
            continue
        editor_angle = item.get("signal") or ""
        original_title = item.get("title") or ""
        stories.append(
            {
                "rank": rank,
                "original_title": original_title,
                "title_zh": original_title,
                "editor_angle": editor_angle,
            }
        )

    if takeaways:
        footer_text = takeaways[0]
    elif keywords:
        footer_text = " · ".join(str(k) for k in keywords)
    else:
        footer_text = ""

    badge = props.get("badge") or "HN Daily Closing"

    result["title"] = title
    result["subtitle"] = subtitle
    result["stories"] = stories
    result["footer_text"] = footer_text
    result["badge"] = badge
    return result


# Dispatch table: element_type -> expander function.
# Each expander returns an expanded props dict, or None to signal "leave props unchanged".
ELEMENT_EXPANDERS = {
    "cover_card": _expand_cover_card,
    "event_card": _expand_event_card,
    "atmosphere_card": _expand_atmosphere_card,
    "closing_card": _expand_closing_card,
}


def expand_element_props(
    element_type: str, props: Dict[str, Any], content, logger, score_ranks=None
) -> Dict[str, Any]:
    """Dispatch to the per-type expander; fall back to raw props on failure or unknown type."""
    if content is None:
        return props
    expander = ELEMENT_EXPANDERS.get(element_type)
    if expander is None:
        return props
    try:
        if element_type in {
            "event_card",
        }:
            result = expander(props, content, score_ranks=score_ranks)  # type: ignore[call-arg]
        else:
            result = expander(props, content)
    except Exception as e:
        logger.info(f"Failed to expand props for {element_type}: {e}")
        return props
    return result if result is not None else props


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
                sanitize_props(item)
                if isinstance(item, dict)
                else str(item)
                if not isinstance(item, (str, int, float, bool, type(None)))
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

    # Pre-compute score rankings across all content items for heat level display
    score_ranks = _compute_score_ranks(content)

    for segment in script.segments:
        duration = float(segment.actual_duration or segment.duration)

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

        # Per-subtitle audio tracks (story_scan with per-card TTS)
        subtitle_audios = segment.meta.get("subtitle_audios", [])
        if subtitle_audios:
            seg_dict["subtitle_audios"] = []
            for sa in subtitle_audios:
                src = Path(sa["audio_path"])
                if not src.is_absolute():
                    src = audio_path_obj / src
                seg_dict["subtitle_audios"].append(
                    {
                        "audio_path": f"audio/{src.name}",
                        "start_time": sa["start_time"],
                        "end_time": sa["end_time"],
                    }
                )

        # 2. Expand element props and use times set by orchestrator
        expanded_count = 0
        for elem in segment.scene_elements:
            if elem.props.get("is_audio_marker"):
                continue
            if elem.end_time <= elem.start_time:
                continue

            expanded_props = expand_element_props(
                elem.element_type,
                elem.props.copy(),
                content,
                logger,
                score_ranks=score_ranks,
            )
            if expanded_props != elem.props:
                expanded_count += 1

            seg_dict["scene_elements"].append(
                {
                    "element_type": elem.element_type,
                    "start_time": round(elem.start_time, 3),
                    "end_time": round(elem.end_time, 3),
                    "props": sanitize_props(expanded_props),
                }
            )

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


# ── Preview props sync (used by orchestrator and editor) ──────────────


def regenerate_preview_props(date: str, config: dict, logger=None) -> str:
    """Load script + content + enrichment from disk, regenerate props.json.

    Copies image assets to Remotion's public/ dir and writes props.json.
    Returns the path to the written props file. Safe to call while Remotion
    Studio is running — it will hot-reload on the next file change.

    Used by:
      - orchestrator._step_sync_preview()
      - editor's "Sync Preview" button
    """
    if logger is None:
        logger = setup_logger(__name__)

    # Load script and content
    from src.pipeline.script.io import load_script as _load_script
    from src.pipeline.content_io import ContentPreparer as _ContentPreparer

    script = _load_script(date)
    cp = _ContentPreparer(config)
    content = cp.load_content(date)

    # Copy image assets to data/{date}/render/remotion/public/images/
    data_remotion = render_remotion_dir(date)
    data_remotion.mkdir(parents=True, exist_ok=True)
    image_subdir = data_remotion / "public" / "images"
    image_subdir.mkdir(parents=True, exist_ok=True)

    def _is_remote(p: str) -> bool:
        return p.startswith(("http://", "https://"))

    def _resolve_local(p: str) -> Path | None:
        if _is_remote(p):
            return None
        src = Path(p)
        if not src.is_absolute():
            src = date_root(date) / p
        return src if src.exists() else None

    copied = 0
    for item in content.items:
        for img_path in item.article_images:
            src = _resolve_local(img_path)
            if src:
                dest = image_subdir / src.name
                if not dest.exists():
                    shutil.copy2(src, dest)
                    copied += 1
        for candidate in item.image_candidates:
            if not isinstance(candidate, dict):
                continue
            cand_path: str | None = candidate.get("path")
            if not cand_path:
                continue
            src = _resolve_local(cand_path)
            if src:
                dest = image_subdir / src.name
                if not dest.exists():
                    shutil.copy2(src, dest)
                    copied += 1
        for attr in ("logo_image", "screenshot_image"):
            val = getattr(item, attr, None)
            if val:
                src = _resolve_local(val)
                if src:
                    dest = image_subdir / src.name
                    if not dest.exists():
                        shutil.copy2(src, dest)
                        copied += 1
    if copied > 0:
        logger.info(f"Copied {copied} images to public/images/")

    # Build props
    video_config = config.get("video", {})
    width = video_config.get("resolution", (1280, 720))[0]
    height = video_config.get("resolution", (1280, 720))[1]
    fps = video_config.get("fps", 24)
    bg_color = video_config.get("bg_color", "#fefcf8")

    audio_dir = str(date_root(date) / "pipeline" / "audio")
    props_data = script_to_props(
        script, audio_dir, width, height, fps, bg_color, content=content, logger=logger
    )
    props_json = json.dumps(props_data, ensure_ascii=False, indent=2)

    # Write to data/{date}/remotion/public/props.json (studio hot-reloads
    # from here when launched with --public-dir)
    public_dir = data_remotion / "public"
    public_dir.mkdir(parents=True, exist_ok=True)
    props_file = public_dir / "props.json"
    atomic_write_text(props_file, props_json)
    logger.info(f"Props written to {props_file} ({len(props_json)} bytes)")

    # Also write to data/{date}/ for CLI use
    cli_path = render_path(date, "cli_props.json")
    atomic_write_text(cli_path, props_json)
    logger.info(f"Props written to {cli_path}")

    return str(props_file)
