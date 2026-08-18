import sys

import scripts.agent_run as agent_run
from scripts.agent_run import (
    XHS_CHAIN,
    VIDEO_CHAIN,
    _choose_steps,
    _failed_recovery_steps,
    _is_explicit_downstream_request,
    _stale_recovery_steps,
)


def test_managed_chain_is_xhs_cards_only():
    assert XHS_CHAIN[-2:] == ["plan_xhs_cards", "render_xhs_cards"]
    for legacy_step in (
        "write_script",
        "synthesize_audio",
        "title",
        "cover_image",
        "prepare_render",
        "render",
        "xhs_guide",
    ):
        assert legacy_step not in XHS_CHAIN


def test_video_chain_restores_tts_and_render_steps():
    assert VIDEO_CHAIN[-5:] == [
        "cover_thumbnail",
        "prepare_subtitles",
        "synthesize_audio",
        "prepare_render",
        "render",
    ]


def test_video_failure_recovery_is_scoped_to_video_chain():
    assert _failed_recovery_steps({"failed_step": "prepare_render"}, flow="video") == [
        "prepare_render",
        "render",
    ]


def test_video_stale_render_recovery_skips_llm_and_tts():
    assert _stale_recovery_steps(
        {"stale_artifacts": [{"reason": "cli_props.json is newer than output.mp4"}]},
        flow="video",
    ) == ["prepare_subtitles", "synthesize_audio", "prepare_render", "render"]


def test_video_stale_audio_manifest_recovers_from_tts_downstream():
    steps = _stale_recovery_steps(
        {
            "stale_artifacts": [
                {"reason": "audio_manifest.json input hash does not match script.json"}
            ]
        },
        flow="video",
    )
    assert steps == [
        "prepare_subtitles",
        "synthesize_audio",
        "prepare_render",
        "render",
    ]


def test_stale_plan_recovers_plan_and_render():
    steps = _stale_recovery_steps(
        {"stale_artifacts": [{"reason": "Xiaohongshu card plan inputs changed"}]}
    )
    assert steps == ["plan_xhs_cards", "render_xhs_cards"]


def test_stale_render_recovers_render_only():
    steps = _stale_recovery_steps(
        {
            "stale_artifacts": [
                {"reason": "Xiaohongshu card renders are stale or incomplete"}
            ]
        }
    )
    assert steps == ["render_xhs_cards"]


def test_failed_recovery_slices_card_chain():
    assert _failed_recovery_steps({"failed_step": "plan_xhs_cards"}) == [
        "plan_xhs_cards",
        "render_xhs_cards",
    ]


def test_old_video_failure_restarts_current_card_product():
    assert _failed_recovery_steps({"failed_step": "render"}) == XHS_CHAIN


def test_complete_state_with_missing_card_plan_is_not_noop():
    steps = _choose_steps(
        status={
            "pipeline_status": "complete",
            "stale_artifacts": [{"reason": "Xiaohongshu card plan is missing"}],
        },
        requested_steps=None,
        force_resume=False,
    )
    assert steps == ["plan_xhs_cards", "render_xhs_cards"]


def test_blocked_manual_download_does_not_restart_upstream_chain():
    steps = _choose_steps(
        status={
            "pipeline_status": "blocked",
            "blocked_reason": "manual_download_required",
            "agent_tasks": {"exists": True, "pending_count": 1},
        },
        requested_steps=None,
        force_resume=False,
        flow="video",
    )
    assert steps is None


def test_from_step_returns_only_the_selected_downstream_video_chain():
    steps = _choose_steps(
        status={"pipeline_status": "complete"},
        requested_steps=None,
        from_step="synthesize_audio",
        force_resume=False,
        flow="video",
    )
    assert steps == [
        "prepare_subtitles",
        "synthesize_audio",
        "prepare_render",
        "render",
    ]


def test_explicit_video_downstream_can_run_after_unrelated_upstream_block(
    monkeypatch,
):
    status = {
        "pipeline_status": "blocked",
        "blocked_reason": "manual_download_required",
        "agent_tasks": {"exists": True, "pending_count": 1},
    }
    monkeypatch.setattr(agent_run, "_preflight", lambda *args: 1)
    monkeypatch.setattr(agent_run, "build_status", lambda *args, **kwargs: status)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "agent_run.py",
            "--date",
            "2026-04-26",
            "--flow",
            "video",
            "--from",
            "synthesize_audio",
            "--dry-run",
            "--skip-audit",
        ],
    )

    assert agent_run.main() == 0


def test_only_downstream_step_requests_bypass_upstream_block_gate():
    assert _is_explicit_downstream_request(
        requested_steps="synthesize_audio,prepare_render,render",
        from_step=None,
        flow="video",
    )
    assert _is_explicit_downstream_request(
        requested_steps=None,
        from_step="render_xhs_cards",
        flow="xhs",
    )
    assert not _is_explicit_downstream_request(
        requested_steps="write_script",
        from_step=None,
        flow="video",
    )


def test_from_step_returns_only_the_selected_downstream_card_chain():
    steps = _choose_steps(
        status={"pipeline_status": "complete"},
        requested_steps=None,
        from_step="plan_xhs_cards",
        force_resume=False,
    )
    assert steps == ["plan_xhs_cards", "render_xhs_cards"]


def test_refresh_selection_explicitly_restarts_selected_flow():
    assert (
        _choose_steps(
            status={"pipeline_status": "complete"},
            requested_steps=None,
            force_resume=False,
            flow="video",
            refresh_selection=True,
        )
        == VIDEO_CHAIN
    )


def test_refresh_script_restarts_video_from_editorial_step_even_when_complete():
    assert (
        _choose_steps(
            status={"pipeline_status": "complete"},
            requested_steps=None,
            force_resume=False,
            flow="video",
            refresh_script=True,
        )
        == VIDEO_CHAIN[VIDEO_CHAIN.index("write_script") :]
    )


def test_refresh_variants_restarts_video_from_editorial_step_even_when_complete():
    assert (
        _choose_steps(
            status={"pipeline_status": "complete"},
            requested_steps=None,
            force_resume=False,
            flow="video",
            refresh_variants=True,
        )
        == VIDEO_CHAIN[VIDEO_CHAIN.index("write_script") :]
    )
