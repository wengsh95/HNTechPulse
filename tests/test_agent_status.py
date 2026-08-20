from scripts.agent_status import _video_stale_command, build_status
from src.pipeline.paths import agent_path
from src.utils.atomic_io import atomic_write_json


def test_status_reports_not_started_without_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-06-09"

    status = build_status(date)

    assert status["pipeline_status"] == "not_started"
    assert status["artifacts"]["script"]["exists"] is False
    assert status["artifacts"]["output"]["exists"] is False


def test_status_reads_video_scoped_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-06-09"
    atomic_write_json(
        agent_path(date, "pipeline_state_video.json"),
        {
            "schema_version": 2,
            "date": date,
            "status": "complete",
            "product": "video",
        },
    )

    status = build_status(date)

    assert status["pipeline_status"] == "complete"


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
