# CLAUDE.md

## Project Overview

**HN TechPulse** — Python app that generates tech news videos from HN content. Pipeline: fetch stories → LLM script → TTS audio → Remotion video render.

## Commands

```bash
uv sync                                          # Install deps
python main.py                                   # Run pipeline
python main.py --date 2026-04-26 --debug         # With options
python main.py --steps fetch,script              # Run specific steps
python main.py --dry-run                         # Skip API calls
uv run pytest                                    # Run tests
uv run pytest tests/test_pipeline.py             # Specific test
uv run pytest -v                                 # Verbose
```

Remotion dev server:
```bash
cd src/providers/renderer/remotion && npm install && npx remotion studio --port 3000
```

## Architecture

- **Core** ([src/core/](src/core/)): ABCs ([interfaces.py](src/core/interfaces.py)) + data models ([models.py](src/core/models.py))
- **Providers** ([src/providers/](src/providers/)): fetcher, llm, tts, renderer, enricher — auto-register via [factory.py](src/providers/factory.py)
- **Pipeline** ([src/pipeline/](src/pipeline/)): [orchestrator.py](src/pipeline/orchestrator.py) (step execution), [script_writer.py](src/pipeline/script_writer.py) (LLM script gen)
- **Remotion** ([src/providers/renderer/remotion/](src/providers/renderer/remotion/)): React sub-project, receives script as JSON props via [remotion_props.py](src/providers/renderer/remotion_props.py)

Pipeline steps: `fetch` → `enrich` → `translate` → `script` → `tts` → `preview` → `render`

Script structure (daily_brief): **opening** (fixed greeting) → **dashboard** (leaderboard) → **story_scan** (per-story LLM segments) → **closing** (fixed sign-off)

All steps cache to `data/{date}/` and resume from disk. Config: [config.yaml](config.yaml), env vars in `.env`.

## Key Patterns

- **Provider Factory**: Providers auto-register on import via `_auto_register()`. To add a provider: implement ABC + add to `attempts` list.
- **LLM JSON Retry**: `_call_llm_with_json_retry()` retries on invalid JSON and doubles `max_tokens` on `finish_reason=length`.
- **TTS Consistency Check**: Bigram similarity < 0.6 between cached timings and `audio_text` triggers re-synthesis.
- **Two-Model LLM**: Main model for scripts, `fast` model (lower tokens/temp) for translation/summarization.
- **Prompt Placeholders**: `{{ placeholder }}` tokens must be `PH_*` constants in [src/core/prompts.py](src/core/prompts.py). Use `render_prompt()` — typos raise `ValueError`.

---

## Behavioral Guidelines

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

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

### 4. Goal-Driven Execution

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
