#!/usr/bin/env python3
"""Machine-readable status for the Xiaohongshu card pipeline."""

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

from src.pipeline.agent_io import is_artifact_fresh, load_pipeline_state  # noqa: E402
from src.pipeline.paths import (  # noqa: E402
    agent_path,
    date_root,
    pipeline_path,
    publish_path,
    publish_xhs_cards_dir,
)
from src.pipeline.xhs_cards import (  # noqa: E402
    xhs_card_output_paths,
    xhs_card_set_is_fresh,
    xhs_cards_plan_inputs,
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
            save_as = task.get("save_as") or {}
            html_path = Path(save_as.get("html") or "")
            pdf_path = Path(save_as.get("pdf") or "")
            if not html_path.exists() and not pdf_path.exists():
                pending.append(task)
    return {
        "path": str(tasks_path).replace("\\", "/"),
        "exists": tasks_path.exists(),
        "pending_count": len(pending),
        "pending": pending,
    }


def _stale_command(date: str, stale: list[dict[str, str]]) -> dict[str, str]:
    reasons = {item.get("reason") for item in stale}
    if any(reason and "card plan" in reason for reason in reasons):
        return {
            "command": (
                f"uv run python scripts/agent_run.py --date {date} "
                "--steps plan_xhs_cards,render_xhs_cards"
            ),
            "why": "Card source inputs changed or the card plan is missing.",
        }
    return {
        "command": (
            f"uv run python scripts/agent_run.py --date {date} --steps render_xhs_cards"
        ),
        "why": "The card plan is current but PNG renders are missing or stale.",
    }


def build_status(date: str) -> dict[str, Any]:
    base = date_root(date)
    state = load_pipeline_state(date)
    content = pipeline_path(date, "content.json")
    judgement = pipeline_path(date, "comment_judgement.json")
    plan = publish_path(date, "xhs_cards.json")
    card_dir = publish_xhs_cards_dir(date)
    card_index = card_dir / "index.html"
    contact_sheet = card_dir / "_contact-sheet.png"
    card_paths = xhs_card_output_paths(date)

    stale: list[dict[str, str]] = []
    plan_fresh = plan.exists() and is_artifact_fresh(plan, xhs_cards_plan_inputs(date))
    if state and state.get("status") in {"complete", "degraded"} and not plan.exists():
        stale.append(
            {
                "artifact": str(plan).replace("\\", "/"),
                "reason": "Xiaohongshu card plan is missing",
            }
        )
    elif plan.exists() and not plan_fresh:
        stale.append(
            {
                "artifact": str(plan).replace("\\", "/"),
                "reason": "Xiaohongshu card plan inputs changed",
            }
        )
    elif plan_fresh and not xhs_card_set_is_fresh(date):
        stale.append(
            {
                "artifact": str(card_dir).replace("\\", "/"),
                "reason": "Xiaohongshu card renders are stale or incomplete",
            }
        )

    status = state.get("status") if state else "not_started"
    safe_next_commands: list[dict[str, str]] = []
    if not state:
        safe_next_commands.append(
            {
                "command": f"uv run python scripts/agent_run.py --date {date}",
                "why": "No pipeline_state.json exists for this date.",
            }
        )
    elif status in {"blocked", "failed", "running"}:
        safe_next_commands.append(
            {
                "command": f"uv run python scripts/agent_run.py --date {date} --resume",
                "why": f"Pipeline state is {status}.",
            }
        )
    elif stale:
        safe_next_commands.append(_stale_command(date, stale))
    elif card_index.exists():
        safe_next_commands.append(
            {
                "command": f"uv run python scripts/agent_audit.py --date {date}",
                "why": "The card package exists; run the final publishability audit.",
            }
        )

    return {
        "schema_version": 2,
        "date": date,
        "base_dir": str(base).replace("\\", "/"),
        "pipeline_status": status,
        "failed_step": (state or {}).get("failed_step"),
        "blocked_reason": (state or {}).get("blocked_reason"),
        "current_step": (state or {}).get("current_step"),
        "completed_steps": (state or {}).get("completed_steps") or [],
        "next_recommended_command": (state or {}).get("next_recommended_command"),
        "pipeline_state": state or {},
        "artifacts": {
            "content": _artifact(content),
            "comment_judgement": _artifact(judgement),
            "card_plan": _artifact(plan),
            "card_index": _artifact(card_index),
            "contact_sheet": _artifact(contact_sheet),
            "cards": [_artifact(path) for path in card_paths],
        },
        "stale_artifacts": stale,
        "agent_tasks": _pending_tasks(date),
        "safe_next_commands": safe_next_commands,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize Xiaohongshu card status")
    parser.add_argument("--date", default=_default_date())
    args = parser.parse_args()
    print(json.dumps(build_status(args.date), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
