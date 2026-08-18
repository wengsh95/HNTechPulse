"""Train a V2 stance model after grouped evaluation has passed.

This command intentionally does not touch the legacy stance model.  Use the
evaluation script first to choose backend and hyperparameters.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline.comment.stance_v2 import (  # noqa: E402
    DEFAULT_EMBEDDING_MODEL,
    StanceV2Record,
    build_tfidf_model,
    fit_frozen_embedding_model,
    load_records,
    save_frozen_embedding_model,
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
        "--backend",
        choices=("tfidf", "embedding"),
        required=True,
    )
    parser.add_argument("--model-output", type=Path, required=True)
    parser.add_argument("--c", type=float, default=1.0)
    parser.add_argument(
        "--class-weight", choices=("balanced", "none"), default="balanced"
    )
    parser.add_argument("--min-confidence", type=float, default=0.0)
    parser.add_argument("--fit-splits", default="train,validation")
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    return parser.parse_args()


def _training_rows(records: list[StanceV2Record], args: argparse.Namespace):
    allowed_splits = {
        value.strip() for value in args.fit_splits.split(",") if value.strip()
    }
    rows = [
        row
        for row in records
        if row.label in {"support", "skeptic", "neutral"}
        and row.context_sufficient is not False
        and (row.confidence is None or row.confidence >= args.min_confidence)
        and (not row.split or row.split in allowed_splits)
    ]
    if len({row.label for row in rows}) < 3:
        raise SystemExit("Training data must contain all three stance labels")
    if len({row.story_id for row in rows}) < 3:
        raise SystemExit("Training data must contain at least three stories")
    return rows


def main() -> None:
    args = parse_args()
    if args.c <= 0:
        raise SystemExit("--c must be positive")
    records = load_records(args.data)
    rows = _training_rows(records, args)
    class_weight = None if args.class_weight == "none" else "balanced"
    if args.backend == "tfidf":
        model = build_tfidf_model(c=args.c, class_weight=class_weight)
        model.fit([row.text for row in rows], [row.label for row in rows])
        args.model_output.parent.mkdir(parents=True, exist_ok=True)
        import joblib

        joblib.dump(model, args.model_output)
    else:
        model = fit_frozen_embedding_model(
            rows,
            c=args.c,
            class_weight=class_weight,
            embedding_model_name=args.embedding_model,
        )
        save_frozen_embedding_model(model, args.model_output)

    atomic_write_json(
        args.model_output.with_suffix(args.model_output.suffix + ".meta.json"),
        {
            "schema_version": 1,
            "backend": args.backend,
            "c": args.c,
            "class_weight": args.class_weight,
            "min_confidence": args.min_confidence,
            "fit_splits": sorted(
                value.strip() for value in args.fit_splits.split(",") if value.strip()
            ),
            "record_count": len(rows),
            "story_count": len({row.story_id for row in rows}),
            "dataset": str(args.data),
        },
    )
    print(
        f"saved={args.model_output} backend={args.backend} "
        f"records={len(rows)} stories={len({row.story_id for row in rows})}"
    )


if __name__ == "__main__":
    main()
