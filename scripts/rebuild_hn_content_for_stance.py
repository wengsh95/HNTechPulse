"""Rebuild historical HN content.json files for stance training.

This script is intentionally narrow: it fetches historical stories from the HN
Algolia API by date, then reuses the project's Firebase comment fetcher to
attach comments. It does not call the LLM pipeline.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.models import ContentItem, ContentPackage
from src.pipeline.content_io import ContentPreparer
from src.providers.fetcher.hn_fetcher import HNFetcher
from src.utils.config import load_config


ALGOLIA_URL = "https://hn.algolia.com/api/v1/search_by_date"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dates",
        required=True,
        help="Comma-separated dates, e.g. 2026-06-01,2026-06-02",
    )
    parser.add_argument(
        "--story-limit",
        type=int,
        default=12,
        help="Stories to keep per date before comment fetching.",
    )
    parser.add_argument(
        "--min-comments",
        type=int,
        default=20,
        help="Skip stories with fewer than this many HN comments.",
    )
    parser.add_argument("--debug", action="store_true")
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=8.0,
        help="HN API connect/read timeout in seconds for this rebuild run.",
    )
    return parser.parse_args()


def date_window(date: str) -> tuple[int, int]:
    start = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())


def fetch_algolia_stories(
    date: str,
    *,
    story_limit: int,
    min_comments: int,
) -> list[ContentItem]:
    start_ts, end_ts = date_window(date)
    params = {
        "tags": "story",
        "numericFilters": (
            f"created_at_i>={start_ts},created_at_i<{end_ts},"
            f"num_comments>={min_comments}"
        ),
        "hitsPerPage": max(story_limit * 3, story_limit),
    }
    response = requests.get(ALGOLIA_URL, params=params, timeout=(10, 30))
    response.raise_for_status()
    rows = response.json().get("hits") or []

    items: list[ContentItem] = []
    seen_ids = set()
    for row in rows:
        story_id = row.get("objectID")
        title = row.get("title") or row.get("story_title") or ""
        if not story_id or not title or story_id in seen_ids:
            continue
        seen_ids.add(story_id)
        items.append(
            ContentItem(
                source="hackernews",
                source_id=str(story_id),
                title=title,
                url=row.get("url"),
                score=int(row.get("points") or 0),
                comment_count=int(row.get("num_comments") or 0),
                published_at=int(row.get("created_at_i") or 0),
                self_post_text=row.get("story_text") or None,
            )
        )
        if len(items) >= story_limit:
            break
    return items


def main() -> None:
    args = parse_args()
    config = load_config()
    config.setdefault("hn", {})["request_timeout"] = [
        args.request_timeout,
        args.request_timeout,
    ]
    fetcher = HNFetcher(config, debug=args.debug)
    preparer = ContentPreparer(config, debug=args.debug)

    for date in [d.strip() for d in args.dates.split(",") if d.strip()]:
        items = fetch_algolia_stories(
            date,
            story_limit=args.story_limit,
            min_comments=args.min_comments,
        )
        print(f"{date}: fetched {len(items)} Algolia stories", flush=True)
        content = ContentPackage(date=date, items=items)
        content = fetcher.fetch_comments(content, date)
        preparer.save_content(content, date)
        comment_total = sum(len(item.comments) for item in content.items)
        print(
            f"{date}: saved {len(content.items)} stories, {comment_total} comments",
            flush=True,
        )


if __name__ == "__main__":
    main()
