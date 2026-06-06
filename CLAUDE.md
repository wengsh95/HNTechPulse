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
uv run python main.py --resume --agent                 # Resume from pipeline_state.json (agent mode)
uv run python main.py --agent                          # Enable machine-readable state + structured blocking
uv run python -m pytest                                # Tests
uv run python -m pytest tests/test_pipeline.py         # Single test file
uv run python -m pytest -v                             # Verbose
```

Agent entry point — always run preflight first, then resume, never re-derive from logs:

```bash
uv run python scripts/agent_preflight.py --date YYYY-MM-DD          # JSON status + next_recommended_command
uv run python main.py --date YYYY-MM-DD --agent                     # First run
uv run python main.py --date YYYY-MM-DD --resume --agent            # Continue after repair
uv run python scripts/agent_audit.py --date YYYY-MM-DD              # Final publishability audit (read-only JSON, exit code 0/1)
```

Code quality:

```bash
uv run python scripts/quality_check.py              # run all checks (ruff, vulture, mypy, pytest, coverage, pip-audit, pre-commit)
uv run python scripts/quality_check.py --fix         # auto-fix where possible
uv run python scripts/quality_check.py --skip mypy,pip-audit   # skip specific checks
uv run ruff check src/ tests/                       # lint
uv run ruff format src/ tests/                      # format
uv run vulture src/ --min-confidence 80             # dead code
uv run mypy src/ --ignore-missing-imports           # type check
```

`pre-commit` hooks run `ruff` and `vulture` only.

Remotion test rendering (单帧渲染调试):

```bash
# 使用 cli_props.json（与 preview 一致的数据源）
cd src/providers/renderer/remotion
npx remotion still --props="E:/Code/HNTechPulse/data/2026-05-30/cli_props.json" --frame=30 --output="E:/Code/HNTechPulse/tmp_frames/test.png"
```

## Architecture

- **Core** ([src/core/](src/core/)): ABCs ([interfaces.py](src/core/interfaces.py)) + data models ([src/core/models.py](src/core/models.py)) + [prompts.py](src/core/prompts.py) (placeholder validation)
- **Providers** ([src/providers/](src/providers/)): `fetcher` (HN), `llm` (OpenAI / MiniMax), `tts` (edge-tts / mimo / MiniMax), `renderer` (Remotion), `image_generator` (MiniMax / noop), `enricher` (article body + images) — auto-register via [factory.py](src/providers/factory.py). Adding a provider = implement an ABC + add a tuple to the `_auto_register()` `attempts` list in [factory.py](src/providers/factory.py).
- **Pipeline** ([src/pipeline/](src/pipeline/)):
  - [orchestrator.py](src/pipeline/orchestrator.py) — declarative step DAG (`PIPELINE_STEPS` + `STANDALONE_STEPS`), step execution, cache resume
  - [pipeline_progress.py](src/pipeline/pipeline_progress.py) — per-step progress display
  - [content_io.py](src/pipeline/content_io.py) — `ContentPreparer` (save/load `ContentPackage` via `dataclasses.asdict`)
  - [comment/](src/pipeline/comment/) — comment analysis subpackage: [text.py](src/pipeline/comment/text.py) (cleaning), [scoring.py](src/pipeline/comment/scoring.py) (quality + relevance), [selection.py](src/pipeline/comment/selection.py) (stance + candidate/quote picking), [judge.py](src/pipeline/comment/judge.py) (`CommentAnalyzer` VADER + `CommentJudge` LLM + normalization + cache I/O), [refiner.py](src/pipeline/comment/refiner.py) (post-LLM quote refinement)
  - [script/](src/pipeline/script/) — script generation subpackage: [composer.py](src/pipeline/script/composer.py) (`ScriptWriter` class), [cards.py](src/pipeline/script/cards.py) (card normalization), [templates.py](src/pipeline/script/templates.py) (opening/closing/highlights), [io.py](src/pipeline/script/io.py) (save/load)
  - [translation_manager.py](src/pipeline/translation_manager.py), [prefilter.py](src/pipeline/prefilter.py), [timing_engine.py](src/pipeline/timing_engine.py), [tts_processor.py](src/pipeline/tts_processor.py), [transcript_generator.py](src/pipeline/transcript_generator.py), [report_generator.py](src/pipeline/report_generator.py)
  - **Agent layer** — [agent_state.py](src/pipeline/agent_state.py) (`pipeline_state.json` schema), [agent_io.py](src/pipeline/agent_io.py) (state load/save + event log), [agent_decision.py](src/pipeline/agent_decision.py) (decision gates, blocked reasons, confidence scoring), [agent_variants.py](src/pipeline/agent_variants.py) (variant A/B hooks). Activated by `--agent`. See [docs/AGENT_RUNBOOK.md](docs/AGENT_RUNBOOK.md) for the operational contract.
- ~~**Editor** ([src/editor/](src/editor/)): Streamlit-based story editor UI — [app.py](src/editor/app.py) (entry), [state.py](src/editor/state.py) (session state), [components/story_editor.py](src/editor/components/story_editor.py) (UI components). Launched via the `editor` pipeline step.~~（2026-06-03 移除 — orphan code, do not extend）

Pipeline steps are split into three groups (see `src/pipeline/orchestrator.py`):

- **Core chain (12)** — `DEFAULT_STEPS`, what `uv run python main.py` actually runs
- **Optional production (3)** — `OPTIONAL_PRODUCTION_STEPS` = `{cover_image, cover_thumbnail, publish_guide}`. Opt-in via `--steps`; the cover/title flow needs both `cover_image` and `cover_thumbnail` (auto-injected if you only request the thumbnail).
- **Standalone (2)** — `STANDALONE_STEPS` = `{render, preview}`. `render` produces `data/{date}/output.mp4`; `preview` opens the Remotion dev server without writing output. Both are always opt-in.

```
fetch → prefilter → fetch_comments → enrich_articles → translate_titles
  → analyze_comments → judge_comments → write_script
  → translate_comments → synthesize_audio → title
  → cover_image → cover_thumbnail → publish_guide → prepare_render
                                                              ↓ (standalone, opt-in)
                                                            render
                                                              ↓ (standalone, opt-in)
                                                            preview
```

Each step has its own cache file/condition and can be re-run in isolation. `--steps X` expands to all steps up to and including X (e.g. `--steps write_script` runs `fetch` … `write_script`).

### Data Flow

```
HN API
  ↓
[fetch] ContentPackage with items
  ↓
[prefilter] Prefilter (LLM tech-relevance filter) → data/{date}/prefilter.json
  ↓
[fetch_comments] HN comments per story → content.json
  ↓
[enrich_articles] ArticleEnricher fetches body + extracts editor_angle, key_points, images → content.json
  ↓
[translate_titles] LLM batch translate item.title → item.title_cn → content.json
  ↓
[analyze_comments] CommentAnalyzer (VADER + quality scores) → data/{date}/comment_analysis.json
  ↓
[judge_comments] CommentJudge (LLM top-15 → quote_candidates, debate_focus, stance_distribution) → data/{date}/comment_judgement.json
  ↓
[write_script] ScriptWriter.write():
  ├── Selection: top N stories by HN score (no LLM)
  ├── Each story uses full mode: story_script.md → event_card + atmosphere_card
  ├── _normalize_story_cards() injects common metadata (score, comment_count, keywords, etc.) into all card types
  ├── _normalize_quote_card_selection() replaces LLM-picked comment IDs with judge candidates
  └── _normalize_atmosphere_card() injects debate_focus + stance_distribution from judge
  → data/{date}/script.json
  ↓
[translate_comments] TranslationManager batch translate comment text (fast_model) → data/{date}/translations.json
  ↓
[synthesize_audio] TTSProcessor (audio synthesis + text alignment) → data/{date}/audio/*
  ↓
[title] LLM generate video title/description/tags → data/{date}/title.json
  ↓
[cover_image] LLM cover_prompt + mmx image generate → data/{date}/cover_bg.png + cover_props.json
  ↓
[cover_thumbnail] Remotion still render with title overlay → data/{date}/cover.png
  ↓
[publish_guide] LLM generate human-facing publish checklist → data/{date}/publish_guide.md
  ↓
[prepare_render] Renderer.write_props() writes props.json + copies audio/image assets to remotion/public/
  ↓
[render] Remotion video render → data/{date}/output.mp4 (skipped by default; opt-in via --steps render)
  ↓
[always] ReportGenerator: data/{date}/report.md (enrichment stats, timing, issues) — runs unconditionally at pipeline end
```

**Key principle**: CommentAnalyzer scores all comments once → CommentJudge selects top candidates via `get_top_comments()` → ScriptWriter consumes `quote_candidates` directly. No independent re-selection downstream.

### Prompt Templates

| Template | Used By | Placeholders |
|----------|---------|-------------|
| [prompts/persona.md](prompts/persona.md) | All LLM calls (prepended) | `{{ persona }}` |
| [prompts/story_script.md](prompts/story_script.md) | story scripts | `{{ story_json }}`, `{{ story_index }}`, `{{ date }}` |
| [prompts/comment_analyze.md](prompts/comment_analyze.md) | CommentJudge | `{{ story_json }}` |
| [prompts/translate.md](prompts/translate.md) | TranslationManager | `{{ items_json }}` |
| [prompts/article_enrich.md](prompts/article_enrich.md) | Article enricher | `{{ title }}`, `{{ article_text }}` |
| [prompts/prefilter.md](prompts/prefilter.md) | Prefilter | `{{ stories_json }}` |
| [prompts/title.md](prompts/title.md) | title step | `{{ highlight_entries }}`, `{{ date }}` |
| [prompts/cover_prompt.md](prompts/cover_prompt.md) | cover_image step | `{{ highlight_entries }}` |
| [prompts/publish_guide.md](prompts/publish_guide.md) | publish_guide step | `{{ items_json }}`, `{{ script_title }}`, `{{ script_description }}`, `{{ date }}` |

All steps cache to `data/{date}/` and resume from disk. Per-step cache files (used to skip re-runs):

| File | Step | Contents |
|------|------|----------|
| `prefilter.json` | prefilter | LLM-judged tech relevance for raw HN items |
| `content.json` | fetch + fetch_comments + enrich_articles + translate_titles | Canonical `ContentPackage` (items, comments, article text, translations) |
| `comment_analysis.json` | analyze_comments | VADER sentiment + quality scores per comment |
| `comment_judgement.json` | judge_comments | `quote_candidates`, `debate_focus`, `stance_distribution` per story |
| `script.json` | write_script | Final `Script` with event/quote/atmosphere cards |
| `translations.json` | translate_comments | Translated comment text keyed by `comment_{story}_{idx}` |
| `audio/` | synthesize_audio | TTS chunks + alignment JSON |
| `title.json` | title | video title / description / tags |
| `cover_bg.png`, `cover_props.json` | cover_image | raw cover image + props for thumbnail step |
| `cover.png` | cover_thumbnail | final cover with title overlay |
| `publish_guide.md` | publish_guide | human-facing publish checklist |
| `cli_props.json` | prepare_render | Remotion props consumed by `render` step |
| `report.md` | always | enrichment stats, timing, issues (generated at end) |

**Manifest sidecars**: each key artifact gets an adjacent `*.manifest.json` capturing path, hash, input hash, step, date, model, target story count. Use manifests to detect stale artifacts — never delete them casually, prefer rerunning the step.

Config: [config/](config/) directory (YAML deep-merged, alphabetically layered: `analyze.yaml`, `base.yaml`, `enrich.yaml`, `llm.yaml`, `prefilter.yaml`, `remotion.yaml`, `tts.yaml`, plus `hn_sentiment_lexicon.yaml`), env vars in `.env`.

## Key Patterns

- **Provider Factory**: Add a `(kind, name, module_path, class_name, register_fn)` tuple to the `attempts` list inside `_auto_register()` in [src/providers/factory.py](src/providers/factory.py). The class must be importable at the dotted path given, with the exact class name specified, and must inherit from the corresponding ABC in [src/core/interfaces.py](src/core/interfaces.py) (`ContentFetcher` / `LLMProvider` / `TTSProvider` / `Renderer` / `ImageGeneratorProvider`). Registration runs on import of `factory.py`; missing deps are logged and the provider is silently skipped (so the app still boots without optional SDKs).
- **LLM JSON Retry**: `_call_llm_with_json_retry()` retries on invalid JSON; doubles `max_tokens` on `finish_reason=length`. Cap via `llm.max_completion_tokens_cap`.
- **Concurrency**: `llm.max_workers` for story generation, `analyze.comment_judge_max_workers` for comment judging. Cache schema version bump via `llm.cache_schema_version` when segment-cache semantics change.
- **Two-Model LLM**: Main model for scripts, `fast` model (lower tokens/temp) for translation and comment judging. Provider names: `openai`, `minimax` (registered in factory). `anthropic_client.py` exists in [src/providers/llm/](src/providers/llm/) as a base client but is not auto-registered — wire it through factory if you need it.
- **Prompt Placeholders**: `{{ placeholder }}` tokens must be `PH_*` constants in [src/core/prompts.py](src/core/prompts.py). `render_prompt()` raises `ValueError` on typos.
- **Dead Code**: Use `vulture` and `ruff --select F`. False positives: auto-registered provider classes; `src/editor/` (orphan after 2026-06-03 removal).

## Agent Mode

`--agent` flips the pipeline into a machine-readable, resumable mode. Coding agents that drive this project should treat it as the default — never parse human logs, always read the JSON state files and run preflight before each command.

**State files** (all under `data/{date}/`):

| File | Writer | Reader | Purpose |
|------|--------|--------|---------|
| `pipeline_state.json` | orchestrator | `main.py --resume` | Status (`running`/`complete`/`degraded`/`blocked`/`failed`), completed/failed/current step, blocked_reason, `next_recommended_command` |
| `agent_events.jsonl` | orchestrator | agents | Append-only event log (`run_started`, `step_started`, `step_completed`, `step_failed`, `run_blocked`, `run_finished`, `agent_decision_written`) |
| `agent_tasks.json` | orchestrator | agents (browser/MCP) | Pending repair tasks (e.g. `fetch_article` with `save_as` paths under `downloaded_pages/`) |
| `agent_decision.json` | agent_decision.py | agents | Decision gate result: gate, status, confidence, scores, thresholds, rationale |
| `agent_variant_decision.json`, `selected_variant.json`, `variants/` | agent_variants.py | agents | Multi-strategy script generation: in agent mode `write_script` may produce `balanced` / `discussion` / `source_grounded` variants under `variants/{variant_id}/`, score them via `scorecard.json`, and promote the chosen one to `script.json` |

**Decision gates** run after source enrichment and after script generation. A step can succeed but still be blocked. Thresholds live in `config/agent.yaml` — tune those, don't ask the user each run. Default policy: high confidence → continue; low confidence → `low_decision_confidence`; high source risk → `source_risk_high`; insufficient context → `insufficient_story_context`.

**Blocked reasons** the agent must handle: `manual_download_required` (fetch URL with browser, save to `downloaded_pages/`, then `--resume --agent`), `insufficient_story_context`, `low_decision_confidence`, `source_risk_high`, `human_review_required` (stop, ask user), `missing_credentials` (stop, report env var), `external_tool_missing` (`ffmpeg`/`npx`).

**Step handling policy**: agent can auto-repair — `fetch`, `prefilter`, `fetch_comments`, `translate_titles`, `analyze_comments`, `judge_comments`, `translate_comments`, `prepare_render`, `cover_thumbnail`. Agent must stop and wait for source repair — `enrich_articles`, `write_script` when context is insufficient. Agent can produce drafts but quality needs human eyes — `synthesize_audio`, `title`, `cover_image`, `publish_guide`, `render`, `preview`.

**Degraded draft** (incomplete source context, still publishable as draft): only with `--allow-degraded-enrichment`. Never use this for final output unless the user explicitly accepts it.

Full contract: [docs/AGENT_RUNBOOK.md](docs/AGENT_RUNBOOK.md). Module map for agents: [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md). Quick agent-start checklist: [AGENTS.md](AGENTS.md).

**Agent mode flags** (all stack with `--date` and `--steps`):

| Flag | Effect |
|------|--------|
| `--agent` | Machine-readable state + structured blocking. |
| `--resume` | Restore original step chain from `pipeline_state.json`; retried step is the `failed_step` / `current_step` / first incomplete entry. |
| `--allow-degraded-enrichment` | In agent mode, continue past article-enrichment failures. Never use this for final output unless the user explicitly accepts degraded context. |
| `--refresh-variants` | Clear script and variant caches before `write_script` in agent mode. Keeps fact-gathering, regenerates the creative layer. |
| `--force` | Force re-render (clear render cache). |

### Available Tools

| Tool | Description |
|------|-------------|
| `mmx vision describe` | Image understanding — supports local files, URLs, file IDs |
| `mmx search query` | Built-in web search |
| `mmx image generate` | AI image generation (supports `--prompt`, `--aspect-ratio`, `--out`) |

### Cover & Title Generation

**标题思路**：基于每日内容的争议点生成，不要强行归纳。标题应直接点出当天最吸引人的矛盾或反差。

风格参考：
- 争议点切入：「免费的最贵：开源要你千万营收，打扫要你隐私，代码要你忽略错误」
- 反差感：「号称开源，但许可证限制营收千万的公司」
- 简洁有力：一句话概括 2-3 个故事的核心冲突

**封面思路**：参考《经济学人》《纽约时报》风格——大插图 + 粗标题 + 干净排版。

- 用第一个帖子的内容调 `mmx image generate` 生成卡通/插画风格新闻图
- 封面 = AI 生成的插图 + 标题文字叠加
- 生成命令：`mmx image generate --prompt "<基于第一帖内容的英文prompt>" --aspect-ratio 16:9 --out data/{date}/cover.png`
- **禁止**在 prompt 中引用品牌名称（如 The Economist、NYT 等），否则会生成带 logo 的侵权图片

**封面 prompt 模板**（提炼自主流新闻刊物的视觉语言，不引用品牌）：

核心风格描述：
```
editorial illustration in bold flat style, strong central visual metaphor,
limited warm color palette (amber, burnt orange, deep teal), clean composition
with minimal clutter, satirical or conceptual tone, solid textured background,
simple bold shapes with strong silhouettes, scale contrast (tiny vs huge),
hand-drawn feel with clean edges, modern magazine cover aesthetic
```

完整 prompt 结构：
```
A {风格描述} about {帖子核心概念的视觉化比喻}. {具体场景描述}.
No logos, no text, no watermarks, no brand references.
```

**封面文字叠加**：AI 生图不可靠生成文字，必须分两步：
1. mmx 生成纯插画（prompt 中加 `No text`）
2. Remotion 渲染封面帧 — 新建 `CoverThumbnail` 组件，背景为生成的插画，上层叠加标题文字
   - 复用现有 design system（`useDesign()`、`COLORS`、`FONTS`）
   - 标题文字粗体大字号，白色 + 半透明黑色底条保证可读性
   - 用 `npx remotion still` 渲染单帧静态图：
     ```bash
     cd src/providers/renderer/remotion
     npx remotion still CoverThumbnail --props="data/{date}/cover_props.json" --frame=0 --output="data/{date}/cover.png"
     ```
    - `cover_props.json` 格式：`{"backgroundImage": "cover.png", "title": "...", "subtitle": "...", "dateLabel": "..."}`
    - 背景图需先放到 `src/providers/renderer/remotion/public/` 目录

---

## Tool & Environment Pitfalls

### Windows + Git Bash

Drives mount as `/c/`, `/d/` etc. — **not** `C:\` or `D:\`. Prefer `Bash` with Unix-style paths.

| Tool | Correct | Wrong |
|------|---------|-------|
| `Bash` | `cd /d/code/HNTechPulse/...` | `cd d:\code\HNTechPulse\...` |
| `PowerShell` | `Set-Location "D:\code\..." ; cmd` | `cd "D:\..." && cmd` |

### PowerShell encoding

If Chinese output is garbled in PowerShell, run once per session:

```powershell
. .\scripts\encoding.ps1
```

Sets `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`, and `chcp 65001`. Project files are UTF-8; `.editorconfig` + `.gitattributes` keep editors and Git consistent.

### Remotion render temp filename

Remotion's h264+aac validator strictly requires the output filename to end in `.mp4` / `.mkv` / `.mov`. Use `.partial.mp4` (mid-suffix), **never** `.mp4.partial` (post-suffix) — the latter is rejected with `TypeError: When using the h264 codec with the aac audio codec, the output filename must end in one of the following: mp4, mkv, mov.` Implementation: [src/providers/renderer/remotion_renderer.py:285](src/providers/renderer/remotion_renderer.py#L285).

---

## Behavioral Guidelines

**Tradeoff:** bias toward caution. For trivial tasks, use judgment.

1. **Confirm Before Coding** — Present plan and get approval before writing implementation code. Trivial fixes exempt.
2. **Think Before Coding** — State assumptions. If multiple interpretations, present them. If unclear, ask.
3. **Simplicity First** — Minimum code. No speculative features, no single-use abstractions, no impossible-scenario error handling.
4. **Surgical Changes** — Touch only what you must. Match existing style. Remove only your own orphans. Every changed line must trace to the request.
5. **Goal-Driven Execution** — Define verifiable success criteria. Loop until verified.
6. **Separate Thinking from Coding** — During planning, focus on tradeoffs and approach, not implementation. Don't draft code "just in case."