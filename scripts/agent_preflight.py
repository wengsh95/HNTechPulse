#!/usr/bin/env python3
"""Agent preflight checks for HN TechPulse.

Outputs JSON so an agent can decide whether to run, resume, or gather missing
article pages before invoking the full pipeline.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline.agent_io import load_pipeline_state  # noqa: E402
from src.pipeline.agent_state import (  # noqa: E402
    BLOCK_EXTERNAL_TOOL_MISSING,
    BLOCK_MISSING_CREDENTIALS,
)
from src.pipeline.orchestrator import ALL_STEPS  # noqa: E402
from src.utils.config import load_config  # noqa: E402


def _default_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _check_yaml_config(config_path: str) -> tuple[dict[str, Any] | None, list[dict]]:
    issues = []
    try:
        config = load_config(config_path)
    except Exception as e:
        return None, [
            {
                "severity": "fatal",
                "check": "config_load",
                "message": f"{type(e).__name__}: {e}",
            }
        ]
    return config, issues


def _env_checks(config: dict[str, Any]) -> list[dict]:
    issues = []
    env_names = []
    llm_cfg = config.get("llm", {})
    if llm_cfg.get("api_key_env"):
        env_names.append(("llm", llm_cfg["api_key_env"]))
    tts_cfg = config.get("tts", {})
    if tts_cfg.get("api_key_env"):
        env_names.append(("tts", tts_cfg["api_key_env"]))
    image_cfg = config.get("image_generator", {})
    if image_cfg.get("enabled") and image_cfg.get("api_key_env"):
        env_names.append(("image_generator", image_cfg["api_key_env"]))

    for owner, env_name in env_names:
        if not os.environ.get(env_name):
            issues.append(
                {
                    "severity": "blocked",
                    "check": "env",
                    "blocked_reason": BLOCK_MISSING_CREDENTIALS,
                    "owner": owner,
                    "message": f"{env_name} is not set",
                }
            )
    return issues


def _tool_checks() -> list[dict]:
    issues = []
    for tool in ("uv", "ffmpeg", "npx"):
        if not shutil.which(tool):
            issues.append(
                {
                    "severity": "warning",
                    "check": "tool",
                    "blocked_reason": BLOCK_EXTERNAL_TOOL_MISSING,
                    "message": f"{tool} was not found on PATH",
                }
            )
    return issues


def _state_checks(date: str) -> tuple[dict[str, Any] | None, list[dict]]:
    issues = []
    state = load_pipeline_state(date)
    if not state:
        return None, issues
    if state.get("status") == "blocked":
        issues.append(
            {
                "severity": "blocked",
                "check": "pipeline_state",
                "blocked_reason": state.get("blocked_reason"),
                "message": state.get("blocked_reason") or "pipeline is blocked",
                "task_file": state.get("agent_task_file"),
            }
        )
    elif state.get("status") == "failed":
        issues.append(
            {
                "severity": "failed",
                "check": "pipeline_state",
                "message": state.get("failed_step") or "pipeline failed",
                "next_recommended_command": state.get("next_recommended_command"),
            }
        )
    return state, issues


def _last_run_summary(date: str) -> dict[str, Any] | None:
    """One-line summary of the most recent successful run for a date.

    Reads pipeline_state.json + report.md (if present) to give the agent
    the answer to "is this date already done, and if so, what did I get?"
    without re-running the full audit. Saves a full audit call when the
    agent's only question is "did I already do this date?".
    """
    state = load_pipeline_state(date)
    if not state or state.get("status") not in {"complete", "degraded"}:
        return None
    base = Path(f"data/{date}")
    summary: dict[str, Any] = {
        "completed_at": state.get("updated_at"),
        "status": state.get("status"),
        "completed_steps": state.get("completed_steps") or [],
        "blocked_reason": state.get("blocked_reason"),
        "degraded_items": state.get("degraded_items") or [],
    }
    # Pull a few more useful fields from the artifacts when present.
    report = base / "report.md"
    if report.exists():
        # Cheap parse: just grab total_duration, story_count, video title,
        # publishable from the markdown table.
        try:
            txt = report.read_text(encoding="utf-8")
        except OSError:
            txt = ""
        for key, label in [
            ("总耗时", "total_duration"),
            ("故事总数", "story_count"),
            ("视频标题", "video_title"),
            ("视频简介", "video_description"),
        ]:
            for line in txt.splitlines():
                if label in line or key in line:
                    if "|" in line:
                        cells = [c.strip() for c in line.split("|") if c.strip()]
                        if len(cells) >= 2:
                            summary[label] = cells[-1]
                            break
    # Title file is the most direct "is this usable" signal.
    title_path = base / "title.json"
    if title_path.exists():
        try:
            t = json.loads(title_path.read_text(encoding="utf-8"))
            summary["video_title"] = t.get("title") or summary.get("video_title")
        except (OSError, json.JSONDecodeError):
            pass
    # Variant decision: tells the agent which strategy won.
    var = base / "agent_variant_decision.json"
    if var.exists():
        try:
            v = json.loads(var.read_text(encoding="utf-8"))
            summary["selected_variant"] = v.get("selected_variant")
            summary["variant_score"] = (
                (v.get("scores") or [{}])[0].get("total_score")
                if v.get("scores")
                else None
            )
        except (OSError, json.JSONDecodeError):
            pass
    return summary


def _task_checks(date: str) -> tuple[dict[str, Any] | None, list[dict]]:
    path = Path(f"data/{date}/agent_tasks.json")
    if not path.exists():
        return None, []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return None, [
            {
                "severity": "warning",
                "check": "agent_tasks",
                "message": f"Could not read {path}: {e}",
            }
        ]

    pending = []
    for task in data.get("tasks", []):
        save_as = task.get("save_as", {})
        html_path = Path(save_as.get("html", ""))
        pdf_path = Path(save_as.get("pdf", ""))
        if not html_path.exists() and not pdf_path.exists():
            pending.append(task)
    issues = []
    if pending:
        issues.append(
            {
                "severity": "blocked",
                "check": "missing_article_files",
                "blocked_reason": "manual_download_required",
                "message": f"{len(pending)} article fetch task(s) still pending",
            }
        )
    return data, issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent preflight for HN TechPulse")
    parser.add_argument("--date", default=_default_date())
    parser.add_argument("--config", default="config/")
    args = parser.parse_args()

    config, issues = _check_yaml_config(args.config)
    if config:
        issues.extend(_env_checks(config))
    issues.extend(_tool_checks())
    state, state_issues = _state_checks(args.date)
    tasks, task_issues = _task_checks(args.date)
    issues.extend(state_issues)
    issues.extend(task_issues)

    fatal = any(i["severity"] == "fatal" for i in issues)
    blocked = any(i["severity"] == "blocked" for i in issues)
    status = "fatal" if fatal else "blocked" if blocked else "ok"
    last_run = _last_run_summary(args.date)
    payload = {
        "schema_version": 2,
        "date": args.date,
        "status": status,
        "issues": issues,
        "pipeline_state": state,
        "agent_tasks": tasks,
        "last_run_summary": last_run,
        "known_steps": list(ALL_STEPS),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 2 if fatal else 1 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
