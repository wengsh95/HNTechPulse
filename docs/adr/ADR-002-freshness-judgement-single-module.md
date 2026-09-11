# ADR-002: Freshness judgement lives in one module with typed codes

**Status**: Accepted (2026-09)

## Context

`agent_status` and `agent_run` each kept a private copy of the stale-detection
logic ("which artifact is stale and how to repair it"), and communicated the
result across the process seam as a free-text `reason` string that one side
generated and the other parsed with `reason.startswith(...)`.  Every staleness
check was duplicated, and the contract between the two processes was an
unversioned, prefix-matching string protocol.

## Decision

Move all stale-detection, recovery-step resolution, and repair-command
selection into one module (`src/workflow/freshness.py`), and give each stale
result a structured code:

- `StaleCode` — an enum whose `value` is byte-identical to the legacy reason
  string it replaced, and whose `repair` property names the recovering step.
- `StaleArtifact` — one record: artifact path, code, and the derived reason.
- `check_freshness(date)` — the single stale-detection body.
- `recovery_tail(stale_records)` — code-first recovery resolution, with the
  legacy operators retained as fallback.
- `command_for(date, stale_records)` — repair-command selection.

`agent_status` renders the wire format from `StaleArtifact.as_wire_dict()`;
`agent_run` resolves recovery through `recovery_tail`.  Both now dispatch on
the code instead of parsing reason strings.

## Consequences

- Staleness logic exists once; the wire shape (`reason`, `stale_artifacts`)
  is unchanged and test-pinned, so the agent scripts see no behavioral
  difference.
- New staleness kinds are a new `StaleCode` member + a repair mapping, not a
  second copy of the detector.
- Deliberately out of scope: existence-only checks (whether an artifact is
  present at all) stayed in their consumers and were later unified separately
  (see ADR-004).