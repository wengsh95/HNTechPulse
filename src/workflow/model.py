"""Declarative models for the high-level workflow state machine.

This is intentionally smaller than the low-level pipeline step list. A
workflow state represents an agent-facing phase such as ``research`` or
``produce``; its ``pipeline_steps`` field declares the concrete work driven by
the Orchestrator for that phase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StateStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class Phase(str, Enum):
    WORK = "work"
    CHECK = "check"


class FailureType(str, Enum):
    VERIFY = "verify"
    INTEGRITY = "integrity"
    FUTURE_LEAKED = "future_leaked"
    TRANSITION_DENIED = "transition_denied"


@dataclass(frozen=True)
class WorkflowStep:
    """Definition of one high-level state."""

    name: str
    title: str
    deps: tuple[str, ...] = ()
    pipeline_steps: tuple[str, ...] = ()
    transitions_to: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    consumes: tuple[str, ...] = ()


@dataclass
class StateRecord:
    status: StateStatus = StateStatus.PENDING
    phase: Phase = Phase.WORK
    last_error: str | None = None
    failure_type: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    produced_hashes: dict[str, str] = field(default_factory=dict)


@dataclass
class WorkflowSnapshot:
    schema_version: int
    date: str
    product: str
    states: dict[str, StateRecord]
    created_at: str
    updated_at: str
    metadata: dict[str, Any] = field(default_factory=dict)
