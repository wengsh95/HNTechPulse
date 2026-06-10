"""Comment analysis pipeline: VADER sentiment, quality scoring, LLM judging, caching."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from src.core.interfaces import LLMProvider
from src.core.models import ContentComment, ContentItem, ContentPackage
from src.pipeline.comment.text import clean_comment_text
from src.pipeline.comment.scoring import compute_comment_quality
from src.pipeline.comment.selection import (
    select_discussion_profile_comments,
    select_judge_candidate_comments,
)
from src.utils.atomic_io import atomic_write_json
from src.utils.logger import setup_logger


# ── Schema versions ────────────────────────────────────────────────────

ANALYSIS_SCHEMA_VERSION = 3
JUDGEMENT_SCHEMA_VERSION = 2

DISCUSSION_MODES = {
    "debate",
    "field_notes",
    "nostalgia",
    "troubleshooting",
    "qna",
    "correction",
    "showcase",
    "low_signal",
}

COMMENT_LANES = {
    "representative",
    "counterpoint",
    "detail",
    "color",
}

_save_lock = threading.Lock()


# ── CommentAnalyzer: VADER + quality scoring ───────────────────────────


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
        """Find comment words that VADER scores as neutral but appear frequently."""
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
        for comment in item.comments:
            if comment.content:
                scores = self._vader.polarity_scores(
                    clean_comment_text(comment.content)
                )
                comment.sentiment = round(scores["compound"], 4)

        for comment in item.comments:
            comment.quality_score = compute_comment_quality(comment, item)

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
        return select_discussion_profile_comments(
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

        atomic_write_json(path, data)
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


# ── CommentJudge: LLM-based comment judging ────────────────────────────


class CommentJudge:
    def __init__(
        self,
        llm_provider: LLMProvider,
        config: dict,
        comment_analyzer=None,
        comment_refiner=None,
        debug: bool = False,
    ):
        self.llm_provider = llm_provider
        self.config = config
        self.comment_analyzer = comment_analyzer
        self.comment_refiner = comment_refiner
        analyze_cfg = config.get("analyze", {})
        self.enabled = analyze_cfg.get("comment_judge_enabled", True)
        self.max_workers = int(analyze_cfg.get("comment_judge_max_workers", 2) or 1)
        self.prompt_template_path = analyze_cfg.get(
            "comment_judge_prompt",
            "prompts/comment_analyze.md",
        )
        self.judge_candidate_count = analyze_cfg.get("max_comments_for_judge", 8)
        log_level = config.get("logging", {}).get("level")
        self.logger = setup_logger(__name__, debug=debug, level=log_level)

    def judge(self, content: ContentPackage, date: str) -> dict:
        if not self.enabled:
            raise RuntimeError(
                "Comment judge disabled — enable comment_judge_enabled or remove "
                "the script step dependency on comment judge."
            )

        stories = load_comment_judgements(date)
        cached_count = 0
        for idx, item in enumerate(content.items):
            if comment_judgement_key(item) in stories:
                cached_count += 1
                self.logger.info(
                    f"  [{idx + 1}/{len(content.items)}] comment judge cached: "
                    f"{item.source_id} {item.title[:80]}"
                )
        missing = [
            (idx, item)
            for idx, item in enumerate(content.items)
            if comment_judgement_key(item) not in stories
        ]
        if not missing:
            self.logger.info(
                f"Loading comment judgements from cache: data/{date}/comment_judgement.json"
            )
            return stories

        self.logger.info(
            f"Judging comments for {len(missing)} stories "
            f"({cached_count} cached, total={len(content.items)})..."
        )
        workers = max(1, min(self.max_workers, len(missing)))

        if workers == 1:
            self._judge_serial(content, date, missing, stories)
        else:
            self._judge_concurrent(content, date, missing, stories, workers)

        save_comment_judgements(date, stories)
        self.logger.info(f"Saved comment judgements for {len(stories)} stories")
        return stories

    def _judge_one(self, idx_item, total_items: int):
        """Judge a single story; shared by serial and concurrent paths."""
        idx, item = idx_item
        label = f"[{idx + 1}/{total_items}] {item.source_id} {item.title[:80]}"
        if not item.comments:
            raise ValueError(f"  {label}: no comments, cannot judge")
        pre_filtered = None
        if self.comment_analyzer:
            if hasattr(self.comment_analyzer, "get_judge_candidates"):
                pre_filtered = self.comment_analyzer.get_judge_candidates(
                    item, n=self.judge_candidate_count
                )
            else:
                pre_filtered = self.comment_analyzer.get_top_comments(
                    item, n=self.judge_candidate_count
                )

        # Optional: refine stance/quality/topic with cheap LLM
        if self.comment_refiner and pre_filtered:
            refinements = self.comment_refiner.refine(item, pre_filtered)
            if refinements:
                self._apply_refinements(pre_filtered, refinements)
                self.logger.info(f"  {label}: refined {len(refinements)} comments")

        self.logger.info(
            f"  {label}: judging {len(pre_filtered or item.comments)} comments "
            f"(model request starting)"
        )
        result = self.llm_provider.judge_story_comments(
            item,
            idx,
            self.prompt_template_path,
            candidates=pre_filtered,
        )
        normalized = normalize_story_judgement(result, item)
        candidate_count = len(normalized.get("quote_candidates", []) or [])
        self.logger.info(
            f"  {label}: done, candidates={candidate_count}"
        )
        return comment_judgement_key(item), normalized

    def _judge_serial(self, content, date, missing, stories) -> None:
        """Run judgement serially, checkpointing after each story."""
        total = len(content.items)
        for idx_item in missing:
            key, judgement = self._judge_one(idx_item, total)
            stories[key] = judgement
            save_comment_judgements(date, stories)
            self.logger.info(
                f"  Saved comment judgement checkpoint: {len(stories)}/{total} stories"
            )

    def _judge_concurrent(self, content, date, missing, stories, workers: int) -> None:
        """Run judgement in a thread pool; save under a lock per story."""
        total = len(content.items)
        save_lock = threading.Lock()
        save_errors: list[BaseException] = []
        llm_errors: list[tuple[int, BaseException]] = []

        with ThreadPoolExecutor(max_workers=workers) as executor:
            # Submit all work up front so every future gets a callback.
            # add_done_callback fires on the worker thread, so the lock
            # guards the concurrent writes to `stories` and the cache file.
            all_futures = [
                executor.submit(self._judge_one, idx_item, total)
                for idx_item in missing
            ]
            idx_by_future = {
                fut: idx_item[0] for fut, idx_item in zip(all_futures, missing)
            }

            def _on_done(fut):
                if fut.cancelled():
                    return
                exc = fut.exception()
                if exc is not None:
                    # Don't re-raise from the callback (Python would log
                    # it as an "exception was never retrieved" warning
                    # and other in-flight callbacks still need to land).
                    # We collect all exceptions and aggregate them after
                    # wait() drains the pool.
                    llm_errors.append((idx_by_future[fut], exc))
                    return
                key, judgement = fut.result()
                try:
                    with save_lock:
                        stories[key] = judgement
                        save_comment_judgements(date, stories)
                except Exception as save_exc:
                    # In-memory state was already updated above, but the
                    # disk checkpoint is now stale. Record and aggregate
                    # so the user sees every root cause instead of just
                    # the first one.
                    save_errors.append(save_exc)
                    return
                self.logger.info(
                    f"  Saved comment judgement checkpoint: "
                    f"{len(stories)}/{total} stories"
                )

            for fut in all_futures:
                fut.add_done_callback(_on_done)

            # Drain: wait for every future to finish so the callbacks
            # get a chance to land their writes. Without this, a future
            # whose sibling raised would have its result discarded when
            # the `with` block exits.
            wait(all_futures)

            # Aggregate all failures into a single BaseExceptionGroup.
            # Save errors take priority over LLM errors: a stale disk
            # checkpoint is harder to diagnose than a missing one.
            aggregated: list[BaseException] = []
            for err in save_errors:
                aggregated.append(err)
            for idx, err in llm_errors:
                aggregated.append(
                    RuntimeError(
                        f"judge_story_comments failed for story_index={idx}: {err}"
                    )
                )
            if aggregated:
                raise BaseExceptionGroup("comment judge failures", aggregated)

    @staticmethod
    def _apply_refinements(candidates: list, refinements: dict) -> None:
        """Apply refiner adjustments to candidate comments in-place."""
        for comment in candidates:
            cid = str(comment.source_id) if comment.source_id is not None else None
            if cid is None or cid not in refinements:
                continue
            ref = refinements[cid]
            # Adjust quality score
            adjust = ref.get("quality_adjust", 0.0)
            if adjust and comment.quality_score is not None:
                comment.quality_score = round(
                    max(0.0, min(1.0, comment.quality_score + adjust)), 4
                )


# ── Judgement normalization and cache I/O ──────────────────────────────


def judgement_cache_path(date: str) -> Path:
    return Path(f"data/{date}/comment_judgement.json")


def comment_judgement_key(item: ContentItem) -> str:
    if item.source_id is None:
        raise ValueError(
            f"Cannot key judgement on item without source_id: title={item.title!r}"
        )
    return str(item.source_id)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_candidate(raw: dict, valid_ids: set[str]) -> Optional[dict]:
    comment_id = raw.get("comment_id") or raw.get("id") or raw.get("source_id")
    if comment_id is None:
        return None
    comment_id = str(comment_id)
    if comment_id not in valid_ids:
        return None

    reject = bool(raw.get("reject_for_quote", False))
    has_viewpoint = bool(raw.get("has_viewpoint", not reject))
    score = max(0.0, min(1.0, _safe_float(raw.get("quote_score"), 0.0)))

    return {
        "comment_id": comment_id,
        "quote_score": score,
        "category": str(raw.get("category") or "viewpoint"),
        "stance": str(raw.get("stance") or "neutral"),
        "claim": str(raw.get("claim") or "")[:220],
        "role": str(raw.get("role") or raw.get("category") or "viewpoint")[:48],
        "has_viewpoint": has_viewpoint,
        "reject_for_quote": reject,
        "reason": str(raw.get("reason") or "")[:220],
    }


def _normalize_discussion_mode(value: Any) -> str:
    mode = str(value or "").strip()
    return mode if mode in DISCUSSION_MODES else "field_notes"


def _validate_claim(value: Any, max_chars: int = 50) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("comment_lanes claim is required")
    text = " ".join(text.split())
    if len(text) > max_chars:
        raise ValueError(f"comment_lanes claim exceeds {max_chars} characters: {text}")
    return text.strip("，。；：、,.!?！？;:）)]】")


def _normalize_comment_lanes(raw: dict, valid_ids: set[str]) -> dict:
    lanes: dict[str, list[dict]] = {lane: [] for lane in COMMENT_LANES}
    raw_lanes = raw.get("comment_lanes", {}) or {}
    if not isinstance(raw_lanes, dict):
        return lanes

    seen_by_lane: dict[str, set[str]] = {lane: set() for lane in COMMENT_LANES}
    for lane, entries in raw_lanes.items():
        lane_key = str(lane)
        if lane_key not in COMMENT_LANES or not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            candidate = _normalize_candidate(entry, valid_ids)
            if candidate is None:
                continue
            cid = candidate["comment_id"]
            if cid in seen_by_lane[lane_key]:
                continue
            candidate["claim"] = _validate_claim(candidate.get("claim"))
            seen_by_lane[lane_key].add(cid)
            lanes[lane_key].append(candidate)

    return lanes


def normalize_story_judgement(raw: dict, item: ContentItem) -> dict:
    """Normalize LLM comment judgement output into a canonical form."""
    valid_ids = {str(c.source_id) for c in item.comments if c.source_id is not None}
    candidates = []
    seen = set()

    comment_lanes_raw = raw.get("comment_lanes", {}) or {}
    for lane_key in COMMENT_LANES:
        for entry in comment_lanes_raw.get(lane_key, []) or []:
            if not isinstance(entry, dict):
                continue
            candidate = _normalize_candidate(entry, valid_ids)
            if candidate is None or candidate["comment_id"] in seen:
                continue
            seen.add(candidate["comment_id"])
            candidates.append(candidate)

    for entry in raw.get("quote_candidates", []) or []:
        if not isinstance(entry, dict):
            continue
        candidate = _normalize_candidate(entry, valid_ids)
        if candidate is None or candidate["comment_id"] in seen:
            continue
        seen.add(candidate["comment_id"])
        candidates.append(candidate)

    candidates.sort(key=lambda c: c.get("quote_score", 0.0), reverse=True)

    debate_focus = []
    for entry in raw.get("debate_focus", []) or []:
        if isinstance(entry, str) and entry.strip():
            debate_focus.append(entry.strip())

    stance_distribution = {}
    raw_stance = raw.get("stance_distribution", {}) or {}
    if isinstance(raw_stance, dict):
        total = sum(
            float(v)
            for v in raw_stance.values()
            if isinstance(v, (int, float)) and v > 0
        )
        if total > 0:
            stance_distribution = {
                str(k): round(float(v) / total, 4)
                for k, v in raw_stance.items()
                if isinstance(v, (int, float)) and v > 0
            }

    stance_concerns = {}
    raw_concerns = raw.get("stance_concerns", {}) or {}
    if isinstance(raw_concerns, dict):
        for k, v in raw_concerns.items():
            if isinstance(v, str) and v.strip() and k in stance_distribution:
                stance_concerns[str(k)] = v.strip()[:24]

    discussion_mode = _normalize_discussion_mode(raw.get("discussion_mode"))
    discussion_summary = str(raw.get("discussion_summary") or "").strip()[:48]
    comment_lanes = _normalize_comment_lanes(raw, valid_ids)

    return {
        "story_id": comment_judgement_key(item),
        "discussion_mode": discussion_mode,
        "discussion_summary": discussion_summary,
        "comment_lanes": comment_lanes,
        "quote_candidates": candidates,
        "debate_focus": debate_focus,
        "stance_distribution": stance_distribution,
        "stance_concerns": stance_concerns,
    }


def load_comment_judgements(date: str) -> Dict[str, dict]:
    path = judgement_cache_path(date)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("schema_version") != JUDGEMENT_SCHEMA_VERSION:
        return {}
    stories = data.get("stories", {})
    return stories if isinstance(stories, dict) else {}


def save_comment_judgements(date: str, stories: Dict[str, dict]) -> None:
    path = judgement_cache_path(date)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": JUDGEMENT_SCHEMA_VERSION,
        "stories": stories,
    }
    with _save_lock:
        atomic_write_json(path, payload)


def candidate_ids_for_story(judgement: Optional[dict], max_n: int = 3) -> List[str]:
    if not judgement:
        return []
    ids = []
    for candidate in judgement.get("quote_candidates", []) or []:
        if candidate.get("reject_for_quote"):
            continue
        if not candidate.get("has_viewpoint", True):
            continue
        comment_id = candidate.get("comment_id")
        if comment_id is None:
            continue
        ids.append(str(comment_id))
        if len(ids) >= max_n:
            break
    return ids
