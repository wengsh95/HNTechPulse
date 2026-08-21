"""Atomic persistence for high-level workflow state."""

from __future__ import annotations

import json
from pathlib import Path

from src.pipeline.paths import agent_path
from src.utils.atomic_io import atomic_write_json
from src.workflow.model import Phase, StateRecord, StateStatus, WorkflowSnapshot

SCHEMA_VERSION = 2


class WorkflowCorruptError(ValueError):
    """Raised when a workflow file exists but cannot be trusted."""


def workflow_path(date: str, product: str = "video") -> Path:
    if product != "video":
        raise ValueError(f"Unsupported workflow product: {product}")
    return agent_path(date, "workflow_video.json")


def load(path: Path) -> WorkflowSnapshot | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowCorruptError(f"Could not read workflow {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise WorkflowCorruptError(f"Workflow {path} must be a JSON object")
    version = raw.get("schema_version")
    if version != SCHEMA_VERSION:
        raise WorkflowCorruptError(
            f"Workflow {path} has schema_version={version!r}; expected {SCHEMA_VERSION}"
        )
    required = ("date", "product", "states", "created_at", "updated_at")
    missing = [key for key in required if key not in raw]
    if missing:
        raise WorkflowCorruptError(
            f"Workflow {path} is missing required fields: {', '.join(missing)}"
        )
    if not isinstance(raw["states"], dict):
        raise WorkflowCorruptError(f"Workflow {path}.states must be an object")

    states: dict[str, StateRecord] = {}
    for name, value in raw["states"].items():
        if not isinstance(value, dict):
            raise WorkflowCorruptError(f"Workflow state {name!r} must be an object")
        try:
            states[str(name)] = StateRecord(
                status=StateStatus(value.get("status", StateStatus.PENDING.value)),
                phase=Phase(value.get("phase", Phase.WORK.value)),
                last_error=value.get("last_error"),
                failure_type=value.get("failure_type"),
                started_at=value.get("started_at"),
                completed_at=value.get("completed_at"),
                produced_hashes=dict(value.get("produced_hashes") or {}),
            )
        except (TypeError, ValueError) as exc:
            raise WorkflowCorruptError(
                f"Workflow state {name!r} has invalid status or phase"
            ) from exc

    metadata = raw.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise WorkflowCorruptError(f"Workflow {path}.metadata must be an object")

    return WorkflowSnapshot(
        schema_version=SCHEMA_VERSION,
        date=str(raw["date"]),
        product=str(raw["product"]),
        states=states,
        created_at=str(raw["created_at"]),
        updated_at=str(raw["updated_at"]),
        metadata=metadata,
    )


def save(path: Path, snapshot: WorkflowSnapshot) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "date": snapshot.date,
        "product": snapshot.product,
        "created_at": snapshot.created_at,
        "updated_at": snapshot.updated_at,
        "states": {
            name: {
                "status": record.status.value,
                "phase": record.phase.value,
                "last_error": record.last_error,
                "failure_type": record.failure_type,
                "started_at": record.started_at,
                "completed_at": record.completed_at,
                "produced_hashes": record.produced_hashes,
            }
            for name, record in snapshot.states.items()
        },
        "metadata": snapshot.metadata,
    }
    atomic_write_json(path, payload)
