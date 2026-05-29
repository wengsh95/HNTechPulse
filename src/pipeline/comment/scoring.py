"""Comment quality and relevance scoring."""

import re
from typing import Optional

from src.core.models import ContentComment, ContentItem
from src.pipeline.comment.text import (
    clean_comment_text,
    is_resource_pointer_comment,
)


_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_+#.-]+")
_URL_RE = re.compile(r"https?://\S+")
_CODE_RE = re.compile(r"```|`[^`]+`")
_STRUCTURED_RE = re.compile(r"^\s*[-*>]\s", re.MULTILINE)

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
_LOW_SIGNAL_RE = re.compile(
    r"^\s*(lol|same|thanks|thank you|this|exactly|\+1|agree|first)\s*[.!?]*\s*$",
    re.IGNORECASE,
)


def _content_flags(text: str) -> tuple[bool, bool, bool]:
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
