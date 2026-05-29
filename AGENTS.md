# AGENTS.md

## Quick start

```bash
uv sync                          # install
uv run python main.py            # run full pipeline
uv run python -m pytest          # tests
uv run python scripts/quality_check.py  # lint + typecheck + test + coverage
```

## Windows path gotcha

- Git Bash mounts drives as `/d/`, `/c/` — **not** `D:\`, `C:\`
- Always use Unix-style paths: `cd /d/code/HNTechPulse/...`

## Console encoding

If Chinese output is garbled in PowerShell, run once per session:

```powershell
. .\scripts\encoding.ps1
```

Sets `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`, and `chcp 65001`.

## Config

- YAML files in `config/` are deep-merged at runtime (`src/utils/config.py`)
- Env vars in `.env` (copy from `.env.example`)

## Pipeline steps

```text
fetch → enrich → script → translate → html
```

Run a subset: `uv run python main.py --steps fetch,script`

## Key patterns agents might miss

- **Provider factory**: Implement an ABC, add to the `_auto_register()` `attempts` list in `src/providers/factory.py`. Auto-registers on import.
- **Prompt placeholders**: `{{ foo }}` tokens must be `PH_FOO` constants in `src/core/prompts.py`. `render_prompt()` raises on typos.
- **Two-model LLM**: Main model for scripts, `fast` model (lower tokens/temp) for translation and comment judging.
- **Comment flow**: `CommentAnalyzer` (VADER + quality) → `CommentJudge` (LLM top-15) → `quote_candidates`. ScriptWriter consumes `quote_candidates` directly. No re-selection downstream.
- **LLM JSON retry**: `_call_llm_with_json_retry()` retries on bad JSON; doubles `max_tokens` on `finish_reason=length`, capped by `llm.max_completion_tokens_cap`.
- **Cache schema version**: Bump `llm.cache_schema_version` in config when segment-cache semantics change.

## Code quality

| Check | Command |
|-------|---------|
| All | `uv run python scripts/quality_check.py` |
| Auto-fix | `uv run python scripts/quality_check.py --fix` |
| Skip a check | `--skip mypy,pip-audit` |
| Ruff lint | `uv run ruff check src/ tests/` |
| Ruff format | `uv run ruff format src/ tests/` |
| Dead code | `uv run vulture src/ --min-confidence 80` |
| Type check | `uv run mypy src/ --ignore-missing-imports` |

`pre-commit` hooks run `ruff` and `vulture` only.

## Entry point

`main.py` → `Orchestrator` → individual step modules. Not a web app.