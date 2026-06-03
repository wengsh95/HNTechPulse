"""CommentRefiner: cheap LLM pass to refine stance, quality, and topic for pre-filtered comments.

Disabled by default. Enable via config:
    analyze:
        comment_refiner_enabled: true
        comment_refiner_model: "qwen3.5-flash"  # optional, defaults to fast_model
"""

import json
from typing import Any, Dict, List

from src.core.interfaces import LLMProvider
from src.core.models import ContentComment, ContentItem
from src.pipeline.comment.text import clean_comment_text
from src.utils.logger import setup_logger

REFINER_SCHEMA_VERSION = 1

REFINER_PROMPT = """<!-- SYSTEM_CUT -->
你是一个评论分析助手。对每条评论快速判断立场、质量和话题。
<!-- SYSTEM_CUT -->

以下是 {title} 的 {count} 条评论，请逐条分析：

{comments_json}

对每条评论返回一个 JSON 对象，格式如下：
{{
  "refinements": [
    {{
      "id": "评论ID",
      "stance": "支持|质疑|中立",
      "quality_adjust": 0.0,
      "topic": "一句话标签"
    }}
  ]
}}

quality_adjust 范围 -1.0 到 1.0，表示相对于当前质量分的修正。
topic 用中文，不超过 8 个字。
只返回 JSON，不要解释。"""


class CommentRefiner:
    """Cheap LLM pass to refine stance, quality, and topic for pre-filtered comments.

    Sits between CommentAnalyzer (VADER + heuristics) and CommentJudge (expensive LLM).
    Uses a cheap model to do a quick batch pass on the candidate pool.

    Disabled by default — set ``analyze.comment_refiner_enabled: true`` to activate.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        config: dict,
        debug: bool = False,
    ):
        self.llm_provider = llm_provider
        self.config = config
        analyze_cfg = config.get("analyze", {})
        self.enabled = analyze_cfg.get("comment_refiner_enabled", False)
        self.model = analyze_cfg.get("comment_refiner_model", None)
        self.max_tokens = analyze_cfg.get("comment_refiner_max_tokens", 1024)
        log_level = config.get("logging", {}).get("level")
        self.logger = setup_logger(__name__, debug=debug, level=log_level)

    def refine(
        self,
        item: ContentItem,
        candidates: List[ContentComment],
    ) -> Dict[str, Dict[str, Any]]:
        """Refine comment analysis for a story's candidate pool.

        Returns:
            {comment_id: {"stance": str, "quality_adjust": float, "topic": str}}
            Empty dict if disabled or on failure.
        """
        if not self.enabled:
            return {}
        if not candidates:
            return {}

        comments_json = self._build_comments_json(item, candidates)
        prompt = REFINER_PROMPT.format(
            title=item.title or "",
            count=len(candidates),
            comments_json=comments_json,
        )

        try:
            client = self.llm_provider.llm_client
            response_text = client.call_llm_with_json_retry(
                messages=client.split_prompt(prompt),
                label=f"comment_refiner_{item.source_id}",
                max_tokens=self.max_tokens,
                model=self.model,
                temperature=0.1,
            )
            result = client.extract_json(response_text)
            return self._normalize(result, candidates)
        except Exception as e:
            self.logger.warning(f"  CommentRefiner failed for {item.source_id}: {e}")
            return {}

    def _build_comments_json(
        self, item: ContentItem, candidates: List[ContentComment]
    ) -> str:
        entries = []
        for c in candidates:
            text = clean_comment_text(c.content or "")
            if not text or c.source_id is None:
                continue
            entries.append(
                {
                    "id": str(c.source_id),
                    "text": text[:300],
                    "sentiment": c.sentiment,
                    "quality_score": c.quality_score,
                }
            )
        return json.dumps(entries, ensure_ascii=False, indent=2)

    def _normalize(
        self,
        raw: dict,
        candidates: List[ContentComment],
    ) -> Dict[str, Dict[str, Any]]:
        valid_ids = {str(c.source_id) for c in candidates if c.source_id is not None}
        refinements = raw.get("refinements", [])
        if not isinstance(refinements, list):
            return {}

        result: Dict[str, Dict[str, Any]] = {}
        for entry in refinements:
            if not isinstance(entry, dict):
                continue
            cid = str(entry.get("id", ""))
            if cid not in valid_ids:
                continue

            stance = str(entry.get("stance") or "中立").strip()
            if stance not in ("支持", "质疑", "中立"):
                stance = "中立"

            try:
                quality_adjust = float(entry.get("quality_adjust", 0.0))
            except (TypeError, ValueError):
                quality_adjust = 0.0
            quality_adjust = max(-1.0, min(1.0, quality_adjust))

            topic = str(entry.get("topic") or "").strip()[:16]

            result[cid] = {
                "stance": stance,
                "quality_adjust": quality_adjust,
                "topic": topic,
            }

        return result
