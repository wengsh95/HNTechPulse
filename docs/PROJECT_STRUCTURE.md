# Project Structure

HN TechPulse is a Python pipeline, not a web app. The managed workflow pulls
Hacker News stories, enriches source context, analyzes comments, writes a
narration script, then runs TTS and the configured renderer to produce an MP4
video.

The managed step chain is:

```text
fetch -> prefilter -> fetch_comments -> enrich_articles -> judge_comments ->
write_script -> draft_quick_news -> prepare_story_images ->
title -> cover_image -> cover_thumbnail ->
draft_storyboard -> human_review -> apply_storyboard -> prepare_subtitles ->
synthesize_audio -> prepare_render -> render
```

Enrichment also fills `title_cn`; `judge_comments` first hydrates the local
comment analysis cache before selecting its LLM candidates. Automatic script
review runs while preparing the human-review page. The `title` prompt emits
the three cover-copy angles and visual image prompt into `publish/title.json`;
`cover_image` reuses them and only calls the image provider. The opening
narration is assembled locally from selected story hooks rather than using a
one-line LLM call. `draft_quick_news` also persists the deterministic video
structure normalization and applies the final selected-comment translations;
these are internal operations rather than standalone pipeline steps.
`prepare_render` also writes the final `publish_guide.md` as part of render
packaging.

## Top-Level Layout

```text
.
|-- main.py
|-- config/
|-- prompts/
|-- src/
|-- scripts/
|-- tests/
|-- docs/
|-- data/{month}/{date}/
|-- expressions/
`-- src/providers/renderer/remotion/
```

## Entry Point

```text
main.py
`-- src/pipeline/orchestrator.py
```

`main.py` parses CLI flags and builds the `Orchestrator`. The orchestrator owns
step expansion, cache checks, agent state, decision gates, and artifact
manifest writing.

Important CLI patterns:

```bash
uv run python main.py
uv run python main.py --date YYYY-MM-DD
uv run python main.py --steps render
uv run python scripts/agent_run.py --date YYYY-MM-DD
uv run python scripts/agent_run.py --date YYYY-MM-DD --resume
uv run python scripts/agent_status.py --date YYYY-MM-DD
```

`main.py --agent` is an internal pipeline mode for structured state. Autonomous
agents should enter through `scripts/agent_run.py`, which performs preflight,
artifact-status checks, safe step selection, pipeline execution, and audit.
Manual debugging can bypass the wrapper with `main.py --agent --direct-agent-run`.

## Config

```text
config/
|-- base.yaml
|-- llm.yaml
|-- agent.yaml
|-- enrich.yaml
|-- prefilter.yaml
|-- analyze.yaml
|-- remotion.yaml
`-- tts.yaml
```

Config files are deep-merged at runtime by `src/utils/config.py`.

Agent-specific controls live in `config/agent.yaml`, including:

- script variant strategies
- auto-selection thresholds
- decision weights
- minimum confidence/readiness requirements

When segment-cache semantics change, bump `llm.cache_schema_version`.

## Prompts

```text
prompts/
|-- article_enrich.md
|-- comment_analyze.md
|-- comment_distribution.md
|-- comment_stance_label.md
|-- comment_stance_label_v2.md
|-- image_entities.md
|-- opening_closing.md
|-- persona.md
|-- prefilter.md
|-- publish_guide.md
|-- quick_news.md
|-- script_review.md
|-- story_script.md
|-- storyboard_draft.md
|-- title.md
`-- translate.md
```

Prompt placeholders use `{{ foo }}` syntax. Every placeholder should have a
matching `PH_FOO` constant in `src/core/prompts.py`; `render_prompt()` raises on
unknown placeholders.

## Core Modules

```text
src/core/
|-- interfaces.py
|-- models.py
`-- prompts.py
```

Core modules define shared provider interfaces, data models, and prompt
rendering behavior.

## Workflow Modules

```text
src/workflow/
|-- model.py
|-- machine.py
|-- persistence.py
|-- runtime.py
`-- video.py
```

`video.py` is the single source of truth for the five workflow phases and the
managed pipeline step order. `machine.py` owns phase transitions, blocked and
failed states, while `persistence.py` stores the date-scoped
`workflow_video.json` snapshot. `runtime.py` exposes the execution metadata
used by the orchestrator and status/audit tools.

## Pipeline Modules

```text
src/pipeline/
|-- orchestrator.py
|-- content_io.py
|-- prefilter.py
|-- publish_guide_inputs.py
|-- translation_manager.py
|-- timing_engine.py
|-- tts_processor.py
|-- transcript_generator.py
|-- quick_news.py
|-- video_structure.py
|-- story_images.py
|-- storyboard.py
|-- storyboard_draft.py
|-- storyboard_linter.py
|-- human_review.py
|-- subtitle_planner.py
|-- agent_io.py
|-- agent_decision.py
|-- agent_variants.py
|-- stages/
|-- comment/
`-- script/
```

Key responsibilities:

- `stages/workflow.py`: workflow state-machine lifecycle and tracked-step events.
- `stages/research.py`: fetch, selection lock, prefilter, comments, enrichment,
  and comment judgement stages.
- `stages/script.py`: script generation/variants, selected-comment translation,
  and TTS audio stages.
- `stages/packaging.py`: cover stills and publish-guide packaging.
- `stages/production.py`: renderer props, video render, preview, and renderer
  cache cleanup.

`orchestrator.py` keeps the step order, cross-stage coordination, and shared
runtime wiring; stage mixins own the implementation details for each boundary.

- `orchestrator.py`: step execution, prerequisite expansion, agent gates,
  resume behavior, and manifests.
- `content_io.py`: date-scoped content artifact loading/writing.
- `agent_io.py`: JSONL events, artifact hashes, and manifests.
- `agent_decision.py`: source-context and script-quality decision gates.
- `agent_variants.py`: script variants, scorecards, selected variant promotion.

## Script Generation

```text
src/pipeline/script/
|-- composer.py
|-- io.py
|-- cards.py
|-- markdown_importer.py
`-- templates.py
```

`composer.py` generates the script and, in agent mode, can generate multiple
strategies:

- `balanced`
- `discussion`
- `source_grounded`

Agent mode writes variants under `data/{month}/{date}/pipeline/variants/`, selects one, and
promotes the selected output to `data/{month}/{date}/pipeline/script.json`.

## Comment Pipeline

```text
src/pipeline/comment/
|-- scoring.py
|-- selection.py
|-- judge.py
|-- refiner.py
|-- stance_classifier.py
`-- text.py
```

The intended flow is:

```text
judge_comments (ensures local comment analysis) -> quote_candidates -> write_script
```

Downstream script generation consumes `quote_candidates` directly. It should
not independently reselect comments.

`stance_classifier.py` contains the local CPU classifier used to estimate
`支持 / 质疑 / 中立` distributions over all fetched comments. Training labels
are generated once with the configured LLM via
`scripts/train_comment_stance.py`; local reports are written to
`data/{month}/{date}/stance_distribution.local.json` (a user-side training artifact,
not part of the new bucket layout). See
[Comment Stance Classifier](comment_stance_classifier.md) for the current
findings and training strategy.

## Providers

```text
src/providers/
|-- factory.py
|-- fetcher/
|-- enricher/
|-- llm/
|-- tts/
|-- image_generator/
`-- renderer/
```

Provider factory pattern:

1. Implement the relevant ABC.
2. Add the provider to `_auto_register()` attempts in
   `src/providers/factory.py`.
3. Let registration happen on import.

LLM usage is split between the main model and a faster model. The fast model is
used for lower-cost tasks such as translation and comment judging.

## Renderers

The video renderer is `remotion` (default) or `hyperframes`, selected via the
`--renderer` CLI flag.

```text
src/providers/renderer/
|-- remotion_renderer.py
|-- remotion_props.py
|-- hyperframes_renderer.py
|-- hyperframes_props.py
|-- cue_builder.py
|-- chunk_planner.py
|-- remotion/
`-- hyperframes/
```

The Remotion app lives at:

```text
src/providers/renderer/remotion/
|-- assets/fonts/          # 本地 woff2 字体 (Fraunces / JetBrains Mono /
|                          #   Noto Sans SC / Noto Serif SC) + OFL.txt
|-- src/                   # React/TS 组件、Composition、Root.tsx
`-- public/                # 空（运行时通过 --public-dir 指向
                           #   data/{month}/{date}/render/remotion/public/）
```

字体在 `Root.tsx` 顶层用 `delayRender` + `FontFace` 阻塞加载，避免抓帧时
回退到系统字体导致跨机器字形不一致。`prepare_render` 把 `assets/fonts/*.woff2`
复制到 `data/{month}/{date}/render/remotion/public/fonts/`，由 Remotion CLI 通过
`--public-dir` 暴露给 `staticFile("fonts/...")`。

Important render detail: temporary h264+aac output must use `.partial.mp4`
rather than `.mp4.partial`, because Remotion validates the final filename
suffix.

## Scripts

```text
scripts/
|-- agent_run.py
|-- agent_status.py
|-- agent_preflight.py
|-- agent_audit.py
|-- train_comment_stance.py
|-- quality_check.py
|-- encoding.ps1
`-- _archive/
```

`agent_run.py` is the canonical autonomous entrypoint. It runs preflight and
status checks, follows stale-artifact recovery recommendations, invokes the
pipeline, and runs post-run status/audit checks.

`agent_status.py` emits JSON about current state, stale artifacts, and
`safe_next_commands`. Prefer it over logs when choosing a repair path.

`agent_preflight.py` is still useful for low-level environment checks, but
autonomous pipeline execution should go through `agent_run.py`.

`encoding.ps1` switches the current PowerShell session to UTF-8. Use it before
reading Chinese logs or docs if console output is garbled.

## Tests

```text
tests/
```

Useful focused checks:

```bash
uv run python -m pytest tests/test_agent_decision.py tests/test_orchestrator_steps.py tests/test_pipeline.py
uv run ruff check main.py src/pipeline/ scripts/agent_run.py scripts/agent_status.py scripts/agent_preflight.py tests/test_agent_decision.py tests/test_orchestrator_steps.py
```

Full quality check:

```bash
uv run python scripts/quality_check.py
```

## Date-Scoped Artifacts

Most runtime outputs live under `data/{month}/{date}/`, grouped by lifecycle into
buckets. All path literals go through [src/pipeline/paths.py](../src/pipeline/paths.py).

```text
data/{month}/{date}/
|-- raw/         raw_stories.json, downloaded_pages/
|-- pipeline/    prefilter, enrichment, content, comment_*, script,
|                audio_manifest, segments/, variants/, audio/
|-- media/       images/
|-- render/      remotion/{chunks,public}/, cli_props.json
|-- publish/     output.mp4, title.json, transcript.md, publish_guide.md,
|                cover_bg.png, cover.png
|-- agent/       workflow_video.json,
|                agent_events.jsonl, report.md
`-- outputs/     (organize_outputs.py mirror — unchanged)
```

Common pipeline artifacts:

```text
pipeline/content.json
pipeline/comment_judgement.json
pipeline/script.json
pipeline/audio_manifest.json
publish/output.mp4
publish/title.json
```

Agent artifacts:

```text
agent/workflow_video.json
agent/agent_events.jsonl
agent/agent_tasks.json
agent/agent_decision.json
agent/agent_variant_decision.json
pipeline/variants/
```

Variant artifacts:

```text
pipeline/variants/index.json
pipeline/variants/selection_brief.md
pipeline/variants/{variant_id}/script.json
pipeline/variants/{variant_id}/scorecard.json
```

Artifact manifests are written next to key outputs:

```text
pipeline/content.json.manifest.json
pipeline/script.json.manifest.json
pipeline/audio_manifest.json
publish/title.json.manifest.json
render/cover_props_v1.json.manifest.json
publish/publish_guide.md.manifest.json
```

The Remotion props manifest lives beside the canonical render props file:

```text
data/YYYY-MM/YYYY-MM-DD/render/cli_props.json.manifest.json
```

For human review or handoff, mirror the useful deliverables into a tidy
date-scoped folder without moving the canonical pipeline files:

```bash
uv run python scripts/organize_outputs.py --date YYYY-MM-DD --refresh
```

This creates:

```text
data/{month}/{date}/outputs/
|-- final/     # output.mp4 and selected cover
|-- publish/   # publish guide, transcript, title metadata
|-- script/    # promoted script and agent decisions
|-- render/    # render props and render manifest
|-- sources/   # compact source/context JSON
|-- cover/     # cover background, variants, and props
```

## Agent Blocking Model

Agent mode should continue autonomously when it can repair the problem with
available tools, and should stop only when the next action requires missing
credentials, missing local tools, insufficient source context, high source risk,
or human review.

Structured blocked reasons include:

```text
manual_download_required
missing_credentials
external_tool_missing
insufficient_story_context
low_decision_confidence
source_risk_high
human_review_required
```

See [Agent Runbook](AGENT_RUNBOOK.md) for the exact repair behavior for each
reason.
