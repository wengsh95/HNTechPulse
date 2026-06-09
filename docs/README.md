# Documentation

This directory contains the project docs that are most useful for agents and
maintainers.

## Start Here

- [Agent Runbook](AGENT_RUNBOOK.md): how an agent should run, resume, repair,
  and audit the pipeline.
- [Project Structure](PROJECT_STRUCTURE.md): where the major modules,
  generated artifacts, configs, prompts, and tests live.
- [Comment Stance Classifier](comment_stance_classifier.md): local stance
  classifier notes, LLM teacher labeling workflow, evaluation results, and
  follow-up plan for the `支持 / 质疑 / 中立` chart.

## Common Agent Commands

```bash
uv run python scripts/agent_run.py --date YYYY-MM-DD
uv run python scripts/agent_run.py --date YYYY-MM-DD --resume
uv run python scripts/agent_status.py --date YYYY-MM-DD
uv run python scripts/agent_run.py --date YYYY-MM-DD --steps write_script --refresh-variants
```

Autonomous agents should not call `main.py --agent` directly. Use
`scripts/agent_run.py`; it performs preflight/status checks and chooses safe
steps before invoking the pipeline.

## Agent Output Contracts

Prefer these machine-readable files over human-readable logs:

```text
data/{date}/pipeline_state.json
data/{date}/agent_events.jsonl
data/{date}/agent_tasks.json
data/{date}/agent_decision.json
data/{date}/agent_variant_decision.json
data/{date}/variants/index.json
data/{date}/variants/selection_brief.md
```

The normal publishable script is always promoted to:

```text
data/{date}/script.json
```
