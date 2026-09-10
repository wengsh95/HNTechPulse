"""High-level workflow state machine for HN TechPulse products."""

from src.workflow.machine import WorkflowMachine
from src.workflow.model import (
    FailureType,
    Phase,
    StateStatus,
    WorkflowStep,
)
from src.workflow.video import (
    VIDEO_PHASE_PIPELINE_STEPS,
    VIDEO_ALL_STEPS,
    VIDEO_PIPELINE_EXECUTION_STEPS,
    VIDEO_PIPELINE_STEPS,
    VIDEO_STANDALONE_STEPS,
    VIDEO_WORKFLOW_STEPS,
)
from src.workflow.runtime import (
    BLOCK_EXTERNAL_TOOL_MISSING,
    BLOCK_INSUFFICIENT_CONTEXT,
    BLOCK_MANUAL_DOWNLOAD,
    BLOCK_MANUAL_IMAGE_SELECTION,
    BLOCK_MANUAL_SCRIPT_REVIEW,
    BLOCK_MISSING_CREDENTIALS,
    write_image_selection_tasks,
    write_manual_download_tasks,
)
from src.workflow.reporting import load_workflow_report
from src.workflow.planner import (
    resolve_steps,
    downstream_tail,
    from_step_tail,
    fail_recovery_slice,
    resume_tail,
    validation_errors,
)
from src.workflow.steps import (
    StepSpec,
    STEP_SPECS,
    SCRIPT_CONSUMING_STEPS,
    SCRIPT_MUTATING_STEPS,
    HUMAN_REVIEW_PROTECTED_STEPS,
    DOWNSTREAM_REENTRY,
    FAILURE_REENTRY,
)

__all__ = [
    "FailureType",
    "Phase",
    "StateStatus",
    "VIDEO_WORKFLOW_STEPS",
    "VIDEO_PIPELINE_STEPS",
    "VIDEO_PIPELINE_EXECUTION_STEPS",
    "VIDEO_STANDALONE_STEPS",
    "VIDEO_ALL_STEPS",
    "VIDEO_PHASE_PIPELINE_STEPS",
    "WorkflowMachine",
    "WorkflowStep",
    "BLOCK_EXTERNAL_TOOL_MISSING",
    "BLOCK_INSUFFICIENT_CONTEXT",
    "BLOCK_MANUAL_DOWNLOAD",
    "BLOCK_MANUAL_IMAGE_SELECTION",
    "BLOCK_MANUAL_SCRIPT_REVIEW",
    "BLOCK_MISSING_CREDENTIALS",
    "write_image_selection_tasks",
    "write_manual_download_tasks",
    "load_workflow_report",
    "StepSpec",
    "STEP_SPECS",
    "resolve_steps",
    "downstream_tail",
    "from_step_tail",
    "fail_recovery_slice",
    "resume_tail",
    "validation_errors",
    "SCRIPT_CONSUMING_STEPS",
    "SCRIPT_MUTATING_STEPS",
    "HUMAN_REVIEW_PROTECTED_STEPS",
    "DOWNSTREAM_REENTRY",
    "FAILURE_REENTRY",
]


def _validate_on_import() -> None:
    """Fail fast if the step tables are inconsistent.

    The workflow registry is now the single source of truth for step order and
    policy; an invalid table should surface the moment the package is imported,
    not halfway through a run.
    """
    problems = validation_errors()
    if problems:
        raise RuntimeError(
            "Workflow step table validation failed:\n- " + "\n- ".join(problems)
        )


_validate_on_import()
