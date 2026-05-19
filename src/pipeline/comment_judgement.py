import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.models import ContentItem
from src.pipeline.comment_selection import clean_comment_text, is_quotable_comment


JUDGEMENT_SCHEMA_VERSION = 2

DISCUSSION_MODES = {
    "debate",
    "field_notes",
    "nostalgia",
    "troubleshooting",
    "qna",
    "correction",
    "showcase",
    "low_signal",
}

COMMENT_LANES = {
    "representative",
    "counterpoint",
    "detail",
    "color",
}

_save_lock = threading.Lock()


def judgement_cache_path(date: str) -> Path:
    return Path(f"data/{date}/comment_judgement.json")


def comment_judgement_key(item: ContentItem) -> str:
    return str(item.source_id)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_candidate(raw: dict, valid_ids: set[str]) -> Optional[dict]:
    comment_id = raw.get("comment_id") or raw.get("id") or raw.get("source_id")
    if comment_id is None:
        return None
    comment_id = str(comment_id)
    if comment_id not in valid_ids:
        return None

    reject = bool(raw.get("reject_for_quote", False))
    has_viewpoint = bool(raw.get("has_viewpoint", not reject))
    score = max(0.0, min(1.0, _safe_float(raw.get("quote_score"), 0.0)))

    return {
        "comment_id": comment_id,
        "quote_score": score,
        "category": str(raw.get("category") or "viewpoint"),
        "stance": str(raw.get("stance") or "neutral"),
        "claim": str(raw.get("claim") or "")[:220],
        "role": str(raw.get("role") or raw.get("category") or "viewpoint")[:48],
        "has_viewpoint": has_viewpoint,
        "reject_for_quote": reject,
        "reason": str(raw.get("reason") or "")[:220],
    }


def _normalize_discussion_mode(value: Any) -> str:
    mode = str(value or "").strip()
    return mode if mode in DISCUSSION_MODES else "field_notes"


def _validate_claim(value: Any, max_chars: int = 28) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("comment_lanes claim is required")
    text = " ".join(text.split())
    if len(text) > max_chars:
        raise ValueError(f"comment_lanes claim exceeds {max_chars} characters: {text}")
    return text.strip("，。；：、,.!?！？;:）)]】")


def _normalize_comment_lanes(raw: dict, valid_ids: set[str]) -> dict:
    lanes: dict[str, list[dict]] = {lane: [] for lane in COMMENT_LANES}
    raw_lanes = raw.get("comment_lanes", {}) or {}
    if not isinstance(raw_lanes, dict):
        return lanes

    seen_by_lane: dict[str, set[str]] = {lane: set() for lane in COMMENT_LANES}
    for lane, entries in raw_lanes.items():
        lane_key = str(lane)
        if lane_key not in COMMENT_LANES or not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            candidate = _normalize_candidate(entry, valid_ids)
            if candidate is None:
                continue
            cid = candidate["comment_id"]
            if cid in seen_by_lane[lane_key]:
                continue
            candidate["claim"] = _validate_claim(candidate.get("claim"))
            seen_by_lane[lane_key].add(cid)
            lanes[lane_key].append(candidate)

    return lanes


def normalize_story_judgement(raw: dict, item: ContentItem) -> dict:
    """Normalize LLM comment judgement output into a canonical form."""
    valid_ids = {str(c.source_id) for c in item.comments if c.source_id is not None}
    candidates = []
    seen = set()

    # Derive quote_candidates from comment_lanes instead of a separate selected_comment_ids.
    # comment_lanes already contains structured, lane-categorized candidates with claims and scores.
    comment_lanes_raw = raw.get("comment_lanes", {}) or {}
    for lane_key in COMMENT_LANES:
        for entry in comment_lanes_raw.get(lane_key, []) or []:
            if not isinstance(entry, dict):
                continue
            candidate = _normalize_candidate(entry, valid_ids)
            if candidate is None or candidate["comment_id"] in seen:
                continue
            seen.add(candidate["comment_id"])
            candidates.append(candidate)

    for entry in raw.get("quote_candidates", []) or []:
        if not isinstance(entry, dict):
            continue
        candidate = _normalize_candidate(entry, valid_ids)
        if candidate is None or candidate["comment_id"] in seen:
            continue
        seen.add(candidate["comment_id"])
        candidates.append(candidate)

    candidates.sort(key=lambda c: c.get("quote_score", 0.0), reverse=True)
    rejected = []
    for entry in raw.get("rejected", []) or []:
        if isinstance(entry, dict):
            normalized = _normalize_candidate(
                {**entry, "reject_for_quote": True},
                valid_ids,
            )
            if normalized is not None:
                rejected.append(normalized)

    debate_focus = []
    for entry in raw.get("debate_focus", []) or []:
        if isinstance(entry, str) and entry.strip():
            debate_focus.append(entry.strip())

    stance_distribution = {}
    raw_stance = raw.get("stance_distribution", {}) or {}
    if isinstance(raw_stance, dict):
        total = sum(
            float(v)
            for v in raw_stance.values()
            if isinstance(v, (int, float)) and v > 0
        )
        if total > 0:
            stance_distribution = {
                str(k): round(float(v) / total, 4)
                for k, v in raw_stance.items()
                if isinstance(v, (int, float)) and v > 0
            }

    stance_concerns = {}
    raw_concerns = raw.get("stance_concerns", {}) or {}
    if isinstance(raw_concerns, dict):
        for k, v in raw_concerns.items():
            if isinstance(v, str) and v.strip() and k in stance_distribution:
                stance_concerns[str(k)] = v.strip()[:24]

    discussion_mode = _normalize_discussion_mode(raw.get("discussion_mode"))
    discussion_summary = str(raw.get("discussion_summary") or "").strip()[:180]
    comment_lanes = _normalize_comment_lanes(raw, valid_ids)

    return {
        "story_id": comment_judgement_key(item),
        "discussion_mode": discussion_mode,
        "discussion_summary": discussion_summary,
        "comment_lanes": comment_lanes,
        "quote_candidates": candidates,
        "rejected": rejected,
        "debate_focus": debate_focus,
        "stance_distribution": stance_distribution,
        "stance_concerns": stance_concerns,
    }


def heuristic_story_judgement(item: ContentItem, max_candidates: int = 12) -> dict:
    candidates = []
    for comment in item.comments:
        if comment.source_id is None or not is_quotable_comment(comment):
            continue
        text = clean_comment_text(comment.content or "")
        candidates.append(
            {
                "comment_id": str(comment.source_id),
                "quote_score": round(float(comment.quality_score or 0.0), 4),
                "category": "viewpoint",
                "stance": "neutral",
                "claim": text[:180],
                "has_viewpoint": True,
                "reject_for_quote": False,
                "reason": "Heuristic fallback candidate",
            }
        )
    candidates.sort(key=lambda c: c["quote_score"], reverse=True)
    return {
        "story_id": comment_judgement_key(item),
        "discussion_mode": "field_notes",
        "discussion_summary": "",
        "comment_lanes": {
            "representative": candidates[:2],
            "counterpoint": candidates[2:3],
            "detail": candidates[3:5],
            "color": [],
        },
        "quote_candidates": candidates[:max_candidates],
        "rejected": [],
    }


def load_comment_judgements(date: str) -> Dict[str, dict]:
    path = judgement_cache_path(date)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("schema_version") != JUDGEMENT_SCHEMA_VERSION:
        return {}
    stories = data.get("stories", {})
    return stories if isinstance(stories, dict) else {}


def save_comment_judgements(date: str, stories: Dict[str, dict]) -> None:
    path = judgement_cache_path(date)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": JUDGEMENT_SCHEMA_VERSION,
        "stories": stories,
    }
    with _save_lock:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)


def candidate_ids_for_story(judgement: Optional[dict], max_n: int = 3) -> List[str]:
    if not judgement:
        return []
    ids = []
    for candidate in judgement.get("quote_candidates", []) or []:
        if candidate.get("reject_for_quote"):
            continue
        if not candidate.get("has_viewpoint", True):
            continue
        comment_id = candidate.get("comment_id")
        if comment_id is None:
            continue
        ids.append(str(comment_id))
        if len(ids) >= max_n:
            break
    return ids
