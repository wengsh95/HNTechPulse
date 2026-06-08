# AGENTS.md

Quick-start checklist for coding agents operating the pipeline.

## Commands

```bash
uv run python scripts/agent_preflight.py --date YYYY-MM-DD   # 1. Always preflight first
uv run python main.py --date YYYY-MM-DD --agent              # 2. First run
uv run python main.py --date YYYY-MM-DD --resume --agent     # 3. Resume after repair
uv run python scripts/agent_audit.py --date YYYY-MM-DD       # 4. Final publishability audit
uv run python -m pytest                                       # Tests
```

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

1. Always run preflight before any pipeline command.
2. Read JSON state files, never parse human logs.
3. On `blocked` status → read `blocked_reason` in `pipeline_state.json` → follow [AGENT_RUNBOOK.md](docs/AGENT_RUNBOOK.md).
4. Never use `--allow-degraded-enrichment` for final output without explicit user approval.
