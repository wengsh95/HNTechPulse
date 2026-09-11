# ADR-003: `run()` returns a typed outcome; interruption points are named guards

**Status**: Accepted (2026-09)

## Context

`Orchestrator.run()` originally returned `None`.  A blocked run was
communicated purely through side effects — the workflow metadata file and a
`run_blocked` event — and `agent_run` re-derived the shell exit code (2 for
blocked/failed) by re-reading the status dict and matching `blocked_reason`
strings.  Separately, the five interruption points (enrichment failure,
source-context, script quality, story-image selection, human review) were
inlined in `run()` between the step calls, each building a block payload and
calling `_workflow_block`.

## Decision

- `run()` returns a typed `RunOutcome` (`src/workflow/outcome.py`) with a
  `RunStatus` (completed / blocked / failed), the blocking step/reason/items,
  the executed step sequence, and a derived `exit_code` (0 / 2 / 1).  `main.py`
  propagates that exit code directly; the metadata and event side effects are
  kept as the durable record.
- The five interruption points are extracted into `_guard_*` methods, each
  returning a terminal `RunOutcome` or `None` (continue).  `run()` keeps only
  the linear step sequence with one guard call per step.
- Non-agent enrichment failure explicitly returns `RunOutcome.failed` instead
  of a bare `return` (which had silently violated the `-> RunOutcome` contract
  and made `main.py` crash into a generic exit 1).

Deliberately *not* done: a uniform "Stage" interface.  The `_step_*` signatures
are heterogeneous because that is honest — each step names exactly what it
consumes.  Forcing them behind a single `execute(ctx)` signature would replace
a readable call site with an adapter layer and buy nothing.

## Consequences

- Shells and schedulers see the run's direct result instead of inferring it
  from status strings; blocked no longer logs "Pipeline completed
  successfully".
- The five block paths are named, unit-testable, and no longer interleaved
  with the step sequence.
- Wire format (reason strings, items, exit codes, `blocked_reason` metadata)
  unchanged and test-pinned.
- The decision not to uniformize step interfaces is recorded so it is not
  re-litigated.