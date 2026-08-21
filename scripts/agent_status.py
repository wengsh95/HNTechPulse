#!/usr/bin/env python3
"""Machine-readable status for the video pipeline."""

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

from src.pipeline.agent_io import (  # noqa: E402
    file_sha256,
    is_artifact_fresh,
    stable_hash,
)
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
from src.pipeline.script.io import (  # noqa: E402
    audio_manifest_is_usable,
    load_audio_manifest,
    load_script,
    script_audio_input_hash,
    script_editorial_hash,
)
from src.pipeline.human_review import (  # noqa: E402
    script_approval_is_current,
    script_review_page_path,
)
from src.workflow import load_workflow_report  # noqa: E402


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


def _prepare_render_renderer(date: str) -> str:
    manifest_path = render_path(date, "cli_props.json").with_suffix(
        render_path(date, "cli_props.json").suffix + ".manifest.json"
    )
    manifest = _read_json(manifest_path)
    if not isinstance(manifest, dict):
        return ""
    inputs = manifest.get("inputs") or {}
    return str(inputs.get("renderer") or "") if isinstance(inputs, dict) else ""


def _is_newer(a: Path, b: Path) -> bool:
    return a.exists() and b.exists() and a.stat().st_mtime > b.stat().st_mtime


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


def _has_stale_publish_guide(
    date: str, content_path: Path, script_path: Path, guide_path: Path
) -> bool:
    if not guide_path.exists():
        return False
    context = _publish_guide_context(date, content_path, script_path)
    if context is None:
        return False
    manifest = _read_json(guide_path.with_suffix(guide_path.suffix + ".manifest.json"))
    return not isinstance(manifest, dict) or manifest.get("input_hash") != stable_hash(
        context
    )


def _video_stale_command(date: str, stale: list[dict[str, str]]) -> dict[str, str]:
    artifacts = [item.get("artifact", "") for item in stale]
    if any("script.json" in artifact for artifact in artifacts):
        return {
            "command": (
                f"uv run python scripts/agent_run.py --date {date} --refresh-script"
            ),
            "why": "Content changed after script generation; regenerate video artifacts.",
        }
    if any("script_approval.json" in artifact for artifact in artifacts):
        return {
            "command": (
                f"uv run python scripts/agent_run.py --date {date} --from human_review"
            ),
            "why": "The current editorial script has not passed the human checkpoint.",
        }
    if any("storyboard.json" in artifact for artifact in artifacts):
        return {
            "command": (
                f"uv run python scripts/agent_run.py --date {date} "
                "--from apply_storyboard"
            ),
            "why": "storyboard.json changed after script application; rebuild video visuals.",
        }
    if any("subtitle_plan.json" in artifact for artifact in artifacts):
        return {
            "command": (
                f"uv run python scripts/agent_run.py --date {date} "
                "--steps prepare_subtitles,synthesize_audio,prepare_render,render"
            ),
            "why": "The local subtitle plan is missing or does not match script.json.",
        }
    if any("audio_manifest.json" in artifact for artifact in artifacts):
        return {
            "command": (
                f"uv run python scripts/agent_run.py --date {date} "
                "--steps prepare_subtitles,synthesize_audio,prepare_render,render"
            ),
            "why": "The editorial script changed; regenerate audio and downstream video artifacts.",
        }
    return {
        "command": (
            f"uv run python scripts/agent_run.py --date {date} "
            "--steps prepare_subtitles,prepare_render,render"
        ),
        "why": "Render props/output look stale or incomplete.",
    }


def _build_video_status(date: str) -> dict[str, Any]:
    base = date_root(date)
    workflow = _workflow_status(date)
    execution = workflow.get("metadata", {}) if isinstance(workflow, dict) else {}
    content = pipeline_path(date, "content.json")
    script = pipeline_path(date, "script.json")
    script_review = pipeline_path(date, "script_review.json")
    script_review_page = script_review_page_path(date)
    script_approval = agent_path(date, "script_approval.json")
    storyboard = pipeline_path(date, "storyboard.json")
    story_images = pipeline_path(date, "story_images.json")
    subtitle_plan = pipeline_path(date, "subtitle_plan.json")
    audio_manifest = pipeline_path(date, "audio_manifest.json")
    cli_props = render_path(date, "cli_props.json")
    public_props = render_remotion_dir(date) / "public" / "props.json"
    hyperframes_index = base / "hyperframes_project" / "index.html"
    output = publish_path(date, "output.mp4")
    title = publish_path(date, "title.json")
    cover = publish_path(date, "cover.png")
    publish_guide = publish_path(date, "publish_guide.md")

    stale: list[dict[str, str]] = []
    if _is_newer(content, script):
        stale.append(
            {
                "artifact": str(script).replace("\\", "/"),
                "reason": "content.json is newer than script.json",
            }
        )
    if _is_newer(storyboard, script):
        stale.append(
            {
                "artifact": str(storyboard).replace("\\", "/"),
                "reason": "storyboard.json is newer than script.json",
            }
        )
    if (
        script.exists()
        and not story_images.exists()
        and (workflow is not None or cli_props.exists() or output.exists())
    ):
        stale.append(
            {
                "artifact": str(story_images).replace("\\", "/"),
                "reason": "story_images.json is missing; every story needs a local image",
            }
        )
    approval_current = False
    if script.exists():
        try:
            loaded_script = load_script(date)
            approval_current = script_approval_is_current(date, loaded_script)
            if not approval_current:
                stale.append(
                    {
                        "artifact": str(script_approval).replace("\\", "/"),
                        "reason": (
                            "script_approval.json is missing or does not match "
                            "script.json"
                        ),
                    }
                )
            render_manifest = _read_json(
                cli_props.with_suffix(cli_props.suffix + ".manifest.json")
            )
            render_inputs = (
                render_manifest.get("inputs")
                if isinstance(render_manifest, dict)
                else None
            )
            if not isinstance(render_inputs, dict) or any(
                render_inputs.get(key) != expected
                for key, expected in {
                    "script_editorial_hash": script_editorial_hash(loaded_script),
                    "audio_manifest_hash": file_sha256(audio_manifest),
                    "content_hash": file_sha256(content),
                }.items()
            ):
                if _is_newer(script, cli_props) or not cli_props.exists():
                    stale.append(
                        {
                            "artifact": str(cli_props).replace("\\", "/"),
                            "reason": "script.json is newer than cli_props.json",
                        }
                    )
            subtitle_plan_data = _read_json(subtitle_plan)
            if not subtitle_plan.exists():
                if workflow is not None or cli_props.exists() or output.exists():
                    stale.append(
                        {
                            "artifact": str(subtitle_plan).replace("\\", "/"),
                            "reason": "subtitle_plan.json is missing",
                        }
                    )
            elif not isinstance(subtitle_plan_data, dict) or subtitle_plan_data.get(
                "audio_input_hash_after"
            ) != script_audio_input_hash(loaded_script):
                stale.append(
                    {
                        "artifact": str(subtitle_plan).replace("\\", "/"),
                        "reason": "subtitle_plan.json does not match script.json",
                    }
                )
            audio_inputs = {
                "audio_input_hash": script_audio_input_hash(loaded_script),
                "segment_count": len(loaded_script.segments),
            }
            if audio_manifest.exists():
                manifest = load_audio_manifest(date)
                if not is_artifact_fresh(audio_manifest, audio_inputs):
                    reason = "audio_manifest.json input hash does not match script.json"
                elif manifest is not None and not audio_manifest_is_usable(
                    manifest, expected_segment_count=len(loaded_script.segments)
                ):
                    reason = "audio_manifest.json references missing audio files"
                else:
                    reason = ""
                if reason:
                    stale.append(
                        {
                            "artifact": str(audio_manifest).replace("\\", "/"),
                            "reason": reason,
                        }
                    )
            elif (
                pipeline_audio_dir(date).exists()
                or cli_props.exists()
                or output.exists()
            ):
                stale.append(
                    {
                        "artifact": str(audio_manifest).replace("\\", "/"),
                        "reason": "audio_manifest.json is missing",
                    }
                )
        except (OSError, ValueError, TypeError):
            stale.append(
                {
                    "artifact": str(audio_manifest).replace("\\", "/"),
                    "reason": "cannot validate audio manifest against script.json",
                }
            )
    if _is_newer(cli_props, output):
        output_manifest = _read_json(
            output.with_suffix(output.suffix + ".manifest.json")
        )
        output_inputs = (
            output_manifest.get("inputs") if isinstance(output_manifest, dict) else None
        )
        output_matches_current = False
        if isinstance(output_inputs, dict) and script.exists():
            try:
                current_script = load_script(date)
                output_matches_current = not any(
                    output_inputs.get(key) != expected
                    for key, expected in {
                        "script_editorial_hash": script_editorial_hash(current_script),
                        "audio_manifest_hash": file_sha256(audio_manifest),
                        "content_hash": file_sha256(content),
                        "props_hash": file_sha256(cli_props),
                    }.items()
                )
            except (OSError, ValueError, TypeError):
                output_matches_current = False
        if not output_matches_current:
            stale.append(
                {
                    "artifact": str(output).replace("\\", "/"),
                    "reason": "cli_props.json is newer than output.mp4",
                }
            )
    renderer_name = _prepare_render_renderer(date)
    if (
        cli_props.exists()
        and renderer_name == "RemotionRenderer"
        and not public_props.exists()
    ):
        stale.append(
            {
                "artifact": str(public_props).replace("\\", "/"),
                "reason": "public Remotion props mirror is missing",
            }
        )
    if (
        cli_props.exists()
        and renderer_name == "HyperFramesRenderer"
        and not hyperframes_index.exists()
    ):
        stale.append(
            {
                "artifact": str(hyperframes_index).replace("\\", "/"),
                "reason": "HyperFrames project index is missing",
            }
        )
    if _has_stale_publish_guide(date, content, script, publish_guide):
        stale.append(
            {
                "artifact": str(publish_guide).replace("\\", "/"),
                "reason": "publish_guide.md input hash does not match content/script",
            }
        )

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
                "command": f"uv run python scripts/agent_run.py --date {date}",
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
                    f"uv run python scripts/agent_run.py --date {date} --approve-script"
                ),
                "why": "Review script_review.html, then approve this exact script version.",
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
        safe_next_commands.append(_video_stale_command(date, stale))
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
            "hyperframes_index": _artifact(hyperframes_index),
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
