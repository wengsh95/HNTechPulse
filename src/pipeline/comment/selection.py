"""Comment selection: stance classification, candidate picking, quote selection."""

from typing import Iterable, List, Optional

from src.core.models import ContentComment, ContentItem
from src.pipeline.comment.text import clean_comment_text, is_resource_pointer_comment
from src.pipeline.comment.scoring import (
    compute_comment_quality,
    compute_judge_candidate_score,
)


def _similarity(a: str, b: str) -> float:
    """Semantic similarity between two comment texts.

    Delegates to the embedding module which uses cosine similarity when
    embeddings are cached, and falls back to word-overlap Jaccard otherwise.
    """
    from src.pipeline.comment.embedding import text_similarity

    return text_similarity(a, b)


def classify_comment_stance(comment: ContentComment) -> str:
    sentiment = comment.sentiment or 0.0
    if sentiment > 0.3:
        return "支持"
    if sentiment < -0.3:
        return "质疑"
    return "中立"


def comment_key(
    story_idx: int,
    story_source_id: Optional[str],
    comment: ContentComment,
    fallback_idx: int,
) -> str:
    """Build a stable translation key when source ids are available."""
    story_part = story_source_id or str(story_idx)
    comment_part = comment.source_id or str(fallback_idx)
    return f"comment_{story_part}_{comment_part}"


def is_quotable_comment(comment: ContentComment, min_quality: float = 0.22) -> bool:
    """Whether a comment is suitable for quote display, not merely useful context."""
    text = clean_comment_text(comment.content or "")
    if not text:
        return False
    if is_resource_pointer_comment(text):
        return False
    if len(text) < 20:
        return False
    if (comment.quality_score or 0.0) < min_quality:
        return False
    return True


def _ranked_comments(comments: Iterable[ContentComment]) -> List[ContentComment]:
    scored = [
        c
        for c in comments
        if (c.quality_score or 0) > 0 and clean_comment_text(c.content or "")
    ]
    scored.sort(
        key=lambda c: (
            c.quality_score or 0,
            -1 * (c.depth if c.depth is not None else 3),
        ),
        reverse=True,
    )
    return scored


def select_judge_candidate_comments(
    item: ContentItem,
    max_n: int = 15,
    min_quality: float = 0.05,
    similarity_threshold: float = 0.82,
) -> List[ContentComment]:
    """Pick a local, balanced candidate pool before the LLM comment judge."""
    from src.pipeline.comment.scoring import local_comment_type_hints

    if max_n <= 0:
        return []

    candidates: list[tuple[float, ContentComment, str, set[str]]] = []
    for comment in item.comments:
        if comment.source_id is None:
            continue
        text = clean_comment_text(comment.content or "")
        if len(text) < 20:
            continue
        quality = comment.quality_score
        if quality is None:
            quality = compute_comment_quality(comment, item)
            comment.quality_score = quality
        if float(quality or 0.0) < min_quality:
            continue
        hints = local_comment_type_hints(text)
        if "resource_only" in hints:
            continue
        if "low_signal" in hints:
            continue
        candidates.append(
            (compute_judge_candidate_score(comment, item), comment, text, hints)
        )

    candidates.sort(
        key=lambda row: (
            row[0],
            row[1].quality_score or 0.0,
            -1 * (row[1].depth if row[1].depth is not None else 3),
        ),
        reverse=True,
    )

    selected: list[tuple[float, ContentComment, str, set[str]]] = []
    selected_ids: set[str] = set()

    def can_add(row: tuple[float, ContentComment, str, set[str]]) -> bool:
        _score, comment, text, _hints = row
        cid = str(comment.source_id)
        if cid in selected_ids:
            return False
        return all(
            _similarity(text, existing_text) < similarity_threshold
            for _s, _c, existing_text, _h in selected
        )

    def add_from(
        rows: list[tuple[float, ContentComment, str, set[str]]], limit: int
    ) -> None:
        for row in rows:
            if len(selected) >= max_n or limit <= 0:
                return
            if not can_add(row):
                continue
            selected.append(row)
            selected_ids.add(str(row[1].source_id))
            limit -= 1

    top_quality_limit = min(max_n, max(5, max_n // 2))
    add_from(candidates, top_quality_limit)
    add_from([r for r in candidates if (r[1].sentiment or 0.0) <= -0.25], 3)
    add_from([r for r in candidates if (r[1].sentiment or 0.0) >= 0.25], 2)
    add_from([r for r in candidates if r[1].depth is not None and r[1].depth >= 2], 2)
    add_from([r for r in candidates if "experience" in r[3]], 2)
    add_from(
        [r for r in candidates if "correction" in r[3] or "comparison" in r[3]],
        1,
    )
    add_from(candidates, max_n - len(selected))

    selected.sort(
        key=lambda row: (
            row[0],
            row[1].quality_score or 0.0,
            -1 * (row[1].depth if row[1].depth is not None else 3),
        ),
        reverse=True,
    )
    return [row[1] for row in selected[:max_n]]


def select_discussion_profile_comments(
    item: ContentItem,
    max_n: int = 15,
    min_quality: float = 0.05,
    similarity_threshold: float = 0.78,
) -> List[ContentComment]:
    """Pick a judge sample that represents the discussion, not only quote quality.

    The comment judge is responsible for both quote selection and the existing
    discussion profile fields. A pure quality ranking is good for quotes but can
    overstate the most polished minority thread. This sampler keeps strong
    comments, then adds stance/type/depth slices so `discussion_mode`,
    `stance_distribution`, and `debate_focus` see a broader cross-section.
    """
    from src.pipeline.comment.scoring import local_comment_type_hints

    if max_n <= 0:
        return []

    rows: list[tuple[float, ContentComment, str, set[str], int]] = []
    for ordinal, comment in enumerate(item.comments):
        if comment.source_id is None:
            continue
        text = clean_comment_text(comment.content or "")
        if len(text) < 20:
            continue
        quality = comment.quality_score
        if quality is None:
            quality = compute_comment_quality(comment, item)
            comment.quality_score = quality
        hints = local_comment_type_hints(text)
        if "resource_only" in hints or "low_signal" in hints:
            continue

        upvotes = comment.upvotes or 0
        has_profile_signal = bool(
            hints
            & {
                "experience",
                "skeptical",
                "correction",
                "comparison",
                "question",
                "viewpoint",
            }
        )
        if (
            float(quality or 0.0) < min_quality
            and upvotes < 2
            and not has_profile_signal
        ):
            continue

        # Earlier comments tend to be higher-level discussion starters in HN's
        # tree traversal. Keep that as a weak profile signal without letting it
        # dominate quote-quality scoring.
        early_bonus = max(0.0, 1.0 - (ordinal / max(len(item.comments), 1))) * 0.04
        score = compute_judge_candidate_score(comment, item) + early_bonus
        rows.append((round(min(score, 1.0), 4), comment, text, hints, ordinal))

    rows.sort(
        key=lambda row: (
            row[0],
            row[1].quality_score or 0.0,
            -1 * (row[1].depth if row[1].depth is not None else 3),
            -row[4],
        ),
        reverse=True,
    )

    selected: list[tuple[float, ContentComment, str, set[str], int]] = []
    selected_ids: set[str] = set()

    def can_add(row: tuple[float, ContentComment, str, set[str], int]) -> bool:
        _score, comment, text, _hints, _ordinal = row
        cid = str(comment.source_id)
        if cid in selected_ids:
            return False
        return all(
            _similarity(text, existing_text) < similarity_threshold
            for _s, _c, existing_text, _h, _o in selected
        )

    def add_from(
        candidates: list[tuple[float, ContentComment, str, set[str], int]], limit: int
    ) -> None:
        for row in candidates:
            if len(selected) >= max_n or limit <= 0:
                return
            if not can_add(row):
                continue
            selected.append(row)
            selected_ids.add(str(row[1].source_id))
            limit -= 1

    anchor_limit = min(max_n, max(3, max_n // 3))
    add_from(rows, anchor_limit)
    add_from([r for r in rows if (r[1].depth or 0) <= 1], 3)
    add_from(
        [r for r in rows if "skeptical" in r[3] or (r[1].sentiment or 0) <= -0.25], 3
    )
    add_from([r for r in rows if (r[1].sentiment or 0) >= 0.25], 2)
    add_from([r for r in rows if "experience" in r[3]], 2)
    add_from([r for r in rows if "correction" in r[3] or "comparison" in r[3]], 2)
    add_from([r for r in rows if "question" in r[3]], 1)
    add_from([r for r in rows if r[1].depth is not None and r[1].depth >= 2], 3)
    add_from(rows, max_n - len(selected))

    selected.sort(
        key=lambda row: (
            row[0],
            row[1].quality_score or 0.0,
            -1 * (row[1].depth if row[1].depth is not None else 3),
        ),
        reverse=True,
    )
    return [row[1] for row in selected[:max_n]]


def select_representative_comments(
    comments: Iterable[ContentComment],
    max_n: int = 3,
    min_quality: float = 0.22,
    similarity_threshold: float = 0.78,
) -> List[ContentComment]:
    """Pick high-quality, stance-diverse comments while avoiding near-duplicates."""
    ranked = [
        c for c in _ranked_comments(comments) if is_quotable_comment(c, min_quality)
    ]
    selected: List[ContentComment] = []

    def can_add(candidate: ContentComment) -> bool:
        text = clean_comment_text(candidate.content or "")
        return all(
            _similarity(text, clean_comment_text(existing.content or ""))
            < similarity_threshold
            for existing in selected
        )

    target_stances = ["支持", "质疑", "中立"]
    seen_stances: set[str] = set()
    for stance in target_stances:
        for c in ranked:
            if classify_comment_stance(c) != stance:
                continue
            if not can_add(c):
                continue
            selected.append(c)
            seen_stances.add(stance)
            break
        if len(selected) >= max_n:
            return selected

    for c in ranked:
        if c in selected or not can_add(c):
            continue
        selected.append(c)
        if len(selected) >= max_n:
            return selected

    if len(selected) < min(2, max_n):
        for c in ranked:
            if c in selected or not can_add(c):
                continue
            selected.append(c)
            if len(selected) >= min(2, max_n):
                break

    return selected[:max_n]


def select_comments_by_ids(
    comments: Iterable[ContentComment],
    selected_ids: Iterable,
    max_n: int = 3,
    min_quality: float = 0.22,
) -> List[ContentComment]:
    """Pick explicitly requested quotable comments by source_id, preserving id order."""
    id_order = [
        str(comment_id) for comment_id in selected_ids if comment_id is not None
    ]
    if not id_order:
        return []
    comments_by_id = {
        str(c.source_id): c
        for c in comments
        if c.source_id is not None and is_quotable_comment(c, min_quality)
    }
    selected = []
    seen = set()
    for comment_id in id_order:
        if comment_id in seen:
            continue
        comment = comments_by_id.get(comment_id)
        if comment is None:
            continue
        selected.append(comment)
        seen.add(comment_id)
        if len(selected) >= max_n:
            break
    return selected


def select_quote_comments(
    comments: Iterable[ContentComment],
    selected_ids: Optional[Iterable] = None,
    judgement: Optional[dict] = None,
    max_n: int = 3,
    min_quality: float = 0.22,
    similarity_threshold: float = 0.78,
) -> List[ContentComment]:
    """Select quote comments: honor LLM ids, then fill with strong fallbacks."""
    comments_list = list(comments)
    selected = select_comments_by_ids(
        comments_list,
        selected_ids or [],
        max_n=max_n,
        min_quality=min_quality,
    )
    selected_object_ids = {id(c) for c in selected}
    selected_stances = {classify_comment_stance(c) for c in selected}

    target_stances = ["支持", "质疑", "中立"]
    if len(selected) < max_n:
        judged_fillers = []
        if judgement:
            comments_by_id = {
                str(c.source_id): c
                for c in comments_list
                if c.source_id is not None and is_quotable_comment(c, min_quality)
            }
            for candidate in judgement.get("quote_candidates", []) or []:
                if candidate.get("reject_for_quote") or not candidate.get(
                    "has_viewpoint", True
                ):
                    continue
                comment_id = candidate.get("comment_id")
                if comment_id is None:
                    continue
                comment = comments_by_id.get(str(comment_id))
                if comment is not None:
                    judged_fillers.append(comment)
                if len(judged_fillers) >= max_n * 2:
                    break

        for stance in target_stances:
            if stance in selected_stances:
                continue
            for comment in judged_fillers:
                if id(comment) in selected_object_ids:
                    continue
                if classify_comment_stance(comment) == stance:
                    selected.append(comment)
                    selected_object_ids.add(id(comment))
                    selected_stances.add(stance)
                    break
            if len(selected) >= max_n:
                return selected[:max_n]

        for comment in judged_fillers:
            if id(comment) in selected_object_ids:
                continue
            selected.append(comment)
            selected_object_ids.add(id(comment))
            selected_stances.add(classify_comment_stance(comment))
            if len(selected) >= max_n:
                return selected[:max_n]

    fillers = select_representative_comments(
        comments_list,
        max_n=max_n,
        min_quality=min_quality,
        similarity_threshold=similarity_threshold,
    )
    for stance in target_stances:
        if stance in selected_stances:
            continue
        for comment in fillers:
            if id(comment) in selected_object_ids:
                continue
            if classify_comment_stance(comment) == stance:
                selected.append(comment)
                selected_object_ids.add(id(comment))
                selected_stances.add(stance)
                break
        if len(selected) >= max_n:
            return selected[:max_n]

    for comment in fillers:
        if id(comment) in selected_object_ids:
            continue
        selected.append(comment)
        selected_object_ids.add(id(comment))
        if len(selected) >= max_n:
            break
    return selected[:max_n]
