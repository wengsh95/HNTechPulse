"""Generate LLM stance labels once, then train a reusable local classifier.

Examples:
  uv run python scripts/train_comment_stance.py --dates 2026-06-05,2026-06-07 --label --train
  uv run python scripts/train_comment_stance.py --dates 2026-06-09 --report
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline.comment.stance_classifier import (
    DEFAULT_EMBEDDING_MODEL,
    STANCE_LABELS,
    StanceExample,
    append_labeled_examples,
    configure_local_ai_environment,
    evaluate_stance_classifier,
    iter_comment_examples,
    load_labeled_examples,
    load_stance_classifier,
    save_stance_classifier,
    stance_label_path,
    stance_model_path,
    train_stance_classifier,
    write_distribution_report,
)
from src.pipeline.content_io import ContentPreparer
from src.providers.factory import create_llm_provider
from src.utils.config import load_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dates",
        required=True,
        help="Comma-separated dates to read from data/YYYY-MM-DD/content.json",
    )
    parser.add_argument("--label", action="store_true", help="Generate LLM labels")
    parser.add_argument("--train", action="store_true", help="Train local classifier")
    parser.add_argument("--report", action="store_true", help="Write stance reports")
    parser.add_argument("--limit", type=int, default=360, help="Max examples to label")
    parser.add_argument(
        "--batch-size", type=int, default=24, help="LLM labeling batch size"
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.0,
        help="Minimum LLM confidence to include when training",
    )
    parser.add_argument(
        "--backend",
        choices=("sentence-transformers", "tfidf"),
        default="sentence-transformers",
        help="Local classifier backend. sentence-transformers is more accurate; tfidf is dependency-light.",
    )
    parser.add_argument(
        "--embedding-model",
        default=DEFAULT_EMBEDDING_MODEL,
        help="Sentence-transformers model name for the embedding backend",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Report output path; default data/{date}/stance_distribution.local.json",
    )
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def load_content_for_dates(config: dict, dates: list[str]):
    preparer = ContentPreparer(config)
    return [preparer.load_content(date) for date in dates]


def select_unlabeled_examples(
    examples: Iterable[StanceExample],
    labeled_path: Path,
    limit: int,
) -> list[StanceExample]:
    labeled_ids = {example.id for example in load_labeled_examples(labeled_path)}
    by_story: dict[str, list[StanceExample]] = {}
    for example in examples:
        if example.id in labeled_ids:
            continue
        by_story.setdefault(example.story_id, []).append(example)

    selected = []
    while len(selected) < limit and by_story:
        for story_id in list(by_story):
            rows = by_story[story_id]
            if not rows:
                del by_story[story_id]
                continue
            selected.append(rows.pop(0))
            if len(selected) >= limit:
                break
    return selected


def chunks(items: list[StanceExample], size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def label_examples_with_llm(
    llm_provider,
    examples: list[StanceExample],
    *,
    batch_size: int,
) -> list[StanceExample]:
    labeled: list[StanceExample] = []
    for batch_index, batch in enumerate(chunks(examples, batch_size), start=1):
        items_json = json.dumps(
            [
                {
                    "id": example.id,
                    "text": example.text,
                }
                for example in batch
            ],
            ensure_ascii=False,
            indent=2,
        )
        result = llm_provider.complete_prompt(
            "prompts/comment_stance_label.md",
            {"items_json": items_json},
            label=f"comment_stance_label_{batch_index}",
            expect_json=True,
            max_tokens=max(llm_provider.fast_max_tokens, 4096),
            model=llm_provider.fast_model,
            temperature=0.0,
        )
        by_id = {example.id: example for example in batch}
        seen = set()
        for row in result.get("labels", []) or []:
            if not isinstance(row, dict):
                continue
            example_id = str(row.get("id") or "")
            stance = str(row.get("stance") or "")
            if example_id not in by_id or stance not in STANCE_LABELS:
                continue
            seen.add(example_id)
            confidence = _safe_float(row.get("confidence"), default=0.0)
            source = by_id[example_id]
            labeled.append(
                StanceExample(
                    id=source.id,
                    story_id=source.story_id,
                    comment_id=source.comment_id,
                    text=source.text,
                    label=stance,
                    confidence=confidence,
                )
            )
        missing = [example.id for example in batch if example.id not in seen]
        if missing:
            print(f"Batch {batch_index}: missing {len(missing)} labels")
        print(f"Batch {batch_index}: labeled {len(seen)}/{len(batch)}")
    return labeled


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def main() -> None:
    configure_local_ai_environment()
    args = parse_args()
    dates = [date.strip() for date in args.dates.split(",") if date.strip()]
    config = load_config()
    contents = load_content_for_dates(config, dates)
    examples = [
        example for content in contents for example in iter_comment_examples(content)
    ]

    labels_path = stance_label_path(config)
    model_path = stance_model_path(config)

    if args.label:
        unlabeled = select_unlabeled_examples(examples, labels_path, args.limit)
        print(f"Labeling {len(unlabeled)} examples with configured LLM")
        if unlabeled:
            llm_name = config.get("llm", {}).get("provider", "openai")
            llm_provider = create_llm_provider(llm_name, config, debug=args.debug)
            labeled = label_examples_with_llm(
                llm_provider,
                unlabeled,
                batch_size=args.batch_size,
            )
            append_labeled_examples(labels_path, labeled)
            print(f"Appended {len(labeled)} labels to {labels_path}")

    if args.train:
        labeled_examples = load_labeled_examples(labels_path)
        print(
            f"Training on {len(labeled_examples)} labeled examples from {labels_path}"
        )
        model = train_stance_classifier(
            labeled_examples,
            min_confidence=args.min_confidence,
            backend=args.backend,
            embedding_model=args.embedding_model,
        )
        save_stance_classifier(model, model_path)
        print(f"Saved classifier to {model_path}")
        print(evaluate_stance_classifier(model, labeled_examples))

    if args.report:
        model = load_stance_classifier(model_path)
        for content in contents:
            output = (
                Path(args.output)
                if args.output
                else Path(f"data/{content.date}/stance_distribution.local.json")
            )
            payload = write_distribution_report(content, model, output)
            print(f"Wrote {output}")
            for story_id, story in payload["stories"].items():
                print(story_id, story["stance_distribution"])


if __name__ == "__main__":
    main()
