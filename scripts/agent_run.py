#!/usr/bin/env python3
"""Managed entry point for agent pipeline runs.

Agents should call this wrapper instead of invoking main.py --agent directly.
It always runs preflight first, inspects artifact staleness, chooses a safe
step chain, and then runs the pipeline with the internal wrapper guard enabled.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.agent_preflight import main as preflight_main  # noqa: E402
from scripts.agent_status import build_status  # noqa: E402


DEFAULT_CHAIN = [
    "fetch",
    "prefilter",
    "fetch_comments",
    "enrich_articles",
    "translate_titles",
    "analyze_comments",
    "judge_comments",
    "write_script",
    "translate_comments",
    "synthesize_audio",
    "title",
    "cover_image",
    "cover_thumbnail",
    "publish_guide",
    "prepare_render",
    "render",
]

DOWNSTREAM_FROM = {
    "write_script": [
        "write_script",
        "translate_comments",
        "synthesize_audio",
        "title",
        "prepare_render",
        "cover_image",
        "cover_thumbnail",
        "publish_guide",
        "render",
    ],
    "prepare_render": ["prepare_render", "render"],
    "render": ["render"],
}


def _default_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _run(cmd: list[str], *, env: dict[str, str] | None = None) -> int:
    merged_env = dict(os.environ)
    if env:
        merged_env.update(env)
    completed = subprocess.run(cmd, cwd=ROOT, env=merged_env)
    return completed.returncode


def _preflight(date: str, config: str) -> int:
    old_argv = sys.argv[:]
    try:
        sys.argv = ["agent_preflight.py", "--date", date, "--config", config]
        return preflight_main()
    finally:
        sys.argv = old_argv


def _stale_recovery_steps(status: dict[str, Any]) -> list[str] | None:
    reasons = {item.get("reason") for item in status.get("stale_artifacts") or []}
    if any(reason and reason.startswith("content.json is newer") for reason in reasons):
        return DOWNSTREAM_FROM["write_script"]
    if "script.json is newer than cli_props.json" in reasons:
        return DOWNSTREAM_FROM["prepare_render"]
    if (
        "cli_props.json is newer than output.mp4" in reasons
        or "public Remotion props mirror is missing" in reasons
    ):
        return DOWNSTREAM_FROM["prepare_render"]
    return None


def _failed_recovery_steps(status: dict[str, Any]) -> list[str] | None:
    failed = status.get("failed_step") or status.get("current_step")
    if not failed:
        return None
    failed = str(failed)
    if failed in DEFAULT_CHAIN:
        return DEFAULT_CHAIN[DEFAULT_CHAIN.index(failed) :]
    return [failed]


def _manual_downloads_repaired(status: dict[str, Any]) -> bool:
    if status.get("blocked_reason") != "manual_download_required":
        return False
    agent_tasks = status.get("agent_tasks") or {}
    if agent_tasks.get("exists") and agent_tasks.get("pending_count") == 0:
        return True
    state = status.get("pipeline_state") or {}
    missing = state.get("missing_manual_files") or []
    if not missing:
        return False
    for item in missing:
        html = item.get("expected_html")
        pdf = item.get("expected_pdf")
        has_html = bool(html and (ROOT / str(html)).exists())
        has_pdf = bool(pdf and (ROOT / str(pdf)).exists())
        if not has_html and not has_pdf:
            return False
    return True


def _choose_steps(
    *,
    status: dict[str, Any],
    requested_steps: str | None,
    force_resume: bool,
) -> list[str] | None:
    if requested_steps:
        return [s.strip() for s in requested_steps.split(",") if s.strip()]

    pipeline_status = status.get("pipeline_status")
    if pipeline_status == "not_started":
        return DEFAULT_CHAIN
    if pipeline_status == "blocked" and _manual_downloads_repaired(status):
        return _failed_recovery_steps(status)
    if pipeline_status in {"failed", "running"} or force_resume:
        failed_steps = _failed_recovery_steps(status)
        if failed_steps:
            return failed_steps
    stale_steps = _stale_recovery_steps(status)
    if stale_steps:
        return stale_steps
    if pipeline_status == "complete":
        return None
    return DEFAULT_CHAIN


def main() -> int:
    parser = argparse.ArgumentParser(description="Managed agent pipeline runner")
    parser.add_argument("--date", default=_default_date())
    parser.add_argument("--config", default="config/")
    parser.add_argument("--steps", default=None, help="Override managed step choice")
    parser.add_argument("--resume", action="store_true", help="Resume from failed/current step")
    parser.add_argument("--force", action="store_true", help="Force renderer cache clear")
    parser.add_argument("--refresh-variants", action="store_true")
    parser.add_argument("--allow-degraded-enrichment", action="store_true")
    parser.add_argument("--renderer", choices=["remotion", "hyperframes"], default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the managed command without invoking main.py or mutating state",
    )
    parser.add_argument("--skip-audit", action="store_true")
    args = parser.parse_args()

    preflight_code = _preflight(args.date, args.config)
    if preflight_code not in {0}:
        preflight_status = build_status(args.date)
        if not _manual_downloads_repaired(preflight_status):
            return preflight_code

    status = build_status(args.date)
    _print_json({"event": "agent_status", **status})
    if status.get("pipeline_status") == "blocked" and not _manual_downloads_repaired(status):
        return 2

    steps = _choose_steps(
        status=status,
        requested_steps=args.steps,
        force_resume=args.resume,
    )
    if not steps:
        _print_json(
            {
                "event": "agent_run_noop",
                "date": args.date,
                "reason": "pipeline already complete and no stale artifact requires rerun",
            }
        )
        if not args.skip_audit and status.get("artifacts", {}).get("output", {}).get("exists"):
            return _run(["uv", "run", "python", "scripts/agent_audit.py", "--date", args.date])
        return 0

    cmd = [
        "uv",
        "run",
        "python",
        "main.py",
        "--date",
        args.date,
        "--config",
        args.config,
        "--agent",
        "--steps",
        ",".join(steps),
    ]
    if args.force:
        cmd.append("--force")
    if args.refresh_variants:
        cmd.append("--refresh-variants")
    if args.allow_degraded_enrichment:
        cmd.append("--allow-degraded-enrichment")
    if args.renderer:
        cmd.extend(["--renderer", args.renderer])
    _print_json({"event": "agent_run_command", "command": " ".join(cmd), "steps": steps})
    if args.dry_run:
        return 0

    code = _run(cmd, env={"HN_AGENT_RUNNER": "1"})
    if code != 0:
        return code

    final_status = build_status(args.date)
    _print_json({"event": "agent_status_after_run", **final_status})
    if (
        not args.skip_audit
        and final_status.get("artifacts", {}).get("output", {}).get("exists")
    ):
        return _run(["uv", "run", "python", "scripts/agent_audit.py", "--date", args.date])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
