import json
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from src.core.models import ContentComment, ContentItem, ContentPackage
from src.pipeline.comment_selection import clean_comment_text, is_quotable_comment


JUDGEMENT_SCHEMA_VERSION = 1

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
        "has_viewpoint": has_viewpoint,
        "reject_for_quote": reject,
        "reason": str(raw.get("reason") or "")[:220],
    }


def normalize_story_judgement(raw: dict, item: ContentItem) -> dict:
    """Normalize LLM comment judgement output into a canonical form.

    Deduplication priority: selected_comment_ids entries take precedence over
    quote_candidates entries. When the same comment_id appears in both lists,
    the first occurrence (from selected_comment_ids) wins and the duplicate
    from quote_candidates is silently dropped.
    """
    valid_ids = {str(c.source_id) for c in item.comments if c.source_id is not None}
    candidates = []
    seen = set()

    notes_by_id = {}
    for note in raw.get("notes", []) or []:
        if isinstance(note, dict):
            note_id = note.get("comment_id")
            if note_id is not None:
                notes_by_id[str(note_id)] = note

    for rank, comment_id in enumerate(raw.get("selected_comment_ids", []) or []):
        comment_id = str(comment_id)
        if comment_id not in valid_ids or comment_id in seen:
            continue
        note = notes_by_id.get(comment_id, {})
        candidates.append({
            "comment_id": comment_id,
            "quote_score": round(max(0.0, 1.0 - rank * 0.08), 4),
            "category": str(note.get("category") or "viewpoint"),
            "stance": str(note.get("stance") or "neutral"),
            "claim": "",
            "has_viewpoint": True,
            "reject_for_quote": False,
            "reason": "LLM selected",
        })
        seen.add(comment_id)

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
        total = sum(float(v) for v in raw_stance.values() if isinstance(v, (int, float)) and v > 0)
        if total > 0:
            stance_distribution = {
                str(k): round(float(v) / total, 4)
                for k, v in raw_stance.items()
                if isinstance(v, (int, float)) and v > 0
            }

    return {
        "story_id": comment_judgement_key(item),
        "quote_candidates": candidates,
        "rejected": rejected,
        "debate_focus": debate_focus,
        "stance_distribution": stance_distribution,
    }


def heuristic_story_judgement(item: ContentItem, max_candidates: int = 12) -> dict:
    candidates = []
    for comment in item.comments:
        if comment.source_id is None or not is_quotable_comment(comment):
            continue
        text = clean_comment_text(comment.content or "")
        candidates.append({
            "comment_id": str(comment.source_id),
            "quote_score": round(float(comment.quality_score or 0.0), 4),
            "category": "viewpoint",
            "stance": "neutral",
            "claim": text[:180],
            "has_viewpoint": True,
            "reject_for_quote": False,
            "reason": "Heuristic fallback candidate",
        })
    candidates.sort(key=lambda c: c["quote_score"], reverse=True)
    return {
        "story_id": comment_judgement_key(item),
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


def selected_ids_from_judgements(
    date: str,
    content: ContentPackage,
    max_n: int = 3,
) -> Dict[int, List[str]]:
    judgements = load_comment_judgements(date)
    selected: Dict[int, List[str]] = {}
    for story_idx, item in enumerate(content.items):
        ids = candidate_ids_for_story(
            judgements.get(comment_judgement_key(item)),
            max_n=max_n,
        )
        if ids:
            selected[story_idx] = ids
    return selected


def select_comments_from_judgement(
    comments: Iterable[ContentComment],
    judgement: Optional[dict],
    max_n: int = 3,
) -> List[ContentComment]:
    comments_by_id = {
        str(c.source_id): c
        for c in comments
        if c.source_id is not None and is_quotable_comment(c)
    }
    selected = []
    for comment_id in candidate_ids_for_story(judgement, max_n=max_n * 3):
        comment = comments_by_id.get(str(comment_id))
        if comment is None:
            continue
        selected.append(comment)
        if len(selected) >= max_n:
            break
    return selected
