"""Inspect LLM-based image selection against existing daily data.

This script is intentionally read-only with respect to daily pipeline artifacts:
it loads ``content.json`` / ``enrichment.json`` and calls ArticleEnricher's image
selection helper, but it does not rewrite ``image_selection.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.models import ContentItem
from src.pipeline.content_io import ContentPreparer
from src.providers.enricher.article_enricher import ArticleEnricher
from src.providers.factory import create_llm_provider
from src.utils.config import load_config


def _load_enrichment(date: str) -> dict[str, Any]:
    path = Path("data") / date / "enrichment.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _merge_enrichment(item: ContentItem, cached: dict[str, Any]) -> ContentItem:
    copy = deepcopy(item)
    for key in (
        "article_images",
        "article_summary",
        "editor_angle",
        "dek",
        "key_points",
        "keywords",
        "category",
        "why_it_matters",
        "logo_image",
        "screenshot_image",
        "image_candidates",
    ):
        if key in cached:
            setattr(copy, key, cached.get(key))
    return copy


def _candidate_summary(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for candidate in candidates:
        if not isinstance(candidate, dict) or not candidate.get("path"):
            continue
        rows.append(
            {
                "path": candidate.get("path"),
                "source": candidate.get("source"),
                "width": candidate.get("width"),
                "height": candidate.get("height"),
                "selection_source": candidate.get("selection_source"),
                "selection_reason": candidate.get("selection_reason"),
                "auto_selected": candidate.get("auto_selected"),
            }
        )
    return rows


def inspect_dates(
    dates: list[str],
    config_path: str,
    limit: int | None,
    source_ids: set[str] | None = None,
) -> dict[str, Any]:
    config = load_config(config_path)
    llm_name = config.get("llm", {}).get("provider", "openai")
    llm_provider = create_llm_provider(llm_name, config, debug=False)
    enricher = ArticleEnricher(llm_provider, config, debug=False)
    preparer = ContentPreparer(config)

    report: dict[str, Any] = {
        "dates": dates,
        "items": [],
        "summary": {
            "total": 0,
            "llm": 0,
            "heuristic": 0,
            "no_candidates": 0,
            "changed_from_existing_auto": 0,
        },
    }

    for date in dates:
        content_path = Path("data") / date / "content.json"
        if not content_path.exists():
            report["items"].append(
                {"date": date, "status": "missing_content", "content_path": str(content_path)}
            )
            continue
        content = preparer.load_content(date)
        enrichment = _load_enrichment(date).get("items", {})

        seen = 0
        for item in content.items:
            merged = _merge_enrichment(item, enrichment.get(str(item.source_id), {}))
            candidates = deepcopy(merged.image_candidates or [])
            if source_ids is not None and str(item.source_id) not in source_ids:
                continue
            if not candidates:
                report["summary"]["no_candidates"] += 1
                continue
            if limit is not None and seen >= limit:
                break
            seen += 1

            existing_auto = next(
                (
                    candidate.get("path")
                    for candidate in candidates
                    if isinstance(candidate, dict) and candidate.get("auto_selected")
                ),
                None,
            )
            setattr(merged, "_content_date", date)
            selected = enricher._select_image_candidate(
                merged, candidates, article_summary=merged.article_summary
            )
            selected_path = selected.get("path") if selected else None
            selection_source = selected.get("selection_source") if selected else None
            if selection_source == "llm":
                report["summary"]["llm"] += 1
            elif selection_source == "heuristic":
                report["summary"]["heuristic"] += 1
            if existing_auto and selected_path != existing_auto:
                report["summary"]["changed_from_existing_auto"] += 1

            report["summary"]["total"] += 1
            report["items"].append(
                {
                    "date": date,
                    "source_id": item.source_id,
                    "title": item.title,
                    "existing_auto": existing_auto,
                    "selected_path": selected_path,
                    "selection_source": selection_source,
                    "selection_reason": selected.get("selection_reason") if selected else None,
                    "candidates": _candidate_summary(candidates),
                }
            )

    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dates", nargs="+", required=True)
    parser.add_argument("--config", default="config/")
    parser.add_argument("--limit", type=int, default=None, help="Max selectable items per date")
    parser.add_argument("--source-ids", nargs="*", default=None)
    parser.add_argument("--output", default=None, help="Optional report JSON path")
    args = parser.parse_args()

    source_ids = set(args.source_ids) if args.source_ids else None
    report = inspect_dates(args.dates, args.config, args.limit, source_ids=source_ids)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
