"""Versioned stance dataset and model utilities.

The original stance model was trained on comments from only a handful of
stories and was evaluated on its training rows.  This module keeps the V2
dataset format and frozen-embedding baseline separate until it passes a
story-grouped holdout evaluation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import random
from typing import Any, Iterable, Sequence

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from src.core.models import ContentItem, ContentPackage
from src.pipeline.comment.stance_classifier import (
    DEFAULT_EMBEDDING_MODEL,
    STANCE_LABELS,
    configure_local_ai_environment,
    embedding_ready_text,
)
from src.pipeline.comment.text import clean_comment_text, is_resource_pointer_comment


V2_SCHEMA_VERSION = 1
V2_MODEL_SCHEMA_VERSION = 1
V2_LABELS = tuple(STANCE_LABELS)


@dataclass
class StanceV2Record:
    id: str
    story_id: str
    comment_id: str
    story_title: str
    core_claim: str
    comment_text: str
    parent_id: str | None = None
    parent_text: str | None = None
    depth: int | None = None
    context_sufficient: bool | None = None
    label: str | None = None
    confidence: float | None = None
    label_source: str | None = None
    split: str | None = None

    @property
    def text(self) -> str:
        return build_v2_input(
            self.story_title,
            self.core_claim,
            self.comment_text,
            parent_text=self.parent_text,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean(value: Any, limit: int = 0) -> str:
    text = clean_comment_text(str(value or "")).strip()
    if limit and len(text) > limit:
        return text[:limit].rstrip()
    return text


def core_claim_for_item(item: ContentItem, max_chars: int = 280) -> str:
    """Build a deterministic claim from already-enriched story fields.

    The claim is deliberately conservative: it does not invent a new fact and
    prefers the editor's existing angle over a long article summary.  A later
    dataset pass may replace this with an independently reviewed claim.
    """
    candidates = (
        item.editor_angle,
        item.why_it_matters,
        item.dek,
        item.article_summary,
        item.title,
    )
    for value in candidates:
        claim = _clean(value, max_chars)
        if claim:
            return claim
    return "该条 Hacker News 内容值得社区讨论"


def build_v2_input(
    story_title: str,
    core_claim: str,
    comment_text: str,
    *,
    parent_text: str | None = None,
) -> str:
    parts = [
        f"[STORY TITLE]\n{_clean(story_title, 220)}\n\n"
        f"[CORE CLAIM]\n{_clean(core_claim, 280)}\n\n"
    ]
    if parent_text:
        parts.append(f"[PARENT COMMENT]\n{_clean(parent_text, 420)}\n\n")
    parts.append(f"[COMMENT]\n{_clean(comment_text, 900)}")
    return "".join(parts).strip()


def make_record(
    story_id: str,
    comment_id: str,
    story_title: str,
    core_claim: str,
    comment_text: str,
    parent_id: str | None = None,
    parent_text: str | None = None,
    depth: int | None = None,
) -> StanceV2Record:
    clean_text = _clean(comment_text, 900)
    return StanceV2Record(
        id=f"{story_id}:{comment_id}",
        story_id=str(story_id),
        comment_id=str(comment_id),
        story_title=_clean(story_title, 220),
        core_claim=_clean(core_claim, 280),
        comment_text=clean_text,
        parent_id=str(parent_id) if parent_id is not None else None,
        parent_text=_clean(parent_text, 420) if parent_text else None,
        depth=depth,
    )


def iter_story_records(
    content: ContentPackage,
    *,
    min_chars: int = 20,
    max_chars: int = 900,
    require_context: bool = False,
) -> Iterable[StanceV2Record]:
    for item in content.items:
        if item.source_id is None:
            continue
        claim = core_claim_for_item(item)
        for comment in item.comments:
            if comment.source_id is None:
                continue
            text = _clean(comment.content, max_chars)
            if len(text) < min_chars or is_resource_pointer_comment(text):
                continue
            if require_context and comment.depth is not None and comment.depth > 1:
                if not _clean(comment.parent_text):
                    continue
            yield make_record(
                str(item.source_id),
                str(comment.source_id),
                item.title,
                claim,
                text,
                parent_id=comment.parent_id,
                parent_text=comment.parent_text,
                depth=comment.depth,
            )


def sample_records(
    records: Sequence[StanceV2Record],
    *,
    sample_per_story: int,
    seed: int,
) -> list[StanceV2Record]:
    """Sample a fixed number per story with stable ordering and seed."""
    by_story: dict[str, list[StanceV2Record]] = {}
    for record in records:
        by_story.setdefault(record.story_id, []).append(record)

    selected: list[StanceV2Record] = []
    for story_id in sorted(by_story):
        rows = sorted(by_story[story_id], key=lambda row: row.id)
        rng = random.Random(f"{seed}:{story_id}")
        if len(rows) > sample_per_story:
            rows = rng.sample(rows, sample_per_story)
        selected.extend(sorted(rows, key=lambda row: row.id))
    return selected


def split_story_ids(
    story_ids: Iterable[str],
    *,
    seed: int = 20260817,
    train_ratio: float = 0.70,
    validation_ratio: float = 0.15,
) -> dict[str, str]:
    """Assign whole stories to train/validation/test deterministically."""
    ids = sorted({str(value) for value in story_ids if str(value).strip()})
    if len(ids) < 3:
        raise ValueError("Need at least three stories for grouped splitting")
    if not 0 < train_ratio < 1 or not 0 < validation_ratio < 1:
        raise ValueError("Split ratios must be between 0 and 1")
    if train_ratio + validation_ratio >= 1:
        raise ValueError("Train and validation ratios must leave test stories")

    shuffled = list(ids)
    random.Random(seed).shuffle(shuffled)
    total = len(shuffled)
    train_count = max(1, int(round(total * train_ratio)))
    validation_count = max(1, int(round(total * validation_ratio)))
    if train_count + validation_count >= total:
        validation_count = max(1, total - train_count - 1)
    assignments: dict[str, str] = {}
    for index, story_id in enumerate(shuffled):
        if index < train_count:
            assignments[story_id] = "train"
        elif index < train_count + validation_count:
            assignments[story_id] = "validation"
        else:
            assignments[story_id] = "test"
    return assignments


def assign_splits(
    records: Iterable[StanceV2Record],
    *,
    seed: int = 20260817,
) -> list[StanceV2Record]:
    rows = list(records)
    assignments = split_story_ids((row.story_id for row in rows), seed=seed)
    for row in rows:
        row.split = assignments[row.story_id]
    return rows


def save_records(path: Path, records: Iterable[StanceV2Record]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": V2_SCHEMA_VERSION,
        "records": [record.to_dict() for record in records],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_records(path: Path) -> list[StanceV2Record]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != V2_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported stance V2 schema: {payload.get('schema_version')}"
        )
    rows = payload.get("records")
    if not isinstance(rows, list):
        raise ValueError("Stance V2 dataset must contain a records list")
    records: list[StanceV2Record] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        depth_value = row.get("depth")
        record = StanceV2Record(
            id=str(row.get("id") or ""),
            story_id=str(row.get("story_id") or ""),
            comment_id=str(row.get("comment_id") or ""),
            story_title=_clean(row.get("story_title"), 220),
            core_claim=_clean(row.get("core_claim"), 280),
            comment_text=_clean(row.get("comment_text"), 900),
            parent_id=str(row.get("parent_id")) if row.get("parent_id") else None,
            parent_text=_clean(row.get("parent_text"), 420)
            if row.get("parent_text")
            else None,
            depth=int(str(depth_value)) if depth_value is not None else None,
            context_sufficient=(
                bool(row.get("context_sufficient"))
                if row.get("context_sufficient") is not None
                else None
            ),
            label=str(row.get("label")) if row.get("label") else None,
            confidence=_safe_float(row.get("confidence")),
            label_source=str(row.get("label_source"))
            if row.get("label_source")
            else None,
            split=str(row.get("split")) if row.get("split") else None,
        )
        if not record.id or not record.story_id or not record.comment_id:
            continue
        if record.label is not None and record.label not in V2_LABELS:
            raise ValueError(f"Unknown stance V2 label: {record.label}")
        records.append(record)
    return records


def dataset_fingerprint(records: Iterable[StanceV2Record]) -> str:
    rows = [
        {
            "id": row.id,
            "story_id": row.story_id,
            "core_claim": row.core_claim,
            "comment_text": row.comment_text,
            "parent_id": row.parent_id,
            "parent_text": row.parent_text,
            "depth": row.depth,
            "context_sufficient": row.context_sufficient,
            "label": row.label,
            "split": row.split,
        }
        for row in records
    ]
    text = json.dumps(rows, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_tfidf_model(
    c: float = 1.0, class_weight: str | None = "balanced"
) -> Pipeline:
    return Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    analyzer="word",
                    ngram_range=(1, 2),
                    min_df=1,
                    max_df=0.95,
                    sublinear_tf=True,
                    strip_accents="unicode",
                ),
            ),
            (
                "clf",
                LogisticRegression(
                    max_iter=1000,
                    class_weight=class_weight,
                    C=c,
                ),
            ),
        ]
    )


class FrozenEmbeddingModel:
    """A persistable classifier over a frozen local sentence embedding."""

    def __init__(
        self,
        classifier: LogisticRegression,
        embedding_model_name: str = DEFAULT_EMBEDDING_MODEL,
    ):
        self.classifier = classifier
        self.embedding_model_name = embedding_model_name
        self._embedding_model = None

    @property
    def classes_(self):
        return self.classifier.classes_

    def _load_embedding_model(self):
        if self._embedding_model is None:
            configure_local_ai_environment()
            from sentence_transformers import SentenceTransformer

            self._embedding_model = SentenceTransformer(
                self.embedding_model_name,
                device="cpu",
            )
        return self._embedding_model

    def _encode(self, texts: Sequence[str]) -> np.ndarray:
        return np.asarray(
            self._load_embedding_model().encode(
                [embedding_ready_text(text) for text in texts],
                batch_size=64,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        )

    def predict(self, texts: Sequence[str]) -> np.ndarray:
        return self.classifier.predict(self._encode(texts))

    def predict_proba(self, texts: Sequence[str]) -> np.ndarray:
        return self.classifier.predict_proba(self._encode(texts))


def fit_frozen_embedding_model(
    records: Sequence[StanceV2Record],
    *,
    c: float = 1.0,
    class_weight: str | None = "balanced",
    embedding_model_name: str = DEFAULT_EMBEDDING_MODEL,
) -> FrozenEmbeddingModel:
    if not records:
        raise ValueError("Cannot train a stance model with no records")
    configure_local_ai_environment()
    from sentence_transformers import SentenceTransformer

    encoder = SentenceTransformer(embedding_model_name, device="cpu")
    embeddings = np.asarray(
        encoder.encode(
            [embedding_ready_text(row.text) for row in records],
            batch_size=64,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
    )
    classifier = LogisticRegression(
        max_iter=1000,
        class_weight=class_weight,
        C=c,
    )
    classifier.fit(embeddings, [row.label for row in records])
    return FrozenEmbeddingModel(classifier, embedding_model_name)


def save_frozen_embedding_model(model: FrozenEmbeddingModel, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "schema_version": V2_MODEL_SCHEMA_VERSION,
            "backend": "frozen_sentence_embedding",
            "embedding_model_name": model.embedding_model_name,
            "classifier": model.classifier,
        },
        path,
    )


def load_frozen_embedding_model(path: Path) -> FrozenEmbeddingModel:
    bundle = joblib.load(path)
    if not isinstance(bundle, dict):
        raise ValueError(f"Invalid frozen embedding model bundle: {path}")
    if bundle.get("schema_version") != V2_MODEL_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported stance V2 model schema: {bundle.get('schema_version')}"
        )
    classifier = bundle.get("classifier")
    if classifier is None or not hasattr(classifier, "predict_proba"):
        raise ValueError(f"Frozen embedding bundle has no classifier: {path}")
    return FrozenEmbeddingModel(
        classifier,
        str(bundle.get("embedding_model_name") or DEFAULT_EMBEDDING_MODEL),
    )


def distribution_from_probabilities(
    probabilities: np.ndarray,
    classes: Sequence[str],
    *,
    prior: float = 1.0,
) -> dict[str, float]:
    """Aggregate soft predictions with a small symmetric Dirichlet prior."""
    if probabilities.size == 0:
        return {}
    totals = np.full(len(V2_LABELS), float(prior), dtype=float)
    by_class = {str(label): index for index, label in enumerate(classes)}
    for target_index, label in enumerate(V2_LABELS):
        source_index = by_class.get(label)
        if source_index is not None:
            totals[target_index] += float(probabilities[:, source_index].sum())
    total = totals.sum()
    if total <= 0:
        return {}
    return {
        label: round(float(value / total), 4) for label, value in zip(V2_LABELS, totals)
    }


def distribution_mae_pp(
    actual_labels: Sequence[str], predicted: dict[str, float]
) -> float:
    if not actual_labels or not predicted:
        return math.nan
    actual = np.array(
        [actual_labels.count(label) / len(actual_labels) for label in V2_LABELS]
    )
    estimate = np.array([float(predicted.get(label, 0.0)) for label in V2_LABELS])
    return float(np.abs(actual - estimate).mean() * 100.0)


def _safe_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None
