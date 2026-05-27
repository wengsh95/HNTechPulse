"""
Comment analysis pipeline step.
Performs VADER sentiment analysis and heuristic quality scoring.
Results cached to data/{date}/comment_analysis.json.
"""

import json
from pathlib import Path
from typing import List, Optional

import yaml
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from src.core.models import ContentComment, ContentItem, ContentPackage
from src.pipeline.comment_selection import (
    clean_comment_text,
    compute_comment_quality,
    select_judge_candidate_comments,
)
from src.utils.logger import setup_logger


ANALYSIS_SCHEMA_VERSION = 3


class CommentAnalyzer:
    def __init__(self, config: dict, debug: bool = False):
        self.config = config
        analyze_cfg = config.get("analyze", {})
        self.enabled = analyze_cfg.get("enabled", True)
        self.min_quality_score = analyze_cfg.get("min_quality_score", 0.1)
        self.max_keywords = analyze_cfg.get("max_keywords_per_comment", 5)
        self.max_comments_for_llm = analyze_cfg.get("max_comments_for_llm", 10)
        self.judge_candidate_strategy = analyze_cfg.get(
            "judge_candidate_strategy", "balanced"
        )
        self.judge_candidate_min_quality = analyze_cfg.get(
            "judge_candidate_min_quality",
            analyze_cfg.get("judge_min_quality_score", 0.05),
        )
        self.judge_candidate_similarity_threshold = analyze_cfg.get(
            "judge_candidate_similarity_threshold", 0.62
        )
        log_level = config.get("logging", {}).get("level")
        self.logger = setup_logger(__name__, debug=debug, level=log_level)
        self._vader = SentimentIntensityAnalyzer()
        self._apply_custom_lexicon(analyze_cfg)

    def _apply_custom_lexicon(self, analyze_cfg: dict) -> None:
        lexicon_path = analyze_cfg.get(
            "custom_lexicon_path", "config/hn_sentiment_lexicon.yaml"
        )
        path = Path(lexicon_path)
        if not path.exists():
            self.logger.debug(f"Custom sentiment lexicon not found: {path}")
            return
        with open(path, "r", encoding="utf-8") as f:
            entries = yaml.safe_load(f)
        if not isinstance(entries, dict):
            return
        before = len(self._vader.lexicon)
        self._vader.lexicon.update(entries)
        added = len(entries)
        self.logger.info(
            f"Applied HN sentiment lexicon: {added} entries from {path} "
            f"(lexicon grew {before} -> {len(self._vader.lexicon)})"
        )

    _STOP_WORDS = frozenset(
        {
            "this",
            "that",
            "these",
            "those",
            "with",
            "from",
            "have",
            "been",
            "will",
            "would",
            "could",
            "should",
            "about",
            "which",
            "their",
            "there",
            "than",
            "then",
            "them",
            "they",
            "what",
            "when",
            "where",
            "does",
            "done",
            "just",
            "like",
            "also",
            "very",
            "much",
            "more",
            "most",
            "some",
            "such",
            "only",
            "even",
            "still",
            "since",
            "while",
            "after",
            "before",
            "other",
            "into",
            "over",
            "under",
            "again",
            "here",
            "being",
            "having",
            "doing",
            "going",
            "using",
            "making",
            "getting",
            "trying",
            "looking",
            "working",
            "based",
            "thing",
            "things",
            "point",
            "approach",
            "actually",
            "really",
            "already",
            "probably",
            "maybe",
            "perhaps",
            "something",
            "anything",
            "everything",
            "nothing",
            "someone",
            "anyone",
            "everyone",
        }
    )

    def detect_lexicon_gaps(
        self, content: ContentPackage, threshold: float = 0.05
    ) -> List[dict]:
        """Find comment words that VADER scores as neutral but appear frequently.

        Returns list of {word, count, avg_abs_sentiment} sorted by count desc.
        Words already in the custom lexicon or VADER's built-in lexicon are excluded.
        """
        from collections import Counter
        import re

        custom_path = Path(
            self.config.get("analyze", {}).get(
                "custom_lexicon_path", "config/hn_sentiment_lexicon.yaml"
            )
        )
        custom_words = set()
        if custom_path.exists():
            with open(custom_path, "r", encoding="utf-8") as f:
                custom_words = set(yaml.safe_load(f).keys())

        known = set(self._vader.lexicon.keys()) | custom_words
        word_re = re.compile(r"[A-Za-z][A-Za-z\-']+[A-Za-z]")
        word_counts: Counter = Counter()
        word_sentiments: dict[str, list[float]] = {}

        for item in content.items:
            for comment in item.comments:
                if not comment.content:
                    continue
                text = clean_comment_text(comment.content)
                for word in word_re.findall(text):
                    w = word.lower()
                    if w in known or w in self._STOP_WORDS or len(w) < 4:
                        continue
                    word_counts[w] += 1
                    score = self._vader.polarity_scores(w)["compound"]
                    word_sentiments.setdefault(w, []).append(abs(score))

        gaps = []
        for word, count in word_counts.most_common():
            if count < 3:
                break
            avg_abs = sum(word_sentiments[word]) / len(word_sentiments[word])
            if avg_abs < threshold:
                gaps.append(
                    {
                        "word": word,
                        "count": count,
                        "avg_abs_sentiment": round(avg_abs, 4),
                    }
                )
        return gaps

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

    def _rebuild_cache(
        self, content: ContentPackage, cache_path: Path
    ) -> ContentPackage:
        self.logger.info(f"Rebuilding analysis cache: {cache_path}")
        for item in content.items:
            self._analyze_item(item)
        self._save_cache(content, cache_path)
        return content

    def _analyze_item(self, item: ContentItem) -> None:
        # 1. VADER sentiment
        for comment in item.comments:
            if comment.content:
                scores = self._vader.polarity_scores(
                    clean_comment_text(comment.content)
                )
                comment.sentiment = round(scores["compound"], 4)

        # 2. Heuristic quality scoring
        for comment in item.comments:
            comment.quality_score = self._compute_quality_score(comment, item)

    def _compute_quality_score(
        self, comment: ContentComment, item: Optional[ContentItem] = None
    ) -> float:
        return compute_comment_quality(comment, item)

    def get_top_comments(
        self, item: ContentItem, n: Optional[int] = None
    ) -> List[ContentComment]:
        if n is None:
            n = self.max_comments_for_llm
        scored = [
            c for c in item.comments if (c.quality_score or 0) >= self.min_quality_score
        ]
        scored.sort(key=lambda c: c.quality_score or 0, reverse=True)
        return scored[:n]

    def get_judge_candidates(
        self, item: ContentItem, n: Optional[int] = None
    ) -> List[ContentComment]:
        if n is None:
            n = self.max_comments_for_llm
        if self.judge_candidate_strategy != "balanced":
            return self.get_top_comments(item, n=n)
        return select_judge_candidate_comments(
            item,
            max_n=n,
            min_quality=float(self.judge_candidate_min_quality),
            similarity_threshold=float(self.judge_candidate_similarity_threshold),
        )

    def _save_cache(self, content: ContentPackage, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        items_list: list[dict[str, object]] = []
        for item in content.items:
            item_data: dict[str, object] = {
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
            items_list.append(item_data)
        data = {
            "schema_version": ANALYSIS_SCHEMA_VERSION,
            "date": content.date,
            "items": items_list,
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.logger.info(f"Saved analysis cache to {path}")

    def _load_from_cache(self, content: ContentPackage, path: Path) -> None:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("schema_version") != ANALYSIS_SCHEMA_VERSION:
            self.logger.info(
                f"Analysis cache schema changed; ignoring stale cache: {path}"
            )
            self._rebuild_cache(content, path)
            return

        items_by_id = {item.source_id: item for item in content.items}
        for item_data in data.get("items", []):
            item = items_by_id.get(item_data["source_id"])
            if item is None:
                continue
            comments_by_id = {c.source_id: c for c in item.comments if c.source_id}
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
