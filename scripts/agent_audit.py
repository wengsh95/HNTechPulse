#!/usr/bin/env python3
"""Final publishability audit for agent-driven HN TechPulse runs.

The audit is read-only. It inspects date-scoped artifacts and emits JSON so an
agent can decide whether the current run is publishable, blocked, or needs a
specific follow-up command.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline.agent_io import file_sha256, load_pipeline_state  # noqa: E402


def _default_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _issue(
    severity: str,
    check: str,
    message: str,
    *,
    path: Path | str | None = None,
    recommendation: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "severity": severity,
        "check": check,
        "message": message,
    }
    if path is not None:
        payload["path"] = str(path).replace("\\", "/")
    if recommendation:
        payload["recommendation"] = recommendation
    return payload


def _artifact_check(base: Path) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    required = {
        "content": base / "content.json",
        "script": base / "script.json",
    }
    optional_publish = {
        "title": base / "title.json",
        "cover_props": base / "cover_props.json",
        "publish_guide": base / "publish_guide.md",
    }

    for name, path in required.items():
        if not path.exists():
            issues.append(
                _issue(
                    "error",
                    f"{name}_exists",
                    f"Required artifact is missing: {path}",
                    path=path,
                    recommendation="Rerun the producing pipeline step.",
                )
            )

    for name, path in optional_publish.items():
        if not path.exists():
            issues.append(
                _issue(
                    "warning",
                    f"{name}_exists",
                    f"Publish artifact is missing: {path}",
                    path=path,
                    recommendation="Run the remaining publish steps before release.",
                )
            )
    return issues


def _manifest_check(paths: list[Path]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for artifact in paths:
        if not artifact.exists():
            continue
        manifest_path = artifact.with_suffix(artifact.suffix + ".manifest.json")
        manifest = _read_json(manifest_path)
        if not manifest:
            issues.append(
                _issue(
                    "warning",
                    "manifest_exists",
                    f"Manifest is missing or unreadable for {artifact}",
                    path=manifest_path,
                )
            )
            continue
        expected_hash = file_sha256(artifact)
        actual_hash = manifest.get("artifact_hash")
        if actual_hash and actual_hash != expected_hash:
            issues.append(
                _issue(
                    "error",
                    "manifest_hash_matches",
                    f"Manifest hash does not match artifact: {artifact}",
                    path=manifest_path,
                    recommendation="Regenerate the artifact or manifest.",
                )
            )
    return issues


def _state_check(date: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    state = load_pipeline_state(date)
    if not state:
        return None, [
            _issue(
                "warning",
                "pipeline_state_exists",
                "pipeline_state.json is missing or unreadable.",
                path=Path(f"data/{date}/pipeline_state.json"),
                recommendation="Run in --agent mode to produce machine-readable state.",
            )
        ]

    status = state.get("status")
    if status in {"blocked", "failed"}:
        return state, [
            _issue(
                "error",
                "pipeline_state_status",
                f"Pipeline state is {status}.",
                path=Path(f"data/{date}/pipeline_state.json"),
                recommendation=state.get("next_recommended_command"),
            )
        ]
    if status == "degraded":
        return state, [
            _issue(
                "warning",
                "pipeline_state_status",
                "Pipeline completed with degraded items.",
                path=Path(f"data/{date}/pipeline_state.json"),
            )
        ]
    if status != "complete":
        return state, [
            _issue(
                "warning",
                "pipeline_state_status",
                f"Pipeline state is {status or 'unknown'}.",
                path=Path(f"data/{date}/pipeline_state.json"),
            )
        ]
    return state, []


def _decision_check(base: Path) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    decision = _read_json(base / "agent_decision.json")
    issues: list[dict[str, Any]] = []
    if not decision:
        issues.append(
            _issue(
                "warning",
                "agent_decision_exists",
                "agent_decision.json is missing or unreadable.",
                path=base / "agent_decision.json",
            )
        )
        return None, issues
    if decision.get("status") not in {"continue", "degraded"}:
        issues.append(
            _issue(
                "error",
                "agent_decision_status",
                f"Agent decision status is {decision.get('status')}.",
                path=base / "agent_decision.json",
                recommendation=decision.get("blocked_reason"),
            )
        )
    return decision, issues


def _variant_check(base: Path) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    decision = _read_json(base / "agent_variant_decision.json")
    issues: list[dict[str, Any]] = []
    if not decision:
        issues.append(
            _issue(
                "warning",
                "variant_decision_exists",
                "agent_variant_decision.json is missing or unreadable.",
                path=base / "agent_variant_decision.json",
            )
        )
        return None, issues

    selected = decision.get("selected_variant")
    selected_script = base / "variants" / str(selected) / "script.json"
    promoted_script = base / "script.json"
    if decision.get("status") != "continue":
        issues.append(
            _issue(
                "error",
                "variant_decision_status",
                f"Variant decision status is {decision.get('status')}.",
                path=base / "agent_variant_decision.json",
                recommendation=decision.get("blocked_reason"),
            )
        )
    if selected and selected_script.exists() and promoted_script.exists():
        if file_sha256(selected_script) != file_sha256(promoted_script):
            issues.append(
                _issue(
                    "error",
                    "selected_variant_promoted",
                    "script.json does not match the selected variant script.",
                    path=promoted_script,
                    recommendation="Rerun write_script with --agent or promote the selected variant.",
                )
            )
    elif selected:
        issues.append(
            _issue(
                "warning",
                "selected_variant_script_exists",
                "Selected variant script or promoted script is missing.",
                path=selected_script,
            )
        )
    return decision, issues


def _next_command(date: str, issues: list[dict[str, Any]]) -> str | None:
    for issue in issues:
        recommendation = issue.get("recommendation")
        if isinstance(recommendation, str) and recommendation.startswith("uv run "):
            return recommendation
    if any(i["severity"] == "error" for i in issues):
        return f"uv run python main.py --date {date} --resume --agent"
    if any(i["check"] == "title_exists" for i in issues):
        return f"uv run python main.py --date {date} --steps title --agent"
    if any(i["check"] == "cover_props_exists" for i in issues):
        return f"uv run python main.py --date {date} --steps cover_image --agent"
    if any(i["check"] == "publish_guide_exists" for i in issues):
        return f"uv run python main.py --date {date} --steps publish_guide --agent"
    return None


def audit(date: str) -> dict[str, Any]:
    base = Path(f"data/{date}")
    issues: list[dict[str, Any]] = []

    state, state_issues = _state_check(date)
    issues.extend(state_issues)
    decision, decision_issues = _decision_check(base)
    issues.extend(decision_issues)
    variant_decision, variant_issues = _variant_check(base)
    issues.extend(variant_issues)
    issues.extend(_artifact_check(base))
    issues.extend(
        _manifest_check(
            [
                base / "content.json",
                base / "script.json",
                base / "title.json",
                base / "cover_props.json",
                base / "publish_guide.md",
            ]
        )
    )

    error_count = sum(1 for i in issues if i["severity"] == "error")
    warning_count = sum(1 for i in issues if i["severity"] == "warning")
    publishable = error_count == 0 and (state or {}).get("status") in {
        "complete",
        "degraded",
    }
    status = "ok" if publishable else "blocked" if error_count else "warning"
    return {
        "schema_version": 1,
        "date": date,
        "status": status,
        "publishable": publishable,
        "error_count": error_count,
        "warning_count": warning_count,
        "issues": issues,
        "pipeline_state": state,
        "agent_decision": decision,
        "agent_variant_decision": variant_decision,
        "next_command": _next_command(date, issues),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent final publishability audit")
    parser.add_argument("--date", default=_default_date())
    args = parser.parse_args()

    payload = audit(args.date)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["publishable"] else 1


if __name__ == "__main__":
    sys.exit(main())
