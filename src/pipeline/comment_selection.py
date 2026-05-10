import html
import re
from typing import Iterable, List, Optional, Tuple

from src.core.models import ContentComment, ContentItem


_HTML_TAG_RE = re.compile(r"<[^>]*>")
_URL_RE = re.compile(r"https?://\S+")
_CODE_RE = re.compile(r"```|`[^`]+`")
_STRUCTURED_RE = re.compile(r"^\s*[-*>]\s", re.MULTILINE)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_+#.-]+")


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


def comment_key(story_idx: int, story_source_id: Optional[str], comment: ContentComment, fallback_idx: int) -> str:
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


def _quote_heavy_penalty(raw_text: str, clean_text: str) -> float:
    quote_lines = [
        line for line in raw_text.splitlines()
        if line.strip().startswith((">", "&gt;"))
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
        part for part in [
            item.title,
            item.title_cn or "",
            item.article_summary or "",
            item.summary or "",
        ]
        if part
    )
    context_words = {w.lower() for w in _WORD_RE.findall(context) if len(w) >= 4}
    if not context_words:
        return 0.0
    comment_words = {w.lower() for w in _WORD_RE.findall(clean_text) if len(w) >= 4}
    overlap = len(context_words & comment_words)
    return min(0.2, overlap * 0.04)


def compute_comment_quality(comment: ContentComment, item: Optional[ContentItem] = None) -> float:
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

    explanation_markers = len(re.findall(
        r"\b(because|since|therefore|however|example|means|actually|why|how|but|if|when)\b",
        text,
        flags=re.IGNORECASE,
    ))
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
    score -= _url_only_penalty(text)
    score -= _quote_heavy_penalty(raw_text, text)

    return round(max(0.0, min(1.0, score)), 4)


def _similarity(a: str, b: str) -> float:
    words_a = {w.lower() for w in _WORD_RE.findall(a) if len(w) >= 4}
    words_b = {w.lower() for w in _WORD_RE.findall(b) if len(w) >= 4}
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def _ranked_comments(comments: Iterable[ContentComment]) -> List[ContentComment]:
    scored = [c for c in comments if (c.quality_score or 0) > 0 and clean_comment_text(c.content or "")]
    scored.sort(
        key=lambda c: (
            c.quality_score or 0,
            -1 * (c.depth if c.depth is not None else 3),
        ),
        reverse=True,
    )
    return scored


def select_representative_comments(
    comments: Iterable[ContentComment],
    max_n: int = 3,
    min_quality: float = 0.1,
    similarity_threshold: float = 0.58,
) -> List[ContentComment]:
    """Pick high-quality, stance-diverse comments while avoiding near-duplicates."""
    ranked = [c for c in _ranked_comments(comments) if (c.quality_score or 0) >= min_quality]
    selected: List[ContentComment] = []
    seen_stances = set()

    def can_add(candidate: ContentComment) -> bool:
        text = clean_comment_text(candidate.content or "")
        return all(
            _similarity(text, clean_comment_text(existing.content or "")) < similarity_threshold
            for existing in selected
        )

    for c in ranked:
        stance = classify_comment_stance(c)
        if stance in seen_stances or not can_add(c):
            continue
        selected.append(c)
        seen_stances.add(stance)
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
            if c not in selected:
                selected.append(c)
            if len(selected) >= min(2, max_n):
                break

    return selected[:max_n]
