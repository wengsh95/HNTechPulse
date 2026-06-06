"""Variant storage helpers for agent-driven candidate generation."""

from __future__ import annotations

import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.core.models import Script
from src.pipeline.agent_io import append_agent_event, utc_now
from src.utils.atomic_io import atomic_write_json


def variants_root(date: str) -> Path:
    return Path(f"data/{date}/variants")


def variant_dir(date: str, variant_id: str) -> Path:
    return variants_root(date) / variant_id


def variant_id_for_index(index: int) -> str:
    return f"v{index:02d}"


def save_script_variant(
    date: str,
    variant_id: str,
    script: Script,
    *,
    label: str,
    strategy: str,
    inputs: dict[str, Any] | None = None,
) -> Path:
    base = variant_dir(date, variant_id)
    base.mkdir(parents=True, exist_ok=True)
    script_path = base / "script.json"
    from src.pipeline.script.io import save_script_to_path

    save_script_to_path(
        script,
        script_path,
        date=date,
        step="write_script_variant",
        inputs={
            "variant_id": variant_id,
            "label": label,
            "strategy": strategy,
            **(inputs or {}),
        },
    )
    atomic_write_json(
        base / "variant.json",
        {
            "schema_version": 1,
            "date": date,
            "variant_id": variant_id,
            "label": label,
            "strategy": strategy,
            "script": str(script_path).replace("\\", "/"),
            "created_at": utc_now(),
        },
    )
    append_agent_event(
        date,
        "variant_written",
        variant_id=variant_id,
        label=label,
        script=str(script_path).replace("\\", "/"),
    )
    return script_path


def write_variants_index(
    date: str,
    variants: list[dict[str, Any]],
    *,
    selected_variant: str | None = None,
    status: str = "generated",
) -> Path:
    path = variants_root(date) / "index.json"
    atomic_write_json(
        path,
        {
            "schema_version": 1,
            "date": date,
            "status": status,
            "selected_variant": selected_variant,
            "variants": variants,
            "updated_at": utc_now(),
        },
    )
    append_agent_event(
        date,
        "variants_index_written",
        count=len(variants),
        selected_variant=selected_variant,
        status=status,
    )
    return path


def write_scorecard(
    date: str,
    variant_id: str,
    scorecard: dict[str, Any],
) -> Path:
    path = variant_dir(date, variant_id) / "scorecard.json"
    atomic_write_json(path, scorecard)
    append_agent_event(
        date,
        "variant_scorecard_written",
        variant_id=variant_id,
        total_score=scorecard.get("total_score"),
    )
    return path


def write_selected_variant(
    date: str,
    variant_id: str,
    *,
    decision: dict[str, Any] | None = None,
) -> Path:
    path = Path(f"data/{date}/selected_variant.json")
    atomic_write_json(
        path,
        {
            "schema_version": 1,
            "date": date,
            "selected_variant": variant_id,
            "decision": decision or {},
            "updated_at": utc_now(),
        },
    )
    append_agent_event(date, "variant_selected", variant_id=variant_id)
    return path


def write_selection_brief(date: str, decision: dict[str, Any]) -> Path:
    path = variants_root(date) / "selection_brief.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    selected = decision.get("selected_variant") or "-"
    confidence = decision.get("confidence", 0.0)
    rationale = decision.get("rationale") or ""
    status = decision.get("status") or "unknown"
    blocked_reason = decision.get("blocked_reason") or "-"

    lines = [
        f"# Agent Variant Selection | {date}",
        "",
        f"- Status: `{status}`",
        f"- Selected: `{selected}`",
        f"- Confidence: `{confidence}`",
        f"- Blocked reason: `{blocked_reason}`",
        "",
        "## Rationale",
        "",
        rationale or "-",
        "",
        "## Scores",
        "",
        "| Variant | Label | Total | Factual | Coherence | Comments | Title | Publish | Risk |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for scorecard in decision.get("scores", []) or []:
        scores = scorecard.get("scores", {}) or {}
        lines.append(
            "| {variant} | {label} | {total} | {factual} | {coherence} | "
            "{comments} | {title} | {publish} | {risk} |".format(
                variant=scorecard.get("variant_id", "-"),
                label=scorecard.get("label", "-"),
                total=scorecard.get("total_score", "-"),
                factual=scores.get("factual_grounding", "-"),
                coherence=scores.get("story_coherence", "-"),
                comments=scores.get("comment_usage", "-"),
                title=scores.get("title_strength", "-"),
                publish=scores.get("publish_readiness", "-"),
                risk=scores.get("source_risk", "-"),
            )
        )

    rejected = decision.get("rejected", []) or []
    if rejected:
        lines.extend(["", "## Rejected", ""])
        for item in rejected:
            lines.append(
                "- `{variant}` score `{score}`: {reason}".format(
                    variant=item.get("variant_id", "-"),
                    score=item.get("total_score", "-"),
                    reason=item.get("reason", "-"),
                )
            )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "This brief is for review and tuning. Downstream audio, cover, and render steps run only for the selected script.",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    append_agent_event(
        date,
        "variant_selection_brief_written",
        selected_variant=selected,
        path=str(path).replace("\\", "/"),
    )
    return path


def promote_variant_script(date: str, variant_id: str) -> Script:
    src = variant_dir(date, variant_id) / "script.json"
    if not src.exists():
        raise FileNotFoundError(f"Variant script not found: {src}")
    dest = Path(f"data/{date}/script.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    from src.pipeline.script.io import load_script as _load_script

    script = _load_script(date)
    append_agent_event(
        date,
        "variant_script_promoted",
        variant_id=variant_id,
        destination=str(dest).replace("\\", "/"),
    )
    return script


def script_preview(script: Script, max_chars: int = 260) -> str:
    text = " ".join((segment.audio_text or "") for segment in script.segments).strip()
    return text[:max_chars] + ("..." if len(text) > max_chars else "")


def script_to_dict(script: Script) -> dict[str, Any]:
    return asdict(script)
