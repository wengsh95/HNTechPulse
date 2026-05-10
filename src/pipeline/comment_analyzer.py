"""
Comment analysis pipeline step.
Performs VADER sentiment analysis, heuristic quality scoring,
and TF-IDF keyword extraction. Results cached to data/{date}/comment_analysis.json.
"""

import html as _html
import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, FrozenSet, List

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from sklearn.feature_extraction.text import TfidfVectorizer

from src.core.models import ContentComment, ContentItem, ContentPackage
from src.utils.logger import setup_logger


# Tokens that should never appear as keyword tags — HTML entity fragments
# and common English function words whose TF-IDF is noise in a Chinese context.
_JUNK_TOKENS: FrozenSet[str] = frozenset({
    # HTML entity fragments
    "quot", "amp", "lt", "gt", "nbsp", "apos",
    "x27", "x2f", "x3c", "x3e", "x26",
    # Common English stop/function words
    "the", "to", "and", "it", "is", "of", "you", "that", "for",
    "in", "on", "at", "be", "this", "are", "was", "we", "all",
    "can", "an", "by", "do", "if", "no", "or", "so", "as",
    "has", "had", "but", "not", "what", "will", "from", "have",
    "with", "they", "been", "would", "there", "their", "about",
    "which", "when", "make", "like", "just", "him", "his", "her",
    "she", "them", "than", "then", "also", "very", "too", "only",
    "some", "such", "more", "its", "up", "out", "who", "how",
    "get", "got", "don", "does", "did", "should", "could", "may",
    "any", "one", "our", "your", "he", "me", "my", "am", "into",
    "over", "other", "after", "before", "most", "much", "really",
    "even", "still", "say", "said", "see", "think", "know", "well",
    "way", "now", "here", "go", "going", "ve", "re", "ll",
    # Bigram noise
    "x2f x2f", "and the", "of the", "in the", "to the", "it is",
    "it s", "that s", "don t", "doesn t", "isn t", "won t", "can t",
    "i m", "you re", "they re", "we re",
})

_TAG_STRIP_RE = re.compile(r"<[^>]*>")


def _clean_text(text: str) -> str:
    """Decode HTML entities and strip tags from comment text."""
    # Strip HTML tags (e.g., <p>, <a href=...>)
    text = _TAG_STRIP_RE.sub(" ", text)
    # Decode HTML entities like &#x27; &#x2F; &quot; &amp;
    return _html.unescape(text)


def _is_junk_token(token: str) -> bool:
    """Return True if token is meaningless as a keyword tag."""
    if len(token) <= 1:
        return True
    if token.isdigit():
        return True
    # Hex numbers like 'x27' slip through the stopword list
    if re.fullmatch(r"x[0-9a-fA-F]+", token):
        return True
    if token in _JUNK_TOKENS:
        return True
    return False


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

        # 3. TF-IDF keyword extraction (per story)
        texts = [c.content or "" for c in item.comments]
        if texts and any(t.strip() for t in texts):
            self._extract_keywords(item, texts)

        # 4. Weighted word frequencies for the story
        item.comment_word_freq = self._compute_weighted_word_freq(item)

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

    def _extract_keywords(self, item: ContentItem, texts: List[str]) -> None:
        try:
            # Clean HTML entities and tags from text before TF-IDF
            cleaned_texts = [_clean_text(t) for t in texts]
            stop_words = list(self.extra_stopwords) if self.extra_stopwords else "english"
            vectorizer = TfidfVectorizer(
                max_features=100,
                stop_words=stop_words,
                max_df=0.85,
                min_df=1,
                ngram_range=(1, 2),
            )
            tfidf_matrix = vectorizer.fit_transform(cleaned_texts)
            feature_names = vectorizer.get_feature_names_out()

            for i, comment in enumerate(item.comments):
                if i >= tfidf_matrix.shape[0]:
                    comment.keywords = []
                    continue
                row = tfidf_matrix[i].toarray()[0]
                if row.sum() == 0:
                    comment.keywords = []
                    continue
                top_indices = row.argsort()[-self.max_keywords:][::-1]
                comment.keywords = [
                    str(feature_names[j])
                    for j in top_indices
                    if row[j] > 0 and not _is_junk_token(str(feature_names[j]))
                ]
        except ValueError as e:
            self.logger.debug(f"TF-IDF failed for story {item.source_id}: {e}")
            for comment in item.comments:
                if comment.keywords is None:
                    comment.keywords = []

    def _compute_weighted_word_freq(self, item: ContentItem) -> Dict[str, float]:
        weighted_counts: Counter = Counter()
        total_weight = 0.0

        for comment in item.comments:
            weight = comment.quality_score or 0.0
            if weight <= 0:
                continue
            total_weight += weight
            if comment.keywords:
                for kw in comment.keywords:
                    weighted_counts[kw] += weight

        if total_weight == 0:
            return {}

        return {k: round(v / total_weight, 4) for k, v in weighted_counts.most_common(30)}

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
                "comment_word_freq": item.comment_word_freq,
                "comments": [
                    {
                        "sentiment": c.sentiment,
                        "quality_score": c.quality_score,
                        "keywords": c.keywords,
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
            item.comment_word_freq = item_data.get("comment_word_freq")
            for i, c_data in enumerate(item_data.get("comments", [])):
                if i < len(item.comments):
                    item.comments[i].sentiment = c_data.get("sentiment")
                    item.comments[i].quality_score = c_data.get("quality_score")
                    item.comments[i].keywords = c_data.get("keywords")
