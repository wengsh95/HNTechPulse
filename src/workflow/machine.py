"""High-level workflow state machine for HNTechPulse."""

from __future__ import annotations

import hashlib
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from src.pipeline.paths import date_root
from src.workflow.model import (
    FailureType,
    Phase,
    StateRecord,
    StateStatus,
    WorkflowSnapshot,
    WorkflowStep,
)
from src.workflow.persistence import (
    SCHEMA_VERSION,
    WorkflowCorruptError,
    load,
    save,
    workflow_path,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class WorkflowMachine:
    """DAG state machine for one date-scoped product workflow.

    The machine does not execute pipeline work.  It records what the agent or
    existing orchestrator is doing and verifies transition prerequisites.
    """

    def __init__(
        self,
        date: str,
        steps: Iterable[WorkflowStep],
        *,
        product: str = "video",
    ) -> None:
        self.date = date
        self.product = product
        self.steps = tuple(steps)
        self._defs = {step.name: step for step in self.steps}
        if len(self._defs) != len(self.steps):
            raise ValueError("Workflow step names must be unique")
        self._topo = self._validate_and_toposort()
        self.path = workflow_path(date, product)
        self.snapshot: WorkflowSnapshot | None = None

    def _validate_and_toposort(self) -> list[str]:
        in_degree = {name: len(step.deps) for name, step in self._defs.items()}
        for name, step in self._defs.items():
            for dep in step.deps:
                if dep not in self._defs:
                    raise ValueError(
                        f"Workflow step {name!r} depends on unknown {dep!r}"
                    )

        queue = deque(sorted(name for name, degree in in_degree.items() if degree == 0))
        order: list[str] = []
        while queue:
            current = queue.popleft()
            order.append(current)
            for name, step in self._defs.items():
                if current in step.deps:
                    in_degree[name] -= 1
                    if in_degree[name] == 0:
                        queue.append(name)
        if len(order) != len(self._defs):
            raise ValueError("Workflow step graph contains a cycle")

        for name, step in self._defs.items():
            successors = set(self.successors(name))
            for target in step.transitions_to:
                if target not in self._defs:
                    raise ValueError(
                        f"Workflow step {name!r} transitions to unknown {target!r}"
                    )
                if target not in successors:
                    raise ValueError(
                        f"Workflow step {name!r} transitions to non-successor {target!r}"
                    )
        return order

    def _require_snapshot(self) -> WorkflowSnapshot:
        if self.snapshot is None:
            raise RuntimeError("Workflow is not loaded; call create() or load() first")
        return self.snapshot

    def create(self, metadata: dict[str, Any] | None = None) -> WorkflowSnapshot:
        timestamp = _now()
        self.snapshot = WorkflowSnapshot(
            schema_version=SCHEMA_VERSION,
            date=self.date,
            product=self.product,
            states={name: StateRecord() for name in self._topo},
            created_at=timestamp,
            updated_at=timestamp,
            metadata=dict(metadata or {}),
        )
        self._save()
        return self.snapshot

    def load(self) -> bool:
        snapshot = load(self.path)
        if snapshot is None:
            self.snapshot = None
            return False
        expected = set(self._defs)
        actual = set(snapshot.states)
        if actual != expected:
            missing = sorted(expected - actual)
            unknown = sorted(actual - expected)
            raise WorkflowCorruptError(
                "Workflow state model mismatch; "
                f"missing={missing}, unknown={unknown}. "
                "Create a new workflow state file before continuing."
            )
        self.snapshot = snapshot
        return self.snapshot is not None

    def ensure(self, metadata: dict[str, Any] | None = None) -> WorkflowSnapshot:
        if self.snapshot is None and self.path.exists():
            self.load()
        if self.snapshot is None:
            return self.create(metadata=metadata)
        if self.snapshot.date != self.date or self.snapshot.product != self.product:
            raise ValueError("Workflow identity does not match requested date/product")
        missing = [name for name in self._topo if name not in self.snapshot.states]
        if missing:
            for name in missing:
                self.snapshot.states[name] = StateRecord()
        metadata_changed = False
        for key, value in (metadata or {}).items():
            if self.snapshot.metadata.get(key) != value:
                self.snapshot.metadata[key] = value
                metadata_changed = True
        if missing or metadata_changed:
            self._save()
        return self.snapshot

    def _save(self) -> None:
        snapshot = self._require_snapshot()
        snapshot.updated_at = _now()
        save(self.path, snapshot)

    def update_metadata(self, **values: Any) -> None:
        """Persist runtime metadata owned by the native workflow."""
        snapshot = self._require_snapshot()
        snapshot.metadata.update(values)
        self._save()

    def get(self, name: str) -> WorkflowStep:
        try:
            return self._defs[name]
        except KeyError as exc:
            raise ValueError(f"Unknown workflow state: {name}") from exc

    def successors(self, name: str) -> list[str]:
        self.get(name)
        return [
            candidate for candidate, step in self._defs.items() if name in step.deps
        ]

    def descendants(self, name: str) -> set[str]:
        pending = deque(self.successors(name))
        result: set[str] = set()
        while pending:
            candidate = pending.popleft()
            if candidate in result:
                continue
            result.add(candidate)
            pending.extend(self.successors(candidate))
        return result

    def state_for_pipeline_step(self, pipeline_step: str) -> str | None:
        for step in self.steps:
            if pipeline_step in step.pipeline_steps:
                return step.name
        return None

    def ready_states(self) -> list[str]:
        snapshot = self._require_snapshot()
        return [
            name
            for name in self._topo
            if snapshot.states[name].status == StateStatus.PENDING
            and all(
                snapshot.states[dependency].status == StateStatus.DONE
                for dependency in self.get(name).deps
            )
        ]

    def current_state(self) -> str | None:
        ready = self.ready_states()
        return ready[0] if ready else None

    def is_done(self) -> bool:
        snapshot = self._require_snapshot()
        return all(
            record.status == StateStatus.DONE for record in snapshot.states.values()
        )

    def mark_running(self, name: str, phase: Phase = Phase.WORK) -> None:
        snapshot = self._require_snapshot()
        self._assert_ready_or_active(name)
        record = snapshot.states[name]
        record.status = StateStatus.RUNNING
        record.phase = phase
        record.last_error = None
        record.failure_type = None
        record.started_at = record.started_at or _now()
        self._save()

    def mark_done(
        self, name: str, produced_hashes: dict[str, str] | None = None
    ) -> None:
        snapshot = self._require_snapshot()
        self._assert_ready_or_active(name)
        record = snapshot.states[name]
        record.status = StateStatus.DONE
        record.phase = Phase.WORK
        record.last_error = None
        record.failure_type = None
        record.completed_at = _now()
        if produced_hashes is None:
            produced_hashes = self.snapshot_produced_hashes(name)
        record.produced_hashes = produced_hashes
        self._save()

    def mark_failed(
        self,
        name: str,
        message: str,
        *,
        failure_type: FailureType = FailureType.VERIFY,
        phase: Phase = Phase.WORK,
    ) -> None:
        snapshot = self._require_snapshot()
        self.get(name)
        record = snapshot.states[name]
        record.status = StateStatus.FAILED
        record.phase = phase
        record.last_error = message
        record.failure_type = failure_type.value
        self._save()

    def block(self, name: str, message: str, *, phase: Phase = Phase.WORK) -> None:
        snapshot = self._require_snapshot()
        self.get(name)
        record = snapshot.states[name]
        record.status = StateStatus.BLOCKED
        record.phase = phase
        record.last_error = message
        record.failure_type = FailureType.VERIFY.value
        self._save()

    def reset(self, name: str, *, shallow: bool = False) -> list[str]:
        snapshot = self._require_snapshot()
        self.get(name)
        affected = [name] if shallow else [name, *sorted(self.descendants(name))]
        for state_name in affected:
            snapshot.states[state_name] = StateRecord()
        snapshot.metadata["last_reset_state"] = name
        snapshot.metadata["last_reset_shallow"] = shallow
        snapshot.metadata["last_reset_cascade"] = affected
        self._save()
        return affected

    def _assert_ready_or_active(self, name: str) -> None:
        snapshot = self._require_snapshot()
        self.get(name)
        record = snapshot.states[name]
        if record.status == StateStatus.RUNNING:
            return
        if name not in self.ready_states():
            raise ValueError(f"Workflow state {name!r} is not ready")

    def snapshot_produced_hashes(self, name: str) -> dict[str, str]:
        root = date_root(self.date)
        hashes: dict[str, str] = {}
        for pattern in self.get(name).produces:
            for path in root.glob(pattern):
                if path.is_file():
                    hashes[str(path.relative_to(root)).replace("\\", "/")] = _hash_file(
                        path
                    )
        return hashes

    def check_integrity(self, name: str) -> list[str]:
        """Return predecessor artifacts whose content changed after completion."""
        snapshot = self._require_snapshot()
        self.get(name)
        ancestors: set[str] = set()
        pending = deque(self.get(name).deps)
        while pending:
            candidate = pending.popleft()
            if candidate in ancestors:
                continue
            ancestors.add(candidate)
            pending.extend(self.get(candidate).deps)

        current_root = date_root(self.date)
        tampered: list[str] = []
        for ancestor in ancestors:
            record = snapshot.states[ancestor]
            if record.status != StateStatus.DONE:
                continue
            for relative, expected in record.produced_hashes.items():
                path = current_root / relative
                if not path.exists():
                    tampered.append(f"{ancestor}:{relative} — file deleted")
                elif _hash_file(path) != expected:
                    tampered.append(f"{ancestor}:{relative} — file modified")
        return tampered

    def status_report(self) -> dict[str, Any]:
        snapshot = self._require_snapshot()
        ready = self.ready_states()
        statuses = {record.status for record in snapshot.states.values()}
        if self.is_done():
            overall_status = "complete"
        elif StateStatus.BLOCKED in statuses:
            overall_status = "blocked"
        elif StateStatus.FAILED in statuses:
            overall_status = "failed"
        elif StateStatus.RUNNING in statuses:
            overall_status = "running"
        else:
            overall_status = "pending"
        return {
            "status": overall_status,
            "date": snapshot.date,
            "product": snapshot.product,
            "created_at": snapshot.created_at,
            "updated_at": snapshot.updated_at,
            "current_state": self.current_state(),
            "ready_states": ready,
            "is_done": self.is_done(),
            "states": {
                name: {
                    "title": self.get(name).title,
                    "status": record.status.value,
                    "phase": record.phase.value,
                    "last_error": record.last_error,
                    "failure_type": record.failure_type,
                    "pipeline_steps": list(self.get(name).pipeline_steps),
                }
                for name, record in snapshot.states.items()
            },
            "metadata": snapshot.metadata,
            "workflow_file": str(self.path).replace("\\", "/"),
        }
