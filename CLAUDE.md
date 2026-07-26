# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**HN TechPulse** — Python CLI pipeline (not a web app) that turns one high-signal Hacker News story into a six-page Xiaohongshu card package. Entry point: [main.py](main.py) → [src/pipeline/orchestrator.py](src/pipeline/orchestrator.py).

## Commands

```bash
uv sync                                                # Install deps
uv run python main.py                                  # Run pipeline (default steps)
uv run python main.py --date 2026-04-26 --debug        # Specific date, debug logging
uv run python main.py --steps render_xhs_cards         # Re-render an existing card plan
uv run python main.py --dry-run                        # Skip API calls
uv run python -m pytest                                # Tests
```

Agent mode - always use the managed wrapper:

```bash
uv run python scripts/agent_run.py --date YYYY-MM-DD                # Preflight + status + safe pipeline run + audit
uv run python scripts/agent_run.py --date YYYY-MM-DD --resume       # Continue after repair
uv run python scripts/agent_status.py --date YYYY-MM-DD             # Inspect machine-readable state/artifacts
uv run python scripts/agent_audit.py --date YYYY-MM-DD              # Final publishability audit
```

Do not call `main.py --agent` directly during autonomous runs. It is guarded and
will reject direct agent calls unless `--direct-agent-run` is passed for manual
debugging.

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

The managed/default chain has nine steps:

```
fetch → prefilter → fetch_comments → enrich_articles → translate_titles
  → analyze_comments → judge_comments → plan_xhs_cards → render_xhs_cards
```

`plan_xhs_cards` selects one story and writes a deterministic six-page JSON
contract. `render_xhs_cards` can be repaired independently without another LLM
call. Old video steps remain available only for manual maintenance of old dates.

### Data Flow

```
HN API → [fetch/prefilter/enrich] ContentPackage + source images
  → [analyze_comments/judge_comments] quote candidates + stance distribution
  → [plan_xhs_cards] one focus story + six-page card contract → xhs_cards.json
  → [render_xhs_cards] Swiss HTML seed + Playwright
  → xhs-01-cover.png … xhs-06-closing.png + _contact-sheet.png
```

**Key principle**: CommentAnalyzer scores → CommentJudge selects exact
`quote_candidates` → the card planner selects comment IDs → the renderer hydrates
the original claims. The LLM never rewrites card quotes.

### Data Layout

Artifacts under `data/{month}/{date}/` are grouped by lifecycle into subdirectories. All
path literals go through [src/pipeline/paths.py](src/pipeline/paths.py) — never
build `f"data/{month}/{date}/foo.json"` strings directly.

```
data/{month}/{date}/
├── raw/         raw_stories.json, downloaded_pages/
├── pipeline/    prefilter, enrichment, content, comment_*; legacy video caches
├── media/       images/
├── render/      legacy video render artifacts
├── publish/     xhs_cards.json, xhs_cards/{index.html,assets/,xhs-*.png,
│                _contact-sheet.png}; legacy video artifacts may also exist
├── agent/       pipeline_state.json, agent_decision.json, agent_tasks.json,
│                agent_events.jsonl, selected_variant.json, report.md
└── outputs/     (organize_outputs.py mirror — unchanged)
```

### Cache Files

Resolved via `src/pipeline/paths.py` helpers — paths in the table below are
relative to `data/{month}/{date}/`.

| File | Step | Contents |
|------|------|----------|
| `pipeline/prefilter.json` | prefilter | LLM tech relevance |
| `pipeline/content.json` | fetch…translate_titles | Canonical ContentPackage |
| `pipeline/comment_analysis.json` | analyze_comments | VADER + quality scores |
| `pipeline/comment_judgement.json` | judge_comments | quote_candidates, debate_focus, stance |
| `publish/xhs_cards.json` | plan_xhs_cards | One-story six-page card contract |
| `publish/xhs_cards/index.html` | render_xhs_cards | Renderable Swiss card source |
| `publish/xhs_cards/xhs-*.png` | render_xhs_cards | Six 1080×1440 cards |
| `publish/xhs_cards/_contact-sheet.png` | render_xhs_cards | 3×2 visual overview |

**Manifest sidecars**: `*.manifest.json` captures path, hash, input hash, step, date, model. Use to detect stale artifacts — never delete casually.

Config: [config/](config/) (YAML deep-merged, alphabetically layered), env vars in `.env`.

## Key Patterns

- **Provider Factory**: Add `(kind, name, module_path, class_name, register_fn)` tuple to `_auto_register()` `attempts` in [factory.py](src/providers/factory.py). Must implement ABC from [interfaces.py](src/core/interfaces.py). Registration runs on import; missing deps are silently skipped.
- **LLM JSON Retry**: `_call_llm_with_json_retry()` retries on invalid JSON; doubles `max_tokens` on `finish_reason=length`. Cap via `llm.max_completion_tokens_cap`.
- **Two-Model LLM**: `fast` model handles title translation, comment judging, and the structured card plan.
- **Prompt Placeholders**: `{{ placeholder }}` tokens must be `PH_*` constants in [prompts.py](src/core/prompts.py). `render_prompt()` raises `ValueError` on typos.
- **Concurrency**: `llm.max_workers` for stories, `analyze.comment_judge_max_workers` for comment judging. Bump `llm.cache_schema_version` when segment-cache semantics change.
- **Dead Code**: Use `vulture` and `ruff --select F`. False positives: auto-registered provider classes.

## Agent Mode

`scripts/agent_run.py` is the canonical entrypoint for machine-readable,
resumable agent execution. It runs preflight, inspects state/artifacts, selects
safe steps, invokes `main.py --agent` with the internal runner environment, then
runs status/audit checks. Always read JSON state files, never parse human logs.

Full contract: [docs/AGENT_RUNBOOK.md](docs/AGENT_RUNBOOK.md)

**Managed flags**: `--resume` (continue from `pipeline_state.json`), `--steps`
(explicit repair path), `--allow-degraded-enrichment` (continue past enrichment
failures only with user approval), and `--dry-run` (show the selected command
without mutating state).

Manual debugging may use `main.py --agent --direct-agent-run`, but autonomous
agents should not use that escape hatch.

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
