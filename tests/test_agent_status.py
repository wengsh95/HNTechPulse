from scripts.agent_status import _stale_command, build_status
from src.pipeline.paths import agent_path, publish_path
from src.utils.atomic_io import atomic_write_json


def test_complete_old_state_reports_missing_card_plan(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-06-09"
    atomic_write_json(
        agent_path(date, "pipeline_state.json"),
        {"schema_version": 1, "date": date, "status": "complete"},
    )

    status = build_status(date)

    assert any("card plan" in item["reason"] for item in status["stale_artifacts"])
    assert status["artifacts"]["card_plan"]["exists"] is False


def test_status_tracks_card_plan_and_six_outputs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-06-09"
    atomic_write_json(
        agent_path(date, "pipeline_state.json"),
        {
            "schema_version": 2,
            "date": date,
            "status": "complete",
            "product": "xhs_cards",
        },
    )
    atomic_write_json(publish_path(date, "xhs_cards.json"), {"cards": []})

    status = build_status(date)

    assert status["artifacts"]["card_plan"]["exists"] is True
    assert len(status["artifacts"]["cards"]) == 6


def test_stale_plan_command_only_runs_card_tail():
    command = _stale_command(
        "2026-06-09",
        [
            {
                "artifact": "xhs_cards.json",
                "reason": "Xiaohongshu card plan inputs changed",
            }
        ],
    )["command"]
    assert command.endswith("--steps plan_xhs_cards,render_xhs_cards")


def test_stale_render_command_does_not_call_llm():
    command = _stale_command(
        "2026-06-09",
        [{"artifact": "xhs_cards", "reason": "Xiaohongshu card renders are stale"}],
    )["command"]
    assert command.endswith("--steps render_xhs_cards")
