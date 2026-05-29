"""Content I/O: save/load ContentPackage with enrichment overlay."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.core.models import ContentComment, ContentItem, ContentPackage
from src.utils.logger import setup_logger


# ── Enrichment overlay fields ──────────────────────────────────────────

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


# ── ContentPreparer ────────────────────────────────────────────────────


class ContentPreparer:
    def __init__(self, config: dict, debug: bool = False):
        self.config = config
        self.debug = debug
        log_level = config.get("logging", {}).get("level")
        self.logger = setup_logger(__name__, debug=debug, level=log_level)

    def save_content(self, content: ContentPackage, date: str) -> None:
        content_path = Path(f"data/{date}/content.json")
        content_path.parent.mkdir(parents=True, exist_ok=True)

        content_dict = asdict(content)

        with open(content_path, "w", encoding="utf-8") as f:
            json.dump(content_dict, f, ensure_ascii=False, indent=2)

        self.logger.info(f"Saved content to {content_path}")

    def load_content(self, date: str) -> ContentPackage:
        content_path = Path(f"data/{date}/content.json")
        if not content_path.exists():
            raise FileNotFoundError(f"Content file not found: {content_path}")

        try:
            with open(content_path, "r", encoding="utf-8") as f:
                content_dict = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Content file {content_path} contains invalid JSON: {e}"
            ) from e

        try:
            items = []
            for item_dict in content_dict["items"]:
                comments = [
                    ContentComment(
                        author=c.get("author", ""),
                        content=c.get("content", ""),
                        content_cn=c.get("content_cn"),
                        source_id=c.get("source_id"),
                        upvotes=c.get("upvotes"),
                        depth=c.get("depth"),
                        published_at=c.get("published_at"),
                        sentiment=c.get("sentiment"),
                        quality_score=c.get("quality_score"),
                    )
                    for c in item_dict.get("comments", [])
                ]
                items.append(
                    ContentItem(
                        source=item_dict.get("source", ""),
                        source_id=item_dict.get("source_id", ""),
                        title=item_dict.get("title", ""),
                        url=item_dict.get("url"),
                        title_cn=item_dict.get("title_cn"),
                        score=item_dict.get("score"),
                        comment_count=item_dict.get("comment_count"),
                        published_at=item_dict.get("published_at", 0),
                        comments=comments,
                        article_text=item_dict.get("article_text"),
                        article_images=item_dict.get("article_images", []),
                        image_candidates=item_dict.get("image_candidates", []),
                        article_summary=item_dict.get("article_summary"),
                        editor_angle=item_dict.get("editor_angle"),
                        dek=item_dict.get("dek"),
                        key_points=item_dict.get("key_points"),
                        keywords=item_dict.get("keywords"),
                        category=item_dict.get("category"),
                        why_it_matters=item_dict.get("why_it_matters"),
                        logo_image=item_dict.get("logo_image"),
                        screenshot_image=item_dict.get("screenshot_image"),
                        enrichment_source=item_dict.get("enrichment_source"),
                        enrichment_error=item_dict.get("enrichment_error"),
                    )
                )

            return ContentPackage(
                date=content_dict["date"],
                items=items,
                deep_dive_indices=content_dict.get("deep_dive_indices", []),
                brief_indices=content_dict.get("brief_indices", []),
                quick_news_indices=content_dict.get("quick_news_indices", []),
            )
        except (KeyError, TypeError) as e:
            raise ValueError(
                f"Content file {content_path} has unexpected structure: {e}"
            ) from e


# ── Enrichment overlay ─────────────────────────────────────────────────


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
    """Merge enrichment/editor data into content in place."""
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
