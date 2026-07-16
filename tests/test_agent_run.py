from scripts.agent_run import (
    XHS_CHAIN,
    VIDEO_CHAIN,
    _stale_recovery_steps,
    _failed_recovery_steps,
)


def test_xhs_and_video_chains_are_independent():
    """The two flows share an upstream prefix but must not contain each other's
    tail steps: xhs never pulls synthesize_audio/prepare_render/render; video
    never pulls xhs_guide."""
    assert XHS_CHAIN[-1] == "xhs_guide"
    assert "synthesize_audio" not in XHS_CHAIN
    assert "prepare_render" not in XHS_CHAIN
    assert "render" not in XHS_CHAIN

    assert VIDEO_CHAIN[-1] == "render"
    assert "xhs_guide" not in VIDEO_CHAIN


def test_stale_content_recovery_is_flow_scoped():
    """A content.json staleness reruns ONLY the selected flow from write_script,
    never dragging in the other flow's tail."""
    xhs_steps = _stale_recovery_steps(
        {
            "stale_artifacts": [
                {
                    "artifact": "data/2026-06/2026-06-09/script.json",
                    "reason": "content.json is newer than script.json",
                }
            ]
        },
        flow="xhs",
    )
    assert xhs_steps == XHS_CHAIN[XHS_CHAIN.index("write_script") :]
    assert "synthesize_audio" not in xhs_steps
    assert "render" not in xhs_steps

    video_steps = _stale_recovery_steps(
        {
            "stale_artifacts": [
                {
                    "artifact": "data/2026-06/2026-06-09/script.json",
                    "reason": "content.json is newer than script.json",
                }
            ]
        },
        flow="video",
    )
    assert video_steps == VIDEO_CHAIN[VIDEO_CHAIN.index("write_script") :]
    assert "xhs_guide" not in video_steps


def test_stale_render_recovery_only_applies_to_video_flow():
    """Render-side staleness is video-only; the xhs flow returns None."""
    video_steps = _stale_recovery_steps(
        {"stale_artifacts": [{"reason": "cli_props.json is newer than output.mp4"}]},
        flow="video",
    )
    assert video_steps == ["prepare_render", "render"]

    xhs_steps = _stale_recovery_steps(
        {"stale_artifacts": [{"reason": "cli_props.json is newer than output.mp4"}]},
        flow="xhs",
    )
    assert xhs_steps is None


def test_failed_recovery_slices_selected_flow():
    """A failed step resumes the selected flow's chain from that step, not the
    other flow's."""
    xhs_steps = _failed_recovery_steps({"failed_step": "title"}, flow="xhs")
    assert xhs_steps == XHS_CHAIN[XHS_CHAIN.index("title") :]
    assert "render" not in xhs_steps

    video_steps = _failed_recovery_steps({"failed_step": "title"}, flow="video")
    assert video_steps == VIDEO_CHAIN[VIDEO_CHAIN.index("title") :]
    assert "xhs_guide" not in video_steps
