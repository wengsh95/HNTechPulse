# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**HN TechPulse** — Python CLI pipeline (not a web app) that generates a video tech news briefing from Hacker News content, producing a daily digest with editorial judgment. Entry point: [main.py](main.py) → [src/pipeline/orchestrator.py](src/pipeline/orchestrator.py).

## Commands

```bash
uv sync                                                # Install deps
uv run python main.py                                  # Run pipeline (default steps)
uv run python main.py --date 2026-04-26 --debug        # Specific date, debug logging
uv run python main.py --steps fetch,write_script       # Sub-chain (expands to all prerequisites)
uv run python main.py --dry-run                        # Skip API calls
uv run python -m pytest                                # Tests
```

Agent mode — always run preflight first, then resume:

```bash
uv run python scripts/agent_preflight.py --date YYYY-MM-DD          # JSON status + next_recommended_command
uv run python main.py --date YYYY-MM-DD --agent                     # First run
uv run python main.py --date YYYY-MM-DD --resume --agent            # Continue after repair
uv run python scripts/agent_audit.py --date YYYY-MM-DD              # Final publishability audit
```

Code quality:

```bash
uv run python scripts/quality_check.py              # All checks (ruff, vulture, mypy, pytest, coverage, pip-audit)
uv run python scripts/quality_check.py --fix         # Auto-fix where possible
uv run ruff check src/ tests/                       # Lint
uv run ruff format src/ tests/                      # Format
```

`pre-commit` hooks run `ruff` and `vulture` only.

## Architecture

- **Core** ([src/core/](src/core/)): ABCs ([interfaces.py](src/core/interfaces.py)), data models ([models.py](src/core/models.py)), prompt rendering ([prompts.py](src/core/prompts.py))
- **Providers** ([src/providers/](src/providers/)): fetcher, llm, tts, renderer, image_generator, enricher — auto-register via [factory.py](src/providers/factory.py)
- **Pipeline** ([src/pipeline/](src/pipeline/)): orchestrator, content_io, comment/, script/, agent layer, translation, TTS, timing, reports

Full module map: [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)

### Pipeline Steps

Three groups (see `src/pipeline/orchestrator.py`):

- **Core chain (12)** — `DEFAULT_STEPS`, what `main.py` runs by default
- **Optional production (3)** — `{cover_image, cover_thumbnail, publish_guide}`, opt-in via `--steps`
- **Standalone (2)** — `{render, preview}`, always opt-in

```
fetch → prefilter → fetch_comments → enrich_articles → translate_titles
  → analyze_comments → judge_comments → write_script
  → translate_comments → synthesize_audio → title
  → cover_image → cover_thumbnail → publish_guide → prepare_render
                                                              ↓ (opt-in)
                                                            render → preview
```

`--steps X` expands to all steps up to and including X. Each step has its own cache and can be re-run in isolation.

### Data Flow

```
HN API → [fetch] ContentPackage
  → [prefilter] LLM tech-relevance filter → prefilter.json
  → [fetch_comments] HN comments → content.json
  → [enrich_articles] Article body + images → content.json
  → [translate_titles] Batch translate titles → content.json
  → [analyze_comments] VADER + quality scores → comment_analysis.json
  → [judge_comments] LLM top-15 → quote_candidates, debate_focus → comment_judgement.json
  → [write_script] ScriptWriter → event/quote/atmosphere cards → script.json
  → [translate_comments] Fast model translate comments → translations.json
  → [synthesize_audio] TTS + alignment → audio/
  → [title] LLM video title/description/tags → title.json
  → [cover_image] Image generator → cover_bg.png + cover_props.json
  → [cover_thumbnail] Remotion still render → cover.png
  → [publish_guide] LLM publish checklist → publish_guide.md
  → [prepare_render] Write props + copy assets → cli_props.json
  → [render] Remotion video → output.mp4 (opt-in)
  → [always] ReportGenerator → report.md
```

**Key principle**: CommentAnalyzer scores → CommentJudge selects `quote_candidates` → ScriptWriter consumes directly. No independent re-selection downstream.

### Cache Files

All under `data/{date}/`:

| File | Step | Contents |
|------|------|----------|
| `prefilter.json` | prefilter | LLM tech relevance |
| `content.json` | fetch…translate_titles | Canonical ContentPackage |
| `comment_analysis.json` | analyze_comments | VADER + quality scores |
| `comment_judgement.json` | judge_comments | quote_candidates, debate_focus, stance |
| `script.json` | write_script | Final Script with cards |
| `translations.json` | translate_comments | Translated comment text |
| `audio/` | synthesize_audio | TTS chunks + alignment |
| `title.json` | title | Video title/description/tags |
| `cover_bg.png`, `cover_props.json` | cover_image | Raw image + props |
| `cover.png` | cover_thumbnail | Final cover with title overlay |
| `publish_guide.md` | publish_guide | Publish checklist |
| `cli_props.json` | prepare_render | Remotion props |
| `report.md` | always | Enrichment stats + issues |

**Manifest sidecars**: `*.manifest.json` captures path, hash, input hash, step, date, model. Use to detect stale artifacts — never delete casually.

Config: [config/](config/) (YAML deep-merged, alphabetically layered), env vars in `.env`.

## Key Patterns

- **Provider Factory**: Add `(kind, name, module_path, class_name, register_fn)` tuple to `_auto_register()` `attempts` in [factory.py](src/providers/factory.py). Must implement ABC from [interfaces.py](src/core/interfaces.py). Registration runs on import; missing deps are silently skipped.
- **LLM JSON Retry**: `_call_llm_with_json_retry()` retries on invalid JSON; doubles `max_tokens` on `finish_reason=length`. Cap via `llm.max_completion_tokens_cap`.
- **Two-Model LLM**: Main model for scripts, `fast` model (lower tokens/temp) for translation and comment judging.
- **Prompt Placeholders**: `{{ placeholder }}` tokens must be `PH_*` constants in [prompts.py](src/core/prompts.py). `render_prompt()` raises `ValueError` on typos.
- **Concurrency**: `llm.max_workers` for stories, `analyze.comment_judge_max_workers` for comment judging. Bump `llm.cache_schema_version` when segment-cache semantics change.
- **Dead Code**: Use `vulture` and `ruff --select F`. False positives: auto-registered provider classes.

## Agent Mode

`--agent` enables machine-readable, resumable pipeline execution. Always read JSON state files, never parse human logs. Run preflight before each command.

Full contract: [docs/AGENT_RUNBOOK.md](docs/AGENT_RUNBOOK.md)

**Flags**: `--agent` (structured state), `--resume` (restore from `pipeline_state.json`), `--allow-degraded-enrichment` (continue past enrichment failures), `--refresh-variants` (regenerate script variants), `--force` (clear render cache).

## Tool & Environment Pitfalls

### Windows Paths

Git Bash mounts drives as `/c/`, `/d/` — **not** `C:\`. PowerShell uses `D:\` with `Set-Location`.

### PowerShell Encoding

If Chinese output is garbled: `. .\scripts\encoding.ps1` (sets `PYTHONUTF8=1`, `chcp 65001`).

### Remotion Render Filename

h264+aac requires output ending in `.mp4`/`.mkv`/`.mov`. Use `.partial.mp4`, **never** `.mp4.partial`. See [remotion_renderer.py:285](src/providers/renderer/remotion_renderer.py#L285).

## Behavioral Guidelines

**Tradeoff:** bias toward caution. For trivial tasks, use judgment.

1. **Confirm Before Coding** — Present plan and get approval before writing implementation code. Trivial fixes exempt.
2. **Think Before Coding** — State assumptions. If multiple interpretations, present them. If unclear, ask.
3. **Simplicity First** — Minimum code. No speculative features, no single-use abstractions, no impossible-scenario error handling.
4. **Surgical Changes** — Touch only what you must. Match existing style. Remove only your own orphans. Every changed line must trace to the request.
5. **Goal-Driven Execution** — Define verifiable success criteria. Loop until verified.
6. **Separate Thinking from Coding** — During planning, focus on tradeoffs and approach, not implementation. Don't draft code "just in case."
