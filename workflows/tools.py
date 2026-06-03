"""SKETCH: tool protocol — the L1 layer of process control.

Tools don't know about workflows. They declare:
  - input state requirements (preconditions)
  - output state contributions
  - the actual work

The orchestrator looks at these to decide whether a tool can run.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class ToolContext:
    state: Any  # WorkflowState
    config: dict
    logger: Any


@dataclass
class ToolResult:
    summary: str
    updates: dict[str, Any]  # patches to apply to state
    produced_outputs: list[str] = None  # e.g. ['script.fact_check']


class ToolPreconditionError(RuntimeError):
    """Raised when a tool's preconditions aren't met."""


class Tool:
    """Base class for fine-grained tools. Replaces the coarse
    LLMProvider.generate_single_story_segment() interface.
    """

    name: str = ""
    requires: list[str] = []  # gates that must be satisfied to invoke
    produces: list[str] = []  # gates this tool contributes to

    def __init__(self, fn: Callable[[ToolContext], ToolResult]):
        self.fn = fn

    def invoke(self, state, config) -> ToolResult:
        ctx = ToolContext(state=state, config=config, logger=None)
        # Precondition check — the L1 contract
        for gate in self.requires:
            if not state.satisfy(gate):
                raise ToolPreconditionError(
                    f"tool {self.name!r} requires {gate!r}, not satisfied"
                )
        return self.fn(ctx)


# ── Example tools (replacing current coarse methods) ─────────────


def fetch_hn_stories(ctx: ToolContext) -> ToolResult:
    """Replaces orchestrator._step_fetch. Tiny, single-purpose."""
    # In real code: ctx.config['hn']..., call HN API
    return ToolResult(
        summary="fetched 30 stories",
        updates={"content.state": "ready", "content.items": "..."},
        produced_outputs=["content.state=ready"],
    )


def fact_check(ctx: ToolContext) -> ToolResult:
    """Replaces... nothing — this verifier doesn't exist yet. Add it."""
    # In real code: LLM call with verifier prompt, return pass/fail
    return ToolResult(
        summary="fact_check: 3 claims verified, 1 fail",
        updates={"script.fact_check": {"passed": False, "failures": [...]}},
        produced_outputs=["script.fact_check"],
    )


def draft_event_card(ctx: ToolContext) -> ToolResult:
    """Replaces LLMProvider.generate_single_story_segment (one slice of it)."""
    # In real code: LLM call with story_script.md prompt for ONE story
    return ToolResult(
        summary="drafted event_card for story 1",
        updates={"script.segments[0]": "..."},
        produced_outputs=["script.segments"],
    )


# ── Registry (the orchestrator's phonebook) ─────────────────────


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list_available(self, state) -> list[str]:
        """Tools whose preconditions are met right now."""
        out = []
        for name, tool in self._tools.items():
            try:
                # dry-run precondition check
                for gate in tool.requires:
                    if not state.satisfy(gate):
                        break
                else:
                    out.append(name)
            except Exception:
                pass
        return out


# ── Wiring (replaces Orchestrator.__init__'s manual assembly) ───


def default_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(Tool(fetch_hn_stories))
    reg.register(Tool(fact_check))
    reg.register(Tool(draft_event_card))
    # ... register all the fine-grained tools
    return reg
