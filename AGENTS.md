# AGENTS.md

Quick-start checklist for coding agents operating the pipeline.

## Commands

```bash
uv run python scripts/agent_run.py --date YYYY-MM-DD         # 1. Managed agent run (preflight + status + safe steps)
uv run python scripts/agent_run.py --date YYYY-MM-DD --resume # 2. Resume through managed entrypoint
uv run python scripts/agent_status.py --date YYYY-MM-DD      # 3. Inspect machine-readable state/artifacts
uv run python scripts/agent_audit.py --date YYYY-MM-DD       # 4. Final publishability audit
uv run python -m pytest                                      # Tests
```

Do **not** run `main.py --agent` directly. `main.py --agent` is guarded and
will reject direct agent calls. Manual debugging may use
`main.py --agent --direct-agent-run`, but autonomous agents should always use
`scripts/agent_run.py`.

## Key References

- **Full guidance**: [CLAUDE.md](CLAUDE.md) — architecture, patterns, pitfalls, behavioral rules
- **Agent contract**: [docs/AGENT_RUNBOOK.md](docs/AGENT_RUNBOOK.md) — state files, blocked reasons, decision gates, step handling policy, variants
- **Module map**: [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)

## State Files (under `data/{date}/`)

| File | Purpose |
|------|---------|
| `pipeline_state.json` | Pipeline status, completed/failed steps, blocked reason |
| `agent_events.jsonl` | Append-only event log |
| `agent_tasks.json` | Pending repair tasks (e.g. manual article fetch) |
| `agent_decision.json` | Decision gate result (confidence, scores, thresholds) |

## Rules

1. Always use `scripts/agent_run.py` for pipeline execution; it runs preflight
   and status checks before invoking `main.py --agent`.
2. Read JSON state files, never parse human logs.
3. On `blocked` status → read `blocked_reason` in `pipeline_state.json` → follow [AGENT_RUNBOOK.md](docs/AGENT_RUNBOOK.md).
4. Never use `--allow-degraded-enrichment` for final output without explicit user approval.
5. If `agent_status.py` reports stale artifacts, follow its `safe_next_commands`;
   do not render stale `script.json`/`cli_props.json` combinations.
