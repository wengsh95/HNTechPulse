# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**HN TechPulse** is a Python application that generates tech news videos from Hacker News content. It fetches stories/comments, uses LLMs to write video scripts, synthesizes audio via TTS, and renders videos with Remotion (React/TypeScript).

## Commands

### Install Dependencies
```bash
uv sync
```

### Run the Application
```bash
# Full pipeline (uses product from config.yaml, default "daily_brief")
python main.py

# With options
python main.py --date 2026-04-26 --debug
python main.py --steps fetch,script        # Steps to run — see caveat below
python main.py --product daily_brief       # Product type (only "daily_brief" is supported)
python main.py --dry-run                   # Skip API calls
```

Note on `--steps`: steps NOT listed are not re-run, but the orchestrator will still try to *load* their cached outputs from `data/{date}/` ([orchestrator.py:48-65](src/pipeline/orchestrator.py#L48-L65)). If the cache is missing it falls back to running the step anyway. An unrecognized step name (e.g. a typo) is silently ignored.

### Run Tests
```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_pipeline.py

# Run with verbose output
uv run pytest -v

# Run with coverage
uv run pytest --cov=src
```

## Architecture

### Key Layers (src/)

1. **Core** ([src/core/](src/core/))
   - [interfaces.py](src/core/interfaces.py): Abstract base classes for providers (ContentFetcher, LLMProvider, TTSProvider, Renderer)
   - [models.py](src/core/models.py): Data models (ContentPackage, Script, SelectionResult, etc.)

2. **Providers** ([src/providers/](src/providers/))
   - `fetcher/`: Content fetching (Hacker News API with fine-grained caching)
   - `llm/`: Script generation (OpenAI-compatible API with multi-round calls)
   - `tts/`: Audio synthesis (Edge TTS / OpenAI TTS)
   - `renderer/`: Video rendering (Remotion)
   - `enricher/`: Article content enrichment (static fetch, headless fallback, LLM summarization)
   - [factory.py](src/providers/factory.py): Auto-registering provider factory — providers register themselves on import via `_auto_register()`

3. **Pipeline** ([src/pipeline/](src/pipeline/))
   - [orchestrator.py](src/pipeline/orchestrator.py): Main pipeline coordinator, manages step execution
   - [script_writer.py](src/pipeline/script_writer.py): Script generation logic with LLM interaction
   - [content_preparer.py](src/pipeline/content_preparer.py): Content handling and persistence

4. **Utils** ([src/utils/](src/utils/))
   - [config.py](src/utils/config.py): Config loading from YAML + dotenv
   - [logger.py](src/utils/logger.py): Logging setup
   - [audio.py](src/utils/audio.py): Audio processing utilities

### Remotion Renderer ([src/providers/renderer/remotion/](src/providers/renderer/remotion/))
A self-contained React/Remotion sub-project that receives script data as JSON props:
- [types.ts](src/providers/renderer/remotion/src/types.ts): TypeScript types mirroring Python models (SegmentData, SceneElementData, ScriptProps)
- [Root.tsx](src/providers/renderer/remotion/src/Root.tsx): Composition registration with `calculateMetadata` for dynamic duration
- [Components/HNTechPulseComposition.tsx](src/providers/renderer/remotion/src/Components/HNTechPulseComposition.tsx): Main video composition
- [Components/Elements.tsx](src/providers/renderer/remotion/src/Components/Elements.tsx): Visual element components

Python serializes `Script` → JSON props → `public/props.json`, then invokes Remotion CLI. The renderer also copies audio files to `public/audio/` and enriched images to `public/images/`.

### LLM Pipeline Flow (R2)
The script generation is a single-phase LLM strategy:
- **R2 (Per-story segments)**: Each selected story generates its own `story_scan_item` segment via `single_story_scan.md`, producing event summaries, viewpoints, and audio text. The final script is cached in `data/{date}/script.json`. Per-story segments also cache to `data/{date}/segments/`.

Story selection uses simple score ranking: top N stories by HN score are selected.

All LLM calls use `<!-- SYSTEM_CUT -->` in prompt templates to split into system + user messages for prompt caching.

### Product Types
Currently hardcoded to `daily_brief` in [main.py:51](main.py#L51) and [config.yaml:37](config.yaml#L37):
- `daily_brief`: short daily-news video (~120-150s, ~6 items) — uses `prompts/daily_brief.md` (R2 template, currently unused in split mode) + `prompts/single_story_scan.md` (per-story segments)

The `full` and `deep_dive` product types have been removed; their prompts (`script_gen.md`, `deep_dive.md`, `round1_global_decision.md`, `round1_global_decision_deep_dive.md`) were deleted.

### Prompts
Templates in [prompts/](prompts/):
- `single_story_scan.md` — R2 per-story segment generation (daily_brief split mode)
- `daily_brief.md` — R2 template (loaded by main.py, injected with persona)
- `persona.md` — inserted into any R2 template via the `{{ persona }}` placeholder by [main.py:36-42](main.py#L36-L42). Edit persona.md to change narrator voice/style.
- `translate.md` — translation of selected titles/comments to Chinese (currently unused in split mode)
- `article_summarize.md` — LLM summarization of enriched article content

All prompts and narration are Chinese (zh-CN); the default TTS voice is `zh-CN-XiaoxiaoNeural`.

### Pipeline Steps
1. `fetch`: Get stories/comments from Hacker News API
2. `enrich`: Fetch article content from URLs, extract text/images, LLM-summarize (optional, controlled by `enrich.enabled` in config)
3. `translate`: Translate all story titles via the fast/cheap LLM model (optional, not in default `--steps`; checkpointed to `data/{date}/translations.json`)
4. `script`: Generate video script using LLM (R2 per-story segments)
5. `tts`: Synthesize audio from script
6. `preview`: Open Remotion Studio at http://localhost:3000 for visual review (opt-in, not in default `--steps`)
7. `render`: Render final video

### Script Segment Structure (daily_brief)
The generated script always follows this fixed 4-segment structure:
1. **opening**: Fixed greeting ("大家好，我是小P...") with title card — generated by `_generate_fixed_opening()` in [script_writer.py](src/pipeline/script_writer.py)
2. **dashboard**: Top-N leaderboard card with story rankings — generated by `_generate_dashboard_segment()`
3. **story_scan**: Combined segment of all per-story LLM-generated segments. Each story gets its own `story_scan_item` via `generate_single_story_segment()`, then they're merged into one `story_scan` segment with offset-adjusted timestamps
4. **closing**: Fixed sign-off ("多喝热水") — generated by `_generate_fixed_closing()`

### Prompt Placeholder System
All `{{ placeholder }}` tokens in `prompts/*.md` must be declared as `PH_*` constants in [src/core/prompts.py](src/core/prompts.py). Use `render_prompt(template, foo=value)` instead of string `.replace()` — typos in placeholder names raise `ValueError` instead of silently no-oping. To add a new placeholder: (1) add a `PH_FOO = "foo"` constant, (2) add it to `_KNOWN_PLACEHOLDERS`, (3) use `render_prompt(template, foo=value)` at the call site.

### Remotion Setup
The Remotion renderer at [src/providers/renderer/remotion/](src/providers/renderer/remotion/) is a Node.js project. Before first use:
```bash
cd src/providers/renderer/remotion
npm install
```
On Windows, you may need to set `remotion.browser_executable` in [config.yaml](config.yaml) to point to your Chrome/Edge installation path.

### Caching & Resume
Every expensive step resumes from disk, so re-running the pipeline is cheap:
- **fetch**: `data/{date}/raw.json` for full cache; when `hn.granular_cache: true`, per-story comment trees are cached in `data/_comment_cache/{story_id}.json` so interrupted fetches pick up mid-run
- **enrich**: `data/{date}/enrichment.json` checkpoint
- **script**: `data/{date}/script.json` is reused if `script` isn't in `--steps`; per-story segments cache to `data/{date}/segments/`.
- **tts**: each `segment_XX.mp3` + `segment_XX_timings.json` is reused; if the cached word-timings text diverges from the current `audio_text` by more than a bigram-similarity threshold, the orchestrator auto re-synthesizes ([orchestrator.py:279-323](src/pipeline/orchestrator.py#L279-L323))

### Data Flow

Data is stored in `data/{date}/`:
- `raw.json`: Raw HN API data
- `content.json`: Fetched stories/comments (with translations and enrichment)
- `enrichment.json`: Article enrichment checkpoint
- `script.json`: Generated script with timing info
- `audio/segment_XX.mp3`: Synthesized audio files
- `images/`: Downloaded article images
- `transcript.md`: Human-readable markdown transcript
- `output.mp4`: Final rendered video

## Configuration

Main config: [config.yaml](config.yaml)
- LLM settings (provider, model, API endpoint, concurrency)
- TTS settings (voice, rate, pitch)
- Video settings (resolution, FPS, colors)
- Remotion settings (codec, quality, concurrency)
- Pipeline settings (number of stories, comment truncation strategy)
- Enrichment settings (article fetching, image extraction, LLM summarization)

Environment variables: Copy `.env.example` to `.env` and add API keys. The LLM provider uses `OPENAI_API_KEY` and optional `OPENAI_BASE_URL` (for OpenAI-compatible APIs like DeepSeek).
