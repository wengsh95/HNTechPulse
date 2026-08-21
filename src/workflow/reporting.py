"""Read-only helpers for inspecting persisted workflow state."""

from __future__ import annotations

from typing import Any

from src.workflow.machine import WorkflowMachine
from src.workflow.persistence import WorkflowCorruptError
from src.workflow.video import VIDEO_WORKFLOW_STEPS


def load_workflow_report(date: str) -> dict[str, Any] | None:
    """Return a status report for ``date`` without mutating workflow state.

    Missing state is represented by ``None``. A present but unreadable state is
    represented by a ``corrupt`` report so callers can distinguish a fresh date
    from a state that must not be resumed automatically.
    """

    machine = WorkflowMachine(date, VIDEO_WORKFLOW_STEPS)
    if not machine.path.exists():
        return None
    try:
        machine.load()
    except (WorkflowCorruptError, OSError, ValueError) as exc:
        return {
            "status": "corrupt",
            "date": date,
            "product": "video",
            "workflow_file": str(machine.path).replace("\\", "/"),
            "error": str(exc),
        }
    return machine.status_report()
