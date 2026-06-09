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

from src.pipeline.agent_io import file_sha256, load_pipeline_state, stable_hash  # noqa: E402
from src.utils.text import normalize_cjk_mixed_spacing  # noqa: E402


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


def _format_mmss(seconds: float | int | None) -> str:
    total = max(0, int(round(float(seconds or 0))))
    return f"{total // 60:02d}:{total % 60:02d}"


def _script_runtime_payload(script_data: dict[str, Any]) -> dict[str, Any]:
    chapters = []
    for segment in script_data.get("segments") or []:
        if not isinstance(segment, dict):
            continue
        label = {
            "opening": "开场",
            "story_scan": "逐条速览",
            "closing": "收尾",
        }.get(segment.get("segment_type"), segment.get("segment_type"))
        chapters.append(
            {
                "start": _format_mmss(segment.get("start_time")),
                "end": _format_mmss(segment.get("end_time")),
                "label": label,
                "summary": normalize_cjk_mixed_spacing(
                    segment.get("audio_text") or ""
                )[:90],
            }
        )
    return {
        "total_duration": _format_mmss(script_data.get("total_duration")),
        "chapters": chapters,
    }


def _stale_command(date: str, stale: list[dict[str, str]]) -> dict[str, str]:
    artifacts = [item.get("artifact", "") for item in stale]
    if any("script.json" in artifact for artifact in artifacts):
        return {
            "command": f"uv run python scripts/agent_run.py --date {date} --steps write_script,translate_comments,synthesize_audio,title,prepare_render,cover_image,cover_thumbnail,publish_guide,render",
            "why": "Content changed after script generation; regenerate script and all downstream artifacts.",
        }
    if any("cli_props.json" in artifact for artifact in artifacts) or any(
        "output.mp4" in artifact for artifact in artifacts
    ):
        return {
            "command": f"uv run python scripts/agent_run.py --date {date} --steps prepare_render,render",
            "why": "Script changed after render props; regenerate props and render.",
        }
    if any("publish_guide.md" in artifact for artifact in artifacts):
        return {
            "command": f"uv run python scripts/agent_run.py --date {date} --steps title,publish_guide",
            "why": "Publish metadata changed after the guide; regenerate the guide.",
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


def _publish_guide_context(
    date: str, content_path: Path, script_path: Path
) -> dict[str, Any] | None:
    content_data = _read_json(content_path)
    script_data = _read_json(script_path)
    if not isinstance(content_data, dict) or not isinstance(script_data, dict):
        return None
    title_data = _read_json(content_path.parent / "title.json")
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
        "script_runtime": json.dumps(
            _script_runtime_payload(script_data), ensure_ascii=False, indent=2
        ),
        "items_json": json.dumps(items_payload, ensure_ascii=False, indent=2),
        "prompt_hash": file_sha256(Path("prompts/publish_guide.md")),
        "date": date,
    }


def _has_stale_publish_guide(date: str, content_path: Path, script_path: Path, guide_path: Path) -> bool:
    if not guide_path.exists():
        return False
    context = _publish_guide_context(date, content_path, script_path)
    if context is None:
        return False
    manifest = _read_json(guide_path.with_suffix(guide_path.suffix + ".manifest.json"))
    return not isinstance(manifest, dict) or manifest.get("input_hash") != stable_hash(context)


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
    if _has_stale_publish_guide(date, content, script, publish_guide):
        stale.append(
            {
                "artifact": str(publish_guide).replace("\\", "/"),
                "reason": "publish_guide.md input hash does not match content/script",
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
