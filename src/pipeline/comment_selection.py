import html
import re
from typing import Iterable, List, Optional, Tuple

from src.core.models import ContentComment, ContentItem


_HTML_TAG_RE = re.compile(r"<[^>]*>")
_URL_RE = re.compile(r"https?://\S+")
_CODE_RE = re.compile(r"```|`[^`]+`")
_STRUCTURED_RE = re.compile(r"^\s*[-*>]\s", re.MULTILINE)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_+#.-]+")
_RESOURCE_POINTER_RE = re.compile(
    r"\b("
    r"here(?:'s| is)|there(?:'s| is)|see also|related|link|article|paper|blog post|"
    r"write-?up|documentation|docs|guide|tutorial|resource|read this|check out|"
    r"worth reading|may be useful|might be useful"
    r")\b",
    re.IGNORECASE,
)
_VIEWPOINT_MARKER_RE = re.compile(
    r"\b("
    r"because|since|therefore|however|but|although|unless|if|when|why|how|"
    r"should|shouldn't|cannot|can't|won't|would|could|problem|trade-?off|risk|"
    r"concern|worried|skeptical|convinced|agree|disagree|prefer|instead|actually|"
    r"experience|used|tried|built|maintain|production|fails?|breaks?|works?|"
    r"means|implies|depends"
    r")\b",
    re.IGNORECASE,
)
_EXPERIENCE_MARKER_RE = re.compile(
    r"\b("
    r"i (?:used|tried|built|wrote|maintain|worked|ran)|"
    r"we (?:use|used|tried|built|maintain|run)|"
    r"in production|at (?:my|our) company|on my team|from experience|"
    r"operational|deployment|deploy|maintain|debug|migration"
    r")\b",
    re.IGNORECASE,
)
_SKEPTICAL_MARKER_RE = re.compile(
    r"\b("
    r"however|but|concern|worried|skeptical|not convinced|risk|problem|"
    r"trade-?off|fails?|breaks?|hard part|downside|danger|unsafe|"
    r"wouldn't|won't|can't|cannot"
    r")\b",
    re.IGNORECASE,
)
_CORRECTION_MARKER_RE = re.compile(
    r"\b("
    r"actually|to be clear|that's not|that is not|misleading|correction|"
    r"clarify|worth noting|the title|not exactly|in fact"
    r")\b",
    re.IGNORECASE,
)
_COMPARISON_MARKER_RE = re.compile(
    r"\b("
    r"compared to|similar to|unlike|instead of|alternative|versus|vs\.?|"
    r"rather than|reminds me of"
    r")\b",
    re.IGNORECASE,
)
_LOW_SIGNAL_RE = re.compile(
    r"^\s*(lol|same|thanks|thank you|this|exactly|\+1|agree|first)\s*[.!?]*\s*$",
    re.IGNORECASE,
)


def clean_comment_text(text: str) -> str:
    """Strip HN HTML and normalize whitespace for scoring, translation, and display."""
    if not text:
        return ""
    cleaned = _HTML_TAG_RE.sub(" ", text)
    cleaned = html.unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


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


def _content_flags(text: str) -> Tuple[bool, bool, bool]:
    return (
        bool(_CODE_RE.search(text)),
        bool(_URL_RE.search(text)),
        bool(_STRUCTURED_RE.search(text)),
    )


def _url_only_penalty(text: str) -> float:
    without_urls = _URL_RE.sub("", text).strip()
    if _URL_RE.search(text) and len(without_urls) < 30:
        return 0.25
    return 0.0


def is_resource_pointer_comment(text: str) -> bool:
    """Return True for link/resource pointers that do not carry a viewpoint."""
    clean_text = clean_comment_text(text)
    if not clean_text or not _URL_RE.search(clean_text):
        return False

    without_urls = _URL_RE.sub("", clean_text).strip(" :-.,;()[]{}<>")
    word_count = len(_WORD_RE.findall(without_urls))
    has_pointer_language = bool(_RESOURCE_POINTER_RE.search(without_urls))
    has_viewpoint_language = bool(_VIEWPOINT_MARKER_RE.search(without_urls))

    if len(without_urls) < 30:
        return True
    if len(without_urls) < 90 and has_pointer_language and not has_viewpoint_language:
        return True
    if word_count <= 14 and has_pointer_language and not has_viewpoint_language:
        return True
    return False


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


def _quote_heavy_penalty(raw_text: str, clean_text: str) -> float:
    quote_lines = [
        line for line in raw_text.splitlines() if line.strip().startswith((">", "&gt;"))
    ]
    if not quote_lines:
        return 0.0
    quoted_len = sum(len(clean_comment_text(line)) for line in quote_lines)
    if clean_text and quoted_len / max(len(clean_text), 1) > 0.55:
        return 0.15
    return 0.0


def _depth_score(depth: Optional[int]) -> float:
    if depth is None:
        return 0.08
    if depth <= 1:
        return 0.15
    if depth == 2:
        return 0.12
    if depth == 3:
        return 0.08
    if depth == 4:
        return 0.04
    return 0.0


def _relevance_score(clean_text: str, item: Optional[ContentItem]) -> float:
    if item is None:
        return 0.0
    context = " ".join(
        part
        for part in [
            item.title,
            item.title_cn or "",
            item.article_summary or "",
        ]
        if part
    )
    context_words = {w.lower() for w in _WORD_RE.findall(context) if len(w) >= 4}
    if not context_words:
        return 0.0
    comment_words = {w.lower() for w in _WORD_RE.findall(clean_text) if len(w) >= 4}
    overlap = len(context_words & comment_words)
    return min(0.2, overlap * 0.04)


def compute_comment_relevance(
    clean_text: str, item: Optional[ContentItem], max_score: float = 0.25
) -> float:
    """Cheap local relevance signal based on overlap with story/enrichment context."""
    if item is None:
        return 0.0
    key_points = item.key_points or []
    key_point_text = " ".join(
        str(kp.get("text") or "") for kp in key_points if isinstance(kp, dict)
    )
    context = " ".join(
        part
        for part in [
            item.title,
            item.title_cn or "",
            item.article_summary or "",
            item.editor_angle or "",
            item.dek or "",
            key_point_text,
            " ".join(item.keywords or []),
            item.category or "",
            item.why_it_matters or "",
        ]
        if part
    )
    context_words = {w.lower() for w in _WORD_RE.findall(context) if len(w) >= 4}
    if not context_words:
        return 0.0
    comment_words = {w.lower() for w in _WORD_RE.findall(clean_text) if len(w) >= 4}
    if not comment_words:
        return 0.0
    overlap = len(context_words & comment_words)
    return min(max_score, overlap * 0.035)


def compute_comment_quality(
    comment: ContentComment, item: Optional[ContentItem] = None
) -> float:
    raw_text = comment.content or ""
    text = clean_comment_text(raw_text)
    text_len = len(text)

    if text_len < 20:
        length_score = 0.0
    elif text_len < 80:
        length_score = (text_len - 20) / 60.0 * 0.18
    elif text_len <= 350:
        length_score = 0.25
    elif text_len <= 800:
        length_score = max(0.08, (800 - text_len) / 450.0 * 0.25)
    else:
        length_score = 0.03

    has_code, has_link, has_structured = _content_flags(text)
    structure_score = 0.0
    if has_code:
        structure_score += 0.08
    if has_structured:
        structure_score += 0.05
    if has_link and text_len >= 80:
        structure_score += 0.04
    structure_score = min(structure_score, 0.15)

    explanation_markers = len(
        re.findall(
            r"\b(because|since|therefore|however|example|means|actually|why|how|but|if|when)\b",
            text,
            flags=re.IGNORECASE,
        )
    )
    info_score = min(0.2, explanation_markers * 0.04)
    if re.search(r"\b\d+(?:\.\d+)?%?\b", text):
        info_score = min(0.2, info_score + 0.04)

    upvotes = comment.upvotes or 0
    discussion_score = min(upvotes / 50.0, 1.0) * 0.05

    score = (
        length_score
        + structure_score
        + info_score
        + _relevance_score(text, item)
        + _depth_score(comment.depth)
        + discussion_score
    )

    if text_len < 45 and upvotes == 0:
        score -= 0.12
    if is_resource_pointer_comment(text):
        score = min(score - 0.35, 0.08)
    score -= _url_only_penalty(text)
    score -= _quote_heavy_penalty(raw_text, text)

    return round(max(0.0, min(1.0, score)), 4)


def local_comment_type_hints(text: str) -> set[str]:
    """Classify useful local hints for balanced pre-LLM candidate sampling."""
    clean_text = clean_comment_text(text)
    hints: set[str] = set()
    if not clean_text:
        return hints
    if is_resource_pointer_comment(clean_text):
        hints.add("resource_only")
    elif _URL_RE.search(clean_text):
        hints.add("resource")
    if _EXPERIENCE_MARKER_RE.search(clean_text):
        hints.add("experience")
    if _SKEPTICAL_MARKER_RE.search(clean_text):
        hints.add("skeptical")
    if _CORRECTION_MARKER_RE.search(clean_text):
        hints.add("correction")
    if _COMPARISON_MARKER_RE.search(clean_text):
        hints.add("comparison")
    if _VIEWPOINT_MARKER_RE.search(clean_text):
        hints.add("viewpoint")
    if "?" in clean_text:
        hints.add("question")
    if _LOW_SIGNAL_RE.match(clean_text):
        hints.add("low_signal")
    return hints


def compute_judge_candidate_score(
    comment: ContentComment, item: Optional[ContentItem] = None
) -> float:
    """Rank comments before sending a compact, diverse set to the LLM judge."""
    text = clean_comment_text(comment.content or "")
    quality = comment.quality_score
    if quality is None:
        quality = compute_comment_quality(comment, item)
    relevance = compute_comment_relevance(text, item)
    hints = local_comment_type_hints(text)

    bonus = 0.0
    if "viewpoint" in hints:
        bonus += 0.04
    if "experience" in hints:
        bonus += 0.06
    if "skeptical" in hints:
        bonus += 0.04
    if "correction" in hints or "comparison" in hints:
        bonus += 0.03
    if comment.depth is not None and comment.depth >= 2:
        bonus += 0.025

    penalty = 0.0
    if "resource_only" in hints:
        penalty += 0.25
    if "low_signal" in hints:
        penalty += 0.2

    score = (float(quality or 0.0) * 0.65) + relevance + bonus - penalty
    return round(max(0.0, min(1.0, score)), 4)


def _similarity(a: str, b: str) -> float:
    words_a = {w.lower() for w in _WORD_RE.findall(a) if len(w) >= 4}
    words_b = {w.lower() for w in _WORD_RE.findall(b) if len(w) >= 4}
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


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
    similarity_threshold: float = 0.62,
) -> List[ContentComment]:
    """Pick a local, balanced candidate pool before the LLM comment judge.

    This keeps cost fixed while improving coverage: high-quality comments,
    skeptical/supportive minority views, deeper replies, and practical experience.
    """
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


def select_representative_comments(
    comments: Iterable[ContentComment],
    max_n: int = 3,
    min_quality: float = 0.22,
    similarity_threshold: float = 0.58,
) -> List[ContentComment]:
    """Pick high-quality, stance-diverse comments while avoiding near-duplicates.

    Prefers the trio 支持/反对/中立 when max_n >= 3.
    """
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

    # First pass: try to get one of each stance (支持, 质疑, 中立)
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

    # Second pass: fill remaining slots with any stance
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
    similarity_threshold: float = 0.58,
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

    # Try to fill to 3 with 支持/质疑/中立 coverage
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

        # First, fill missing target stances
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

        # Then fill any remaining slots
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
