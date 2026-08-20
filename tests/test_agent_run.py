import sys

import scripts.agent_run as agent_run
from scripts.agent_run import (
    VIDEO_CHAIN,
    _choose_steps,
    _failed_recovery_steps,
    _is_explicit_downstream_request,
    _stale_recovery_steps,
)


def test_video_chain_restores_storyboard_tts_and_render_steps():
    assert VIDEO_CHAIN[-7:] == [
        "cover_thumbnail",
        "draft_storyboard",
        "apply_storyboard",
        "prepare_subtitles",
        "synthesize_audio",
        "prepare_render",
        "render",
    ]


def test_video_chain_keeps_editorial_and_card_free_steps():
    for step in VIDEO_CHAIN:
        assert "xhs" not in step


def test_video_failure_recovery_is_scoped_to_video_chain():
    assert _failed_recovery_steps({"failed_step": "prepare_render"}) == [
        "prepare_render",
        "render",
    ]


def test_video_stale_render_recovery_skips_llm_and_tts():
    assert _stale_recovery_steps(
        {"stale_artifacts": [{"reason": "cli_props.json is newer than output.mp4"}]},
    ) == ["prepare_subtitles", "synthesize_audio", "prepare_render", "render"]


def test_video_stale_audio_manifest_recovers_from_tts_downstream():
    steps = _stale_recovery_steps(
        {
            "stale_artifacts": [
                {"reason": "audio_manifest.json input hash does not match script.json"}
            ]
        },
    )
    assert steps == [
        "prepare_subtitles",
        "synthesize_audio",
        "prepare_render",
        "render",
    ]


def test_video_stale_storyboard_recovers_from_storyboard_downstream():
    steps = _stale_recovery_steps(
        {"stale_artifacts": [{"reason": "storyboard.json is newer than script.json"}]},
    )
    assert steps == [
        "apply_storyboard",
        "prepare_subtitles",
        "synthesize_audio",
        "prepare_render",
        "render",
    ]


def test_video_missing_human_approval_recovers_from_review_gate():
    steps = _stale_recovery_steps(
        {
            "stale_artifacts": [
                {
                    "reason": (
                        "script_approval.json is missing or does not match script.json"
                    )
                }
            ]
        },
    )
    assert steps == VIDEO_CHAIN[VIDEO_CHAIN.index("human_review") :]


def test_failed_recovery_slices_video_chain():
    assert (
        _failed_recovery_steps({"failed_step": "write_script"})
        == VIDEO_CHAIN[VIDEO_CHAIN.index("write_script") :]
    )


def test_failed_image_selection_rehydrates_quick_news():
    steps = _failed_recovery_steps({"failed_step": "prepare_story_images"})
    assert steps[0] == "draft_quick_news"
    assert steps[-1] == "render"


def test_blocked_manual_download_does_not_restart_upstream_chain():
    steps = _choose_steps(
        status={
            "pipeline_status": "blocked",
            "blocked_reason": "manual_download_required",
            "agent_tasks": {"exists": True, "pending_count": 1},
        },
        requested_steps=None,
        force_resume=False,
    )
    assert steps is None


def test_approved_human_review_resumes_video_tail():
    steps = _choose_steps(
        status={
            "pipeline_status": "blocked",
            "blocked_reason": "manual_script_review_required",
            "script_approval_current": True,
            "failed_step": "human_review",
        },
        requested_steps=None,
        force_resume=False,
    )
    assert steps == VIDEO_CHAIN[VIDEO_CHAIN.index("human_review") :]


def test_from_step_returns_only_the_selected_downstream_video_chain():
    steps = _choose_steps(
        status={"pipeline_status": "complete"},
        requested_steps=None,
        from_step="synthesize_audio",
        force_resume=False,
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
    )
    assert _is_explicit_downstream_request(
        requested_steps=None,
        from_step="render",
    )
    assert not _is_explicit_downstream_request(
        requested_steps="write_script",
        from_step=None,
    )


def test_refresh_selection_explicitly_restarts_selected_flow():
    assert (
        _choose_steps(
            status={"pipeline_status": "complete"},
            requested_steps=None,
            force_resume=False,
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
            refresh_variants=True,
        )
        == VIDEO_CHAIN[VIDEO_CHAIN.index("write_script") :]
    )
