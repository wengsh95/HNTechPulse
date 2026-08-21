import json
from pathlib import Path
from typing import Any

from src.core.models import ContentPackage
from src.pipeline.paths import pipeline_path
from src.utils.logger import setup_logger

_CACHE_SCHEMA_VERSION = 14


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
        original_items = list(content.items)

        # Apply decisions
        keep_ids = self._resolve_keep_set(content.items, decisions)
        original_count = len(content.items)
        content.items = [item for item in content.items if item.source_id in keep_ids]
        filtered_count = original_count - len(content.items)
        self.logger.info(
            f"Prefilter result: kept {len(content.items)}, removed {filtered_count}"
        )

        # Editorial eligibility is resolved above. News events remain the
        # first choice, but high-value experiments, postmortems, tools,
        # research, and tech-culture stories can also pass on shareability.
        target_count = self.config.get("pipeline", {}).get("target_story_count", 10)

        if len(content.items) < target_count:
            self._backfill_after_editorial_filter(
                content,
                decisions,
                original_items=original_items,
                target_count=target_count,
            )

        # Sort by editorial score, then HN score, then source ID. The final
        # deterministic tiebreaker keeps repeated runs stable when scores tie.
        content.items = sorted(content.items, key=self._editorial_sort_key)

        # Cap to target_story_count (items already sorted by priority then score)
        if len(content.items) > target_count:
            self.logger.info(
                f"Capping from {len(content.items)} to {target_count} stories"
            )
            content.items = content.items[:target_count]

        return content

    @staticmethod
    def _editorial_score(decision: dict, weights: dict) -> float:
        nf = decision.get("news_focus") or 0
        nw = decision.get("newsworthiness") or 0
        ai = decision.get("audience_interest") or 0
        dh = decision.get("discussion_heat") or 0
        pf = decision.get("project_fit") or 0
        ar = decision.get("ai_relevance") or 0
        return float(
            nf * weights.get("news_focus", 2.0)
            + nw * weights.get("newsworthiness", 1.5)
            + ai * weights.get("audience_interest", 1.8)
            + dh * weights.get("discussion_heat", 1.2)
            + pf * weights.get("project_fit", 1.5)
            + ar * weights.get("ai_relevance", 1.5)
        )

    @staticmethod
    def _editorial_sort_key(item) -> tuple:
        return (
            -(item.editorial_score or 0),
            -(item.score or 0),
            str(item.source_id),
        )

    @staticmethod
    def _passes_news_gate(
        decision: dict, min_news_focus: int, min_newsworthiness: int
    ) -> bool:
        if not decision.get("keep"):
            return False
        return (decision.get("news_focus") or 0) >= min_news_focus and (
            decision.get("newsworthiness") or 0
        ) >= min_newsworthiness

    def _passes_editorial_gate(self, decision: dict) -> bool:
        """Accept either a timely news event or a highly shareable tech story."""
        cfg = self.config.get("prefilter", {})
        project_fit = decision.get("project_fit")
        if project_fit is None:
            return False
        if project_fit < cfg.get("min_project_fit", 3):
            return False

        if self._passes_news_gate(
            decision,
            cfg.get("min_news_focus", 4),
            cfg.get("min_newsworthiness", 3),
        ):
            return True

        if not cfg.get("allow_shareable_non_news", True):
            return False

        shareable_types = set(
            cfg.get(
                "shareable_non_news_types",
                [
                    "technical_experiment",
                    "incident_postmortem",
                    "tool_product",
                    "research_science",
                    "tech_culture",
                ],
            )
        )
        if decision.get("content_type") == "research_science" and (
            project_fit < cfg.get("min_research_project_fit", 4)
        ):
            return False
        return (
            bool(decision.get("keep"))
            and decision.get("content_type") in shareable_types
            and (decision.get("audience_interest") or 0)
            >= cfg.get("min_non_news_audience_interest", 4)
            and (decision.get("discussion_heat") or 0)
            >= cfg.get("min_non_news_discussion_heat", 3)
        )

    def _apply_editorial_signals(self, items, decisions: dict) -> None:
        weights = self._score_weights()
        for item in items:
            decision = decisions.get(str(item.source_id), {})
            item.news_focus = decision.get("news_focus")
            item.newsworthiness = decision.get("newsworthiness")
            if decision.get("category"):
                item.category = decision.get("category")
            item.editorial_score = self._editorial_score(decision, weights)

    def _score_weights(self) -> dict:
        cfg = self.config.get("prefilter", {})
        return {
            "news_focus": cfg.get("news_focus_weight", 2.0),
            "newsworthiness": cfg.get("newsworthiness_weight", 1.5),
            "audience_interest": cfg.get("audience_interest_weight", 1.8),
            "discussion_heat": cfg.get("discussion_heat_weight", 1.2),
            "project_fit": cfg.get("project_fit_weight", 1.5),
            "ai_relevance": cfg.get("ai_relevance_weight", 1.5),
        }

    def _backfill_after_editorial_filter(
        self,
        content: ContentPackage,
        decisions: dict,
        original_items: list,
        target_count: int,
    ) -> None:
        existing_ids = {item.source_id for item in content.items}
        candidates = []
        for item in original_items:
            if item.source_id in existing_ids:
                continue
            decision = decisions.get(str(item.source_id), {})
            if self._passes_editorial_gate(decision):
                candidates.append(item)

        candidates = sorted(
            candidates,
            key=self._editorial_sort_key,
        )
        needed = max(0, target_count - len(content.items))
        if needed and candidates:
            additions = candidates[:needed]
            content.items.extend(additions)
            self.logger.info(
                f"Backfilled {len(additions)} editorial candidates after filtering"
            )

    def _run_llm(self, items):
        stories = [
            (
                i,
                item.title or "",
                item.url or "",
                item.score or 0,
                item.comment_count or 0,
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
                "content_type": d.get("content_type"),
                "category": d.get("category"),
                "news_focus": d.get("news_focus"),
                "newsworthiness": d.get("newsworthiness"),
                "audience_interest": d.get("audience_interest"),
                "discussion_heat": d.get("discussion_heat"),
                "project_fit": d.get("project_fit"),
                "ai_relevance": d.get("ai_relevance"),
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
            if d and self._passes_editorial_gate(d):
                keep_ids.add(item.source_id)

        # Safety valve: report shortages, but do not lower the editorial gate.
        if len(keep_ids) < self.min_keep:
            self.logger.warning(
                f"Only {len(keep_ids)} stories passed the editorial filter; "
                f"min_keep={self.min_keep} will not lower the quality gate"
            )

        return keep_ids

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
            "min_news_focus": prefilter_cfg.get("min_news_focus", 4),
            "allow_shareable_non_news": prefilter_cfg.get(
                "allow_shareable_non_news", True
            ),
            "min_non_news_audience_interest": prefilter_cfg.get(
                "min_non_news_audience_interest", 4
            ),
            "min_non_news_discussion_heat": prefilter_cfg.get(
                "min_non_news_discussion_heat", 3
            ),
            "min_project_fit": prefilter_cfg.get("min_project_fit", 3),
            "min_research_project_fit": prefilter_cfg.get(
                "min_research_project_fit", 4
            ),
            "shareable_non_news_types": prefilter_cfg.get(
                "shareable_non_news_types",
                [
                    "technical_experiment",
                    "incident_postmortem",
                    "tool_product",
                    "research_science",
                    "tech_culture",
                ],
            ),
            "news_focus_weight": prefilter_cfg.get("news_focus_weight", 2.0),
            "newsworthiness_weight": prefilter_cfg.get("newsworthiness_weight", 1.5),
            "audience_interest_weight": prefilter_cfg.get(
                "audience_interest_weight", 1.8
            ),
            "discussion_heat_weight": prefilter_cfg.get("discussion_heat_weight", 1.2),
            "project_fit_weight": prefilter_cfg.get("project_fit_weight", 1.5),
            "ai_relevance_weight": prefilter_cfg.get("ai_relevance_weight", 1.5),
            "target_story_count": pipeline_cfg.get("target_story_count", 10),
            "scoring_strategy": "bilibili_shareability_editor_v2",
            "comment_preview_enabled": prefilter_cfg.get(
                "comment_preview_enabled", True
            ),
            "comment_preview_count": prefilter_cfg.get("comment_preview_count", 5),
            "prefilter_comment_count": _PREFILTER_COMMENT_COUNT,
        }
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        return hashlib.sha256(encoded).hexdigest()[:16]

    def _input_fingerprint(self, content: ContentPackage) -> str:
        """Stable identity of the prefilter input set.

        Hashes story identity plus the preview comment text sent to the LLM.
        If that preview changes, the editorial classification input changed
        too, so the cached prefilter decision must be invalidated.
        """
        import hashlib

        payload = []
        for item in content.items:
            payload.append(
                {
                    "source_id": item.source_id,
                    "title": item.title,
                    "url": item.url,
                    "score": item.score,
                    "comment_count": item.comment_count,
                    "comments_partial": item.comments_partial,
                    "preview_comments": self._extract_comment_texts(item),
                }
            )
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        return hashlib.sha256(encoded).hexdigest()[:16]

    def _load_cache(self, date: str, expected_meta: dict[str, Any]):
        cache_path = pipeline_path(date, "prefilter.json")
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
        cache_path = pipeline_path(date, "prefilter.json")
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
