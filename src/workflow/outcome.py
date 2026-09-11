"""Typed result of an orchestrator ``run()`` invocation.

Before this module, ``Orchestrator.run()`` returned ``None`` and communicated a
blocked run purely through side effects: the workflow metadata file and the
``run_blocked`` event.  Shells and schedulers then had to re-read the status
dict in ``agent_run`` and infer the exit code from a string.  ``RunOutcome``
makes the outcome the return value itself; the metadata and event side effects
are kept, but no longer the only carrier of the result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RunStatus(str, Enum):
    """Exit-relevant status of one orchestrator run."""

    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True)
class RunOutcome:
    """Result of one ``run()`` call, typed for consumers and exit codes.

    ``steps`` records the executed step sequence so status consumers can mirror
    the planner's snapshot without re-reading metadata.  ``step``/``reason``/
    ``items`` carry the block payload (``None``/empty for completed runs).
    """

    status: RunStatus
    steps: tuple[str, ...] = ()
    step: str | None = None
    reason: str | None = None
    items: list[dict[str, Any]] = field(default_factory=list)
    task_file: str | None = None

    @property
    def exit_code(self) -> int:
        """Shell exit code: 0 completed, 2 blocked, 1 failed."""
        if self.status is RunStatus.COMPLETED:
            return 0
        if self.status is RunStatus.BLOCKED:
            return 2
        return 1

    @classmethod
    def completed(cls, steps: list[str] | tuple[str, ...]) -> RunOutcome:
        return cls(status=RunStatus.COMPLETED, steps=tuple(steps))

    @classmethod
    def blocked(
        cls,
        step: str,
        reason: str,
        steps: list[str] | tuple[str, ...],
        *,
        items: list[dict[str, Any]] | None = None,
        task_file: str | None = None,
    ) -> RunOutcome:
        return cls(
            status=RunStatus.BLOCKED,
            steps=tuple(steps),
            step=step,
            reason=reason,
            items=list(items or []),
            task_file=task_file,
        )

    @classmethod
    def failed(
        cls,
        step: str,
        steps: list[str] | tuple[str, ...],
        *,
        reason: str | None = None,
    ) -> RunOutcome:
        return cls(
            status=RunStatus.FAILED,
            steps=tuple(steps),
            step=step,
            reason=reason,
        )

    def as_wire_dict(self) -> dict[str, Any]:
        """JSON-serializable snapshot mirrored to status/audit payloads."""
        return {
            "status": self.status.value,
            "step": self.step,
            "reason": self.reason,
            "items": self.items,
            "task_file": self.task_file,
            "steps": list(self.steps),
            "exit_code": self.exit_code,
        }
