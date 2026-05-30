import json
from pathlib import Path

from src.core.models import ContentPackage
from src.utils.logger import setup_logger

_CACHE_SCHEMA_VERSION = 1


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

        # Cap to target_story_count (items already sorted by score from fetcher)
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
        decisions = {}
        for batch_start in range(0, len(items), self.batch_size):
            batch = items[batch_start : batch_start + self.batch_size]
            stories = [
                (batch_start + i, item.title or "", item.url or "")
                for i, item in enumerate(batch)
            ]
            self.logger.info(
                f"Prefilter batch {batch_start // self.batch_size + 1}: "
                f"{len(stories)} stories"
            )
            batch_decisions = self.llm_provider.prefilter_stories(stories)
            for d in batch_decisions:
                idx = d.get("index")
                if idx is None or idx < 0 or idx >= len(batch):
                    continue
                source_id = batch[idx].source_id
                decisions[str(source_id)] = {
                    "keep": bool(d.get("keep", True)),
                    "reason": d.get("reason", ""),
                }

        # Default to keep for any item not in LLM response
        for i, item in enumerate(items):
            sid = str(item.source_id)
            if sid not in decisions:
                decisions[sid] = {"keep": True, "reason": "not in LLM response"}

        return decisions

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
