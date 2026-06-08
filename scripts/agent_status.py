#!/usr/bin/env python3
"""Compact machine-readable status for agent runs.

This script is intentionally read-only. It summarizes the date-scoped state,
artifact presence/staleness, and the safest next commands without requiring an
agent to inspect several JSON files manually.
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

from src.pipeline.agent_io import load_pipeline_state  # noqa: E402


def _default_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _artifact(path: Path) -> dict[str, Any]:
    exists = path.exists()
    return {
        "path": str(path).replace("\\", "/"),
        "exists": exists,
        "mtime": path.stat().st_mtime if exists else None,
        "size": path.stat().st_size if exists and path.is_file() else None,
    }


def _is_newer(a: Path, b: Path) -> bool:
    return a.exists() and b.exists() and a.stat().st_mtime > b.stat().st_mtime


def _stale_command(date: str, stale: list[dict[str, str]]) -> dict[str, str]:
    reasons = [item.get("reason", "") for item in stale]
    if any(reason.startswith("content.json is newer") for reason in reasons):
        return {
            "command": f"uv run python scripts/agent_run.py --date {date} --steps write_script,translate_comments,synthesize_audio,title,prepare_render,cover_image,cover_thumbnail,publish_guide,render",
            "why": "Content changed after script generation; regenerate script and all downstream artifacts.",
        }
    if any("script.json is newer" in reason for reason in reasons):
        return {
            "command": f"uv run python scripts/agent_run.py --date {date} --steps prepare_render,render",
            "why": "Script changed after render props; regenerate props and render.",
        }
    return {
        "command": f"uv run python scripts/agent_run.py --date {date} --steps prepare_render,render",
        "why": "Render props/output look stale or incomplete.",
    }


def _pending_tasks(base: Path) -> dict[str, Any]:
    tasks_path = base / "agent_tasks.json"
    data = _read_json(tasks_path)
    pending: list[dict[str, Any]] = []
    if isinstance(data, dict):
        for task in data.get("tasks") or []:
            save_as = task.get("save_as") or {}
            html = Path(save_as.get("html") or "")
            pdf = Path(save_as.get("pdf") or "")
            if not html.exists() and not pdf.exists():
                pending.append(task)
    return {
        "path": str(tasks_path).replace("\\", "/"),
        "exists": tasks_path.exists(),
        "pending_count": len(pending),
        "pending": pending,
    }


def build_status(date: str) -> dict[str, Any]:
    base = Path("data") / date
    state = load_pipeline_state(date)
    content = base / "content.json"
    script = base / "script.json"
    cli_props = base / "cli_props.json"
    public_props = base / "remotion" / "public" / "props.json"
    output = base / "output.mp4"
    title = base / "title.json"
    cover = base / "cover.png"
    publish_guide = base / "publish_guide.md"

    stale: list[dict[str, str]] = []
    if _is_newer(content, script):
        stale.append(
            {
                "artifact": str(script).replace("\\", "/"),
                "reason": "content.json is newer than script.json",
            }
        )
    if _is_newer(content, cli_props):
        stale.append(
            {
                "artifact": str(cli_props).replace("\\", "/"),
                "reason": "content.json is newer than cli_props.json",
            }
        )
    if _is_newer(script, cli_props):
        stale.append(
            {
                "artifact": str(cli_props).replace("\\", "/"),
                "reason": "script.json is newer than cli_props.json",
            }
        )
    if _is_newer(cli_props, output):
        stale.append(
            {
                "artifact": str(output).replace("\\", "/"),
                "reason": "cli_props.json is newer than output.mp4",
            }
        )
    if cli_props.exists() and not public_props.exists():
        stale.append(
            {
                "artifact": str(public_props).replace("\\", "/"),
                "reason": "public Remotion props mirror is missing",
            }
        )

    safe_next_commands: list[dict[str, str]] = []
    status = state.get("status") if state else "not_started"
    if not state:
        safe_next_commands.append(
            {
                "command": f"uv run python scripts/agent_run.py --date {date}",
                "why": "No pipeline_state.json exists for this date.",
            }
        )
    elif status in {"blocked", "failed", "running"}:
        next_step = (state or {}).get("failed_step") or (state or {}).get("current_step")
        command = (
            f"uv run python scripts/agent_run.py --date {date} --steps {next_step}"
            if next_step
            else f"uv run python scripts/agent_run.py --date {date} --resume"
        )
        safe_next_commands.append(
            {
                "command": command,
                "why": f"Pipeline state is {status}.",
            }
        )
    elif stale:
        safe_next_commands.append(_stale_command(date, stale))
    elif cli_props.exists():
        safe_next_commands.append(
            {
                "command": f"uv run python scripts/render_review_stills.py --date {date}",
                "why": "cli_props.json exists; review stills can be rendered without rerunning LLM/TTS.",
            }
        )
    if output.exists():
        safe_next_commands.append(
            {
                "command": f"uv run python scripts/agent_audit.py --date {date}",
                "why": "Final video exists; run publishability audit.",
            }
        )

    return {
        "schema_version": 1,
        "date": date,
        "base_dir": str(base).replace("\\", "/"),
        "pipeline_status": status,
        "failed_step": (state or {}).get("failed_step"),
        "blocked_reason": (state or {}).get("blocked_reason"),
        "current_step": (state or {}).get("current_step"),
        "completed_steps": (state or {}).get("completed_steps") or [],
        "next_recommended_command": (state or {}).get("next_recommended_command"),
        "artifacts": {
            "content": _artifact(base / "content.json"),
            "script": _artifact(script),
            "cli_props": _artifact(cli_props),
            "public_props": _artifact(public_props),
            "output": _artifact(output),
            "title": _artifact(title),
            "cover": _artifact(cover),
            "publish_guide": _artifact(publish_guide),
        },
        "stale_artifacts": stale,
        "agent_tasks": _pending_tasks(base),
        "safe_next_commands": safe_next_commands,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize agent run status")
    parser.add_argument("--date", default=_default_date())
    args = parser.parse_args()
    print(json.dumps(build_status(args.date), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
