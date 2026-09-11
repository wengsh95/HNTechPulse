#!/usr/bin/env python3
"""Machine-readable status for the video pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline.paths import (  # noqa: E402
    agent_path,
    date_root,
    media_images_dir,
    pipeline_audio_dir,
    pipeline_path,
    publish_path,
    render_path,
    render_remotion_dir,
)
from src.pipeline.human_review import (  # noqa: E402
    script_review_page_path,
)
from src.workflow import load_workflow_report  # noqa: E402
from src.workflow.freshness import (  # noqa: E402
    check_freshness,
    command_for,
)


def _default_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _workflow_status(date: str) -> dict[str, Any] | None:
    """Read the native workflow without mutating it."""
    return load_workflow_report(date)


def _artifact(path: Path) -> dict[str, Any]:
    exists = path.exists()
    return {
        "path": str(path).replace("\\", "/"),
        "exists": exists,
        "mtime": path.stat().st_mtime if exists else None,
        "size": path.stat().st_size if exists and path.is_file() else None,
    }


def _pending_tasks(date: str) -> dict[str, Any]:
    tasks_path = agent_path(date, "agent_tasks.json")
    data = _read_json(tasks_path)
    pending: list[dict[str, Any]] = []
    if isinstance(data, dict):
        for task in data.get("tasks") or []:
            if task.get("task_type") == "select_image":
                selection_path = Path(
                    task.get("selection_file")
                    or (task.get("save_as") or {}).get("image_selection")
                    or ""
                )
                selection = _read_json(selection_path)
                entry = (
                    selection.get("items", {}).get(str(task.get("story_id")), {})
                    if isinstance(selection, dict)
                    else {}
                )
                selected = (
                    entry.get("selected_image") if isinstance(entry, dict) else None
                )
                candidate_paths = {
                    candidate.get("path")
                    for candidate in task.get("candidates") or []
                    if isinstance(candidate, dict)
                }
                local_path = None
                selected_candidate: dict[str, Any] | None = None
                for candidate in task.get("candidates") or []:
                    if (
                        isinstance(candidate, dict)
                        and candidate.get("path") == selected
                    ):
                        local_path = candidate.get("local_path")
                        selected_candidate = candidate
                        break
                selected_sources = {
                    entry.get("selection_source") if isinstance(entry, dict) else None,
                    selected_candidate.get("selection_source")
                    if isinstance(selected_candidate, dict)
                    else None,
                }
                confirmed_by_agent = not {
                    "llm",
                    "heuristic",
                }.intersection(selected_sources)
                selected_exists = bool(
                    local_path
                    and Path(str(local_path)).exists()
                    or selected
                    and (
                        Path(str(selected)).exists()
                        or (
                            str(selected).replace("\\", "/").startswith("images/")
                            and (
                                media_images_dir(date) / Path(str(selected)).name
                            ).exists()
                        )
                    )
                )
                if (
                    not selected
                    or selected not in candidate_paths
                    or not selected_exists
                    or not confirmed_by_agent
                ):
                    pending.append(task)
                continue
            save_as = task.get("save_as") or {}
            html_value = save_as.get("html")
            pdf_value = save_as.get("pdf")
            html_exists = bool(html_value and Path(str(html_value)).exists())
            pdf_exists = bool(pdf_value and Path(str(pdf_value)).exists())
            if not html_exists and not pdf_exists:
                pending.append(task)
    return {
        "path": str(tasks_path).replace("\\", "/"),
        "exists": tasks_path.exists(),
        "pending_count": len(pending),
        "pending": pending,
    }


def _is_newer(a: Path, b: Path) -> bool:
    return a.exists() and b.exists() and a.stat().st_mtime > b.stat().st_mtime


def _publish_guide_context(
    date: str, content_path: Path, script_path: Path
) -> dict[str, Any] | None:
    """Build the publish-guide input context (delegated to freshness)."""
    from src.workflow.freshness import publish_guide_context

    return publish_guide_context(date, content_path, script_path)


def _has_stale_publish_guide(
    date: str, content_path: Path, script_path: Path, guide_path: Path
) -> bool:
    """Check whether the publish guide is stale (delegated to freshness)."""
    from src.workflow.freshness import has_stale_publish_guide

    return has_stale_publish_guide(date, content_path, script_path, guide_path)


def _video_stale_command(date: str, stale: list[dict[str, str]]) -> dict[str, str]:
    """Recommended repair command for stale artifacts.

    Delegates to the freshness module, which owns the repair routing.
    """
    return command_for(date, stale)


def _build_video_status(date: str) -> dict[str, Any]:
    base = date_root(date)
    workflow = _workflow_status(date)
    execution = workflow.get("metadata", {}) if isinstance(workflow, dict) else {}
    content = pipeline_path(date, "content.json")
    script = pipeline_path(date, "script.json")
    script_review = pipeline_path(date, "script_review.json")
    script_review_page = script_review_page_path(date)
    storyboard = pipeline_path(date, "storyboard.json")
    story_images = pipeline_path(date, "story_images.json")
    subtitle_plan = pipeline_path(date, "subtitle_plan.json")
    audio_manifest = pipeline_path(date, "audio_manifest.json")
    cli_props = render_path(date, "cli_props.json")
    public_props = render_remotion_dir(date) / "public" / "props.json"
    output = publish_path(date, "output.mp4")
    title = publish_path(date, "title.json")
    cover = publish_path(date, "cover.png")
    publish_guide = publish_path(date, "publish_guide.md")
    script_approval = agent_path(date, "script_approval.json")

    freshness = check_freshness(date)
    stale: list[dict[str, str]] = [record.as_wire_dict() for record in freshness.stale]
    approval_current = freshness.approval_current

    if workflow is None:
        status = "not_started"
    else:
        workflow_state = workflow.get("status")
        if workflow_state == "corrupt":
            status = "failed"
        elif workflow_state == "pending":
            workflow_states = workflow.get("states") or {}
            status = (
                "not_started"
                if workflow_states
                and all(
                    record.get("status") == "pending"
                    for record in workflow_states.values()
                )
                else "running"
            )
        else:
            status = workflow_state or "not_started"
    safe_next_commands: list[dict[str, str]] = []
    if workflow is not None and workflow.get("status") == "corrupt":
        safe_next_commands.append(
            {
                "command": "Create a new workflow state file after inspecting the corrupt file.",
                "why": "The native workflow state cannot be trusted and is not auto-converted.",
            }
        )
    elif workflow is None:
        safe_next_commands.append(
            {
                "command": f"uv run python scripts/internal/agent/agent_run.py --date {date}",
                "why": "No native workflow state exists for this date.",
            }
        )
    elif (
        status == "blocked"
        and execution.get("blocked_reason") == "manual_script_review_required"
    ):
        safe_next_commands.append(
            {
                "command": (
                    f"uv run python scripts/internal/agent/agent_run.py --date {date} --approve-script"
                ),
                "why": "Review script_review.html, then approve this exact script version.",
            }
        )
    elif status in {"blocked", "failed", "running"}:
        safe_next_commands.append(
            {
                "command": f"uv run python scripts/internal/agent/agent_run.py --date {date} --resume",
                "why": f"Pipeline state is {status}.",
            }
        )
    elif stale:
        safe_next_commands.append(_video_stale_command(date, stale))
    elif cli_props.exists():
        safe_next_commands.append(
            {
                "command": f"uv run python scripts/internal/tools/render_review_stills.py --date {date}",
                "why": "cli_props.json exists; review stills can be rendered without rerunning LLM/TTS.",
            }
        )
    if output.exists():
        safe_next_commands.append(
            {
                "command": f"uv run python scripts/internal/agent/agent_audit.py --date {date}",
                "why": "Final video exists; run publishability audit.",
            }
        )

    return {
        "schema_version": 2,
        "date": date,
        "base_dir": str(base).replace("\\", "/"),
        "pipeline_status": status,
        "failed_step": execution.get("failed_pipeline_step"),
        "blocked_reason": execution.get("blocked_reason"),
        "current_step": execution.get("current_pipeline_step"),
        "completed_steps": execution.get("completed_pipeline_steps") or [],
        "next_recommended_command": (
            safe_next_commands[0].get("command") if safe_next_commands else None
        ),
        "workflow": workflow,
        "script_approval_current": approval_current,
        "artifacts": {
            "content": _artifact(content),
            "script": _artifact(script),
            "script_review": _artifact(script_review),
            "script_review_page": _artifact(script_review_page),
            "script_approval": _artifact(script_approval),
            "storyboard": _artifact(storyboard),
            "story_images": _artifact(story_images),
            "subtitle_plan": _artifact(subtitle_plan),
            "audio_manifest": _artifact(audio_manifest),
            "audio_dir": _artifact(pipeline_audio_dir(date)),
            "cli_props": _artifact(cli_props),
            "public_props": _artifact(public_props),
            "output": _artifact(output),
            "title": _artifact(title),
            "cover": _artifact(cover),
            "publish_guide": _artifact(publish_guide),
        },
        "stale_artifacts": stale,
        "agent_tasks": _pending_tasks(date),
        "safe_next_commands": safe_next_commands,
    }


def build_status(date: str) -> dict[str, Any]:
    return _build_video_status(date)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize HN TechPulse pipeline status"
    )
    parser.add_argument("--date", default=_default_date())
    args = parser.parse_args()
    print(json.dumps(build_status(args.date), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
