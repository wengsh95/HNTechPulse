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
uv run pytest                                    # Run tests
uv run pytest tests/test_pipeline.py             # Specific test
uv run pytest -v                                 # Verbose
uv run pytest tests/test_article_enricher.py tests/test_remotion_renderer.py
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

- **Core** ([src/core/](src/core/)): ABCs ([interfaces.py](src/core/interfaces.py)) + data models ([models.py](src/core/models.py))
- **Providers** ([src/providers/](src/providers/)): fetcher, llm, tts, renderer, enricher — auto-register via [factory.py](src/providers/factory.py)
- **Pipeline** ([src/pipeline/](src/pipeline/)): [orchestrator.py](src/pipeline/orchestrator.py) (step execution), [comment_analyzer.py](src/pipeline/comment_analyzer.py), [comment_selection.py](src/pipeline/comment_selection.py), [translation_manager.py](src/pipeline/translation_manager.py), [script_writer.py](src/pipeline/script_writer.py)
- **Remotion** ([src/providers/renderer/remotion/](src/providers/renderer/remotion/)): React sub-project, receives script as JSON props via [remotion_props.py](src/providers/renderer/remotion_props.py). Dev preview reads `src/providers/renderer/remotion/public/props.json`.

Pipeline steps: `fetch` → `enrich` → `translate` → `script` → `tts` → `preview` → `render`

Script structure (daily_brief): **opening** (fixed greeting) → **dashboard** (leaderboard) → **story_scan** (per-story LLM segments) → **closing** (fixed sign-off)

All steps cache to `data/{date}/` and resume from disk. Config: [config.yaml](config.yaml), env vars in `.env`.

## Current Product State

Recently completed:

- Global `HN TechPulse` chrome in body segments with date/window label.
- Story chapter indicator (`01/10`) and bottom progress bar story ticks.
- EventCard hierarchy pass: editor angle/title first, HN original title as secondary, key points and why-it-matters modules, keyword limit.
- Article enrichment improvements: minimum image size, candidate ordering, screenshot fallback, Bing query controls.
- AtmosphereCard now foregrounds community mood, compacts stance distribution to top 3 + "其他", and renders controversy as a labeled metric bar.
- QuoteCard now prioritizes Chinese quote text, uses a featured quote plus secondary quotes, places stance labels near authors, and weakens English excerpts.
- Comment selection extracted to [comment_selection.py](src/pipeline/comment_selection.py) with stable keys, quality scoring, quote-heavy penalties, and representative comment selection.
- Tests added/expanded for article enrichment and Remotion renderer behavior.

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
- **TTS Consistency Check**: Bigram similarity < 0.6 between cached timings and `audio_text` triggers re-synthesis.
- **Two-Model LLM**: Main model for scripts, `fast` model (lower tokens/temp) for translation/summarization.
- **Comment Translation Keys**: Use stable keys from story/comment source ids when available. Avoid index-only keys unless no ids exist.
- **Image Selection**: Prefer strong article/page candidates and screenshots before weaker search images; enforce configured minimum dimensions where possible.
- **Remotion Props**: Renderer writes/uses public props for Studio preview. Keep package scripts aligned with composition id `HNTechPulseComposition`.
- **Prompt Placeholders**: `{{ placeholder }}` tokens must be `PH_*` constants in [src/core/prompts.py](src/core/prompts.py). Use `render_prompt()` — typos raise `ValueError`.

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

***

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
