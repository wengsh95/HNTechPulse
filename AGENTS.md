# Repository Guidelines

## Project Structure & Module Organization

HN TechPulse is a Python CLI pipeline for turning Hacker News stories into a narrated tech video. `main.py` is the local entry point; orchestration lives in `src/pipeline/orchestrator.py`. Shared models and prompt rendering are in `src/core/`; pipeline stages, comment analysis, and script generation are in `src/pipeline/`; provider integrations (fetching, enrichment, LLM, TTS, and rendering) are in `src/providers/`; shared helpers are in `src/utils/`. Use `scripts/` for operational tools, `tests/` for pytest tests, and `config/` plus `prompts/` for runtime configuration and prompts. Static media belongs in `assets/` or `expressions/`, and design/architecture notes belong in `docs/`. Date-scoped runtime artifacts are written under `data/{YYYY-MM}/{date}/`; do not hand-edit or casually delete caches and manifests.

## Build, Test, and Development Commands

```bash
uv sync
uv run python main.py --dry-run
uv run python scripts/internal/agent/agent_run.py --date YYYY-MM-DD
uv run python scripts/internal/agent/agent_status.py --date YYYY-MM-DD
uv run python -m pytest
uv run python scripts/quality_check.py
```

Use `scripts/internal/agent/agent_run.py` for autonomous runs; it performs preflight, state checks, execution, and audit. Do not call `main.py --agent` directly. For Remotion changes, run `npm ci` and `npm run quality` from `src/providers/renderer/remotion/`.

## Coding Style & Naming Conventions

Target Python 3.11, use four-space indentation, type hints, `snake_case` for modules/functions, and `PascalCase` for classes and React components. Run Ruff for linting and formatting (`uv run ruff check src tests` and `uv run ruff format src tests`). Use helpers in `src/pipeline/paths.py` for data paths, and keep prompt placeholders synchronized with `PH_*` constants in `src/core/prompts.py`. TypeScript uses Prettier, ESLint, and `tsc`.

## Testing Guidelines

Name Python tests `tests/test_<feature>.py` and keep them focused on one stage or behavior. Run a targeted test while iterating, then the full `uv run python -m pytest` suite; the quality gate requires at least 50% coverage. Add regression coverage for pipeline-state, cache, artifact, and rendering changes.

## Commit & Pull Request Guidelines

Prefer concise imperative commits with the established prefixes, such as `feat:`, `fix:`, or `refactor:`. Keep commits focused. Pull requests should describe the affected flow and date-scoped artifacts, list validation commands, link related issues, and include card/video screenshots when visual output changes. Never commit `.env`, API keys, or generated runtime data.
