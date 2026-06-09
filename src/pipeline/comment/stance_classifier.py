"""Local stance classifier trained from one-time LLM labels.

The goal is a reusable CPU classifier for comment stance bar charts. LLM labels
can be generated once with the configured provider, then this module predicts
`support` / `skeptic` / `neutral` probabilities locally for future runs.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Iterable

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.pipeline import Pipeline

from src.core.models import ContentComment, ContentItem, ContentPackage
from src.pipeline.comment.text import clean_comment_text, is_resource_pointer_comment
from src.utils.atomic_io import atomic_write_json


STANCE_LABELS = ("support", "skeptic", "neutral")
STANCE_ZH = {
    "support": "支持",
    "skeptic": "质疑",
    "neutral": "中立",
}
ZH_TO_STANCE = {value: key for key, value in STANCE_ZH.items()}
LOCAL_MODELS_DIR = Path("data/models")
LOCAL_HF_HOME = LOCAL_MODELS_DIR / "huggingface"
DEFAULT_EMBEDDING_MODEL = str(
    LOCAL_HF_HOME
    / "models--sentence-transformers--all-MiniLM-L6-v2"
    / "snapshots"
    / "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
)


def configure_local_ai_environment() -> None:
    """Keep local AI model caches under the project data/models directory."""
    cache_dir = str(LOCAL_HF_HOME)
    os.environ["HF_HOME"] = cache_dir
    os.environ["HF_HUB_CACHE"] = cache_dir
    os.environ["SENTENCE_TRANSFORMERS_HOME"] = str(
        LOCAL_MODELS_DIR / "sentence-transformers"
    )


@dataclass(frozen=True)
class StanceExample:
    id: str
    story_id: str
    comment_id: str
    text: str
    label: str | None = None
    confidence: float | None = None


class SentenceTransformerStanceClassifier:
    """Small sklearn classifier over local sentence-transformer embeddings."""

    def __init__(
        self,
        embedding_model_name: str = DEFAULT_EMBEDDING_MODEL,
        classifier: LogisticRegression | None = None,
    ):
        self.embedding_model_name = embedding_model_name
        self.classifier = classifier or LogisticRegression(
            max_iter=1000,
            class_weight="balanced",
            C=100.0,
        )
        self._embedding_model = None

    @property
    def classes_(self):
        return self.classifier.classes_

    def _load_embedding_model(self):
        if self._embedding_model is None:
            configure_local_ai_environment()
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "sentence-transformers is required for embedding stance "
                    "classification. Install dependencies with `uv sync`."
                ) from exc
            self._embedding_model = SentenceTransformer(
                self.embedding_model_name,
                device="cpu",
            )
        return self._embedding_model

    def _encode(self, texts: list[str]) -> np.ndarray:
        model = self._load_embedding_model()
        texts = [embedding_ready_text(text) for text in texts]
        return np.asarray(
            model.encode(
                texts,
                batch_size=32,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        )

    def fit(self, texts: list[str], labels: list[str]):
        self.classifier.fit(self._encode(texts), labels)
        return self

    def predict(self, texts: list[str]):
        return self.classifier.predict(self._encode(texts))

    def predict_proba(self, texts: list[str]):
        return self.classifier.predict_proba(self._encode(texts))


def stance_model_path(config: dict) -> Path:
    return Path(
        config.get("analyze", {}).get(
            "stance_classifier_path", str(LOCAL_MODELS_DIR / "comment_stance.joblib")
        )
    )


def stance_label_path(config: dict) -> Path:
    return Path(
        config.get("analyze", {}).get(
            "stance_label_path",
            str(LOCAL_MODELS_DIR / "comment_stance_labels.jsonl"),
        )
    )


def make_example_id(story_id: str, comment_id: str) -> str:
    return f"{story_id}:{comment_id}"


def story_context(item: ContentItem) -> str:
    parts = [
        item.title or "",
        item.title_cn or "",
        item.article_summary or "",
        item.editor_angle or "",
        item.dek or "",
        item.why_it_matters or "",
    ]
    key_points = item.key_points or []
    parts.extend(
        str(point.get("text") or "") for point in key_points if isinstance(point, dict)
    )
    return "\n".join(part.strip() for part in parts if part and part.strip())


def build_stance_input(item: ContentItem, comment: ContentComment) -> str:
    context = story_context(item)
    comment_text = clean_comment_text(comment.content or "")
    return (f"[STORY]\n{context}\n\n[COMMENT]\n{comment_text}").strip()


def embedding_ready_text(text: str, max_story_chars: int = 260) -> str:
    """Put comment first so short embedding models do not truncate it away."""
    marker = "[COMMENT]"
    if marker not in text:
        return text
    story, comment = text.split(marker, 1)
    story = story.replace("[STORY]", "").strip()
    comment = comment.strip()
    if story:
        return f"[COMMENT]\n{comment}\n\n[STORY]\n{story[:max_story_chars]}".strip()
    return f"[COMMENT]\n{comment}".strip()


def iter_comment_examples(
    content: ContentPackage,
    *,
    max_chars: int = 900,
    min_chars: int = 20,
    include_resource_only: bool = False,
) -> Iterable[StanceExample]:
    for item in content.items:
        if item.source_id is None:
            continue
        for comment in item.comments:
            if comment.source_id is None:
                continue
            clean = clean_comment_text(comment.content or "")
            if len(clean) < min_chars:
                continue
            if not include_resource_only and is_resource_pointer_comment(clean):
                continue
            text = build_stance_input(item, comment)
            if len(text) > max_chars:
                text = text[:max_chars].rstrip()
            story_id = str(item.source_id)
            comment_id = str(comment.source_id)
            yield StanceExample(
                id=make_example_id(story_id, comment_id),
                story_id=story_id,
                comment_id=comment_id,
                text=text,
            )


def load_labeled_examples(path: Path) -> list[StanceExample]:
    if not path.exists():
        return []
    examples: list[StanceExample] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            label = str(row.get("label") or row.get("stance") or "")
            if label not in STANCE_LABELS:
                continue
            examples.append(
                StanceExample(
                    id=str(row["id"]),
                    story_id=str(row.get("story_id") or ""),
                    comment_id=str(row.get("comment_id") or ""),
                    text=str(row["text"]),
                    label=label,
                    confidence=_safe_float(row.get("confidence")),
                )
            )
    return examples


def append_labeled_examples(path: Path, examples: Iterable[StanceExample]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_ids = {example.id for example in load_labeled_examples(path)}
    rows = []
    for example in examples:
        if example.label not in STANCE_LABELS or example.id in existing_ids:
            continue
        rows.append(
            json.dumps(
                {
                    "id": example.id,
                    "story_id": example.story_id,
                    "comment_id": example.comment_id,
                    "text": example.text,
                    "label": example.label,
                    "confidence": example.confidence,
                },
                ensure_ascii=False,
            )
        )
        existing_ids.add(example.id)
    if not rows:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(rows) + "\n")


def train_stance_classifier(
    examples: list[StanceExample],
    *,
    min_confidence: float = 0.0,
    backend: str = "tfidf",
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
):
    trainable = [
        example
        for example in examples
        if example.label in STANCE_LABELS
        and (example.confidence is None or example.confidence >= min_confidence)
    ]
    labels = {example.label for example in trainable}
    if len(labels) < 2:
        raise ValueError("Need at least two stance labels to train classifier")
    if len(trainable) < 12:
        raise ValueError("Need at least 12 labeled examples to train classifier")

    texts = [example.text for example in trainable]
    y = [example.label for example in trainable]
    if backend == "sentence-transformers":
        model = SentenceTransformerStanceClassifier(
            embedding_model_name=embedding_model,
        )
        model.fit(texts, y)
        return model
    if backend != "tfidf":
        raise ValueError(
            "Unknown stance classifier backend. Use 'tfidf' or 'sentence-transformers'."
        )

    model = Pipeline(
        steps=[
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
                    class_weight="balanced",
                ),
            ),
        ]
    )
    model.fit(texts, y)
    return model


def save_stance_classifier(model: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)


def load_stance_classifier(path: Path) -> Any:
    return joblib.load(path)


def evaluate_stance_classifier(model: Any, examples: list[StanceExample]) -> str:
    labeled = [example for example in examples if example.label in STANCE_LABELS]
    if not labeled:
        return ""
    predicted = model.predict([example.text for example in labeled])
    return classification_report(
        [example.label for example in labeled],
        predicted,
        labels=list(STANCE_LABELS),
        zero_division=0,
    )


def predict_comment_probs(model: Any, text: str) -> dict[str, float]:
    if not hasattr(model, "predict_proba"):
        label = str(model.predict([text])[0])
        return {stance: 1.0 if stance == label else 0.0 for stance in STANCE_LABELS}

    probabilities = model.predict_proba([text])[0]
    classes = [str(cls) for cls in model.classes_]
    result = {stance: 0.0 for stance in STANCE_LABELS}
    for cls, prob in zip(classes, probabilities):
        if cls in result:
            result[cls] = float(prob)
    total = sum(result.values())
    if total <= 0:
        return {stance: 1.0 / len(STANCE_LABELS) for stance in STANCE_LABELS}
    return {stance: result[stance] / total for stance in STANCE_LABELS}


def comment_weight(comment: ContentComment) -> float:
    text = clean_comment_text(comment.content or "")
    if not text or is_resource_pointer_comment(text):
        return 0.0
    weight = 1.0
    if comment.depth is not None and comment.depth >= 3:
        weight *= 0.75
    elif comment.depth is not None and comment.depth <= 1:
        weight *= 1.1
    if comment.quality_score is not None:
        if comment.quality_score < 0.08:
            weight *= 0.35
        elif comment.quality_score >= 0.35:
            weight *= 1.15
    if comment.upvotes:
        weight *= min(1.35, 1.0 + (comment.upvotes / 200.0))
    return weight


def predict_item_stance_distribution(
    model: Any,
    item: ContentItem,
) -> dict[str, float]:
    totals = {stance: 0.0 for stance in STANCE_LABELS}
    total_weight = 0.0
    for comment in item.comments:
        if comment.source_id is None:
            continue
        text = clean_comment_text(comment.content or "")
        if len(text) < 20:
            continue
        weight = comment_weight(comment)
        if weight <= 0:
            continue
        probs = predict_comment_probs(model, build_stance_input(item, comment))
        for stance, prob in probs.items():
            totals[stance] += prob * weight
        total_weight += weight
    if total_weight <= 0:
        return {}
    return {
        STANCE_ZH[stance]: round(value / total_weight, 4)
        for stance, value in totals.items()
        if value > 0
    }


def write_distribution_report(
    content: ContentPackage,
    model: Any,
    path: Path,
) -> dict:
    stories = {}
    for item in content.items:
        if item.source_id is None:
            continue
        stories[str(item.source_id)] = {
            "title": item.title,
            "stance_distribution": predict_item_stance_distribution(model, item),
        }
    payload = {"date": content.date, "stories": stories}
    atomic_write_json(path, payload)
    return payload


def _safe_float(value) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
