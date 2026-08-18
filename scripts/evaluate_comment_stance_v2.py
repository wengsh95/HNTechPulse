"""Evaluate stance V2 with story-grouped validation and test metrics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline.comment.stance_v2 import (  # noqa: E402
    DEFAULT_EMBEDDING_MODEL,
    V2_LABELS,
    StanceV2Record,
    build_tfidf_model,
    distribution_from_probabilities,
    distribution_mae_pp,
    fit_frozen_embedding_model,
    load_records,
)
from src.utils.atomic_io import atomic_write_json  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data/models/comment_stance_v2_dataset.json"),
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=Path("data/models/comment_stance_v2_report.json"),
    )
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    return parser.parse_args()


def _labeled(rows: Sequence[StanceV2Record]) -> list[StanceV2Record]:
    return [
        row
        for row in rows
        if row.label in V2_LABELS and row.context_sufficient is not False
    ]


def _metric_payload(true: Sequence[str], pred: Sequence[str]) -> dict[str, Any]:
    precision, recall, f1, support = precision_recall_fscore_support(
        true,
        pred,
        labels=list(V2_LABELS),
        zero_division=0,
    )
    return {
        "n": len(true),
        "accuracy": round(float(accuracy_score(true, pred)), 4),
        "balanced_accuracy": round(float(balanced_accuracy_score(true, pred)), 4),
        "macro_f1": round(
            float(
                f1_score(
                    true, pred, labels=list(V2_LABELS), average="macro", zero_division=0
                )
            ),
            4,
        ),
        "per_class": {
            label: {
                "precision": round(float(p), 4),
                "recall": round(float(r), 4),
                "f1": round(float(score), 4),
                "support": int(count),
            }
            for label, p, r, score, count in zip(
                V2_LABELS, precision, recall, f1, support
            )
        },
        "confusion_matrix": confusion_matrix(
            true, pred, labels=list(V2_LABELS)
        ).tolist(),
    }


def _story_distribution_metrics(
    rows: Sequence[StanceV2Record], probabilities: np.ndarray, classes
) -> dict[str, Any]:
    story_indices: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        story_indices.setdefault(row.story_id, []).append(index)
    details = []
    maes = []
    for story_id in sorted(story_indices):
        indices = story_indices[story_id]
        actual = [rows[index].label for index in indices]
        predicted = distribution_from_probabilities(probabilities[indices], classes)
        mae = distribution_mae_pp(actual, predicted)
        maes.append(mae)
        details.append(
            {
                "story_id": story_id,
                "n": len(indices),
                "actual": {
                    label: round(actual.count(label) / len(actual), 4)
                    for label in V2_LABELS
                },
                "predicted": predicted,
                "mae_pp": round(mae, 4),
                "dominant_actual": max(V2_LABELS, key=actual.count),
                "dominant_predicted": max(predicted, key=predicted.get),
            }
        )
    if not maes:
        return {"story_count": 0, "stories": []}
    return {
        "story_count": len(maes),
        "mae_pp_mean": round(float(np.mean(maes)), 4),
        "mae_pp_median": round(float(np.median(maes)), 4),
        "mae_pp_p90": round(float(np.percentile(maes, 90)), 4),
        "mae_pp_worst": round(float(np.max(maes)), 4),
        "dominant_accuracy": round(
            float(
                np.mean(
                    [
                        row["dominant_actual"] == row["dominant_predicted"]
                        for row in details
                    ]
                )
            ),
            4,
        ),
        "stories": details,
    }


def _predict_model(model, rows: Sequence[StanceV2Record]):
    texts = [row.text for row in rows]
    probabilities = model.predict_proba(texts)
    classes = [str(value) for value in model.classes_]
    by_class = {label: index for index, label in enumerate(classes)}
    ordered = np.column_stack(
        [probabilities[:, by_class[label]] for label in V2_LABELS]
    )
    predicted = np.array([V2_LABELS[index] for index in ordered.argmax(axis=1)])
    return predicted, ordered, list(V2_LABELS)


def _evaluate_model(name: str, model, rows: Sequence[StanceV2Record]) -> dict[str, Any]:
    predicted, probabilities, classes = _predict_model(model, rows)
    true = [row.label for row in rows]
    metrics = _metric_payload(true, predicted)
    metrics["distribution"] = _story_distribution_metrics(rows, probabilities, classes)
    return {"model": name, **metrics}


def _fit_and_select(
    backend: str,
    train_rows: list[StanceV2Record],
    validation_rows: list[StanceV2Record],
    embedding_model: str,
):
    candidates = []
    for c in (0.1, 1.0, 10.0, 100.0):
        for class_weight in ("balanced", None):
            if backend == "tfidf":
                model = build_tfidf_model(c=c, class_weight=class_weight)
                model.fit(
                    [row.text for row in train_rows], [row.label for row in train_rows]
                )
            else:
                model = fit_frozen_embedding_model(
                    train_rows,
                    c=c,
                    class_weight=class_weight,
                    embedding_model_name=embedding_model,
                )
            validation = _evaluate_model("candidate", model, validation_rows)
            candidates.append((validation["macro_f1"], c, class_weight, model))
    candidates.sort(
        key=lambda row: (row[0], -row[1], row[2] != "balanced"), reverse=True
    )
    best = candidates[0]
    return best[1], best[2], best[3], candidates


def _vader_model():
    analyzer = SentimentIntensityAnalyzer()

    class VADER:
        classes_ = np.array(V2_LABELS)

        def predict(self, texts):
            return np.array(
                [
                    "support"
                    if analyzer.polarity_scores(text.split("[COMMENT]", 1)[-1])[
                        "compound"
                    ]
                    > 0.3
                    else "skeptic"
                    if analyzer.polarity_scores(text.split("[COMMENT]", 1)[-1])[
                        "compound"
                    ]
                    < -0.3
                    else "neutral"
                    for text in texts
                ]
            )

        def predict_proba(self, texts):
            output = np.zeros((len(texts), 3), dtype=float)
            for index, label in enumerate(self.predict(texts)):
                output[index, V2_LABELS.index(label)] = 1.0
            return output

    return VADER()


def main() -> None:
    args = parse_args()
    records = _labeled(load_records(args.data))
    train_rows = [row for row in records if row.split == "train"]
    validation_rows = [row for row in records if row.split == "validation"]
    test_rows = [row for row in records if row.split == "test"]
    if not train_rows or not validation_rows or not test_rows:
        raise SystemExit(
            "Dataset must contain labeled train, validation, and test stories"
        )
    if len({row.story_id for row in train_rows}) < 3:
        raise SystemExit("Training split must contain at least three stories")

    results = []
    majority = type(
        "Majority",
        (),
        {
            "classes_": np.array(V2_LABELS),
            "predict": lambda self, texts: np.array(["neutral"] * len(texts)),
            "predict_proba": lambda self, texts: np.tile(
                [0.0, 0.0, 1.0], (len(texts), 1)
            ),
        },
    )()
    results.append(_evaluate_model("majority_neutral", majority, test_rows))
    results.append(_evaluate_model("vader", _vader_model(), test_rows))

    for backend in ("tfidf", "embedding"):
        c, class_weight, _validation_model, candidates = _fit_and_select(
            backend,
            train_rows,
            validation_rows,
            args.embedding_model,
        )
        combined = train_rows + validation_rows
        if backend == "tfidf":
            model = build_tfidf_model(c=c, class_weight=class_weight)
            model.fit([row.text for row in combined], [row.label for row in combined])
        else:
            model = fit_frozen_embedding_model(
                combined,
                c=c,
                class_weight=class_weight,
                embedding_model_name=args.embedding_model,
            )
        result = _evaluate_model(backend, model, test_rows)
        result["selected_c"] = c
        result["selected_class_weight"] = class_weight or "none"
        result["validation_candidates"] = [
            {"macro_f1": score, "c": value, "class_weight": weight or "none"}
            for score, value, weight, _model in candidates
        ]
        results.append(result)

    report = {
        "schema_version": 1,
        "dataset": str(args.data),
        "train_stories": sorted({row.story_id for row in train_rows}),
        "validation_stories": sorted({row.story_id for row in validation_rows}),
        "test_stories": sorted({row.story_id for row in test_rows}),
        "test_label_counts": {
            label: sum(row.label == label for row in test_rows) for label in V2_LABELS
        },
        "results": results,
        "production_gate": {
            "macro_f1": 0.70,
            "distribution_mae_pp_mean": 5.0,
            "distribution_dominant_accuracy": 0.85,
        },
    }
    atomic_write_json(args.report_output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
