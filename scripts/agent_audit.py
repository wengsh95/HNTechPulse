#!/usr/bin/env python3
"""Final publishability audit for agent-driven HN TechPulse runs.

The audit is read-only. It inspects date-scoped artifacts and emits JSON so an
agent can decide whether the current run is publishable, blocked, or needs a
specific follow-up command.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline.agent_io import (  # noqa: E402
    file_sha256,
    stable_hash,
)
from src.pipeline.paths import (  # noqa: E402
    agent_path,
    date_root,
    pipeline_path,
    publish_path,
    raw_downloaded_pages_dir,
)
from src.workflow import load_workflow_report  # noqa: E402


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


def _format_mmss(seconds: float | int | None) -> str:
    total = max(0, int(round(float(seconds or 0))))
    return f"{total // 60:02d}:{total % 60:02d}"


def _scripts_semantically_equal(variant_path: Path, promoted_path: Path) -> bool:
    """Compare the segment-level content of two script.json files.

    Why not byte-compare: post-process steps (translate_comments, synthesize_audio,
    title) re-save data/{month}/{date}/script.json to attach top-level fields
    (title/description/tags/cover_subtitle/total_duration) and per-segment
    audio/cue/timing data. The variant snapshot at data/.../variants/{id}/script.json
    is intentionally frozen at write_script time. Byte-equality would always
    fail post-audio/title. Comparing only the *content* the writer controls
    (segment audio_text + scene_elements minus post-process timing fields)
    catches real drift while tolerating legitimate post-process updates.
    """
    # Keys added/mutated by post-process steps (audio/timing/translation).
    # We exclude these so the audit passes after a normal pipeline run.
    _TIMING_KEYS = frozenset({"start_time", "end_time", "audio_duration"})

    def _normalize(obj):
        """Recursively drop timing keys and join subtitle_texts for comparison.

        Post-process steps (synthesize_audio) may re-split subtitle_texts into
        different chunks for timing. Joining them tolerates legitimate
        re-chunking while still catching real content drift.
        """
        if isinstance(obj, dict):
            result = {}
            for k, v in obj.items():
                if k in _TIMING_KEYS:
                    continue
                norm_v = _normalize(v)
                if k == "subtitle_texts" and isinstance(norm_v, list):
                    # Drop all whitespace, not just fold it: the subtitle
                    # splitter (src/utils/subtitles.py) strips whitespace at
                    # chunk boundaries, so "".join loses those spaces and
                    # folding-to-space would still mismatch on English/mixed
                    # content. Removing whitespace tolerates legitimate
                    # re-chunking while still catching real textual drift.
                    result[k] = re.sub(r"\s+", "", "".join(norm_v))
                else:
                    result[k] = norm_v
            return result
        if isinstance(obj, list):
            return [_normalize(v) for v in obj]
        return obj

    try:
        variant = json.loads(variant_path.read_text(encoding="utf-8"))
        promoted = json.loads(promoted_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    v_segs = variant.get("segments") or []
    p_segs = promoted.get("segments") or []
    if len(v_segs) != len(p_segs):
        return False

    for v_seg, p_seg in zip(v_segs, p_segs):
        if not isinstance(v_seg, dict) or not isinstance(p_seg, dict):
            return False
        if v_seg.get("segment_type") != p_seg.get("segment_type"):
            return False
        if v_seg.get("audio_text") != p_seg.get("audio_text"):
            return False
        if _normalize(v_seg.get("scene_elements")) != _normalize(
            p_seg.get("scene_elements")
        ):
            return False
    return True


def _issue(
    severity: str,
    check: str,
    message: str,
    *,
    path: Path | str | None = None,
    recommendation: str | None = None,
    why: str | None = None,
    fixable_by_agent: bool | None = None,
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
    if why:
        payload["why"] = why
    if fixable_by_agent is not None:
        payload["fixable_by_agent"] = fixable_by_agent
    return payload


def _artifact_check(date: str, base: Path) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    required = {
        "content": pipeline_path(date, "content.json"),
        "script": pipeline_path(date, "script.json"),
    }
    optional_publish = {
        "title": publish_path(date, "title.json"),
        "cover": publish_path(date, "cover.png"),
        "publish_guide": publish_path(date, "publish_guide.md"),
    }

    for name, path in required.items():
        if not path.exists():
            issues.append(
                _issue(
                    "error",
                    f"{name}_exists",
                    f"Required artifact is missing: {path}",
                    path=path,
                    recommendation=f"uv run python scripts/agent_run.py --date {date} --resume",
                    why=(
                        f"{name}.json is produced by the pipeline. Either no run "
                        f"has been attempted for this date, or a previous run was "
                        f"interrupted before reaching the {name} step. --resume will "
                        f"pick up at the first incomplete step (everything cached "
                        f"before that step will be reused)."
                    ),
                    fixable_by_agent=True,
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
                    why=(
                        f"{name} is produced by the managed publishing tail. The "
                        f"artifact may be absent when the run stopped before its "
                        f"packaging step. Resume the managed tail to regenerate it."
                    ),
                    fixable_by_agent=True,
                )
            )
    publish_guide = optional_publish["publish_guide"]
    if publish_guide.exists():
        from src.pipeline.publish_guide_inputs import publish_guide_manifest_inputs

        context = publish_guide_manifest_inputs(date)
        manifest = _read_json(
            publish_guide.with_suffix(publish_guide.suffix + ".manifest.json")
        )
        if context is not None and (
            not isinstance(manifest, dict)
            or manifest.get("input_hash") != stable_hash(context)
        ):
            issues.append(
                _issue(
                    "warning",
                    "publish_guide_fresh",
                    f"Publish guide inputs changed: {publish_guide}",
                    path=publish_guide,
                    recommendation=(
                        f"uv run python scripts/agent_run.py --date {date} "
                        "--steps prepare_render"
                    ),
                    why=(
                        "Publish copy depends on the selected content and script. "
                        "Regenerate it after upstream artifacts change."
                    ),
                    fixable_by_agent=True,
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
    state_path = agent_path(date, "workflow_video.json")
    state = load_workflow_report(date)
    if state is None:
        return None, [
            _issue(
                "warning",
                "workflow_state_exists",
                "Native workflow state is missing or unreadable.",
                path=state_path,
                recommendation=f"uv run python scripts/agent_run.py --date {date}",
            )
        ]
    if state.get("status") == "corrupt":
        return None, [
            _issue(
                "error",
                "workflow_state_valid",
                state.get("error", "workflow state is corrupt"),
                path=state_path,
            )
        ]

    status = state.get("status")
    if status in {"blocked", "failed"}:
        current = state.get("current_state") or "unknown"
        record = (state.get("states") or {}).get(current) or {}
        blocked_reason = record.get("last_error")
        why_msg = {
            "manual_download_required": (
                f"Pipeline is waiting on article source files in {raw_downloaded_pages_dir(date)}/. "
                "The save_as.html path for each pending task is in agent_tasks.json — "
                "fetch and save there, then resume."
            ),
            "missing_credentials": (
                "An env var required by the LLM / TTS / image generator provider is unset. "
                "Check the .env file or shell environment."
            ),
            "external_tool_missing": (
                "A required local tool (e.g. ffmpeg, npx) is not on PATH. "
                "Install it or adjust config to skip the dependent step."
            ),
            "source_risk_high": (
                "Agent decision gate flagged source risk above threshold. "
                "Gather more primary-source material for the blocked stories, then resume."
            ),
            "low_decision_confidence": (
                "Source-context or script-quality confidence was below the configured threshold. "
                f"Inspect {agent_path(date, 'agent_decision.json')} scores and repair the weak input."
            ),
            "human_review_required": (
                "Decision layer requires human review before continuing. "
                "Do not auto-resume — ask the user."
            ),
            "insufficient_story_context": (
                "Article is unavailable and comments are too sparse for script generation. "
                "Gather primary source context (README, official docs, original page) or report blocker."
            ),
        }.get(blocked_reason)
        is_fixable = blocked_reason not in {
            "human_review_required",
            "missing_credentials",
            "external_tool_missing",
        }
        return state, [
            _issue(
                "error",
                "workflow_state_status",
                f"Workflow state is {status} ({blocked_reason or 'no reason'}).",
                path=state_path,
                recommendation=state.get("next_recommended_command"),
                why=why_msg,
                fixable_by_agent=is_fixable,
            )
        ]
    if status == "degraded":
        return state, [
            _issue(
                "warning",
                "workflow_state_status",
                "Workflow completed with degraded items.",
                path=state_path,
                why=(
                    "Some items were enriched with degraded source context "
                    "(incomplete article body or missing images). Script was "
                    f"still produced; review {date_root(date)}/degraded_items before publish."
                ),
            )
        ]
    if status != "complete":
        return state, [
            _issue(
                "warning",
                "workflow_state_status",
                f"Workflow state is {status or 'unknown'}.",
                path=state_path,
            )
        ]
    return state, []


def _decision_check(date: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    decision_path = agent_path(date, "agent_decision.json")
    decision = _read_json(decision_path)
    issues: list[dict[str, Any]] = []
    if not decision:
        issues.append(
            _issue(
                "warning",
                "agent_decision_exists",
                "agent_decision.json is missing or unreadable.",
                path=decision_path,
            )
        )
        return None, issues
    if decision.get("status") not in {"continue", "degraded"}:
        issues.append(
            _issue(
                "error",
                "agent_decision_status",
                f"Agent decision status is {decision.get('status')}.",
                path=decision_path,
                recommendation=decision.get("blocked_reason"),
            )
        )
    return decision, issues


def _variant_check(
    date: str, *, enforce_promotion: bool = True
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    from src.pipeline.paths import pipeline_path, pipeline_variants_root

    decision_path = agent_path(date, "agent_variant_decision.json")
    decision = _read_json(decision_path)
    issues: list[dict[str, Any]] = []
    if not decision:
        issues.append(
            _issue(
                "warning",
                "variant_decision_exists",
                "agent_variant_decision.json is missing or unreadable.",
                path=decision_path,
            )
        )
        return None, issues

    selected = decision.get("selected_variant")
    selected_script = pipeline_variants_root(date) / str(selected) / "script.json"
    promoted_script = pipeline_path(date, "script.json")
    if decision.get("status") != "continue":
        issues.append(
            _issue(
                "error",
                "variant_decision_status",
                f"Variant decision status is {decision.get('status')}.",
                path=decision_path,
                recommendation=decision.get("blocked_reason"),
            )
        )
    if (
        enforce_promotion
        and selected
        and selected_script.exists()
        and promoted_script.exists()
    ):
        if not _scripts_semantically_equal(selected_script, promoted_script):
            issues.append(
                _issue(
                    "error",
                    "selected_variant_promoted",
                    "script.json segments do not match the selected variant script.",
                    path=promoted_script,
                    recommendation=(
                        "Rerun write_script through scripts/agent_run.py or promote the "
                        "selected variant."
                    ),
                )
            )
    elif enforce_promotion and selected:
        issues.append(
            _issue(
                "warning",
                "selected_variant_script_exists",
                "Selected variant script or promoted script is missing.",
                path=selected_script,
            )
        )
    return decision, issues


def _next_command(date: str, issues: list[dict[str, Any]]) -> dict[str, str] | None:
    """Pick the highest-priority next command and pair it with a `why`.

    Priority order:
    1. Any issue whose recommendation is itself a `uv run ...` command.
    2. Pipeline-state error → `--resume`.
    3. Missing publish artifacts (title → cover → prepare_render).
    """
    candidates: list[tuple[str, str, str]] = []  # (priority_tag, cmd, why)

    for issue in issues:
        rec = issue.get("recommendation")
        if isinstance(rec, str) and rec.startswith("uv run "):
            candidates.append(
                (
                    issue.get("check", "issue"),
                    rec,
                    issue.get("why") or f"Resolves: {issue.get('message', '')}",
                )
            )

    if any(i["severity"] == "error" for i in issues):
        candidates.append(
            (
                "workflow_state_error",
                f"uv run python scripts/agent_run.py --date {date} --resume",
                "A product-scoped pipeline state error needs --resume to retry the failed step.",
            )
        )

    # Publish-tail ordering: title depends on the script; cover depends on
    # title; prepare_render also writes publish_guide.md.
    publish_step_for_check = {
        "title_exists": (
            "title",
            "Title.json is missing — generate it from script.json.",
        ),
        "cover_props_exists": (
            "cover_image",
            "Cover image not yet generated — needs the title to drive cover_prompt.",
        ),
        "cover_thumbnail_exists": (
            "cover_thumbnail",
            "Cover thumbnail (title overlay) is missing — run after cover_image.",
        ),
        "publish_guide_exists": (
            "prepare_render",
            "Publish guide not yet generated — prepare_render will write it.",
        ),
    }
    for check, (step, why) in publish_step_for_check.items():
        if any(i.get("check") == check for i in issues):
            candidates.append(
                (
                    check,
                    f"uv run python scripts/agent_run.py --date {date} --steps {step}",
                    why,
                )
            )

    if not candidates:
        return None
    # First-in-list wins (insertion order matches priority).
    _tag, cmd, why = candidates[0]
    return {"command": cmd, "why": why}


def _summarize_blocks(issues: list[dict[str, Any]]) -> dict[str, Any]:
    """Top-level summary: how many blocks are agent-fixable vs. needs-human.

    Saves the agent from reading every issue when the answer is a single number.
    """
    agent_fixable = [i for i in issues if i.get("fixable_by_agent") is True]
    needs_human = [i for i in issues if i.get("fixable_by_agent") is False]
    unknown = [
        i
        for i in issues
        if i.get("fixable_by_agent") is None
        and i.get("severity") in {"error", "warning"}
    ]

    def _short(item: dict[str, Any]) -> str:
        return f"{item.get('check', '?')}: {item.get('message', '')[:80]}"

    return {
        "agent_fixable_count": len(agent_fixable),
        "needs_human_count": len(needs_human),
        "unknown_count": len(unknown),
        "agent_fixable": [_short(i) for i in agent_fixable],
        "needs_human": [_short(i) for i in needs_human],
    }


def audit(date: str) -> dict[str, Any]:
    base = date_root(date)
    issues: list[dict[str, Any]] = []

    state, state_issues = _state_check(date)
    issues.extend(state_issues)
    decision, decision_issues = _decision_check(date)
    issues.extend(decision_issues)
    state_steps = set(
        ((state or {}).get("metadata") or {}).get("requested_steps") or []
    )
    # A downstream-only video run intentionally consumes the current
    # editorial script and must not compare it with an older generated
    # variant snapshot. Promotion is only an obligation when this run
    # includes write_script.
    variant_decision, variant_issues = _variant_check(
        date,
        enforce_promotion=(not state_steps or "write_script" in state_steps),
    )
    issues.extend(variant_issues)
    issues.extend(_artifact_check(date, base))
    issues.extend(
        _manifest_check(
            [
                pipeline_path(date, "content.json"),
                pipeline_path(date, "script.json"),
                publish_path(date, "title.json"),
                publish_path(date, "cover.png"),
                publish_path(date, "publish_guide.md"),
            ]
        )
    )
    from src.pipeline.storyboard_linter import lint_storyboard_and_script

    for lint_issue in lint_storyboard_and_script(date):
        issues.append(
            {
                "severity": lint_issue.level,
                "category": f"storyboard_{lint_issue.category}",
                "path": str(pipeline_path(date, "storyboard.json")),
                "message": f"[{lint_issue.shot_id or 'general'}] {lint_issue.message}",
                "detail": None,
            }
        )

    error_count = sum(1 for i in issues if i["severity"] == "error")
    warning_count = sum(1 for i in issues if i["severity"] == "warning")
    publishable = error_count == 0 and (state or {}).get("status") in {
        "complete",
        "degraded",
    }
    status = "ok" if publishable else "blocked" if error_count else "warning"
    next_cmd = _next_command(date, issues)
    return {
        "schema_version": 2,
        "date": date,
        "status": status,
        "publishable": publishable,
        "error_count": error_count,
        "warning_count": warning_count,
        "what_blocks_me": _summarize_blocks(issues),
        "issues": issues,
        "workflow_state": state,
        "agent_decision": decision,
        "agent_variant_decision": variant_decision,
        "next_command": next_cmd["command"] if next_cmd else None,
        "next_command_why": next_cmd["why"] if next_cmd else None,
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
