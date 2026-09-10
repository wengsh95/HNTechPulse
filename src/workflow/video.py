"""High-level state definitions for the managed video product.

The canonical step table lives in :mod:`src.workflow.steps`; everything here
is derived from it.  ``WorkflowStep`` keeps the machine-facing state (deps,
produces, consumes); the concrete ``pipeline_steps`` of each phase and every
flattened view are computed from ``STEP_SPECS`` so adding a step never means
editing this file or a second list.
"""

from __future__ import annotations

from src.workflow.model import WorkflowStep
from src.workflow.steps import STEP_SPECS, VIDEO_STANDALONE_STEPS


def _pipeline_steps_for(phase: str) -> tuple[str, ...]:
    return tuple(
        spec.name
        for spec in STEP_SPECS
        if spec.phase == phase and spec.name != "preview"
    )


VIDEO_WORKFLOW_STEPS: tuple[WorkflowStep, ...] = (
    WorkflowStep(
        name="ingest",
        title="采集与候选整理",
        pipeline_steps=_pipeline_steps_for("ingest"),
        produces=(
            "raw/raw_stories.json",
            "pipeline/content.json",
            "pipeline/prefilter.json",
        ),
    ),
    WorkflowStep(
        name="research",
        title="统一研究与评论判断",
        deps=("ingest",),
        pipeline_steps=_pipeline_steps_for("research"),
        produces=(
            "pipeline/enrichment.json",
            "pipeline/comment_analysis.json",
            "pipeline/comment_judgement.json",
        ),
        consumes=("pipeline/content.json",),
    ),
    WorkflowStep(
        name="editorial",
        title="脚本与完整编辑包",
        deps=("research",),
        pipeline_steps=_pipeline_steps_for("editorial"),
        produces=(
            "pipeline/script.json",
            "pipeline/quick_news.json",
            "pipeline/video_structure.json",
            "pipeline/story_images.json",
            "pipeline/image_selection.json",
            "media/images/*",
            "pipeline/translations.json",
            "publish/title.json",
            "publish/cover.png",
        ),
        consumes=("pipeline/content.json", "pipeline/comment_judgement.json"),
    ),
    WorkflowStep(
        name="human_review",
        title="人工审核与内容冻结",
        deps=("editorial",),
        pipeline_steps=_pipeline_steps_for("human_review"),
        produces=("agent/script_approval.json", "pipeline/script_review.json"),
        consumes=(
            "pipeline/script.json",
            "publish/title.json",
        ),
    ),
    WorkflowStep(
        name="produce",
        title="媒体生产与视频渲染",
        deps=("human_review",),
        pipeline_steps=_pipeline_steps_for("produce"),
        produces=(
            "pipeline/storyboard.json",
            "pipeline/subtitle_plan.json",
            "pipeline/audio/*",
            "pipeline/audio_manifest.json",
            "render/cli_props.json",
            "publish/publish_guide.md",
            "publish/output.mp4",
        ),
        consumes=("pipeline/script.json", "pipeline/audio_manifest.json"),
    ),
)


VIDEO_WORKFLOW_BY_NAME = {step.name: step for step in VIDEO_WORKFLOW_STEPS}

# Keep the low-level execution order derived from the agent-facing workflow.
# Wrappers and the native orchestrator should not maintain a second copy of
# the video chain; recovery code can still choose a narrower tail explicitly.
VIDEO_PIPELINE_STEPS: tuple[str, ...] = tuple(
    spec.name for spec in STEP_SPECS if not spec.standalone or spec.name == "render"
)

# The CLI exposes two kinds of steps in addition to the managed workflow
# chain: ``render`` can be requested as a downstream-only operation, and
# ``preview`` is a renderer-only action that is not part of the persisted
# product workflow. Keep these views beside the registry so callers do not
# rebuild a second step list by hand.
VIDEO_PIPELINE_EXECUTION_STEPS: tuple[str, ...] = tuple(
    step for step in VIDEO_PIPELINE_STEPS if step not in VIDEO_STANDALONE_STEPS
)
VIDEO_ALL_STEPS: tuple[str, ...] = (*VIDEO_PIPELINE_STEPS, "preview")

# Phase aliases are intentionally derived from the same registry.  They give
# operators a compact command surface without introducing a second execution
# plan: ``agent_run --phase research`` still expands through the native
# orchestrator and its existing cache/recovery rules.
VIDEO_PHASE_PIPELINE_STEPS: dict[str, tuple[str, ...]] = {
    workflow_step.name: workflow_step.pipeline_steps
    for workflow_step in VIDEO_WORKFLOW_STEPS
}
