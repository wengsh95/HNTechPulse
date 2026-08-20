#!/usr/bin/env python3
"""Managed entry point for the video pipeline."""

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
from src.pipeline.human_review import approve_current_script  # noqa: E402


# The managed chain runs upstream editorial steps, then continues through TTS
# and the configured renderer.
VIDEO_CHAIN = [
    "fetch",
    "prefilter",
    "fetch_comments",
    "enrich_articles",
    "translate_titles",
    "analyze_comments",
    "judge_comments",
    "write_script",
    "draft_quick_news",
    "normalize_video_structure",
    "prepare_story_images",
    "review_script",
    "human_review",
    "translate_comments",
    "title",
    "cover_image",
    "cover_thumbnail",
    "draft_storyboard",
    "apply_storyboard",
    "prepare_subtitles",
    "synthesize_audio",
    "prepare_render",
    "render",
]

DOWNSTREAM_FROM = {
    "draft_quick_news": ["draft_quick_news"],
    "normalize_video_structure": [
        "normalize_video_structure",
        "prepare_story_images",
        "review_script",
        "human_review",
        "translate_comments",
        "title",
        "cover_image",
        "cover_thumbnail",
        "draft_storyboard",
        "apply_storyboard",
        "prepare_subtitles",
        "synthesize_audio",
        "prepare_render",
        "render",
    ],
    "prepare_story_images": ["prepare_story_images"],
    "draft_storyboard": ["draft_storyboard"],
    "apply_storyboard": [
        "apply_storyboard",
        "prepare_subtitles",
        "synthesize_audio",
        "prepare_render",
        "render",
    ],
    "prepare_subtitles": [
        "prepare_subtitles",
        "synthesize_audio",
        "prepare_render",
        "render",
    ],
    "prepare_render": ["prepare_render", "render"],
    "render": ["render"],
}

DOWNSTREAM_ONLY_STEPS = {
    "draft_quick_news",
    "normalize_video_structure",
    "prepare_story_images",
    "human_review",
    "draft_storyboard",
    "apply_storyboard",
    "prepare_subtitles",
    "synthesize_audio",
    "prepare_render",
    "render",
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
        sys.argv = [
            "agent_preflight.py",
            "--date",
            date,
            "--config",
            config,
        ]
        return preflight_main()
    finally:
        sys.argv = old_argv


def _stale_recovery_steps(status: dict[str, Any]) -> list[str] | None:
    """Recover the stale planning/rendering tail."""
    reasons = {item.get("reason") for item in status.get("stale_artifacts") or []}
    if any(reason and reason.startswith("content.json is newer") for reason in reasons):
        return VIDEO_CHAIN[VIDEO_CHAIN.index("write_script") :]
    if any("script_approval.json" in reason for reason in reasons if reason):
        return VIDEO_CHAIN[VIDEO_CHAIN.index("human_review") :]
    if any(reason and "storyboard.json is newer" in reason for reason in reasons):
        return DOWNSTREAM_FROM["apply_storyboard"]
    if any(reason and "subtitle_plan.json" in reason for reason in reasons):
        return DOWNSTREAM_FROM["prepare_subtitles"]
    if any(reason and "audio_manifest.json" in reason for reason in reasons):
        return DOWNSTREAM_FROM["prepare_subtitles"]
    if "script.json is newer than cli_props.json" in reasons:
        return DOWNSTREAM_FROM["prepare_subtitles"]
    if (
        "cli_props.json is newer than output.mp4" in reasons
        or "public Remotion props mirror is missing" in reasons
        or "HyperFrames project index is missing" in reasons
    ):
        return DOWNSTREAM_FROM["prepare_subtitles"]
    return None


def _failed_recovery_steps(status: dict[str, Any]) -> list[str] | None:
    failed = status.get("failed_step") or status.get("current_step")
    if not failed:
        return None
    failed = str(failed)
    chain = VIDEO_CHAIN
    if failed == "prepare_story_images":
        # Image selection can block after script recovery.  Rehydrate quick
        # news and its visual structure before continuing the video tail.
        return chain[chain.index("draft_quick_news") :]
    if failed in chain:
        return chain[chain.index(failed) :]
    return chain


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
        html_path = item.get("expected_html")
        pdf_path = item.get("expected_pdf")
        has_html = bool(html_path and (ROOT / str(html_path)).exists())
        has_pdf = bool(pdf_path and (ROOT / str(pdf_path)).exists())
        if not has_html and not has_pdf:
            return False
    return True


def _manual_image_selections_repaired(status: dict[str, Any]) -> bool:
    if status.get("blocked_reason") != "manual_image_selection_required":
        return False
    agent_tasks = status.get("agent_tasks") or {}
    return bool(agent_tasks.get("exists") and agent_tasks.get("pending_count") == 0)


def _manual_script_review_repaired(status: dict[str, Any]) -> bool:
    return bool(
        status.get("blocked_reason") == "manual_script_review_required"
        and status.get("script_approval_current") is True
    )


def _is_explicit_downstream_request(
    *, requested_steps: str | None, from_step: str | None
) -> bool:
    """Return whether the request is safe to run without upstream context."""
    allowed = DOWNSTREAM_ONLY_STEPS
    if from_step:
        return from_step in allowed
    if not requested_steps:
        return False
    steps = {step.strip() for step in requested_steps.split(",") if step.strip()}
    return bool(steps) and steps.issubset(allowed)


def _choose_steps(
    *,
    status: dict[str, Any],
    requested_steps: str | None,
    force_resume: bool,
    from_step: str | None = None,
    refresh_selection: bool = False,
    refresh_script: bool = False,
    refresh_variants: bool = False,
) -> list[str] | None:
    if from_step:
        chain = VIDEO_CHAIN
        if from_step not in chain:
            raise ValueError(f"Unknown --from step: {from_step}")
        if from_step in {"synthesize_audio", "prepare_render"}:
            # Subtitle selection is a local-agent prerequisite for every
            # downstream video recovery, even when the caller names an older
            # audio/render entry point.
            return VIDEO_CHAIN[VIDEO_CHAIN.index("prepare_subtitles") :]
        return chain[chain.index(from_step) :]
    if requested_steps:
        return [step.strip() for step in requested_steps.split(",") if step.strip()]

    chain = VIDEO_CHAIN
    if refresh_selection:
        return chain
    if refresh_script or refresh_variants:
        return VIDEO_CHAIN[VIDEO_CHAIN.index("write_script") :]
    pipeline_status = status.get("pipeline_status")
    if pipeline_status == "not_started":
        return chain
    if pipeline_status == "blocked" and (
        _manual_downloads_repaired(status)
        or _manual_image_selections_repaired(status)
        or _manual_script_review_repaired(status)
    ):
        return _failed_recovery_steps(status)
    if pipeline_status == "blocked":
        return None
    if pipeline_status in {"failed", "running"} or force_resume:
        failed_steps = _failed_recovery_steps(status)
        if failed_steps:
            return failed_steps
    stale_steps = _stale_recovery_steps(status)
    if stale_steps:
        return stale_steps
    if pipeline_status == "complete":
        return None
    return chain


def main() -> int:
    parser = argparse.ArgumentParser(description="Managed HN TechPulse pipeline runner")
    parser.add_argument("--date", default=_default_date())
    parser.add_argument("--config", default="config/")
    parser.add_argument("--steps", default=None, help="Override managed step choice")
    parser.add_argument(
        "--from",
        dest="from_step",
        default=None,
        help="Run this step and all downstream pipeline steps",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--refresh-variants", action="store_true")
    parser.add_argument(
        "--refresh-script",
        action="store_true",
        help="Explicitly regenerate a manually changed editorial script",
    )
    parser.add_argument(
        "--refresh-selection",
        action="store_true",
        help="Explicitly allow prefilter to replace the locked story selection",
    )
    parser.add_argument("--allow-degraded-enrichment", action="store_true")
    parser.add_argument("--renderer", choices=["remotion", "hyperframes"], default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the command without invoking main.py or mutating state",
    )
    parser.add_argument("--skip-audit", action="store_true")
    parser.add_argument(
        "--approve-script",
        action="store_true",
        help="Approve the exact script shown in the current human-review page and resume",
    )
    parser.add_argument(
        "--reviewer",
        default="human",
        help="Reviewer name recorded with --approve-script",
    )
    parser.add_argument(
        "--approval-note",
        default="",
        help="Optional audit note recorded with --approve-script",
    )
    args = parser.parse_args()

    if args.steps and args.from_step:
        parser.error("--steps and --from are mutually exclusive")
    if args.approve_script and any(
        (args.steps, args.from_step, args.refresh_script, args.refresh_variants)
    ):
        parser.error(
            "--approve-script cannot be combined with --steps, --from, or script refresh"
        )

    if args.approve_script:
        try:
            approval_path = approve_current_script(
                args.date,
                reviewer=args.reviewer,
                note=args.approval_note,
            )
        except (FileNotFoundError, OSError, ValueError) as exc:
            _print_json(
                {
                    "event": "script_approval_failed",
                    "date": args.date,
                    "error": str(exc),
                }
            )
            return 2
        _print_json(
            {
                "event": "script_approved",
                "date": args.date,
                "approval": str(approval_path).replace("\\", "/"),
            }
        )

    preflight_code = _preflight(args.date, args.config)
    if preflight_code != 0:
        preflight_status = build_status(args.date)
        repaired = (
            _manual_downloads_repaired(preflight_status)
            or (_manual_image_selections_repaired(preflight_status))
            or _manual_script_review_repaired(preflight_status)
        )
        explicit_downstream = _is_explicit_downstream_request(
            requested_steps=args.steps,
            from_step=args.from_step,
        )
        # Explicit downstream work may operate on an already-reviewed local
        # script, even when an unrelated upstream enrichment task is blocked.
        # Fatal preflight failures still stop the run.
        if preflight_code != 1 or (
            not repaired and not args.refresh_selection and not explicit_downstream
        ):
            return preflight_code

    status = build_status(args.date)
    _print_json({"event": "agent_status", **status})
    if (
        status.get("pipeline_status") == "blocked"
        and not (
            _manual_downloads_repaired(status)
            or _manual_image_selections_repaired(status)
            or _manual_script_review_repaired(status)
        )
        and not args.refresh_selection
        and not _is_explicit_downstream_request(
            requested_steps=args.steps,
            from_step=args.from_step,
        )
    ):
        return 2

    steps = _choose_steps(
        status=status,
        requested_steps=args.steps,
        from_step=args.from_step,
        force_resume=args.resume,
        refresh_selection=args.refresh_selection,
        refresh_script=args.refresh_script,
        refresh_variants=args.refresh_variants,
    )
    if not steps:
        _print_json(
            {
                "event": "agent_run_noop",
                "date": args.date,
                "reason": "video product is complete and fresh",
            }
        )
        if not args.skip_audit and status.get("artifacts", {}).get("output", {}).get(
            "exists"
        ):
            return _run(
                ["uv", "run", "python", "scripts/agent_audit.py", "--date", args.date]
            )
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
    if args.allow_degraded_enrichment:
        cmd.append("--allow-degraded-enrichment")
    if args.force:
        cmd.append("--force")
    if args.refresh_variants:
        cmd.append("--refresh-variants")
    if args.refresh_script:
        cmd.append("--refresh-script")
    if args.refresh_selection:
        cmd.append("--refresh-selection")
    if args.renderer:
        cmd.extend(["--renderer", args.renderer])
    _print_json(
        {"event": "agent_run_command", "command": " ".join(cmd), "steps": steps}
    )
    if args.dry_run:
        return 0

    code = _run(cmd, env={"HN_AGENT_RUNNER": "1"})
    if code != 0:
        return code

    final_status = build_status(args.date)
    _print_json({"event": "agent_status_after_run", **final_status})
    if not args.skip_audit and final_status.get("artifacts", {}).get("output", {}).get(
        "exists"
    ):
        return _run(
            ["uv", "run", "python", "scripts/agent_audit.py", "--date", args.date]
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
