"""Generate a blind-review packet for production comment stance labels."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline.comment.judge import CommentAnalyzer  # noqa: E402
from src.pipeline.comment.selection import (  # noqa: E402
    select_distribution_comments,
)
from src.pipeline.content_io import ContentPreparer  # noqa: E402
from src.providers.factory import create_llm_provider  # noqa: E402
from src.utils.atomic_io import atomic_write_json  # noqa: E402
from src.utils.config import load_config  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--content", required=True, help="content.json path")
    parser.add_argument("--story-id", required=True)
    parser.add_argument("--sample", type=int, default=100)
    parser.add_argument(
        "--output",
        default="data/models/comment_stance_audit_100.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    config.setdefault("logging", {})["level"] = "ERROR"
    config.setdefault("analyze", {})["embedding_enabled"] = False

    content = ContentPreparer(config).load_content_path(Path(args.content))
    item_index, item = next(
        (index, candidate)
        for index, candidate in enumerate(content.items)
        if str(candidate.source_id) == str(args.story_id)
    )
    analyzer = CommentAnalyzer(config)
    analyzer._analyze_item(item)
    all_eligible = select_distribution_comments(item, max_n=100000)
    sample = select_distribution_comments(item, max_n=max(1, args.sample))

    provider = create_llm_provider(
        config.get("llm", {}).get("provider", "openai"), config
    )
    labels = []
    for batch_index, start in enumerate(range(0, len(sample), 40)):
        batch = sample[start : start + 40]
        result = provider.judge_story_comment_stances(
            item,
            item_index,
            batch,
            "prompts/comment_distribution.md",
            batch_index=batch_index,
        )
        labels.extend(result.get("stance_labels", []) or [])

    labels_by_id = {
        str(label.get("comment_id")): label
        for label in labels
        if isinstance(label, dict) and label.get("comment_id") is not None
    }
    rows = []
    for comment in sample:
        comment_id = str(comment.source_id)
        label = labels_by_id.get(comment_id, {})
        rows.append(
            {
                "story_id": str(item.source_id),
                "story_title": item.title,
                "discussion_target": item.editor_angle
                or item.why_it_matters
                or item.title,
                "comment_id": comment_id,
                "comment_text": comment.content,
                "parent_text": comment.parent_text,
                "production_stance": label.get("stance"),
                "production_confidence": label.get("confidence"),
                "production_context_sufficient": label.get("context_sufficient"),
                "gold_stance": None,
                "gold_note": "",
            }
        )

    payload = {
        "schema_version": 1,
        "story_id": str(item.source_id),
        "story_title": item.title,
        "eligible_count": len(all_eligible),
        "sample_count": len(sample),
        "labeled_count": len(labels_by_id),
        "instructions": (
            "Fill gold_stance by independently judging whether each comment "
            "supports, questions, or is neutral toward discussion_target."
        ),
        "rows": rows,
    }
    atomic_write_json(Path(args.output), payload)
    print(
        json.dumps(
            {
                "output": args.output,
                "story_id": str(item.source_id),
                "eligible_count": len(all_eligible),
                "sample_count": len(sample),
                "labeled_count": len(labels_by_id),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
