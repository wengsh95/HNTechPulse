from scripts.agent_status import _video_stale_command, build_status
from src.pipeline.paths import agent_path
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
