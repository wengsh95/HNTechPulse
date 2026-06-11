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

from src.pipeline.agent_io import file_sha256, load_pipeline_state, stable_hash  # noqa: E402
from src.pipeline.paths import (  # noqa: E402
    agent_path,
    date_root,
    media_path,
    pipeline_path,
    publish_path,
    raw_downloaded_pages_dir,
)


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
    title) re-save data/{date}/script.json to attach top-level fields
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

    def _strip_timing(obj):
        """Recursively drop timing keys from dicts; pass lists/tuples through."""
        if isinstance(obj, dict):
            return {
                k: _strip_timing(v) for k, v in obj.items() if k not in _TIMING_KEYS
            }
        if isinstance(obj, list):
            return [_strip_timing(v) for v in obj]
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
        if _strip_timing(v_seg.get("scene_elements")) != _strip_timing(
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


def _publish_guide_context(
    date: str, content_path: Path, script_path: Path
) -> dict[str, Any] | None:
    content_data = _read_json(content_path)
    script_data = _read_json(script_path)
    if not isinstance(content_data, dict) or not isinstance(script_data, dict):
        return None
    title_data = _read_json(publish_path(date, "title.json"))
    if not isinstance(title_data, dict):
        title_data = {}
    items_payload = []
    for item in content_data.get("items") or []:
        if not isinstance(item, dict):
            continue
        items_payload.append(
            {
                "title_cn": item.get("title_cn") or item.get("title"),
                "title": item.get("title"),
                "editor_angle": item.get("editor_angle") or item.get("dek") or "",
                "category": item.get("category") or "",
                "keywords": item.get("keywords") or [],
                "score": item.get("score"),
                "comment_count": item.get("comment_count"),
            }
        )
    return {
        "script_title": title_data.get("title")
        or script_data.get("title")
        or "HN每日观察",
        "script_description": title_data.get("description")
        or script_data.get("description")
        or "",
        "items_json": json.dumps(items_payload, ensure_ascii=False, indent=2),
        "prompt_hash": file_sha256(Path("prompts/publish_guide.md")),
        "date": date,
    }


def _artifact_check(date: str, base: Path) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    required = {
        "content": pipeline_path(date, "content.json"),
        "script": pipeline_path(date, "script.json"),
    }
    optional_publish = {
        "title": publish_path(date, "title.json"),
        "cover_props": media_path(date, "cover_props.json"),
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
                        f"{name} is an opt-in publish step (not part of the default "
                        f"12-step chain). Run it explicitly with --steps if you want "
                        f"to publish this date; otherwise it's expected to be absent."
                    ),
                    fixable_by_agent=True,
                )
            )
    publish_guide = optional_publish["publish_guide"]
    if publish_guide.exists():
        context = _publish_guide_context(
            date,
            required["content"],
            required["script"],
        )
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
                        "--steps title,publish_guide"
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
    state = load_pipeline_state(date)
    if not state:
        return None, [
            _issue(
                "warning",
                "pipeline_state_exists",
                "pipeline_state.json is missing or unreadable.",
                path=agent_path(date, "pipeline_state.json"),
                recommendation=f"uv run python scripts/agent_run.py --date {date}",
            )
        ]

    status = state.get("status")
    if status in {"blocked", "failed"}:
        blocked_reason = state.get("blocked_reason")
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
                "pipeline_state_status",
                f"Pipeline state is {status} ({blocked_reason or 'no reason'}).",
                path=agent_path(date, "pipeline_state.json"),
                recommendation=state.get("next_recommended_command"),
                why=why_msg,
                fixable_by_agent=is_fixable,
            )
        ]
    if status == "degraded":
        return state, [
            _issue(
                "warning",
                "pipeline_state_status",
                "Pipeline completed with degraded items.",
                path=agent_path(date, "pipeline_state.json"),
                why=(
                    "Some items were enriched with degraded source context "
                    "(incomplete article body or missing images). Script was "
                    f"still produced; review data/{date}/degraded_items before publish."
                ),
            )
        ]
    if status != "complete":
        return state, [
            _issue(
                "warning",
                "pipeline_state_status",
                f"Pipeline state is {status or 'unknown'}.",
                path=agent_path(date, "pipeline_state.json"),
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


def _variant_check(date: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
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
    if selected and selected_script.exists() and promoted_script.exists():
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


def _next_command(date: str, issues: list[dict[str, Any]]) -> dict[str, str] | None:
    """Pick the highest-priority next command and pair it with a `why`.

    Priority order:
    1. Any issue whose recommendation is itself a `uv run ...` command.
    2. Pipeline-state error → `--resume`.
    3. Missing optional publish artifacts (title → cover → publish_guide).
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
                "pipeline_state_error",
                f"uv run python scripts/agent_run.py --date {date} --resume",
                "An error in pipeline_state.json needs --resume to retry the failed step.",
            )
        )

    # Optional-publish step ordering: title depends on the script; cover depends
    # on title; publish_guide depends on title. Run them in this order.
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
            "publish_guide",
            "Publish guide not yet generated — needs the title/description.",
        ),
    }
    for check, (step, why) in publish_step_for_check.items():
        if any(i["check"] == check for i in issues):
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
    variant_decision, variant_issues = _variant_check(date)
    issues.extend(variant_issues)
    issues.extend(_artifact_check(date, base))
    issues.extend(
        _manifest_check(
            [
                pipeline_path(date, "content.json"),
                pipeline_path(date, "script.json"),
                publish_path(date, "title.json"),
                media_path(date, "cover_props.json"),
                publish_path(date, "publish_guide.md"),
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
        "pipeline_state": state,
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
