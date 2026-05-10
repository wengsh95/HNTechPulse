"""
Comment analysis pipeline step.
Performs VADER sentiment analysis and heuristic quality scoring.
Results cached to data/{date}/comment_analysis.json.
"""

import json
import re
from pathlib import Path
from typing import List

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from src.core.models import ContentComment, ContentItem, ContentPackage
from src.utils.logger import setup_logger


class CommentAnalyzer:
    def __init__(self, config: dict, debug: bool = False):
        self.config = config
        analyze_cfg = config.get("analyze", {})
        self.enabled = analyze_cfg.get("enabled", True)
        self.min_quality_score = analyze_cfg.get("min_quality_score", 0.1)
        self.max_keywords = analyze_cfg.get("max_keywords_per_comment", 5)
        self.max_comments_for_llm = analyze_cfg.get("max_comments_for_llm", 10)
        self.extra_stopwords = set(analyze_cfg.get("stopwords", []))
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
                scores = self._vader.polarity_scores(comment.content)
                comment.sentiment = round(scores["compound"], 4)

        # 2. Heuristic quality scoring
        for comment in item.comments:
            comment.quality_score = self._compute_quality_score(comment)

    def _compute_quality_score(self, comment: ContentComment) -> float:
        text = comment.content or ""
        text_len = len(text)

        # Signal 1: HN upvotes (0-0.4 weight)
        upvotes = comment.upvotes or 0
        uv_score = min(upvotes / 50.0, 1.0) * 0.4

        # Signal 2: Text length bell curve (0-0.3 weight)
        if text_len < 20:
            len_score = 0.0
        elif text_len < 100:
            len_score = text_len / 100.0 * 0.3
        elif text_len <= 500:
            len_score = 0.3
        elif text_len <= 1000:
            len_score = (1000 - text_len) / 500.0 * 0.3
        else:
            len_score = 0.0

        # Signal 3: Code/link presence (0-0.2 weight)
        has_code = bool(re.search(r'```|`[^`]+`', text))
        has_link = bool(re.search(r'https?://', text))
        has_structured = bool(re.search(r'^\s*[-*>]\s', text, re.MULTILINE))
        if has_code or has_link:
            content_score = 0.2
        elif has_structured:
            content_score = 0.1
        else:
            content_score = 0.0

        # Signal 4: Depth/no-upvotes penalty (0-0.1 deduction)
        depth_penalty = 0.0
        if text_len < 100 and (upvotes or 0) == 0:
            depth_penalty = 0.1

        return round(max(0.0, min(1.0, uv_score + len_score + content_score - depth_penalty)), 4)

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
            for i, c_data in enumerate(item_data.get("comments", [])):
                if i < len(item.comments):
                    item.comments[i].sentiment = c_data.get("sentiment")
                    item.comments[i].quality_score = c_data.get("quality_score")
