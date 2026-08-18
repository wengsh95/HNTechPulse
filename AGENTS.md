# AGENTS.md

Quick-start checklist for coding agents operating the pipeline.

## Setup

```bash
uv sync                        # Install deps (Python 3.11, managed by uv)
cp .env.example .env           # Configure API keys (ANTHROPIC, OPENAI, DEEPSEEK, etc.)
```

## Commands

```bash
uv run python scripts/agent_run.py --date YYYY-MM-DD         # 1. Managed agent run (preflight + status + safe steps)
uv run python scripts/agent_run.py --date YYYY-MM-DD --flow video  # Managed TTS + video render flow
uv run python scripts/agent_run.py --date YYYY-MM-DD --resume # 2. Resume through managed entrypoint
uv run python scripts/agent_status.py --date YYYY-MM-DD      # 3. Inspect machine-readable state/artifacts
uv run python scripts/agent_audit.py --date YYYY-MM-DD       # 4. Final publishability audit
uv run python -m pytest                                      # Tests
```

Do **not** run `main.py --agent` directly. `main.py --agent` is guarded and
will reject direct agent calls. Manual debugging may use
`main.py --agent --direct-agent-run`, but autonomous agents should always use
`scripts/agent_run.py`.

## Code Quality

```bash
uv run python scripts/quality_check.py              # All checks (ruff, vulture, mypy, pytest, coverage, pip-audit)
uv run python scripts/quality_check.py --fix         # Auto-fix where possible
uv run ruff check src/ tests/                        # Lint only
uv run ruff format src/ tests/                       # Format only
```

Pre-commit hooks run **ruff + vulture only** (no mypy, no pytest).

## Key References

- **Full guidance**: [CLAUDE.md](CLAUDE.md) — architecture, patterns, pitfalls, behavioral rules
- **Agent contract**: [docs/AGENT_RUNBOOK.md](docs/AGENT_RUNBOOK.md) — state files, blocked reasons, decision gates, step handling policy, variants
- **Module map**: [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)

## State Files (under `data/{month}/{date}/agent/`)

| File | Purpose |
|------|---------|
| `pipeline_state_video.json` / `pipeline_state_xhs.json` | Product-scoped pipeline status; legacy `pipeline_state.json` is migration fallback |
| `agent_events.jsonl` | Append-only event log |
| `agent_tasks.json` | Pending repair tasks (e.g. manual article fetch) |
| `agent_decision.json` | Decision gate result (confidence, scores, thresholds) |
| `script_lock.json` | Editorial script hash; prevents implicit regeneration after manual edits |

## Rules

1. Always use `scripts/agent_run.py` for pipeline execution; it runs preflight
   and status checks before invoking `main.py --agent`.
2. Read JSON state files, never parse human logs.
3. On `blocked` status → read `blocked_reason` in the product state file → follow [AGENT_RUNBOOK.md](docs/AGENT_RUNBOOK.md).
4. Never use `--allow-degraded-enrichment` for final output without explicit user approval.
5. If `agent_status.py` reports stale artifacts, follow its `safe_next_commands`;
   do not render PNGs from a stale `xhs_cards.json` plan.

## Gotchas

- **Chinese output garbled?** Run `. .\scripts\encoding.ps1` (sets `PYTHONUTF8=1`, `chcp 65001`).
- **Card output**: the managed flow writes exactly 6 PNGs at `1080×1440`
  under `publish/xhs_cards/`, plus `_contact-sheet.png`.
- **Browser renderer**: Playwright uses installed Chrome first and Edge as a
  fallback for the XHS card flow. Video rendering uses the configured Remotion
  or HyperFrames provider through `--flow video`.
- **Prompt placeholders**: `{{ foo }}` tokens must have matching `PH_FOO` constants in `src/core/prompts.py`. `render_prompt()` raises on unknown placeholders.
- **Path literals**: Never build `f"data/{month}/{date}/foo.json"` directly — use helpers from `src/pipeline/paths.py`.
