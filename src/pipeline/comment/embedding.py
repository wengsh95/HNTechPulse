"""Embedding utilities for semantic comment similarity and relevance scoring.

Replaces word-overlap Jaccard similarity with sentence-transformer cosine
similarity for comment dedup (in selection.py) and relevance scoring
(in scoring.py).  Falls back to word overlap when embeddings are
unavailable or disabled.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Optional

import numpy as np

from src.pipeline.comment.text import clean_comment_text

if TYPE_CHECKING:
    from src.core.models import ContentComment, ContentItem, ContentPackage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Word-overlap fallback (mirrors the regex previously local to selection.py
# and scoring.py so both modules can share one copy).
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_+#.-]+")


def word_overlap_similarity(a: str, b: str) -> float:
    """Jaccard similarity on ≥4-char words — fallback when embeddings miss."""
    words_a = {w.lower() for w in _WORD_RE.findall(a) if len(w) >= 4}
    words_b = {w.lower() for w in _WORD_RE.findall(b) if len(w) >= 4}
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


# ---------------------------------------------------------------------------
# Module-level caches
# ---------------------------------------------------------------------------

# text → unit-norm embedding vector
_embedding_cache: dict[str, np.ndarray] = {}

# source_id → unit-norm context embedding (story context for relevance)
_context_cache: dict[str, np.ndarray] = {}

# Lazily-loaded model
_model = None

# Whether embedding is enabled (set by configure_embeddings)
_embedding_enabled: bool = True

_DEFAULT_MODEL_NAME = (
    "data/models/huggingface/models--sentence-transformers--all-MiniLM-L6-v2"
    "/snapshots/1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
)


def configure_embeddings(
    enabled: bool = True,
    model_name: Optional[str] = None,
) -> None:
    """Configure embedding behaviour.  Call once before the pipeline runs."""
    global _embedding_enabled
    _embedding_enabled = enabled
    if not enabled:
        return
    # Touch the model so first-run latency is paid up-front.
    _load_model(model_name)


def clear_caches() -> None:
    """Drop all in-memory embedding caches (useful between pipeline runs)."""
    _embedding_cache.clear()
    _context_cache.clear()


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------


def _load_model(model_name: Optional[str] = None):
    global _model
    if _model is not None:
        return _model
    if not _embedding_enabled:
        return None
    try:
        from sentence_transformers import SentenceTransformer
        from src.pipeline.comment.stance_classifier import (
            configure_local_ai_environment,
        )

        configure_local_ai_environment()
        name = model_name or _DEFAULT_MODEL_NAME
        _model = SentenceTransformer(name, device="cpu")
        logger.info(f"Loaded embedding model: {name}")
        return _model
    except Exception as exc:
        logger.warning(f"Embedding model load failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------


def encode_texts(texts: list[str]) -> dict[str, np.ndarray]:
    """Batch-encode *texts* into unit-norm vectors.

    Already-cached texts are skipped.  Returns ``{text: vector}`` for every
    input text.  Returns an empty dict when the model is unavailable.
    """
    if not _embedding_enabled:
        return {}

    model = _load_model()
    if model is None:
        return {}

    to_encode = [t for t in texts if t and t not in _embedding_cache]
    if to_encode:
        vectors = np.asarray(
            model.encode(
                to_encode,
                batch_size=64,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        )
        for text, vec in zip(to_encode, vectors):
            _embedding_cache[text] = vec

    return {t: _embedding_cache[t] for t in texts if t in _embedding_cache}


def get_embedding(text: str) -> Optional[np.ndarray]:
    """Return the cached embedding for *text*, or ``None`` if not cached."""
    return _embedding_cache.get(text)


# ---------------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------------


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two unit-norm vectors (dot product)."""
    return float(np.dot(a, b))


def text_similarity(a: str, b: str) -> float:
    """Semantic similarity between two texts.

    Uses cached embeddings when both texts have been encoded; falls back to
    :func:`word_overlap_similarity` otherwise.
    """
    if _embedding_enabled:
        emb_a = _embedding_cache.get(a)
        emb_b = _embedding_cache.get(b)
        if emb_a is not None and emb_b is not None:
            return cosine_similarity(emb_a, emb_b)
    return word_overlap_similarity(a, b)


# ---------------------------------------------------------------------------
# Story context helpers
# ---------------------------------------------------------------------------


def story_context_text(item: ContentItem) -> str:
    """Build a rich context string from a story for relevance scoring."""
    parts: list[str] = []
    for field in (
        item.title,
        item.title_cn or "",
        item.article_summary or "",
        item.editor_angle or "",
        item.dek or "",
        item.why_it_matters or "",
    ):
        if field:
            parts.append(field)

    key_points = item.key_points or []
    for kp in key_points:
        if isinstance(kp, dict):
            text = kp.get("text") or ""
            if text:
                parts.append(text)

    keywords = item.keywords or []
    if keywords:
        parts.append(" ".join(keywords))

    if item.category:
        parts.append(item.category)

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Warmup: pre-encode everything for a ContentPackage
# ---------------------------------------------------------------------------


def warmup_embeddings(
    content: ContentPackage,
    *,
    max_comment_chars: int = 900,
) -> int:
    """Pre-encode all comment texts and story contexts.

    Call this once in ``CommentAnalyzer.analyze()`` before scoring so that
    subsequent calls to :func:`text_similarity` (dedup) and
    :func:`embedding_relevance` (scoring) hit the cache.

    Returns the number of texts successfully encoded.
    """
    if not _embedding_enabled:
        return 0

    comment_texts: list[str] = []
    context_texts: list[str] = []
    source_id_to_context: dict[str, str] = {}

    for item in content.items:
        if item.source_id is not None:
            ctx = story_context_text(item)
            if ctx:
                source_id_to_context[str(item.source_id)] = ctx
                context_texts.append(ctx)

        for comment in item.comments:
            text = clean_comment_text(comment.content or "")
            if len(text) >= 20:
                if len(text) > max_comment_chars:
                    text = text[:max_comment_chars].rstrip()
                comment_texts.append(text)

    # Deduplicate while preserving order
    all_texts = list(dict.fromkeys(comment_texts + context_texts))
    if not all_texts:
        return 0

    result = encode_texts(all_texts)

    # Map context vectors back to source_id cache
    for sid, ctx_text in source_id_to_context.items():
        vec = _embedding_cache.get(ctx_text)
        if vec is not None:
            _context_cache[sid] = vec

    encoded = len(result)
    logger.info(
        f"Embedding warmup: encoded {encoded}/{len(all_texts)} texts "
        f"({len(comment_texts)} comments, {len(context_texts)} contexts)"
    )
    return encoded


# ---------------------------------------------------------------------------
# Relevance helpers (called from scoring.py)
# ---------------------------------------------------------------------------


def embedding_relevance(
    clean_comment_text: str,
    item: Optional[ContentItem],
    max_score: float = 0.25,
) -> Optional[float]:
    """Semantic relevance score via cosine similarity.

    Returns ``None`` when embeddings are unavailable or not cached, so the
    caller can fall back to word-overlap scoring.
    """
    if not _embedding_enabled or item is None:
        return None
    if item.source_id is None:
        return None

    comment_emb = _embedding_cache.get(clean_comment_text)
    context_emb = _context_cache.get(str(item.source_id))
    if comment_emb is None or context_emb is None:
        return None

    sim = cosine_similarity(comment_emb, context_emb)
    # Cosine similarity typically 0.1–0.7 for related text; scale to match
    # the original scoring range (capped at max_score).
    return round(min(max_score, max(0.0, sim) * max_score * 2.0), 4)
