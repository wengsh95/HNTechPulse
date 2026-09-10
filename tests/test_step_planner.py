"""Invariant tests for the workflow step registry and planner.

These tests are the guardrail for the single-source-of-truth design: the
step table in ``src.workflow.steps`` feeds every ordering, policy set, and
recovery plan.  Anyone adding/removing/reordering a step must keep these
green.
"""

import pytest

from src.workflow import (
    VIDEO_PIPELINE_EXECUTION_STEPS,
    VIDEO_PIPELINE_STEPS,
    VIDEO_STANDALONE_STEPS,
    VIDEO_WORKFLOW_STEPS,
    SCRIPT_CONSUMING_STEPS,
    SCRIPT_MUTATING_STEPS,
    HUMAN_REVIEW_PROTECTED_STEPS,
    resolve_steps,
    downstream_tail,
    from_step_tail,
    fail_recovery_slice,
    resume_tail,
    validation_errors,
)
from src.workflow.steps import STEP_SPECS, STEP_SPECS_BY_NAME, PLANNED_STEPS


# ── Table integrity ──────────────────────────────────────────────────────


class TestTableIntegrity:
    def test_validation_is_clean(self):
        assert validation_errors() == []

    def test_orders_are_contiguous_and_unique(self):
        orders = [spec.order for spec in STEP_SPECS]
        assert sorted(orders) == list(range(len(STEP_SPECS)))
        assert len(set(orders)) == len(orders)

    def test_names_unique_and_match_table(self):
        assert len(STEP_SPECS) == len(set(spec.name for spec in STEP_SPECS))
        assert set(STEP_SPECS_BY_NAME) == set(spec.name for spec in STEP_SPECS)

    def test_prereqs_reference_existing_steps(self):
        known = set(STEP_SPECS_BY_NAME)
        for spec in STEP_SPECS:
            for prereq in spec.prereqs:
                assert prereq in known, f"{spec.name} -> {prereq}"

    def test_planned_steps_include_render_not_preview(self):
        assert "render" in PLANNED_STEPS
        assert "preview" not in PLANNED_STEPS


# ── Derived views match the legacy registry ──────────────────────────────


class TestDerivedViews:
    def test_pipeline_steps_in_expected_order(self):
        assert VIDEO_PIPELINE_EXECUTION_STEPS == (
            "fetch",
            "prefilter",
            "fetch_comments",
            "enrich_articles",
            "judge_comments",
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
        )

    def test_full_chain_ends_with_render(self):
        assert VIDEO_PIPELINE_STEPS[-1] == "render"
        assert set(VIDEO_STANDALONE_STEPS) == {"render", "preview"}

    def test_phase_membership_agrees_with_workflow_steps(self):
        expected_phase: dict[str, str] = {}
        for wf_step in VIDEO_WORKFLOW_STEPS:
            for pipeline_step in wf_step.pipeline_steps:
                expected_phase[pipeline_step] = wf_step.name
        for spec in STEP_SPECS:
            if spec.name in VIDEO_STANDALONE_STEPS:
                continue  # standalone actions are not part of any workflow phase
            assert spec.phase == expected_phase.get(spec.name), (
                f"{spec.name}: table phase {spec.phase} != workflow {expected_phase.get(spec.name)}"
            )


# ── resolve_steps behaviour (legacy-exact) ───────────────────────────────


class TestResolveSteps:
    def test_full_chain_resolves_unchanged(self):
        assert resolve_steps(list(VIDEO_PIPELINE_STEPS)) == list(VIDEO_PIPELINE_STEPS)

    def test_unknown_step_rejected(self):
        with pytest.raises(ValueError, match="Unknown pipeline step"):
            resolve_steps(["translate_titles"])

    def test_empty_returns_empty(self):
        assert resolve_steps([]) == []

    def test_cover_thumbnail_expands_to_cover_image_only(self):
        assert resolve_steps(["cover_thumbnail"]) == [
            "cover_image",
            "cover_thumbnail",
            "human_review",
        ]

    def test_prepare_render_pulls_audio_and_subtitles(self):
        resolved = resolve_steps(["prepare_render", "render"])
        assert resolved.index("prepare_subtitles") < resolved.index("synthesize_audio")
        assert resolved.index("synthesize_audio") < resolved.index("prepare_render")

    def test_render_only_requires_human_approval_gate(self):
        assert resolve_steps(["render"]) == ["human_review", "render"]

    def test_downstream_recovery_does_not_expand_editorial_chain(self):
        resolved = resolve_steps(["synthesize_audio", "prepare_render", "render"])
        assert resolved == [
            "human_review",
            "prepare_subtitles",
            "synthesize_audio",
            "prepare_render",
            "render",
        ]
        assert "write_script" not in resolved


# ── Recovery interface semantics ─────────────────────────────────────────


class TestRecovery:
    def test_downstream_tail_is_pure_chain_slice(self):
        assert downstream_tail("prepare_render") == [
            "prepare_render",
            "render",
        ]

    def test_from_step_audio_reanchors_to_subtitles(self):
        assert from_step_tail("synthesize_audio") == [
            "prepare_subtitles",
            "synthesize_audio",
            "prepare_render",
            "render",
        ]

    def test_from_step_prepare_render_reanchors_to_subtitles(self):
        # Legacy --from: both audio/render entry points start from
        # prepare_subtitles (subtitle selection is a local-agent prerequisite
        # for every downstream video recovery).
        assert from_step_tail("prepare_render") == [
            "prepare_subtitles",
            "synthesize_audio",
            "prepare_render",
            "render",
        ]

    def test_failure_prepare_story_images_rehydrates_quick_news(self):
        steps = fail_recovery_slice("prepare_story_images")
        assert steps[0] == "draft_quick_news"
        assert steps[-1] == "render"

    def test_failure_plain_step_resumes_from_itself(self):
        assert fail_recovery_slice("write_script")[0] == "write_script"

    def test_resume_tail_scoped_to_context(self):
        context = ["write_script", "draft_quick_news", "render"]
        assert resume_tail("draft_quick_news", context=context) == [
            "draft_quick_news",
            "render",
        ]
        assert resume_tail("fetch", context=context) == ["fetch"]


# ── Policy set fidelity ──────────────────────────────────────────────────


class TestPolicySets:
    def test_script_consuming_matches_legacy(self):
        assert SCRIPT_CONSUMING_STEPS == {
            "human_review",
            "draft_quick_news",
            "prepare_story_images",
            "prepare_subtitles",
            "synthesize_audio",
            "title",
            "cover_image",
            "cover_thumbnail",
            "draft_storyboard",
            "apply_storyboard",
            "prepare_render",
            "render",
        }

    def test_script_mutating_matches_legacy(self):
        assert SCRIPT_MUTATING_STEPS == {
            "write_script",
            "draft_quick_news",
            "prepare_story_images",
            "human_review",
            "prepare_subtitles",
            "synthesize_audio",
            "title",
            "apply_storyboard",
        }

    def test_human_review_protected_matches_legacy(self):
        assert HUMAN_REVIEW_PROTECTED_STEPS == {
            "title",
            "cover_image",
            "cover_thumbnail",
            "draft_storyboard",
            "apply_storyboard",
            "prepare_subtitles",
            "synthesize_audio",
            "prepare_render",
            "render",
            "preview",
        }
