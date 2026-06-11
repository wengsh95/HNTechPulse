"""Agent decision gates for continuing, blocking, or requesting review."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.models import ContentPackage, Script
from src.pipeline.agent_variants import (
    write_scorecard,
    write_selected_variant,
    write_selection_brief,
)
from src.pipeline.agent_io import append_agent_event
from src.pipeline.agent_state import BLOCK_INSUFFICIENT_CONTEXT
from src.pipeline.paths import agent_path
from src.utils.atomic_io import atomic_write_json

BLOCK_LOW_DECISION_CONFIDENCE = "low_decision_confidence"
BLOCK_SOURCE_RISK_HIGH = "source_risk_high"
BLOCK_HUMAN_REVIEW_REQUIRED = "human_review_required"


@dataclass
class DecisionResult:
    gate: str
    status: str
    confidence: float
    scores: dict[str, float]
    rationale: str
    blocked_reason: str | None = None
    blocked_items: list[dict[str, Any]] | None = None
    requires_human_review: bool = False

    @property
    def should_continue(self) -> bool:
        return self.status in {"continue", "degraded"}


class AgentDecisionEngine:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        decision_cfg = config.get("agent", {}).get("decision", {})
        self.min_confidence = float(
            decision_cfg.get("min_confidence_to_continue", 0.75)
        )
        self.min_factual_grounding = float(
            decision_cfg.get("min_factual_grounding", 0.8)
        )
        self.max_source_risk = float(decision_cfg.get("max_source_risk", 0.3))
        self.min_script_publish_readiness = float(
            decision_cfg.get("min_script_publish_readiness", 0.7)
        )
        self.min_comments_for_discussion_only = int(
            decision_cfg.get("min_comments_for_discussion_only", 5)
        )
        self.weights = decision_cfg.get("weights", {}) or {}

    def evaluate_source_context(
        self, content: ContentPackage, date: str
    ) -> DecisionResult:
        items = content.items or []
        if not items:
            result = DecisionResult(
                gate="source_context",
                status="blocked",
                confidence=0.0,
                scores={
                    "factual_grounding": 0.0,
                    "source_risk": 1.0,
                    "comment_usage": 0.0,
                    "publish_readiness": 0.0,
                },
                rationale="No content items are available.",
                blocked_reason=BLOCK_INSUFFICIENT_CONTEXT,
                blocked_items=[],
            )
            self.write_decision(date, result)
            return result

        blocked_items = []
        grounded = 0
        discussion_supported = 0
        source_risk_total = 0.0
        for item in items:
            has_article = bool(item.article_text or item.article_summary)
            comments = [c for c in item.comments if (c.content or "").strip()]
            if has_article:
                grounded += 1
                source_risk_total += 0.05
            elif len(comments) >= self.min_comments_for_discussion_only:
                discussion_supported += 1
                source_risk_total += 0.35
            else:
                source_risk_total += 0.85
                blocked_items.append(
                    {
                        "story_id": str(item.source_id),
                        "title": item.title or "",
                        "url": item.url or "",
                        "reason": "article_unavailable_and_too_few_comments",
                        "comment_count": len(comments),
                        "min_comments_required": self.min_comments_for_discussion_only,
                    }
                )

        factual_grounding = (grounded + discussion_supported * 0.7) / len(items)
        comment_usage = discussion_supported / len(items)
        source_risk = min(1.0, source_risk_total / len(items))
        publish_readiness = max(0.0, min(1.0, factual_grounding - source_risk * 0.2))
        confidence = self._weighted_confidence(
            {
                "factual_grounding": factual_grounding,
                "story_coherence": factual_grounding,
                "comment_usage": comment_usage,
                "title_strength": 0.7,
                "publish_readiness": publish_readiness,
            },
            source_risk,
        )

        status = "continue"
        blocked_reason = None
        rationale = "Source context is sufficient for script generation."
        if blocked_items:
            status = "blocked"
            blocked_reason = BLOCK_INSUFFICIENT_CONTEXT
            rationale = (
                "One or more stories lack both article text and sufficient comments."
            )
        elif source_risk > self.max_source_risk:
            status = "blocked"
            blocked_reason = BLOCK_SOURCE_RISK_HIGH
            rationale = "Source risk exceeds the configured threshold."
        elif factual_grounding < self.min_factual_grounding:
            status = "blocked"
            blocked_reason = BLOCK_INSUFFICIENT_CONTEXT
            rationale = "Factual grounding is below the configured threshold."
        elif confidence < self.min_confidence:
            status = "blocked"
            blocked_reason = BLOCK_LOW_DECISION_CONFIDENCE
            rationale = "Decision confidence is below the configured threshold."

        result = DecisionResult(
            gate="source_context",
            status=status,
            confidence=round(confidence, 4),
            scores={
                "factual_grounding": round(factual_grounding, 4),
                "source_risk": round(source_risk, 4),
                "comment_usage": round(comment_usage, 4),
                "publish_readiness": round(publish_readiness, 4),
            },
            rationale=rationale,
            blocked_reason=blocked_reason,
            blocked_items=blocked_items,
        )
        self.write_decision(date, result)
        return result

    def evaluate_script_quality(
        self, content: ContentPackage, script: Script, date: str
    ) -> DecisionResult:
        segments = script.segments or []
        story_segments = [s for s in segments if s.segment_type == "story_scan"]
        audio_text = " ".join((s.audio_text or "") for s in segments).strip()
        has_opening = any(s.segment_type == "opening" for s in segments)
        has_closing = any(s.segment_type == "closing" for s in segments)
        has_story = bool(story_segments) and bool(audio_text)
        quote_elements = 0
        for seg in segments:
            for elem in seg.scene_elements:
                props = elem.props or {}
                quote_elements += len(props.get("quotes") or [])
                quote_elements += len(props.get("selected_comment_ids") or [])

        story_coherence = sum([has_opening, has_story, has_closing]) / 3
        comment_usage = min(1.0, quote_elements / max(1, len(content.items)))
        title_strength = 1.0 if script.title and len(script.title.strip()) >= 4 else 0.4
        factual_grounding = self._content_grounding_score(content)
        publish_readiness = (
            story_coherence * 0.45
            + factual_grounding * 0.35
            + title_strength * 0.1
            + comment_usage * 0.1
        )
        source_risk = max(0.0, 1.0 - factual_grounding)
        confidence = self._weighted_confidence(
            {
                "factual_grounding": factual_grounding,
                "story_coherence": story_coherence,
                "comment_usage": comment_usage,
                "title_strength": title_strength,
                "publish_readiness": publish_readiness,
            },
            source_risk,
        )

        status = "continue"
        blocked_reason = None
        rationale = "Script quality gate passed."
        if publish_readiness < self.min_script_publish_readiness:
            status = "blocked"
            blocked_reason = BLOCK_LOW_DECISION_CONFIDENCE
            rationale = "Script publish readiness is below the configured threshold."
        elif confidence < self.min_confidence:
            status = "blocked"
            blocked_reason = BLOCK_LOW_DECISION_CONFIDENCE
            rationale = "Script decision confidence is below the configured threshold."

        result = DecisionResult(
            gate="script_quality",
            status=status,
            confidence=round(confidence, 4),
            scores={
                "factual_grounding": round(factual_grounding, 4),
                "story_coherence": round(story_coherence, 4),
                "comment_usage": round(comment_usage, 4),
                "title_strength": round(title_strength, 4),
                "publish_readiness": round(publish_readiness, 4),
                "source_risk": round(source_risk, 4),
            },
            rationale=rationale,
            blocked_reason=blocked_reason,
            requires_human_review=False,
        )
        self.write_decision(date, result)
        return result

    def select_script_variant(
        self, content: ContentPackage, variants: list[dict[str, Any]], date: str
    ) -> dict[str, Any]:
        scored = []
        for variant in variants:
            script = variant["script"]
            result = self.evaluate_script_quality(content, script, date)
            total_score = result.confidence
            scorecard = {
                "schema_version": 1,
                "date": date,
                "variant_id": variant["variant_id"],
                "label": variant.get("label", ""),
                "strategy": variant.get("strategy", ""),
                "total_score": total_score,
                "scores": result.scores,
                "status": result.status,
                "blocked_reason": result.blocked_reason,
                "rationale": result.rationale,
                "preview": variant.get("preview", ""),
                "story_indices": variant.get("story_indices", []),
            }
            write_scorecard(date, variant["variant_id"], scorecard)
            scored.append({**variant, "decision": result, "scorecard": scorecard})

        if not scored:
            decision = {
                "schema_version": 1,
                "date": date,
                "decision_type": "variant_selection",
                "status": "blocked",
                "selected_variant": None,
                "confidence": 0.0,
                "blocked_reason": BLOCK_LOW_DECISION_CONFIDENCE,
                "rationale": "No script variants were generated.",
                "scores": [],
            }
            self._write_variant_decision(date, decision)
            return decision

        viable = [v for v in scored if v["decision"].should_continue]
        candidates = viable or scored
        selected = max(candidates, key=lambda v: v["decision"].confidence)
        selected_result = selected["decision"]
        status = "continue" if selected_result.should_continue else "blocked"
        blocked_reason = (
            None
            if selected_result.should_continue
            else (selected_result.blocked_reason or BLOCK_LOW_DECISION_CONFIDENCE)
        )
        rejected = [
            {
                "variant_id": v["variant_id"],
                "total_score": v["decision"].confidence,
                "reason": (
                    "selected"
                    if v["variant_id"] == selected["variant_id"]
                    else v["decision"].rationale
                ),
            }
            for v in scored
            if v["variant_id"] != selected["variant_id"]
        ]
        decision = {
            "schema_version": 1,
            "date": date,
            "decision_type": "variant_selection",
            "status": status,
            "selected_variant": selected["variant_id"],
            "confidence": selected_result.confidence,
            "blocked_reason": blocked_reason,
            "auto_selected": status == "continue",
            "requires_human_review": status != "continue",
            "rationale": (
                f"Selected {selected['variant_id']} with the highest viable score "
                f"({selected_result.confidence:.2f})."
            ),
            "scores": [v["scorecard"] for v in scored],
            "rejected": rejected,
        }
        self._write_variant_decision(date, decision)
        write_selection_brief(date, decision)
        if status == "continue":
            write_selected_variant(date, selected["variant_id"], decision=decision)
        return decision

    def write_decision(self, date: str, result: DecisionResult) -> Path:
        path = agent_path(date, "agent_decision.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "date": date,
            "gate": result.gate,
            "status": result.status,
            "confidence": result.confidence,
            "requires_human_review": result.requires_human_review,
            "blocked_reason": result.blocked_reason,
            "blocked_items": result.blocked_items or [],
            "scores": result.scores,
            "thresholds": {
                "min_confidence_to_continue": self.min_confidence,
                "min_factual_grounding": self.min_factual_grounding,
                "max_source_risk": self.max_source_risk,
                "min_script_publish_readiness": self.min_script_publish_readiness,
            },
            "rationale": result.rationale,
        }
        atomic_write_json(path, payload)
        append_agent_event(
            date,
            "agent_decision_written",
            gate=result.gate,
            status=result.status,
            confidence=result.confidence,
            blocked_reason=result.blocked_reason,
        )
        return path

    def _write_variant_decision(self, date: str, decision: dict[str, Any]) -> Path:
        path = agent_path(date, "agent_variant_decision.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(path, decision)
        append_agent_event(
            date,
            "agent_variant_decision_written",
            status=decision.get("status"),
            selected_variant=decision.get("selected_variant"),
            confidence=decision.get("confidence"),
            blocked_reason=decision.get("blocked_reason"),
        )
        return path

    def _content_grounding_score(self, content: ContentPackage) -> float:
        if not content.items:
            return 0.0
        total = 0.0
        for item in content.items:
            if item.article_text or item.article_summary:
                total += 1.0
            elif len([c for c in item.comments if (c.content or "").strip()]) >= (
                self.min_comments_for_discussion_only
            ):
                total += 0.7
        return total / len(content.items)

    def _weighted_confidence(
        self, scores: dict[str, float], source_risk: float
    ) -> float:
        weights = {
            "factual_grounding": 0.35,
            "story_coherence": 0.25,
            "comment_usage": 0.2,
            "title_strength": 0.1,
            "publish_readiness": 0.1,
            **self.weights,
        }
        total_weight = sum(float(v) for v in weights.values()) or 1.0
        raw = sum(scores.get(k, 0.0) * float(w) for k, w in weights.items())
        confidence = raw / total_weight
        return max(0.0, min(1.0, confidence - source_risk * 0.1))
