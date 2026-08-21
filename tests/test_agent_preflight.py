import json

import pytest

from scripts.internal.agent import agent_preflight
from src.pipeline.paths import agent_path


def test_check_yaml_config_returns_fatal_issue_on_loader_error(monkeypatch):
    monkeypatch.setattr(
        agent_preflight,
        "load_config",
        lambda path: (_ for _ in ()).throw(ValueError("bad yaml")),
    )

    config, issues = agent_preflight._check_yaml_config("config/")

    assert config is None
    assert issues[0]["severity"] == "fatal"
    assert "bad yaml" in issues[0]["message"]


def test_env_checks_reports_only_enabled_missing_credentials(monkeypatch):
    monkeypatch.delenv("TEST_LLM_KEY", raising=False)
    monkeypatch.setenv("TEST_TTS_KEY", "present")

    issues = agent_preflight._env_checks(
        {
            "llm": {"api_key_env": "TEST_LLM_KEY"},
            "tts": {"api_key_env": "TEST_TTS_KEY"},
            "image_generator": {
                "enabled": False,
                "api_key_env": "TEST_IMAGE_KEY",
            },
        }
    )

    assert len(issues) == 1
    assert issues[0]["owner"] == "llm"
    assert issues[0]["blocked_reason"] == agent_preflight.BLOCK_MISSING_CREDENTIALS


def test_tool_checks_distinguishes_warning_uv_and_blocked_video_tools(monkeypatch):
    available = {"uv": False, "ffmpeg": False, "npx": True}
    monkeypatch.setattr(
        agent_preflight.shutil,
        "which",
        lambda name: "x" if available[name] else None,
    )

    issues = agent_preflight._tool_checks()

    assert {issue["message"] for issue in issues} == {
        "uv was not found on PATH",
        "ffmpeg is required for video generation",
    }
    assert (
        next(issue for issue in issues if issue["message"].startswith("uv"))["severity"]
        == "warning"
    )


@pytest.mark.parametrize(
    ("payload", "expected_issue"),
    [
        (None, None),
        ({"status": "failed"}, "workflow failed"),
        (
            {
                "status": "blocked",
                "current_state": "research",
                "states": {"research": {"last_error": "download needed"}},
            },
            "download needed",
        ),
        ({"status": "corrupt", "error": "invalid snapshot"}, "invalid snapshot"),
    ],
)
def test_state_checks_maps_native_workflow_status(monkeypatch, payload, expected_issue):
    monkeypatch.setattr(agent_preflight, "load_workflow_report", lambda date: payload)

    state, issues = agent_preflight._state_checks("2026-04-26")

    if payload and payload.get("status") == "corrupt":
        assert state is None
    else:
        assert state == payload
    if expected_issue is None:
        assert issues == []
    else:
        assert issues[0]["message"] == expected_issue


def test_task_checks_reports_missing_manual_article_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-04-26"
    task_path = agent_path(date, "agent_tasks.json")
    task_path.parent.mkdir(parents=True)
    task_path.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "task_type": "fetch_article",
                        "save_as": {
                            "html": str(tmp_path / "missing.html"),
                            "pdf": str(tmp_path / "missing.pdf"),
                        },
                    },
                    {"task_type": "select_image"},
                ]
            }
        ),
        encoding="utf-8",
    )

    data, issues = agent_preflight._task_checks(date)

    assert data["tasks"]
    assert issues[0]["check"] == "missing_article_files"
    assert issues[0]["blocked_reason"] == "manual_download_required"


def test_last_run_summary_reads_compact_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-04-26"
    report_path = agent_path(date, "report.md")
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        "| 视频标题 | 今日标题 |\n| 故事总数 | 3 |\n", encoding="utf-8"
    )
    state = {
        "status": "complete",
        "updated_at": "2026-08-21T00:00:00Z",
        "states": {"produce": {"status": "done"}},
    }
    monkeypatch.setattr(agent_preflight, "_state_checks", lambda value: (state, []))

    summary = agent_preflight._last_run_summary(date)

    assert summary["status"] == "complete"
    assert summary["video_title"] == "今日标题"
    assert summary["story_count"] == "3"
