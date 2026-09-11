# ADR-004: Artifact presence is one typed fact table

**Status**: Accepted (2026-09)

## Context

Three consumers each kept a private, hard-coded view of "is the artifact
backing step X ready": `PipelineProgress._check_cache` (the run-start
summary), `agent_audit._artifact_check` (the pre-publish audit's
`{name}_exists` issues), and the audit's `publish_step_for_check` table that
mapped check names to repair steps.  The paths and readiness heuristics were
duplicated, and the mapping between the two views had drifted: the audit
emitted `cover_exists` (for `cover.png`, written by `cover_thumbnail`), while
`_next_command` looked for dead `cover_props_exists` / `cover_thumbnail_exists`
check names that nothing ever produced.

## Decision

Create `src/workflow/artifact_presence.py` with a typed
`ArtifactPresence` record — step name, artifact path, `ready`, and a one-line
reason — and two derived views:

- `presence_for_step(date)` — the full chain's readiness facts, byte-for-byte
  judging as the legacy `_check_cache` did and in the same order.
- `publish_presence(date)` — the publish-tail facts (title / cover /
  publish_guide), where `cover` means `cover.png`, matching the audit's
  `cover_exists`.

`PipelineProgress` now derives its summary triples from the table;
`agent_audit._artifact_check` derives its paths from the table.  The
`publish_step_for_check` mapping is fixed to the real `cover_exists` →
`--steps cover_thumbnail`.

Deliberately separate: the progress summary (human-readable run-start text)
and the audit (agent-facing `{name}_exists` issues) keep their distinct
outputs; only the shared path/ready fact is unified.  Staleness (freshness,
ADR-002) is out of scope — this is existence only.

## Consequences

- The readiness fact exists once; consumers format it differently.
- The dead `cover_props_exists` / `cover_thumbnail_exists` mapping bug is
  fixed and pinned by a test.
- Adding an artifact-backed step means declaring it in the table, not editing
  two consumers.