import json

from scripts.agent_status import (
    _build_video_status,
    _has_stale_publish_guide,
    _pending_tasks,
    _publish_guide_context,
    _video_stale_command,
    build_status,
)
from src.pipeline.paths import agent_path, pipeline_path, publish_path
from src.workflow.machine import WorkflowMachine
from src.workflow.video import VIDEO_WORKFLOW_STEPS


def test_status_reports_not_started_without_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-06-09"

    status = build_status(date)

    assert status["pipeline_status"] == "not_started"
    assert status["artifacts"]["script"]["exists"] is False
    assert status["artifacts"]["output"]["exists"] is False


def test_status_reads_native_workflow_without_writing_it(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-06-09"
    machine = WorkflowMachine(date, VIDEO_WORKFLOW_STEPS)
    machine.ensure()
    machine.mark_running("ingest")
    workflow_path = agent_path(date, "workflow_video.json")
    before = workflow_path.read_text(encoding="utf-8")

    status = build_status(date)

    assert status["workflow"]["status"] == "running"
    assert status["workflow"]["states"]["ingest"]["status"] == "running"
    assert workflow_path.read_text(encoding="utf-8") == before


def test_status_exposes_native_execution_metadata(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-06-09"
    machine = WorkflowMachine(date, VIDEO_WORKFLOW_STEPS)
    machine.ensure(
        metadata={
            "failed_pipeline_step": "fetch",
            "blocked_reason": "manual_download_required",
            "completed_pipeline_steps": ["prefilter"],
        }
    )
    machine.mark_running("ingest")

    status = build_status(date)

    assert status["pipeline_status"] == "running"
    assert status["failed_step"] == "fetch"
    assert status["blocked_reason"] == "manual_download_required"
    assert status["completed_steps"] == ["prefilter"]


def test_stale_script_command_refreshes_script():
    command = _video_stale_command(
        "2026-06-09",
        [
            {
                "artifact": "data/2026-06/2026-06-09/pipeline/script.json",
                "reason": "content.json is newer than script.json",
            }
        ],
    )["command"]
    assert command.endswith("--refresh-script")


def test_missing_approval_command_resumes_from_human_review():
    command = _video_stale_command(
        "2026-06-09",
        [
            {
                "artifact": "data/2026-06/2026-06-09/agent/script_approval.json",
                "reason": "script_approval.json is missing or does not match script.json",
            }
        ],
    )["command"]
    assert command.endswith("--from human_review")


def test_stale_audio_manifest_command_only_runs_video_tail():
    command = _video_stale_command(
        "2026-06-09",
        [
            {
                "artifact": "data/2026-06/2026-06-09/pipeline/audio_manifest.json",
                "reason": "audio_manifest.json input hash does not match script.json",
            }
        ],
    )["command"]
    assert command.endswith(
        "--steps prepare_subtitles,synthesize_audio,prepare_render,render"
    )


def test_stale_render_command_does_not_call_llm():
    command = _video_stale_command(
        "2026-06-09",
        [
            {
                "artifact": "data/2026-06/2026-06-09/publish/output.mp4",
                "reason": "cli_props.json is newer than output.mp4",
            }
        ],
    )["command"]
    assert command.endswith("--steps prepare_subtitles,prepare_render,render")


def test_pending_tasks_accepts_agent_confirmed_local_image(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-06-09"
    image_path = tmp_path / "selected.png"
    image_path.write_bytes(b"png")
    selection_path = pipeline_path(date, "image_selection.json")
    selection_path.parent.mkdir(parents=True)
    selection_path.write_text(
        json.dumps(
            {
                "items": {
                    "1": {
                        "selected_image": "candidate.png",
                        "selection_source": "agent",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    task_path = agent_path(date, "agent_tasks.json")
    task_path.parent.mkdir(parents=True)
    task_path.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "task_type": "select_image",
                        "story_id": "1",
                        "selection_file": str(selection_path),
                        "candidates": [
                            {
                                "path": "candidate.png",
                                "local_path": str(image_path),
                                "selection_source": "agent",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = _pending_tasks(date)

    assert result["pending_count"] == 0


def test_pending_tasks_rejects_heuristic_or_missing_selection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-06-09"
    task_path = agent_path(date, "agent_tasks.json")
    task_path.parent.mkdir(parents=True)
    task_path.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "task_type": "select_image",
                        "story_id": "1",
                        "selection_file": str(tmp_path / "selection.json"),
                        "candidates": [{"path": "candidate.png"}],
                    },
                    {
                        "task_type": "fetch_article",
                        "save_as": {"html": str(tmp_path / "missing.html")},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    result = _pending_tasks(date)

    assert result["pending_count"] == 2


def test_publish_guide_context_uses_title_override_and_content_items(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    date = "2026-06-09"
    content_path = pipeline_path(date, "content.json")
    script_path = pipeline_path(date, "script.json")
    content_path.parent.mkdir(parents=True)
    content_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "title": "Original",
                        "title_cn": "中文标题",
                        "editor_angle": "编辑角度",
                        "category": "AI",
                        "keywords": ["agent"],
                        "score": 10,
                        "comment_count": 2,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    script_path.write_text(
        json.dumps({"title": "Script title", "description": "Script desc"}),
        encoding="utf-8",
    )
    title_path = publish_path(date, "title.json")
    title_path.parent.mkdir(parents=True)
    title_path.write_text(
        json.dumps({"title": "Published title", "description": "Published desc"}),
        encoding="utf-8",
    )

    context = _publish_guide_context(date, content_path, script_path)

    assert context["script_title"] == "Published title"
    assert context["script_description"] == "Published desc"
    assert "中文标题" in context["items_json"]


def test_stale_publish_guide_requires_manifest_matching_current_context(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    date = "2026-06-09"
    content_path = pipeline_path(date, "content.json")
    script_path = pipeline_path(date, "script.json")
    content_path.parent.mkdir(parents=True)
    content_path.write_text(json.dumps({"items": []}), encoding="utf-8")
    script_path.write_text(
        json.dumps({"title": "T", "description": "D"}), encoding="utf-8"
    )
    guide_path = publish_path(date, "publish_guide.md")
    guide_path.parent.mkdir(parents=True)
    guide_path.write_text("guide", encoding="utf-8")

    assert _has_stale_publish_guide(date, content_path, script_path, guide_path) is True


def test_build_video_status_exposes_corrupt_workflow_recovery(monkeypatch):
    monkeypatch.setattr(
        "scripts.agent_status._workflow_status",
        lambda date: {"status": "corrupt", "error": "bad state"},
    )

    status = _build_video_status("2026-06-09")

    assert status["pipeline_status"] == "failed"
    assert status["safe_next_commands"][0]["command"].startswith(
        "Create a new workflow"
    )


def test_build_video_status_prompts_approval_for_blocked_review(monkeypatch):
    monkeypatch.setattr(
        "scripts.agent_status._workflow_status",
        lambda date: {
            "status": "blocked",
            "metadata": {"blocked_reason": "manual_script_review_required"},
        },
    )

    status = _build_video_status("2026-06-09")

    assert status["pipeline_status"] == "blocked"
    assert status["next_recommended_command"].endswith("--approve-script")
