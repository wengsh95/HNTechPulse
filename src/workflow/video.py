"""High-level state definitions for the managed video product."""

from __future__ import annotations

from src.workflow.model import WorkflowStep


VIDEO_WORKFLOW_STEPS: tuple[WorkflowStep, ...] = (
    WorkflowStep(
        name="ingest",
        title="采集与候选整理",
        pipeline_steps=(
            "fetch",
            "prefilter",
            "fetch_comments",
        ),
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
        pipeline_steps=(
            "enrich_articles",
            "judge_comments",
        ),
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
        pipeline_steps=(
            "write_script",
            "draft_quick_news",
            "prepare_story_images",
            "title",
            "cover_image",
            "cover_thumbnail",
            "draft_storyboard",
        ),
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
            "pipeline/storyboard.json",
        ),
        consumes=("pipeline/content.json", "pipeline/comment_judgement.json"),
    ),
    WorkflowStep(
        name="human_review",
        title="人工审核与内容冻结",
        deps=("editorial",),
        pipeline_steps=("human_review",),
        produces=("agent/script_approval.json", "pipeline/script_review.json"),
        consumes=(
            "pipeline/script.json",
            "publish/title.json",
            "pipeline/storyboard.json",
        ),
    ),
    WorkflowStep(
        name="produce",
        title="媒体生产与视频渲染",
        deps=("human_review",),
        pipeline_steps=(
            "apply_storyboard",
            "prepare_subtitles",
            "synthesize_audio",
            "prepare_render",
            "render",
        ),
        produces=(
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
    pipeline_step
    for workflow_step in VIDEO_WORKFLOW_STEPS
    for pipeline_step in workflow_step.pipeline_steps
)

# Phase aliases are intentionally derived from the same registry.  They give
# operators a compact command surface without introducing a second execution
# plan: ``agent_run --phase research`` still expands through the native
# orchestrator and its existing cache/recovery rules.
VIDEO_PHASE_PIPELINE_STEPS: dict[str, tuple[str, ...]] = {
    workflow_step.name: workflow_step.pipeline_steps
    for workflow_step in VIDEO_WORKFLOW_STEPS
}
