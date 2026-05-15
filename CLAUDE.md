# CLAUDE.md

## Project Overview

**HN TechPulse** — Python app that generates Chinese tech news videos from Hacker News content. The product goal is not a generic HN summary: it should feel like a daily technical-community briefing with editorial judgment, topic selection, community disagreement, and a recognizable show format.

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
uv run python -m pytest tests/test_article_enricher.py tests/test_remotion_renderer.py
```

Code quality gate:

```bash
uv run python scripts/quality_check.py              # run all checks
uv run python scripts/quality_check.py --fix         # auto-fix where possible
uv run python scripts/quality_check.py --skip mypy,pip-audit  # skip specific checks
```

Individual tools:

```bash
uv run ruff check src/ tests/                       # lint
uv run ruff format src/ tests/                      # format
uv run vulture src/ --min-confidence 80             # dead code
uv run mypy src/ --ignore-missing-imports           # type check
uv run python -m coverage run -m pytest tests/ -q   # coverage
uv run python -m coverage report                    # coverage report
uv run pip-audit                                    # dependency audit
uv run pre-commit run --all-files                   # pre-commit hooks
```

Script editor:

```bash
uv run streamlit run src/editor/app.py --server.port 8501
```

Remotion dev server:

```bash
cd src/providers/renderer/remotion
npm install
npm run start
npm run still
npm run render
```

## Architecture

- **Core** ([src/core/](src/core/)): ABCs ([interfaces.py](src/core/interfaces.py)) + data models ([src/core/models.py](src/core/models.py)) + [prompts.py](src/core/prompts.py) (placeholder validation)
- **Providers** ([src/providers/](src/providers/)): fetcher, llm, tts, renderer, enricher — auto-register via [factory.py](src/providers/factory.py)
- **Pipeline** ([src/pipeline/](src/pipeline/)): [orchestrator.py](src/pipeline/orchestrator.py) (step execution), [comment_analyzer.py](src/pipeline/comment_analyzer.py) (VADER + quality scoring), [comment_judge.py](src/pipeline/comment_judge.py) (LLM comment judging), [comment_judgement.py](src/pipeline/comment_judgement.py) (judgement data model/normalization), [comment_selection.py](src/pipeline/comment_selection.py) (selection helpers), [script_writer.py](src/pipeline/script_writer.py) (LLM script generation + assembly), [translation_manager.py](src/pipeline/translation_manager.py), [content_preparer.py](src/pipeline/content_preparer.py) (ContentPackage I/O), [timing_engine.py](src/pipeline/timing_engine.py) (timing/timeline computation), [tts_processor.py](src/pipeline/tts_processor.py) (audio synthesis orchestration), [report_generator.py](src/pipeline/report_generator.py) (pipeline report), [script_io.py](src/pipeline/script_io.py) (script I/O), [transcript_generator.py](src/pipeline/transcript_generator.py) (transcript generation)
- **Remotion** ([src/providers/renderer/remotion/](src/providers/renderer/remotion/)): React sub-project, receives script as JSON props via [remotion_props.py](src/providers/renderer/remotion_props.py). Dev preview reads `src/providers/renderer/remotion/public/props.json`.
- **Editor** ([src/editor/](src/editor/)): Streamlit app for manual script editing and image selection.

Pipeline steps: `fetch` → `enrich` → `analyze` → `script` → `translate` → `tts` → `render` (`preview` optional, not in default)

Script structure (daily_brief): **opening** (fixed greeting) → **dashboard** (leaderboard) → **story_scan** (per-story LLM segments) → **closing** (fixed sign-off)

### Data Flow

```
HN API
  ↓
[fetch] ContentPackage with items + all comments
  ↓
[enrich] Article text, images, editor_angle, key_points per item
  ↓
[analyze] Two sub-steps, run by orchestrator._step_analyze():
  ├── CommentAnalyzer.analyze()    — VADER sentiment + heuristic quality_score on every comment
  │     Cached to data/{date}/comment_analysis.json
  └── CommentJudge.judge()         — get_top_comments(n=15) → LLM with prompts/comment_analyze.md
        Produces: quote_candidates, debate_focus, stance_distribution
        Falls back to heuristic_story_judgement() when LLM disabled or errors
        Cached to data/{date}/comment_judgement.json
  ↓
[script] ScriptWriter.write()
  ├── Selection: top N stories by HN score (no LLM)
  ├── Per story: generate_single_story_segment() with prompts/story_script.md
  │     _single_story_to_json() uses judge's quote_candidates to select comments
  │     Falls back to quality-score top-N when no judge data
  │     Judge data embedded as story_json.comment_judgement
  ├── _normalize_quote_card_selection() — replace LLM-picked comment IDs with judge candidates
  └── _normalize_atmosphere_card() — inject debate_focus + stance_distribution from judge
  ↓
[translate] TranslationManager: titles, comments (batched LLM calls with fast model)
  ↓
[tts] TTSProcessor: per-subtitle synthesis, timing alignment
  ↓
[render] Remotion: chunked parallel rendering → output.mp4
```

Key principle: **single source of truth for comment selection**. CommentAnalyzer scores all comments once. CommentJudge selects the top candidates via `get_top_comments()`. Story script consumes the judge's `quote_candidates` — it does not independently re-select comments.

### Prompt Templates

| Template | Used By | Placeholders |
|----------|---------|-------------|
| [prompts/persona.md](prompts/persona.md) | All LLM calls (prepended) | `{{ persona }}` |
| [prompts/story_script.md](prompts/story_script.md) | `generate_single_story_segment` | `{{ story_json }}`, `{{ story_index }}`, `{{ date }}` |
| [prompts/comment_analyze.md](prompts/comment_analyze.md) | `judge_story_comments` (CommentJudge) | `{{ story_json }}` |
| [prompts/translate.md](prompts/translate.md) | `translate_titles`, `translate_comments` | `{{ items_json }}` |
| [prompts/article_enrich.md](prompts/article_enrich.md) | Article enricher | `{{ title }}`, `{{ article_text }}` |

All steps cache to `data/{date}/` and resume from disk. Config: [config/](config/) directory (YAML files deep-merged), env vars in `.env`.

## Current Product State

Recently completed:

- Comment pipeline refactored: CommentAnalyzer scores all → CommentJudge pre-filters via `get_top_comments()` → LLM judges → Story script consumes `quote_candidates` directly. No independent re-selection downstream.
- AtmosphereCard: `debate_focus` and `stance_distribution` now injected from comment judgement rather than re-generated by story script LLM.
- Prompt renames: `comment_judge.md` → `comment_analyze.md`, `single_story_scan.md` → `story_script.md`.
- Global `HN TechPulse` chrome in body segments with date/window label.
- Story chapter indicator (`01/10`) and bottom progress bar story ticks.
- EventCard hierarchy pass: editor angle/title first, HN original title as secondary, key points and why-it-matters modules, keyword limit.
- Article enrichment improvements: minimum image size, candidate ordering, screenshot fallback, Bing query controls.
- AtmosphereCard now foregrounds community mood, compacts stance distribution to top 3 + "其他", and renders controversy as a labeled metric bar.
- QuoteCard now prioritizes Chinese quote text, uses a featured quote plus secondary quotes, places stance labels near authors, and weakens English excerpts.
- Comment selection extracted to [comment_selection.py](src/pipeline/comment_selection.py) with stable keys, quality scoring, quote-heavy penalties, and representative comment selection.
- Pipeline modules extracted: [content_preparer.py](src/pipeline/content_preparer.py), [timing_engine.py](src/pipeline/timing_engine.py), [tts_processor.py](src/pipeline/tts_processor.py), [report_generator.py](src/pipeline/report_generator.py), [script_io.py](src/pipeline/script_io.py), [transcript_generator.py](src/pipeline/transcript_generator.py).
- TS quality gate added: Prettier, ESLint, tsc, Vitest, Knip, audit for Remotion sub-project ([scripts/ts_quality_check.sh](scripts/ts_quality_check.sh)).
- Dead code removed and pre-commit hooks updated (ruff + vulture + TS checks).
- Tests added/expanded for article enrichment, Remotion renderer, TTS providers, comment pipeline, and translation.

Known next priorities are tracked in [ROADMAP.md](ROADMAP.md):

- Standard edition duration target: `240-300s`.
- Standard/full edition output structure.
- EventCard source domain/HN id/score/comment metadata.
- Image quality checks and predictable no-image/screenshot fallback layouts.
- Render-before-quality checks and fixed regression sample set.

## Key Patterns

- **Provider Factory**: Providers auto-register on import via `_auto_register()`. To add a provider: implement ABC + add to `attempts` list.
- **LLM JSON Retry**: `_call_llm_with_json_retry()` retries on invalid JSON and doubles `max_tokens` on `finish_reason=length`.
- **LLM Token Cap**: `llm.max_completion_tokens_cap` bounds auto-expansion when model output is truncated.
- **Segment Cache Version**: `llm.cache_schema_version` should be bumped when segment-cache semantics change.
- **Concurrent Story Generation**: `llm.max_workers` controls concurrent story script generation.
- **Concurrent Comment Judging**: `analyze.comment_judge_max_workers` controls concurrent LLM judge calls.
- **TTS Consistency Check**: Bigram similarity < 0.6 between cached timings and `audio_text` triggers re-synthesis.
- **Two-Model LLM**: Main model for scripts, `fast` model (lower tokens/temp) for translation/summarization and comment judging.
- **Comment Data Flow**: CommentAnalyzer scores all → CommentJudge pre-filters via `get_top_comments()` → LLM judges → ScriptWriter consumes `quote_candidates`. No independent re-selection downstream.
- **Comment Translation Keys**: Use stable keys from story/comment source ids when available. Avoid index-only keys unless no ids exist.
- **Image Selection**: Prefer strong article/page candidates and screenshots before weaker search images; enforce configured minimum dimensions where possible.
- **Remotion Props**: Renderer writes/uses public props for Studio preview. Keep package scripts aligned with composition id `HNTechPulseComposition`.
- **Prompt Placeholders**: `{{ placeholder }}` tokens must be `PH_*` constants in [src/core/prompts.py](src/core/prompts.py). Use `render_prompt()` — typos raise `ValueError`.
- **Dead Code Scan**: Use `vulture` (dead functions/classes/attributes) and `ruff --select F` (unused imports, unused variables, undefined names). Vulture false positives: provider classes auto-registered via factory (`Orchestrator`, `HNFetcher`, `RemotionRenderer`, `EdgeTTSProvider`, `MimoTTSProvider`), Streamlit `session_state` attributes (`dirty`, `active_segment`). Vulture 60% findings need manual review — some are real dead code, some are dynamic dispatch or test-only usage.
- **Quality Gate Script**: [scripts/quality_check.py](scripts/quality_check.py) runs ruff, ruff-format, vulture, mypy, pytest, coverage, pip-audit, pre-commit in one pass. Use `--fix` to auto-fix, `--skip` to skip slow checks. Pre-commit hooks (ruff + vulture + TS checks) installed via `.pre-commit-config.yaml`. TS quality gate: [scripts/ts_quality_check.sh](scripts/ts_quality_check.sh) runs Prettier, ESLint, tsc, Vitest, Knip, audit for the Remotion sub-project.

---

## Tool & Environment Pitfalls

### Windows + Git Bash path conventions

This project runs on Windows with Git Bash (MSYS2). The `Bash` tool uses Git Bash, where drives mount as `/c/`, `/d/` etc. — **not** `C:\` or `D:\`.

| Tool | Correct | Wrong |
|------|---------|-------|
| `Bash` | `cd /d/code/HNTechPulse/...` | `cd d:\code\HNTechPulse\...` |
| `PowerShell` | `Set-Location "D:\code\..." ; cmd` | `cd "D:\..." && cmd` (PS 5.1 lacks `&&`) |

**Rule:** When running cross-directory commands, prefer `Bash` with Unix-style paths. For PowerShell, use `;` instead of `&&` to chain commands.

### Serial agents for shared files

When multiple agents edit the same files (e.g., HighlightShared.tsx), run them **serially** to avoid edit conflicts. Parallel agents are safe only when they touch disjoint file sets.

---

## Behavioral Guidelines

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Confirm Before Coding

**Before writing implementation code, present your plan and confirm with the user.**

- For non-trivial tasks, state what you intend to do and wait for approval.
- List key decisions and assumptions — let the user correct them before code is written.
- If the task is ambiguous, ask clarifying questions first. Do not guess and proceed.
- Trivial, single-line fixes are exempt from this rule.

### 2. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 3. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 4. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 5. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:

- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

````
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
````

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

### 6. Separate Thinking from Coding

**When thinking or planning, do not write code. When writing code, think about code.**

- During planning/analysis phases, focus on problem understanding, tradeoffs, and approach — not implementation details.
- Do not draft code in your head or explore code structure "just in case" during planning.
- Only switch to code-level thinking when you are actually about to write code.
- This keeps plans concise and avoids premature commitment to implementation details.

***

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
