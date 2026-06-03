"""Content I/O: save/load ContentPackage."""

import json
from dataclasses import asdict
from pathlib import Path

from src.core.models import ContentComment, ContentItem, ContentPackage
from src.utils.logger import setup_logger


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
            )
        except (KeyError, TypeError) as e:
            raise ValueError(
                f"Content file {content_path} has unexpected structure: {e}"
            ) from e
