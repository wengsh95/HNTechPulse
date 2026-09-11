"""Tests for the freshness judgement module.

Pins the StaleCode catalog (reason strings + repair steps), the wire-format
record shape, and the recovery/command routing parity with the legacy
agent scripts' behaviour.
"""

from src.workflow.freshness import (
    StaleArtifact,
    StaleCode,
    check_freshness,
    command_for,
    recovery_tail,
)


# ── StaleCode catalog ────────────────────────────────────────────────────


class TestStaleCodeCatalog:
    def test_reason_strings_are_legacy_pinned(self):
        # Exact reason strings from the legacy wire format — do not edit
        # without changing the consumers that print them.
        assert StaleCode.CONTENT_NEWER_THAN_SCRIPT.value == (
            "content.json is newer than script.json"
        )
        assert StaleCode.STORYBOARD_NEWER_THAN_SCRIPT.value == (
            "storyboard.json is newer than script.json"
        )
        assert StaleCode.SCRIPT_APPROVAL_STALE.value == (
            "script_approval.json is missing or does not match script.json"
        )
        assert StaleCode.SCRIPT_NEWER_THAN_CLI_PROPS.value == (
            "script.json is newer than cli_props.json"
        )
        assert StaleCode.SUBTITLE_PLAN_MISSING.value == "subtitle_plan.json is missing"
        assert StaleCode.SUBTITLE_PLAN_STALE.value == (
            "subtitle_plan.json does not match script.json"
        )
        assert StaleCode.AUDIO_MANIFEST_STALE.value == (
            "audio_manifest.json input hash does not match script.json"
        )
        assert StaleCode.AUDIO_MANIFEST_UNUSABLE.value == (
            "audio_manifest.json references missing audio files"
        )
        assert StaleCode.AUDIO_MANIFEST_MISSING.value == (
            "audio_manifest.json is missing"
        )
        assert StaleCode.AUDIO_VALIDATION_ERROR.value == (
            "cannot validate audio manifest against script.json"
        )
        assert StaleCode.RENDER_OUTPUT_STALE.value == (
            "cli_props.json is newer than output.mp4"
        )
        assert StaleCode.PUBLIC_PROPS_MIRROR_MISSING.value == (
            "public Remotion props mirror is missing"
        )
        assert StaleCode.PUBLISH_GUIDE_STALE.value == (
            "publish_guide.md input hash does not match content/script"
        )

    def test_repair_steps(self):
        # Repair step for each staleness — recovery/command routing keys off it.
        assert StaleCode.CONTENT_NEWER_THAN_SCRIPT.repair == "write_script"
        assert StaleCode.STORYBOARD_NEWER_THAN_SCRIPT.repair == "apply_storyboard"
        assert StaleCode.STORY_IMAGES_MISSING.repair == "prepare_story_images"
        assert StaleCode.SCRIPT_APPROVAL_STALE.repair == "human_review"
        assert StaleCode.SCRIPT_NEWER_THAN_CLI_PROPS.repair == "prepare_subtitles"
        assert StaleCode.SUBTITLE_PLAN_MISSING.repair == "prepare_subtitles"
        assert StaleCode.SUBTITLE_PLAN_STALE.repair == "prepare_subtitles"
        assert StaleCode.AUDIO_MANIFEST_STALE.repair == "prepare_subtitles"
        assert StaleCode.AUDIO_MANIFEST_UNUSABLE.repair == "prepare_subtitles"
        assert StaleCode.AUDIO_MANIFEST_MISSING.repair == "prepare_subtitles"
        assert StaleCode.AUDIO_VALIDATION_ERROR.repair == "prepare_subtitles"
        assert StaleCode.RENDER_OUTPUT_STALE.repair == "prepare_subtitles"
        assert StaleCode.PUBLIC_PROPS_MIRROR_MISSING.repair == "prepare_subtitles"
        assert StaleCode.PUBLISH_GUIDE_STALE.repair == "prepare_render"


class TestWireFormat:
    def test_as_wire_dict_includes_code_alongside_reason(self):
        art = StaleArtifact(
            artifact="data/2099-01-01/pipeline/script.json",
            code=StaleCode.CONTENT_NEWER_THAN_SCRIPT,
        )
        assert art.as_wire_dict() == {
            "artifact": "data/2099-01-01/pipeline/script.json",
            "reason": "content.json is newer than script.json",
            "code": "content.json is newer than script.json",
        }


# ── recovery_tail parity with legacy agent_run ────────────────────────────


class TestRecoveryTail:
    def test_content_newer_recovers_from_write_script(self):
        assert recovery_tail(
            [{"reason": "content.json is newer than script.json"}]
        ) == [
            "write_script",
            "draft_quick_news",
            "prepare_story_images",
            "title",
            "cover_image",
            "cover_thumbnail",
            "human_review",
            "draft_storyboard",
            "apply_storyboard",
            "prepare_subtitles",
            "synthesize_audio",
            "prepare_render",
            "render",
        ]

    def test_approval_stale_recovers_from_human_review(self):
        out = recovery_tail([{"reason": "script_approval.json is missing"}])
        assert out is not None and out[0] == "human_review"
        assert out[-1] == "render"

    def test_storyboard_newer_recovers_from_apply_storyboard(self):
        assert recovery_tail(
            [{"reason": "storyboard.json is newer than script.json"}]
        ) == [
            "apply_storyboard",
            "prepare_subtitles",
            "synthesize_audio",
            "prepare_render",
            "render",
        ]

    def test_render_stale_recovers_from_prepare_subtitles(self):
        assert recovery_tail(
            [{"reason": "cli_props.json is newer than output.mp4"}]
        ) == [
            "prepare_subtitles",
            "synthesize_audio",
            "prepare_render",
            "render",
        ]

    def test_code_drives_without_reason(self):
        assert recovery_tail([{"code": StaleCode.RENDER_OUTPUT_STALE.value}]) == [
            "prepare_subtitles",
            "synthesize_audio",
            "prepare_render",
            "render",
        ]

    def test_no_stale_returns_none(self):
        assert recovery_tail([]) is None
        assert recovery_tail([{"reason": "unrelated"}]) is None


# ── command_for parity with legacy agent_status ──────────────────────────


class TestCommandFor:
    def test_script_refresh_command(self):
        out = command_for(
            "2026-06-09",
            [{"reason": "content.json is newer than script.json"}],
        )
        assert out["command"].endswith("--refresh-script")

    def test_approval_command_resumes_from_human_review(self):
        out = command_for(
            "2026-06-09",
            [
                {
                    "reason": "script_approval.json is missing or does not match script.json",
                    "code": "script_approval.json is missing or does not match script.json",
                }
            ],
        )
        assert out["command"].endswith("--from human_review")

    def test_audio_manifest_command_runs_video_tail(self):
        out = command_for(
            "2026-06-09",
            [{"reason": "audio_manifest.json input hash does not match script.json"}],
        )
        assert out["command"].endswith(
            "--steps prepare_subtitles,synthesize_audio,prepare_render,render"
        )

    def test_render_command_does_not_call_llm(self):
        out = command_for(
            "2026-06-09",
            [{"reason": "cli_props.json is newer than output.mp4"}],
        )
        assert out["command"].endswith(
            "--steps prepare_subtitles,prepare_render,render"
        )


# ── check_freshness returns typed records ────────────────────────────────


class TestCheckFreshness:
    def test_empty_date_returns_no_stale(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        report = check_freshness("2099-01-01")
        assert isinstance(report.stale, list)
        assert report.approval_current is False
        # With no script, no artifacts, no workflow: nothing is stale.
        assert report.stale == []

    def test_returns_stale_artifacts_typed(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        report = check_freshness("2099-01-01")
        for record in report.stale:
            assert isinstance(record, StaleArtifact)
            assert isinstance(record.code, StaleCode)
            assert record.reason == record.code.value
