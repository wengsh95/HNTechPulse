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
python main.py --product daily_brief       # Override product type (daily_brief | deep_dive | full)
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

### LLM Pipeline Flow (R1 → R2)
The script generation uses a multi-round LLM strategy:
1. **R1a (Analyze)**: Concurrent analysis of each story to assess quality, extract topics, and identify notable comments. Per-story results are cached in `data/{date}/analyses/story_{idx}.json`.
2. **R1b (Decide)**: Global decision-making to select which stories to feature in deep dives vs quick news. Cached in `data/{date}/selection.json`.
3. **Translate**: Selected titles and comments are translated to Chinese. Cached in `data/{date}/translations.json`.
4. **R2 (Write)**: Generate the complete video script based on selected stories and comments. Cached in `data/{date}/script.json`.

All LLM calls use `<!-- SYSTEM_CUT -->` in prompt templates to split into system + user messages for prompt caching. The OpenAI provider includes a warmup strategy: the first R1a call runs serially to prime the prompt cache before concurrent fan-out.

### Product Types
`--product` (or `pipeline.product` in config.yaml) selects the output format, which controls both the R2 prompt template and the R1b decision prompt:
- `full` (default): comprehensive mode — `prompts/script_gen.md` + `prompts/round1_global_decision.md`
- `daily_brief`: short daily-news video (~90s, ~6 items) — `prompts/daily_brief.md`
- `deep_dive`: single long-form deep dive (~5.5min) — `prompts/deep_dive.md`

Product-specific tuning (durations, item counts, camps) lives under `pipeline.daily_brief` / `pipeline.deep_dive` in [config.yaml](config.yaml).

### Prompts
Templates in [prompts/](prompts/):
- `round1_analyze_story.md` — R1a (per-story analysis, always used)
- `round1_global_decision.md` / `_brief.md` / `_deep_dive.md` — R1b (product-specific)
- `script_gen.md` / `daily_brief.md` / `deep_dive.md` — R2 (product-specific)
- `persona.md` — inserted into any R2 template via the `{{ persona }}` placeholder by [main.py:36-42](main.py#L36-L42). Edit persona.md to change narrator voice/style across all products.
- `translate.md` — translation of selected titles/comments to Chinese
- `article_summarize.md` — LLM summarization of enriched article content

All prompts and narration are Chinese (zh-CN); the default TTS voice is `zh-CN-XiaoxiaoNeural`.

### Pipeline Steps
1. `fetch`: Get stories/comments from Hacker News API
2. `enrich`: Fetch article content from URLs, extract text/images, LLM-summarize (optional, controlled by `enrich.enabled` in config)
3. `script`: Generate video script using LLM (R1a → R1b → translate → R2)
4. `tts`: Synthesize audio from script
5. `preview`: Open Remotion Studio at http://localhost:3000 for visual review (opt-in, not in default `--steps`)
6. `render`: Render final video

### Caching & Resume
Every expensive step resumes from disk, so re-running the pipeline is cheap:
- **fetch**: `data/{date}/raw.json` for full cache; when `hn.granular_cache: true`, per-story comment trees are cached in `data/_comment_cache/{story_id}.json` so interrupted fetches pick up mid-run
- **enrich**: `data/{date}/enrichment.json` checkpoint
- **script**: `data/{date}/script.json` is reused if `script` isn't in `--steps`; within script generation, R1a analyses, R1b selection, and translations are each cached independently
- **tts**: each `segment_XX.mp3` + `segment_XX_timings.json` is reused; if the cached word-timings text diverges from the current `audio_text` by more than a bigram-similarity threshold, the orchestrator auto re-synthesizes ([orchestrator.py:279-323](src/pipeline/orchestrator.py#L279-L323))

### Data Flow

Data is stored in `data/{date}/`:
- `raw.json`: Raw HN API data
- `content.json`: Fetched stories/comments (with translations and enrichment)
- `analyses/story_{idx}.json`: R1a per-story analysis results
- `selection.json`: R1b selection results
- `translations.json`: Translated titles/comments
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
