# ADR-001: Step semantics live in one StepSpec registry

**Status**: Accepted (2026-09)

## Context

The orchestrator used to own four hand-maintained policy frozensets
(`CORE_PIPELINE_STEPS`, `OPTIONAL_PRODUCTION_STEPS`, `SCRIPT_CONSUMING_STEPS`,
`SCRIPT_MUTATING_STEPS`, `HUMAN_REVIEW_PROTECTED_STEPS`) plus a `_resolve_steps`
function that expanded a requested step list into the runnable chain.  The
agent scripts and `main.py --resume` each kept their own chain-slicing and
recovery logic, so "which steps run and in what order" was re-derived in four
places from four slightly different private copies.

The stringly-typed step graph was the single most expensive fact in the
codebase: every recovery path, `--from` re-anchor, resume, and audit assumed a
different view of it, and a change to step order or optionality had to be
mirrored across them.

## Decision

Declare every low-level pipeline step once in a typed `StepSpec` table
(`src/workflow/steps.py`), carrying its phase, chain order, and the execution
flags that used to live in the orchestrator's frozensets:

- `optional` / `standalone`
- `consumes_script` / `mutates_script`
- `human_review_protected`
- direct `prereqs` (single-level expansion, matching the legacy behaviour —
  deliberately *not* a transitive closure)

A pure planner module (`src/workflow/planner.py`) derives every execution plan
from that table: `resolve_steps` for a request, tail-slicing for recovery,
`from_step_tail` for `--from`, `resume_tail` for `--resume`.  The high-level
workflow phase steps (`src/workflow/video.py`) are derived by phase membership.
`validation_errors()` runs at package import so an inconsistent table fails
fast instead of halfway through a run.

## Consequences

- One source of truth for step order and policy; the orchestrator, agent
  scripts, and `main.py --resume` share it.
- The table is immutable; adding a step is a one-line declaration, not a sync
  across four copies.
- Single-level (not transitive) prereq expansion is preserved and pinned by
  tests — the legacy behaviour was that, and changing it would alter recovery
  semantics.
- The recovery re-anchoring (`DOWNSTREAM_REENTRY` / `FAILURE_REENTRY`) is
  explicitly separate because `--from` re-anchoring and failure recovery
  genuinely behaved differently.