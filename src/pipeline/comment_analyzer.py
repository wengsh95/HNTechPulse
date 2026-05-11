"""
Comment analysis pipeline step.
Performs VADER sentiment analysis and heuristic quality scoring.
Results cached to data/{date}/comment_analysis.json.
"""

import json
from pathlib import Path
from typing import List

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from src.core.models import ContentComment, ContentItem, ContentPackage
from src.pipeline.comment_selection import clean_comment_text, compute_comment_quality
from src.utils.logger import setup_logger


class CommentAnalyzer:
    def __init__(self, config: dict, debug: bool = False):
        self.config = config
        analyze_cfg = config.get("analyze", {})
        self.enabled = analyze_cfg.get("enabled", True)
        self.min_quality_score = analyze_cfg.get("min_quality_score", 0.1)
        self.max_keywords = analyze_cfg.get("max_keywords_per_comment", 5)
        self.max_comments_for_llm = analyze_cfg.get("max_comments_for_llm", 10)
        log_level = config.get("logging", {}).get("level")
        self.logger = setup_logger(__name__, debug=debug, level=log_level)
        self._vader = SentimentIntensityAnalyzer()

    def analyze(self, content: ContentPackage, date: str) -> ContentPackage:
        if not self.enabled:
            self.logger.info("Analyze step disabled, skipping")
            return content

        cache_path = Path(f"data/{date}/comment_analysis.json")
        if cache_path.exists():
            self.logger.info(f"Loading analysis from cache: {cache_path}")
            self._load_from_cache(content, cache_path)
            return content

        self.logger.info(f"Analyzing comments for {len(content.items)} stories...")
        total_comments = 0
        for item in content.items:
            self._analyze_item(item)
            total_comments += len(item.comments)

        self.logger.info(
            f"Analyzed {total_comments} comments across {len(content.items)} stories"
        )
        self._save_cache(content, cache_path)
        return content

    def _analyze_item(self, item: ContentItem) -> None:
        # 1. VADER sentiment
        for comment in item.comments:
            if comment.content:
                scores = self._vader.polarity_scores(clean_comment_text(comment.content))
                comment.sentiment = round(scores["compound"], 4)

        # 2. Heuristic quality scoring
        for comment in item.comments:
            comment.quality_score = self._compute_quality_score(comment, item)

    def _compute_quality_score(self, comment: ContentComment, item: ContentItem = None) -> float:
        return compute_comment_quality(comment, item)

    def get_top_comments(self, item: ContentItem, n: int = None) -> List[ContentComment]:
        if n is None:
            n = self.max_comments_for_llm
        scored = [
            c for c in item.comments
            if (c.quality_score or 0) >= self.min_quality_score
        ]
        scored.sort(key=lambda c: c.quality_score or 0, reverse=True)
        return scored[:n]

    def _save_cache(self, content: ContentPackage, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"date": content.date, "items": []}
        for item in content.items:
            item_data = {
                "source_id": item.source_id,
                "comments": [
                    {
                        "source_id": c.source_id,
                        "sentiment": c.sentiment,
                        "quality_score": c.quality_score,
                    }
                    for c in item.comments
                ],
            }
            data["items"].append(item_data)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.logger.info(f"Saved analysis cache to {path}")

    def _load_from_cache(self, content: ContentPackage, path: Path) -> None:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        items_by_id = {item.source_id: item for item in content.items}
        for item_data in data.get("items", []):
            item = items_by_id.get(item_data["source_id"])
            if item is None:
                continue
            comments_by_id = {
                c.source_id: c
                for c in item.comments
                if c.source_id
            }
            for i, c_data in enumerate(item_data.get("comments", [])):
                comment = None
                source_id = c_data.get("source_id")
                if source_id:
                    comment = comments_by_id.get(str(source_id))
                elif i < len(item.comments):
                    comment = item.comments[i]
                if comment is not None:
                    comment.sentiment = c_data.get("sentiment")
                    comment.quality_score = c_data.get("quality_score")
