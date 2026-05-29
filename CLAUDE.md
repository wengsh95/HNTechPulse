# CLAUDE.md

## Project Overview

**HN TechPulse** — Python app that generates a video tech news briefing from Hacker News content, producing a daily digest with editorial judgment.

## Commands

```bash
uv sync                                          # Install deps
uv run python main.py                            # Run pipeline
uv run python main.py --date 2026-04-26 --debug  # With options
uv run python main.py --steps fetch,script       # Run specific steps
uv run python main.py --dry-run                  # Skip API calls
uv run python -m pytest                            # Run tests
uv run python -m pytest tests/test_pipeline.py     # Specific test
uv run python -m pytest -v                         # Verbose
```

Code quality:

```bash
uv run python scripts/quality_check.py              # run all checks (ruff, vulture, mypy, pytest, coverage, pip-audit, pre-commit)
uv run python scripts/quality_check.py --fix         # auto-fix where possible
uv run ruff check src/ tests/                       # lint
uv run ruff format src/ tests/                      # format
uv run vulture src/ --min-confidence 80             # dead code
uv run mypy src/ --ignore-missing-imports           # type check
```

## Architecture

- **Core** ([src/core/](src/core/)): ABCs ([interfaces.py](src/core/interfaces.py)) + data models ([src/core/models.py](src/core/models.py)) + [prompts.py](src/core/prompts.py) (placeholder validation)
- **Providers** ([src/providers/](src/providers/)): fetcher, llm, enricher, renderer (Remotion) — auto-register via [factory.py](src/providers/factory.py)
- **Pipeline** ([src/pipeline/](src/pipeline/)): [orchestrator.py](src/pipeline/orchestrator.py) (step execution), [script_writer.py](src/pipeline/script_writer.py) (LLM script generation), [comment_analyzer.py](src/pipeline/comment_analyzer.py) (VADER + quality scoring), [comment_judge.py](src/pipeline/comment_judge.py) (LLM judging), [comment_judgement.py](src/pipeline/comment_judgement.py) (judge orchestration helpers), [comment_selection.py](src/pipeline/comment_selection.py) (selection helpers), [translation_manager.py](src/pipeline/translation_manager.py), [content_preparer.py](src/pipeline/content_preparer.py), [content_hydrator.py](src/pipeline/content_hydrator.py), [prefilter.py](src/pipeline/prefilter.py), [timing_engine.py](src/pipeline/timing_engine.py), [tts_processor.py](src/pipeline/tts_processor.py), [transcript_generator.py](src/pipeline/transcript_generator.py), [script_io.py](src/pipeline/script_io.py), [report_generator.py](src/pipeline/report_generator.py)
- **Editor** ([src/editor/](src/editor/)): Streamlit-based story editor UI — [app.py](src/editor/app.py) (entry), [state.py](src/editor/state.py) (session state), [components/story_editor.py](src/editor/components/story_editor.py) (UI components). Launched via the `editor` pipeline step.

Pipeline steps: `fetch` → `enrich` → `script` → `produce` → `render` → `preview` → `editor` → `sync_preview`

### Data Flow

```
HN API
  ↓
[fetch] ContentPackage with items + all comments
  ↓
[enrich] Prefilter → comment fetch → article text, images, editor_angle, key_points per item
  ↓
[script] CommentAnalyzer (VADER + quality scores) → CommentJudge (LLM top-15 → quote_candidates, debate_focus, stance_distribution)
  │     Cached to data/{date}/comment_analysis.json + comment_judgement.json
  │     Then ScriptWriter.write():
  ├── Selection: top N stories by HN score (no LLM)
  ├── Three tiers per story (mode: quick / standard / full):
  │     quick → story_script_quick.md → quick_item_card (1 subtitle, ~8s)
  │     standard → story_script_standard.md → story_compact_card (3 subtitles, ~14s)
  │     full → story_script.md → event_card + atmosphere_card
  ├── _normalize_story_cards() injects common metadata (score, comment_count, keywords, etc.) into all card types
  ├── _normalize_quote_card_selection() replaces LLM-picked comment IDs with judge candidates
  └── _normalize_atmosphere_card() injects debate_focus + stance_distribution from judge
  ↓
[produce] TranslationManager (titles, comments via batched LLM fast-model calls) → TTSProcessor (audio synthesis + text alignment)
  ↓
[render] Remotion video render → data/{date}/output.mp4 (skipped by default; opt-in via --steps render)
  ↓
[preview] Remotion live preview for manual review
  ↓
[editor] Streamlit story editor UI for manual script adjustments
  ↓
[sync_preview] Regenerate Remotion preview props after editor changes
  ↓
[always] ReportGenerator: data/{date}/report.md (enrichment stats, timing, issues) — runs unconditionally at pipeline end
```

**Key principle**: CommentAnalyzer scores all comments once → CommentJudge selects top candidates via `get_top_comments()` → ScriptWriter consumes `quote_candidates` directly. No independent re-selection downstream.

### Prompt Templates

| Template | Used By | Placeholders |
|----------|---------|-------------|
| [prompts/persona.md](prompts/persona.md) | All LLM calls (prepended) | `{{ persona }}` |
| [prompts/story_script.md](prompts/story_script.md) | full mode | `{{ story_json }}`, `{{ story_index }}`, `{{ date }}` |
| [prompts/story_script_standard.md](prompts/story_script_standard.md) | standard mode | `{{ story_json }}`, `{{ story_index }}`, `{{ date }}` |
| [prompts/story_script_quick.md](prompts/story_script_quick.md) | quick mode | `{{ story_json }}`, `{{ story_index }}`, `{{ date }}` |
| [prompts/comment_analyze.md](prompts/comment_analyze.md) | CommentJudge | `{{ story_json }}` |
| [prompts/translate.md](prompts/translate.md) | TranslationManager | `{{ items_json }}` |
| [prompts/article_enrich.md](prompts/article_enrich.md) | Article enricher | `{{ title }}`, `{{ article_text }}` |
| [prompts/prefilter.md](prompts/prefilter.md) | Prefilter | `{{ stories_json }}` |

All steps cache to `data/{date}/` and resume from disk. Config: [config/](config/) directory (YAML deep-merged), env vars in `.env`.

## Key Patterns

- **Provider Factory**: Implement ABC + add to `attempts` list. Auto-registers on import.
- **LLM JSON Retry**: `_call_llm_with_json_retry()` retries on invalid JSON; doubles `max_tokens` on `finish_reason=length`. Cap via `llm.max_completion_tokens_cap`.
- **Concurrency**: `llm.max_workers` for story generation, `analyze.comment_judge_max_workers` for comment judging. Cache schema version bump via `llm.cache_schema_version` when segment-cache semantics change.
- **Two-Model LLM**: Main model for scripts, `fast` model (lower tokens/temp) for translation and comment judging.
- **Prompt Placeholders**: `{{ placeholder }}` tokens must be `PH_*` constants in [src/core/prompts.py](src/core/prompts.py). `render_prompt()` raises `ValueError` on typos.
- **Dead Code**: Use `vulture` and `ruff --select F`. False positives: auto-registered provider classes.

---

## Tool & Environment Pitfalls

### Windows + Git Bash

Drives mount as `/c/`, `/d/` etc. — **not** `C:\` or `D:\`. Prefer `Bash` with Unix-style paths.

| Tool | Correct | Wrong |
|------|---------|-------|
| `Bash` | `cd /d/code/HNTechPulse/...` | `cd d:\code\HNTechPulse\...` |
| `PowerShell` | `Set-Location "D:\code\..." ; cmd` | `cd "D:\..." && cmd` |

---

## Behavioral Guidelines

**Tradeoff:** bias toward caution. For trivial tasks, use judgment.

1. **Confirm Before Coding** — Present plan and get approval before writing implementation code. Trivial fixes exempt.
2. **Think Before Coding** — State assumptions. If multiple interpretations, present them. If unclear, ask.
3. **Simplicity First** — Minimum code. No speculative features, no single-use abstractions, no impossible-scenario error handling.
4. **Surgical Changes** — Touch only what you must. Match existing style. Remove only your own orphans. Every changed line must trace to the request.
5. **Goal-Driven Execution** — Define verifiable success criteria. Loop until verified.
6. **Separate Thinking from Coding** — During planning, focus on tradeoffs and approach, not implementation. Don't draft code "just in case."