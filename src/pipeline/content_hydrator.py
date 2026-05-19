"""Build render-ready content by applying enrichment/editor data."""

import json
from pathlib import Path
from typing import Any

from src.core.models import ContentPackage
from src.pipeline.content_preparer import ContentPreparer


ENRICHMENT_FIELDS = (
    "article_text",
    "article_summary",
    "editor_angle",
    "dek",
    "key_points",
    "keywords",
    "category",
    "why_it_matters",
    "logo_image",
    "screenshot_image",
    "enrichment_source",
    "enrichment_error",
)


def load_hydrated_content(date: str, config: dict, logger=None) -> ContentPackage:
    """Load content.json and apply enrichment.json as render-time overrides."""
    content = ContentPreparer(config).load_content(date)
    merge_enrichment_into_content(content, date, logger=logger)
    return content


def merge_enrichment_into_content(
    content: ContentPackage | None,
    date: str,
    logger=None,
) -> ContentPackage | None:
    """Merge enrichment/editor data into content in place.

    The editor writes image ordering and uploaded image candidates to
    enrichment.json. Treat that file as the latest render-time overlay while
    keeping content.json as the base snapshot.
    """
    if content is None:
        return None

    enrichment_path = Path(f"data/{date}/enrichment.json")
    if not enrichment_path.exists():
        return content

    try:
        enrich_data = json.loads(enrichment_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        if logger:
            logger.info(f"Failed to load enrichment overlay {enrichment_path}: {e}")
        return content

    enrich_items = enrich_data.get("items", {})
    if not isinstance(enrich_items, dict):
        return content

    for item in content.items:
        entry = enrich_items.get(str(item.source_id))
        if not isinstance(entry, dict):
            continue
        _merge_enrichment_entry(item, entry)

    return content


def _merge_enrichment_entry(item: Any, entry: dict) -> None:
    for field in ENRICHMENT_FIELDS:
        if field not in entry:
            continue
        value = entry.get(field)
        if value not in (None, "", []):
            setattr(item, field, value)

    article_images = entry.get("article_images")
    if isinstance(article_images, list):
        item.article_images = _merge_unique_strings(
            article_images,
            getattr(item, "article_images", []) or [],
        )

    image_candidates = entry.get("image_candidates")
    if isinstance(image_candidates, list) and image_candidates:
        item.image_candidates = image_candidates


def _merge_unique_strings(primary: list, secondary: list) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in [*primary, *secondary]:
        if not isinstance(value, str) or not value or value in seen:
            continue
        seen.add(value)
        merged.append(value)
    return merged
