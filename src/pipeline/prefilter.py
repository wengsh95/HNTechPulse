import json
from pathlib import Path
from typing import Any

from src.core.models import ContentPackage
from src.utils.logger import setup_logger

_CACHE_SCHEMA_VERSION = 5


def _prompt_hash() -> str:
    """Hash the prefilter prompt template to detect changes."""
    import hashlib

    prompt_path = Path("prompts/prefilter.md")
    if not prompt_path.exists():
        return ""
    return hashlib.md5(prompt_path.read_text(encoding="utf-8").encode()).hexdigest()[:8]


# Number of top-level comments to include per story for topic detection
_PREFILTER_COMMENT_COUNT = 5


class Prefilter:
    def __init__(self, llm_provider, config, debug=False):
        self.llm_provider = llm_provider
        self.config = config
        prefilter_cfg = config.get("prefilter", {})
        self.enabled = prefilter_cfg.get("enabled", True)
        self.batch_size = prefilter_cfg.get("batch_size", 30)
        self.min_keep = prefilter_cfg.get("min_keep", 5)
        log_level = config.get("logging", {}).get("level")
        self.logger = setup_logger(__name__, debug=debug, level=log_level)

    def filter(self, content: ContentPackage, date: str) -> ContentPackage:
        if not self.enabled:
            self.logger.info("Prefilter disabled, skipping")
            return content

        if not content.items:
            self.logger.info("No stories to prefilter")
            return content

        self.logger.info(
            f"Prefiltering {len(content.items)} stories for tech relevance"
        )

        cache_meta = self._cache_meta(content)

        # Load cache
        cached = self._load_cache(date, cache_meta)
        if cached is not None:
            self.logger.info("Loaded prefilter from cache")
            decisions = cached
        else:
            decisions = self._run_llm(content.items)
            self._save_cache(date, decisions, cache_meta)

        self._apply_editorial_signals(content.items, decisions)

        # Apply decisions
        keep_ids = self._resolve_keep_set(content.items, decisions)
        original_count = len(content.items)
        content.items = [item for item in content.items if item.source_id in keep_ids]
        filtered_count = original_count - len(content.items)
        self.logger.info(
            f"Prefilter result: kept {len(content.items)}, removed {filtered_count}"
        )

        # Filter by minimum newsworthiness (话题度门槛)
        prefilter_cfg = self.config.get("prefilter", {})
        min_nw = prefilter_cfg.get("min_newsworthiness", 3)
        before_nw = len(content.items)
        content.items = [
            item
            for item in content.items
            if (decisions.get(str(item.source_id), {}).get("newsworthiness") or 0)
            >= min_nw
        ]
        nw_filtered = before_nw - len(content.items)
        if nw_filtered:
            self.logger.info(
                f"Newsworthiness filter (min={min_nw}): removed {nw_filtered}, "
                f"remaining {len(content.items)}"
            )

        # Sort by composite score: ai_relevance*2 + newsworthiness (higher = better)
        # Tiebreaker: HN score (higher = better)
        def _composite_key(item):
            return (-(item.editorial_score or 0), -(item.score or 0))

        content.items = sorted(content.items, key=_composite_key)

        # Cap to target_story_count (items already sorted by priority then score)
        target_count = self.config.get("pipeline", {}).get("target_story_count", 10)
        if len(content.items) > target_count:
            self.logger.info(
                f"Capping from {len(content.items)} to {target_count} stories"
            )
            content.items = content.items[:target_count]

        # Rebuild indices
        self._rebuild_indices(content)

        return content

    @staticmethod
    def _editorial_score(decision: dict) -> float:
        ai = decision.get("ai_relevance") or 0
        nw = decision.get("newsworthiness") or 0
        return float(ai * 2 + nw)

    def _apply_editorial_signals(self, items, decisions: dict) -> None:
        for item in items:
            decision = decisions.get(str(item.source_id), {})
            item.ai_relevance = decision.get("ai_relevance")
            item.newsworthiness = decision.get("newsworthiness")
            item.prefilter_reason = decision.get("reason") or ""
            item.editorial_score = self._editorial_score(decision)

    def _run_llm(self, items):
        stories = [
            (
                i,
                item.title or "",
                item.url or "",
                self._extract_comment_texts(item),
            )
            for i, item in enumerate(items)
        ]

        self.logger.info(
            f"Prefilter: scoring {len(stories)} stories in one batched call"
        )

        raw = self.llm_provider.prefilter_stories(stories)
        by_index = {d.get("index"): d for d in raw if d.get("index") is not None}

        decisions = {}
        for i, item in enumerate(items):
            d = by_index.get(i, {})
            decisions[str(item.source_id)] = {
                "keep": bool(d.get("keep", True)),
                "reason": d.get("reason", ""),
                "ai_relevance": d.get("ai_relevance"),
                "newsworthiness": d.get("newsworthiness"),
            }
        return decisions

    @staticmethod
    def _extract_comment_texts(item) -> list[str]:
        """Extract top N top-level (depth=1) comment texts for topic detection."""
        import re

        comments = []
        for c in item.comments:
            if c.depth and c.depth > 1:
                continue
            # Strip HTML tags for cleaner text
            text = re.sub(r"<[^>]+>", "", c.content or "")
            text = text.strip()
            if text:
                comments.append(text)
            if len(comments) >= _PREFILTER_COMMENT_COUNT:
                break
        return comments

    def _resolve_keep_set(self, items, decisions):
        keep_ids = set()
        for item in items:
            sid = str(item.source_id)
            d = decisions.get(sid)
            if d and d.get("keep"):
                keep_ids.add(item.source_id)

        # Safety valve: ensure min_keep
        if len(keep_ids) < self.min_keep:
            self.logger.warning(
                f"Only {len(keep_ids)} stories passed filter, "
                f"applying min_keep={self.min_keep}"
            )
            # Keep top-N by score
            sorted_items = sorted(items, key=lambda x: x.score or 0, reverse=True)
            for item in sorted_items[: self.min_keep]:
                keep_ids.add(item.source_id)

        return keep_ids

    def _rebuild_indices(self, content: ContentPackage):
        pipeline_cfg = self.config.get("pipeline", {})
        num_deep_dive = pipeline_cfg.get("target_story_count", 3)
        n = len(content.items)
        content.deep_dive_indices = list(range(min(num_deep_dive, n)))
        content.brief_indices = list(range(num_deep_dive, n))

    def _cache_meta(self, content: ContentPackage) -> dict[str, Any]:
        return {
            "prompt_hash": _prompt_hash(),
            "config_fingerprint": self._config_fingerprint(),
            "input_fingerprint": self._input_fingerprint(content),
        }

    def _config_fingerprint(self) -> str:
        import hashlib

        prefilter_cfg = self.config.get("prefilter", {})
        llm_cfg = self.config.get("llm", {})
        pipeline_cfg = self.config.get("pipeline", {})
        payload = {
            "provider": llm_cfg.get("provider"),
            "model": llm_cfg.get("model"),
            "temperature": prefilter_cfg.get("temperature", 0.1),
            "min_keep": prefilter_cfg.get("min_keep", self.min_keep),
            "min_newsworthiness": prefilter_cfg.get("min_newsworthiness", 3),
            "target_story_count": pipeline_cfg.get("target_story_count", 10),
            "comment_preview_enabled": prefilter_cfg.get(
                "comment_preview_enabled", True
            ),
            "comment_preview_count": prefilter_cfg.get("comment_preview_count", 5),
            "prefilter_comment_count": _PREFILTER_COMMENT_COUNT,
        }
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        return hashlib.sha256(encoded).hexdigest()[:16]

    def _input_fingerprint(self, content: ContentPackage) -> str:
        import hashlib

        payload = []
        for item in content.items:
            preview_comments = []
            for comment in item.comments[:_PREFILTER_COMMENT_COUNT]:
                preview_comments.append(
                    {
                        "id": comment.source_id,
                        "content": comment.content,
                        "depth": comment.depth,
                    }
                )
            payload.append(
                {
                    "source_id": item.source_id,
                    "title": item.title,
                    "url": item.url,
                    "score": item.score,
                    "comment_count": item.comment_count,
                    "comments_partial": item.comments_partial,
                    "preview_comments": preview_comments,
                }
            )
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        return hashlib.sha256(encoded).hexdigest()[:16]

    def _load_cache(self, date: str, expected_meta: dict[str, Any]):
        cache_path = Path(f"data/{date}/prefilter.json")
        if not cache_path.exists():
            return None
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            if data.get("schema_version") != _CACHE_SCHEMA_VERSION:
                self.logger.info("Prefilter cache schema mismatch, re-running")
                return None
            if data.get("prompt_hash") != expected_meta["prompt_hash"]:
                self.logger.info("Prefilter prompt changed, re-running")
                return None
            if data.get("config_fingerprint") != expected_meta["config_fingerprint"]:
                self.logger.info("Prefilter config changed, re-running")
                return None
            if data.get("input_fingerprint") != expected_meta["input_fingerprint"]:
                self.logger.info("Prefilter inputs changed, re-running")
                return None
            return data.get("decisions")
        except (json.JSONDecodeError, KeyError) as e:
            self.logger.warning(f"Prefilter cache corrupt: {e}")
            return None

    def _save_cache(self, date: str, decisions: dict, meta: dict[str, Any]):
        cache_path = Path(f"data/{date}/prefilter.json")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        kept = sum(1 for d in decisions.values() if d.get("keep"))
        data = {
            "schema_version": _CACHE_SCHEMA_VERSION,
            **meta,
            "date": date,
            "decisions": decisions,
            "stats": {
                "total": len(decisions),
                "kept": kept,
                "removed": len(decisions) - kept,
            },
        }
        cache_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.logger.info(f"Saved prefilter cache to {cache_path}")
