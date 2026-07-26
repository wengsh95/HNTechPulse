from scripts.agent_run import (
    XHS_CHAIN,
    _choose_steps,
    _failed_recovery_steps,
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
