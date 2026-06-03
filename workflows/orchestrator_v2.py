"""SKETCH: slim orchestrator that reads a workflow YAML and drives a state machine.

This replaces src/pipeline/orchestrator.py (the 397-line class).
Key differences:
  - No more PIPELINE_STEPS constant
  - No more --steps CLI
  - No more _step_fetch / _step_enrich / _step_script private methods
  - No more Progress/--force/--dry-run (those were human ergonomics)
  - LLM is consulted only for deviation decisions; the loop is data-driven

NOT production: state model is sketched, error handling is minimal,
LLM adapter is a stub. Goal is to show the SHAPE, not the implementation.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from src.core.models import ContentPackage, Script
from src.utils.logger import setup_logger


# ── Workflow definition (loaded from YAML) ──────────────────────


@dataclass
class Phase:
    id: str
    description: str
    tools: list[str]
    depends_on: list[str] = field(default_factory=list)
    output_state: dict[str, Any] = field(default_factory=dict)
    gates: list[str] = field(default_factory=list)
    on_failure: str = "abort"  # abort | skip | loop_to
    loop_to: Optional[str] = None
    retry_budget: int = 0
    skip_if: Optional[str] = None
    soft_constraints: list[str] = field(default_factory=list)


@dataclass
class Workflow:
    name: str
    version: int
    description: str
    inputs: dict[str, Any]
    defaults: dict[str, Any]
    phases: list[Phase]
    deviation_policy: dict[str, Any]
    gates: list[dict[str, Any]]

    @classmethod
    def load(cls, path: str | Path) -> "Workflow":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(
            name=data["name"],
            version=data.get("version", 1),
            description=data.get("description", ""),
            inputs=data.get("inputs", {}),
            defaults=data.get("defaults", {}),
            phases=[Phase(**p) for p in data["phases"]],
            deviation_policy=data.get("deviation_policy", {}),
            gates=data.get("gates", []),
        )


# ── Working memory (the type-system surface) ─────────────────────


@dataclass
class WorkflowState:
    """The orchestrator's working memory. This is what the LLM 'sees'."""

    date: str
    content: ContentPackage
    script: Script
    inputs: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    failed: bool = False
    failure_reason: Optional[str] = None
    feedback: dict[str, Any] = field(default_factory=dict)
    _retries: dict[str, int] = field(default_factory=dict)

    def log(self, msg: str) -> None:
        self.history.append({"event": "log", "msg": msg})

    def satisfy(self, gate: str) -> bool:
        """Check a dotted-path gate like 'script.fact_check.passed'."""
        # Tiny eval-by-path; in production use a real expression lang
        obj = self
        for part in gate.split("."):
            if isinstance(obj, dict):
                obj = obj.get(part)
            else:
                obj = getattr(obj, part, None)
            if obj is None:
                return False
        return bool(obj)

    def satisfies(self, requirements: dict[str, Any]) -> bool:
        return all(self.satisfy(k) for k in requirements)

    def retries_left(self, phase: Phase) -> bool:
        return self._retries.get(phase.id, 0) < phase.retry_budget

    def consume_retry(self, phase: Phase) -> None:
        self._retries[phase.id] = self._retries.get(phase.id, 0) + 1


# ── Orchestrator ──────────────────────────────────────────────────


class Orchestrator:
    """Reads workflow YAML. Iterates phases. Invokes tools. Checks gates.

    The LLM enters only at one hook: _decide_deviation(). Otherwise the
    loop is data-driven — same as mavis-team's plan-then-execute pattern.
    """

    def __init__(
        self,
        config: dict,
        tool_registry,  # ToolRegistry — see sketch in tools.py
        llm=None,  # optional; for deviation decisions
        debug: bool = False,
    ):
        self.config = config
        self.tools = tool_registry
        self.llm = llm
        self.logger = setup_logger(__name__, debug=debug)

    def run(self, workflow_path: str, date: str, **inputs: Any) -> WorkflowState:
        workflow = Workflow.load(workflow_path)
        state = WorkflowState(
            date=date,
            content=ContentPackage(date=date, items=[]),
            script=Script.empty(date),
            inputs=inputs,
        )

        for phase in self._ordered_phases(workflow):
            if not self._should_run(phase, state):
                state.log(f"skip phase {phase.id}")
                continue

            state = self._run_phase(phase, state, workflow)

            if state.failed and not self._can_recover(phase, state):
                state.log(f"abort at phase {phase.id}: {state.failure_reason}")
                break

            if self._is_terminal(state):
                break

        self._emit_report(state, workflow)
        return state

    # ── Phase loop ────────────────────────────────────────────────

    def _run_phase(
        self, phase: Phase, state: WorkflowState, workflow: Workflow
    ) -> WorkflowState:
        for tool_id in phase.tools:
            tool = self.tools.get(tool_id)
            if tool is None:
                state.failed = True
                state.failure_reason = f"tool not registered: {tool_id}"
                return state
            result = tool.invoke(state=state, config=self.config)
            state = state.absorb(result) if hasattr(state, "absorb") else state
            state.log({"phase": phase.id, "tool": tool_id, "result": result.summary})

        if not state.satisfies(phase.output_state):
            state.failed = True
            state.failure_reason = f"output_state not satisfied: {phase.output_state}"
            return state

        for gate in phase.gates:
            if not state.satisfy(gate):
                return self._handle_gate_failure(phase, state, workflow)

        return state

    def _handle_gate_failure(
        self, phase: Phase, state: WorkflowState, workflow: Workflow
    ) -> WorkflowState:
        if (
            phase.on_failure == "loop_to"
            and phase.loop_to
            and state.retries_left(phase)
        ):
            state.consume_retry(phase)
            state.log(f"retrying {phase.loop_to} (attempt {state._retries[phase.id]})")
            target = next(p for p in workflow.phases if p.id == phase.loop_to)
            return self._run_phase(target, state, workflow)

        state.failed = True
        state.failure_reason = f"gate failed: {phase.gates}"
        return state

    # ── Deviation (the only place LLM is consulted in the loop) ──

    def _decide_deviation(
        self, phase: Phase, state: WorkflowState, workflow: Workflow
    ) -> str:
        """Returns 'proceed' | 'skip' | 'extra:<tool_id>'.
        Default: follow YAML. With LLM: ask the LLM whether to deviate.
        """
        if not self.llm or not workflow.deviation_policy:
            return "proceed"
        return self.llm.decide_deviation(
            phase=phase,
            state=state,
            policy=workflow.deviation_policy,
        )

    # ── Helpers (terse) ──────────────────────────────────────────

    def _ordered_phases(self, workflow: Workflow) -> list[Phase]:
        # Topological sort by depends_on. Trivial for a linear chain.
        # TODO: handle diamond dependencies
        return list(workflow.phases)

    def _should_run(self, phase: Phase, state: WorkflowState) -> bool:
        # Evaluate phase.skip_if expression against state. Stubbed.
        if phase.skip_if:
            return not eval(phase.skip_if, {"state": state, "inputs": state.inputs})  # noqa
        return True

    def _can_recover(self, phase: Phase, state: WorkflowState) -> bool:
        return phase.on_failure == "skip"

    def _is_terminal(self, state: WorkflowState) -> bool:
        return state.satisfies({"video.state": "ready"})

    def _emit_report(self, state: WorkflowState, workflow: Workflow) -> None:
        # In production: emit structured trace for a supervisor agent,
        # NOT a pretty markdown file for humans.
        self.logger.info(
            f"workflow {workflow.name} done; history: {len(state.history)}"
        )
