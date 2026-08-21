"""Workflow state-machine lifecycle integration for the orchestrator."""

from contextlib import contextmanager
from typing import Any, Iterator

from src.pipeline.agent_io import append_agent_event
from src.workflow import (
    StateStatus,
    VIDEO_WORKFLOW_STEPS,
    WorkflowMachine,
)


class WorkflowLifecycleMixin:
    """Keep compact workflow state updates separate from pipeline stages."""

    @contextmanager
    def _tracked_step(self, name: str) -> Iterator[None]:
        self._workflow_start_step(name)
        append_agent_event(self._progress.date, "step_started", step=name)
        try:
            with self._progress.step(name):
                yield
        except Exception as e:
            append_agent_event(
                self._progress.date,
                "step_failed",
                step=name,
                error_type=type(e).__name__,
                message=str(e),
            )
            self._workflow_fail_step(name, e)
            raise
        else:
            append_agent_event(self._progress.date, "step_completed", step=name)
            self._workflow_complete_step(name)

    def _workflow_start_step(self, step: str) -> None:
        if self._workflow is None:
            return
        state = self._workflow.state_for_pipeline_step(step)
        if state is None:
            return
        record = self._workflow.snapshot.states[state]
        if record.status == StateStatus.PENDING:
            self._workflow.mark_running(state)
        self._workflow.update_metadata(
            current_pipeline_step=step,
            failed_pipeline_step=None,
            execution_status="running",
        )

    def _workflow_complete_step(self, step: str) -> None:
        if self._workflow is None:
            return
        self._workflow_completed_steps.add(step)
        state = self._workflow.state_for_pipeline_step(step)
        if state is None:
            return
        definition = self._workflow.get(state)
        expected_steps = self._workflow_expected_steps.get(
            state, set(definition.pipeline_steps)
        )
        if expected_steps and expected_steps.issubset(self._workflow_completed_steps):
            self._workflow.mark_done(state)
        self._workflow.update_metadata(
            completed_pipeline_steps=sorted(self._workflow_completed_steps),
            current_pipeline_step=None,
        )

    def _workflow_fail_step(self, step: str, error: BaseException) -> None:
        if self._workflow is None:
            return
        state = self._workflow.state_for_pipeline_step(step)
        if state is not None:
            self._workflow.mark_failed(state, str(error))
        self._workflow.update_metadata(
            execution_status="failed",
            current_pipeline_step=None,
            failed_pipeline_step=step,
            last_error={"type": type(error).__name__, "message": str(error)},
        )

    def _workflow_block(
        self,
        step: str,
        reason: str,
        *,
        items: list[dict[str, Any]] | None = None,
        task_file: str | None = None,
    ) -> None:
        if self._workflow is None:
            return
        state = self._workflow.state_for_pipeline_step(step)
        if state is not None:
            self._workflow.block(state, reason)
        self._workflow.update_metadata(
            execution_status="blocked",
            current_pipeline_step=None,
            failed_pipeline_step=step,
            blocked_reason=reason,
            blocked_items=items or [],
            agent_task_file=task_file,
        )
        append_agent_event(
            self._progress.date,
            "run_blocked",
            step=step,
            reason=reason,
            items=items or [],
            task_file=task_file,
        )

    def _prepare_workflow(self, date: str, steps: list[str]) -> None:
        self._workflow = WorkflowMachine(date, VIDEO_WORKFLOW_STEPS)
        self._workflow.ensure(
            metadata={
                "workflow_model": "compact_5_stage",
                "execution_mode": "native_orchestrator",
                "requested_steps": list(steps),
                "execution_status": "running",
                "completed_pipeline_steps": [],
                "current_pipeline_step": None,
                "failed_pipeline_step": None,
                "blocked_reason": None,
                "blocked_items": [],
                "degraded_items": [],
                "last_error": None,
            }
        )
        self._workflow_completed_steps = set()
        self._workflow_expected_steps = {
            state.name: set(state.pipeline_steps).intersection(steps)
            for state in VIDEO_WORKFLOW_STEPS
        }
        first_state = next(
            (
                self._workflow.state_for_pipeline_step(step)
                for step in steps
                if self._workflow.state_for_pipeline_step(step) is not None
            ),
            None,
        )
        if first_state is None:
            return
        record = self._workflow.snapshot.states[first_state]
        if record.status != StateStatus.PENDING:
            self._workflow.reset(first_state)
