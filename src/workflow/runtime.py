"""Runtime metadata and agent task files for the native workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.pipeline.agent_io import append_agent_event, utc_now
from src.pipeline.paths import agent_path, pipeline_path, raw_downloaded_pages_dir
from src.utils.atomic_io import atomic_write_json

BLOCK_MANUAL_DOWNLOAD = "manual_download_required"
BLOCK_MANUAL_IMAGE_SELECTION = "manual_image_selection_required"
BLOCK_MANUAL_SCRIPT_REVIEW = "manual_script_review_required"
BLOCK_MISSING_CREDENTIALS = "missing_credentials"
BLOCK_EXTERNAL_TOOL_MISSING = "external_tool_missing"
BLOCK_INSUFFICIENT_CONTEXT = "insufficient_story_context"


def _task_path(date: str) -> Path:
    return agent_path(date, "agent_tasks.json")


def write_manual_download_tasks(
    date: str, items: list[Any], *, synthesis_from: str = "any"
) -> Path:
    tasks = []
    for item in items:
        story_id = str(getattr(item, "source_id", ""))
        tasks.append(
            {
                "schema_version": 2,
                "task_type": "fetch_article",
                "status": "pending",
                "story_id": story_id,
                "title": getattr(item, "title", "") or "",
                "url": getattr(item, "url", "") or "",
                "synthesis_from": synthesis_from,
                "save_as": {
                    "html": f"{raw_downloaded_pages_dir(date).as_posix()}/{story_id}.html",
                    "pdf": f"{raw_downloaded_pages_dir(date).as_posix()}/{story_id}.pdf",
                },
                "acceptable_outputs": ["html", "pdf", "synthesis_html"],
                "agent_capabilities": ["browser", "mcp", "web_search"],
                "repair_steps": [
                    "Open the URL with browser/MCP.",
                    "Prefer saving the rendered article HTML to save_as.html.",
                    "If the source is a PDF, save it to save_as.pdf.",
                    "If the original URL is blocked, use an authoritative mirror or official source.",
                    f"Resume with: uv run python scripts/agent_run.py --date {date} --resume",
                ],
                "failure_policy": "Do not fabricate article context; leave the task pending if no reliable source is available.",
            }
        )
    return _write_tasks(
        date,
        BLOCK_MANUAL_DOWNLOAD,
        tasks,
        "Every pending task has a reliable HTML or PDF source file.",
    )


def write_image_selection_tasks(date: str, items: list[dict[str, Any]]) -> Path:
    selection_file = str(pipeline_path(date, "image_selection.json")).replace("\\", "/")
    tasks = []
    for item in items:
        tasks.append(
            {
                "schema_version": 2,
                "task_type": "select_image",
                "status": "pending",
                "story_id": item.get("story_id", ""),
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "candidates": item.get("candidates", []),
                "selection_file": selection_file,
                "save_as": {"image_selection": selection_file},
                "acceptable_outputs": ["image_selection"],
                "agent_capabilities": ["view_image", "browser", "mcp", "web_search"],
                "repair_steps": [
                    "Inspect every candidate image.",
                    "Choose the candidate that best matches the story subject.",
                    "Write one selected_image entry for every story.",
                    f"Resume with: uv run python scripts/agent_run.py --date {date} --resume",
                ],
                "failure_policy": "Do not invent an image path; leave the task pending when no candidate is usable.",
            }
        )
    return _write_tasks(
        date,
        BLOCK_MANUAL_IMAGE_SELECTION,
        tasks,
        "Every story has a confirmed image selection.",
    )


def _write_tasks(
    date: str, reason: str, tasks: list[dict[str, Any]], condition: str
) -> Path:
    path = _task_path(date)
    payload = {
        "schema_version": 2,
        "date": date,
        "created_at": utc_now(),
        "blocked_reason": reason,
        "repair_contract": {
            "owner": "agent",
            "minimum_success_condition": condition,
            "resume_command": f"uv run python scripts/agent_run.py --date {date} --resume",
        },
        "tasks": tasks,
    }
    atomic_write_json(path, payload)
    append_agent_event(
        date, "agent_tasks_written", reason=reason, item_count=len(tasks)
    )
    return path
