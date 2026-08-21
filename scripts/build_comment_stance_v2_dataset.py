"""Build and optionally label the story-grouped stance V2 dataset.

Examples:
  uv run python scripts/build_comment_stance_v2_dataset.py \
    --dates 2026-05-27,2026-05-28,2026-06-01,2026-06-03,2026-06-05 \
    --sample-per-story 25

  uv run python scripts/build_comment_stance_v2_dataset.py \
    --dates 2026-05-27,2026-05-28,2026-06-01,2026-06-03,2026-06-05 \
    --sample-per-story 25 --label
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline.comment.stance_v2 import (  # noqa: E402
    StanceV2Record,
    assign_splits,
    iter_story_records,
    load_records,
    sample_records,
    save_records,
)
from src.pipeline.content_io import ContentPreparer  # noqa: E402
from src.pipeline.paths import pipeline_path  # noqa: E402
from src.providers.factory import create_llm_provider  # noqa: E402
from src.providers.enricher.relevance import (  # noqa: E402
    assess_article_relevance,
)
from src.utils.config import load_config  # noqa: E402


DEFAULT_OUTPUT = Path("data/models/comment_stance_v2_dataset.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dates",
        required=True,
        help="Comma-separated dates to read from the canonical data layout",
    )
    parser.add_argument("--sample-per-story", type=int, default=25)
    parser.add_argument("--max-stories", type=int, default=40)
    parser.add_argument("--min-comments-per-story", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260817)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--label",
        action="store_true",
        help="Use the configured LLM to label records; otherwise build an unlabeled dataset",
    )
    parser.add_argument("--batch-size", type=int, default=24)
    parser.add_argument(
        "--require-context",
        action="store_true",
        help="Keep root comments and replies with persisted parent text only",
    )
    return parser.parse_args()


def _load_content(preparer: ContentPreparer, date: str):
    path = pipeline_path(date, "content.json")
    if not path.exists():
        raise FileNotFoundError(f"Content file not found for {date}: {path}")
    return preparer.load_content_path(path)


def _chunks(rows: list[StanceV2Record], size: int):
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def _item_is_usable(item) -> bool:
    if item.url and item.article_text:
        return assess_article_relevance(
            item.title,
            item.article_text,
            url=item.url,
        ).accepted
    return True


def _label_records(
    records: list[StanceV2Record],
    *,
    config: dict,
    batch_size: int,
    output: Path,
) -> None:
    provider_name = config.get("llm", {}).get("provider", "openai")
    llm = create_llm_provider(provider_name, config, debug=False)
    pending = [row for row in records if row.label is None]
    for batch_index, batch in enumerate(_chunks(pending, batch_size), start=1):
        items_json = json.dumps(
            [
                {
                    "id": row.id,
                    "story_title": row.story_title,
                    "core_claim": row.core_claim,
                    "parent_text": row.parent_text,
                    "comment_text": row.comment_text,
                }
                for row in batch
            ],
            ensure_ascii=False,
            indent=2,
        )
        result = llm.complete_prompt(
            "prompts/comment_stance_label_v2.md",
            {"items_json": items_json},
            label=f"comment_stance_v2_label_{batch_index}",
            expect_json=True,
            max_tokens=max(getattr(llm, "fast_max_tokens", 4096), 4096),
            model=getattr(llm, "fast_model", None),
            temperature=0.0,
        )
        by_id = {row.id: row for row in batch}
        seen: set[str] = set()
        for raw in result.get("labels", []) if isinstance(result, dict) else []:
            if not isinstance(raw, dict):
                continue
            record = by_id.get(str(raw.get("id") or ""))
            label = str(raw.get("stance") or "")
            if record is None or label not in {"support", "skeptic", "neutral"}:
                continue
            if record.id in seen:
                continue
            record.label = label
            record.context_sufficient = bool(raw.get("context_sufficient", True))
            try:
                record.confidence = max(0.0, min(1.0, float(raw.get("confidence"))))
            except (TypeError, ValueError):
                record.confidence = None
            record.label_source = "configured_llm"
            seen.add(record.id)
        print(f"batch={batch_index} labeled={len(seen)}/{len(batch)}")
        # Checkpoint after every successful provider response.  Labeling is an
        # intentionally resumable, potentially long-running operation.
        save_records(output, records)


def _merge_saved_labels(
    records: list[StanceV2Record],
    output: Path,
) -> None:
    """Restore labels from a previous run when the sampled IDs still match."""
    if not output.exists():
        return
    saved = load_records(output)
    by_id = {row.id: row for row in saved}
    restored = 0
    for row in records:
        previous = by_id.get(row.id)
        if previous is None or previous.label is None:
            continue
        row.label = previous.label
        row.confidence = previous.confidence
        row.label_source = previous.label_source
        row.context_sufficient = previous.context_sufficient
        restored += 1
    if restored:
        print(f"resumed_labels={restored}/{len(records)}")


def main() -> None:
    args = parse_args()
    if args.sample_per_story <= 0:
        raise SystemExit("--sample-per-story must be positive")
    if args.max_stories < 3:
        raise SystemExit("--max-stories must be at least 3")

    config = load_config()
    preparer = ContentPreparer(config)

    all_records: list[StanceV2Record] = []
    story_sizes: dict[str, int] = {}
    dates = [date.strip() for date in args.dates.split(",") if date.strip()]
    for date in dates:
        content = _load_content(preparer, date)
        for item in content.items:
            story_id = str(item.source_id or "")
            if not story_id or not _item_is_usable(item):
                continue
            rows = list(
                iter_story_records(
                    type(content)(date=content.date, items=[item]),
                    require_context=args.require_context,
                )
            )
            if len(rows) < args.min_comments_per_story:
                continue
            story_sizes[story_id] = len(rows)

    selected_story_ids = sorted(story_sizes)[: args.max_stories]
    if len(selected_story_ids) < 3:
        raise SystemExit(
            f"Only found {len(selected_story_ids)} eligible stories; need at least 3"
        )

    for date in dates:
        content = _load_content(preparer, date)
        for item in content.items:
            if str(
                item.source_id or ""
            ) not in selected_story_ids or not _item_is_usable(item):
                continue
            all_records.extend(
                iter_story_records(
                    type(content)(date=content.date, items=[item]),
                    require_context=args.require_context,
                )
            )

    records = sample_records(
        all_records,
        sample_per_story=args.sample_per_story,
        seed=args.seed,
    )
    assign_splits(records, seed=args.seed)
    if args.label:
        _merge_saved_labels(records, args.output)
        _label_records(
            records,
            config=config,
            batch_size=args.batch_size,
            output=args.output,
        )

    save_records(args.output, records)
    labeled = sum(row.label is not None for row in records)
    print(
        f"saved={args.output} records={len(records)} labeled={labeled} "
        f"stories={len({row.story_id for row in records})}"
    )


if __name__ == "__main__":
    main()
