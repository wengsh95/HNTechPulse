"""Cheap article/title relevance checks used before LLM enrichment.

The fetcher can successfully download an aggregator homepage while the text
extractor selects one unrelated card inside it. This module is intentionally
lexical and deterministic: it is a safety gate, not a semantic ranking model.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urlparse


_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9'_-]{2,}|[\u4e00-\u9fff]{2,}")
_LATIN_RE = re.compile(r"[A-Za-z]")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_STOP_WORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "after",
        "before",
        "what",
        "where",
        "does",
        "have",
        "this",
        "that",
        "show",
        "hn",
    }
)


@dataclass(frozen=True)
class ArticleRelevance:
    score: float
    title_tokens: tuple[str, ...]
    overlapping_tokens: tuple[str, ...]
    accepted: bool
    reason: str = ""


def _tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in _TOKEN_RE.findall(text or "")
        if token.lower() not in _STOP_WORDS
    }


def _is_root_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.path in ("", "/") and not parsed.query


def assess_article_relevance(
    title: str,
    article_text: str,
    *,
    url: str | None = None,
    min_score: float = 0.08,
) -> ArticleRelevance:
    """Check whether extracted text contains meaningful title signals."""
    title_tokens = _tokens(title)
    body_tokens = _tokens(article_text)
    overlap = tuple(sorted(title_tokens & body_tokens))
    score = len(overlap) / max(1, len(title_tokens))

    # There is no lexical evidence to compare. Treat this as an extraction
    # quality problem, not proof that the fetched page belongs to another
    # story; callers can apply their normal short/empty-body handling.
    if len(body_tokens) < 2:
        return ArticleRelevance(
            score=0.0,
            title_tokens=tuple(sorted(title_tokens)),
            overlapping_tokens=(),
            accepted=True,
            reason="body_has_insufficient_lexical_signal",
        )

    if not title_tokens:
        return ArticleRelevance(
            score=0.0,
            title_tokens=(),
            overlapping_tokens=(),
            accepted=True,
            reason="title_has_no_usable_tokens",
        )

    if _is_root_url(url) and not overlap:
        # A translated article may legitimately have no lexical overlap with
        # an English HN title. The root-page guard is only strict when both
        # sides use a comparable script.
        cross_language = bool(
            (_LATIN_RE.search(title) and _CJK_RE.search(article_text))
            or (_CJK_RE.search(title) and _LATIN_RE.search(article_text))
        )
        if cross_language:
            return ArticleRelevance(
                score=0.0,
                title_tokens=tuple(sorted(title_tokens)),
                overlapping_tokens=(),
                accepted=True,
                reason="cross_language_article",
            )
        return ArticleRelevance(
            score=0.0,
            title_tokens=tuple(sorted(title_tokens)),
            overlapping_tokens=(),
            accepted=False,
            reason="root_page_has_no_title_signal",
        )

    cross_language = bool(
        (_LATIN_RE.search(title) and _CJK_RE.search(article_text))
        or (_CJK_RE.search(title) and _LATIN_RE.search(article_text))
    )
    accepted = cross_language or score >= min_score
    reason = (
        "cross_language_article"
        if cross_language
        else ("title_signal_ok" if accepted else "article_has_no_title_signal")
    )
    return ArticleRelevance(
        score=round(score, 4),
        title_tokens=tuple(sorted(title_tokens)),
        overlapping_tokens=overlap,
        accepted=accepted,
        reason=reason,
    )
