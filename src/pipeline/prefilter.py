import json
from pathlib import Path

from src.core.models import ContentPackage
from src.utils.logger import setup_logger

_CACHE_SCHEMA_VERSION = 4


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

        # Load cache
        cached = self._load_cache(date)
        if cached is not None:
            self.logger.info("Loaded prefilter from cache")
            decisions = cached
        else:
            decisions = self._run_llm(content.items)
            self._save_cache(date, decisions)

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
            d = decisions.get(str(item.source_id), {})
            ai = d.get("ai_relevance") or 0
            nw = d.get("newsworthiness") or 0
            return (-(ai * 2 + nw), -(item.score or 0))

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

    def _load_cache(self, date: str):
        cache_path = Path(f"data/{date}/prefilter.json")
        if not cache_path.exists():
            return None
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            if data.get("schema_version") != _CACHE_SCHEMA_VERSION:
                self.logger.info("Prefilter cache schema mismatch, re-running")
                return None
            if data.get("prompt_hash") != _prompt_hash():
                self.logger.info("Prefilter prompt changed, re-running")
                return None
            return data.get("decisions")
        except (json.JSONDecodeError, KeyError) as e:
            self.logger.warning(f"Prefilter cache corrupt: {e}")
            return None

    def _save_cache(self, date: str, decisions: dict):
        cache_path = Path(f"data/{date}/prefilter.json")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        kept = sum(1 for d in decisions.values() if d.get("keep"))
        data = {
            "schema_version": _CACHE_SCHEMA_VERSION,
            "prompt_hash": _prompt_hash(),
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
