"""Score the manually reviewed comment stance audit packet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils.atomic_io import atomic_write_json  # noqa: E402


GOLD_LABELS = [
    "中立",
    "质疑",
    "支持",
    "质疑",
    "质疑",
    "质疑",
    "质疑",
    "质疑",
    "质疑",
    "质疑",
    "质疑",
    "支持",
    "质疑",
    "质疑",
    "质疑",
    "中立",
    "支持",
    "支持",
    "支持",
    "质疑",
    "质疑",
    "支持",
    "中立",
    "质疑",
    "中立",
    "支持",
    "质疑",
    "支持",
    "中立",
    "中立",
    "质疑",
    "支持",
    "支持",
    "支持",
    "支持",
    "支持",
    "质疑",
    "支持",
    "质疑",
    "中立",
    "支持",
    "中立",
    "支持",
    "支持",
    "支持",
    "支持",
    "支持",
    "支持",
    "支持",
    "质疑",
    "中立",
    "支持",
    "支持",
    "支持",
    "中立",
    "中立",
    "中立",
    "质疑",
    "支持",
    "质疑",
    "支持",
    "质疑",
    "质疑",
    "中立",
    "质疑",
    "质疑",
    "中立",
    "支持",
    "质疑",
    "支持",
    "质疑",
    "中立",
    "质疑",
    "中立",
    "中立",
    "支持",
    "支持",
    "质疑",
    "支持",
    "支持",
    "支持",
    "支持",
    "支持",
    "支持",
    "中立",
    "质疑",
    "支持",
    "质疑",
    "支持",
    "支持",
    "支持",
    "支持",
    "支持",
    "质疑",
    "质疑",
    "质疑",
    "中立",
    "中立",
    "支持",
    "支持",
]
LABELS = ["支持", "质疑", "中立"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/models/comment_stance_audit_100.json")
    parser.add_argument(
        "--output", default="data/models/comment_stance_audit_100_scored.json"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    rows = payload.get("rows") or []
    if len(rows) != len(GOLD_LABELS):
        raise ValueError(
            f"manual gold labels={len(GOLD_LABELS)} but audit rows={len(rows)}"
        )

    predicted = [row.get("production_stance") for row in rows]
    if any(label not in LABELS for label in predicted):
        raise ValueError("audit packet contains missing or unknown production labels")

    for row, gold in zip(rows, GOLD_LABELS):
        row["gold_stance"] = gold

    disagreements = []
    for index, (row, gold, prediction) in enumerate(
        zip(rows, GOLD_LABELS, predicted), start=1
    ):
        if gold != prediction:
            disagreements.append(
                {
                    "row": index,
                    "comment_id": row.get("comment_id"),
                    "gold": gold,
                    "predicted": prediction,
                    "confidence": row.get("production_confidence"),
                    "text": str(row.get("comment_text") or "")[:320],
                }
            )

    report = {
        "schema_version": 1,
        "source": args.input,
        "story_id": payload.get("story_id"),
        "story_title": payload.get("story_title"),
        "n": len(rows),
        "gold_method": "manual_blind_review_by_codex",
        "accuracy": round(accuracy_score(GOLD_LABELS, predicted), 4),
        "macro_f1": round(
            f1_score(GOLD_LABELS, predicted, labels=LABELS, average="macro"),
            4,
        ),
        "confusion_matrix_order": LABELS,
        "confusion_matrix": confusion_matrix(
            GOLD_LABELS, predicted, labels=LABELS
        ).tolist(),
        "classification_report": classification_report(
            GOLD_LABELS,
            predicted,
            labels=LABELS,
            output_dict=True,
            zero_division=0,
        ),
        "disagreement_count": len(disagreements),
        "disagreements": disagreements,
        "rows": rows,
    }
    atomic_write_json(Path(args.output), report)
    print(
        json.dumps(
            {
                "output": args.output,
                "n": len(rows),
                "accuracy": report["accuracy"],
                "macro_f1": report["macro_f1"],
                "disagreement_count": len(disagreements),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
