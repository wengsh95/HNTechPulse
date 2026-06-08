# Project Structure

HN TechPulse is a Python pipeline, not a web app. The main workflow pulls
Hacker News stories, enriches source context, analyzes comments, generates a
Chinese script, produces audio/title/cover/publish artifacts, and optionally
prepares or runs Remotion rendering.

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
|-- data/{date}/
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
uv run python main.py --steps fetch,write_script
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
|-- cover_prompt.md
|-- opening_closing.md
|-- persona.md
|-- prefilter.md
|-- publish_guide.md
|-- story_script.md
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

## Pipeline Modules

```text
src/pipeline/
|-- orchestrator.py
|-- content_io.py
|-- prefilter.py
|-- translation_manager.py
|-- timing_engine.py
|-- tts_processor.py
|-- transcript_generator.py
|-- agent_io.py
|-- agent_state.py
|-- agent_decision.py
|-- agent_variants.py
|-- comment/
`-- script/
```

Key responsibilities:

- `orchestrator.py`: step execution, prerequisite expansion, agent gates,
  resume behavior, and manifests.
- `content_io.py`: date-scoped content artifact loading/writing.
- `agent_state.py`: `pipeline_state.json` and blocked/failed/complete state.
- `agent_io.py`: JSONL events, state loading, artifact hashes, manifests.
- `agent_decision.py`: source-context and script-quality decision gates.
- `agent_variants.py`: script variants, scorecards, selected variant promotion.

## Script Generation

```text
src/pipeline/script/
|-- composer.py
|-- io.py
|-- cards.py
`-- templates.py
```

`composer.py` generates the script and, in agent mode, can generate multiple
strategies:

- `balanced`
- `discussion`
- `source_grounded`

Agent mode writes variants under `data/{date}/variants/`, selects one, and
promotes the selected output to `data/{date}/script.json`.

## Comment Pipeline

```text
src/pipeline/comment/
|-- scoring.py
|-- selection.py
|-- judge.py
|-- refiner.py
`-- text.py
```

The intended flow is:

```text
CommentAnalyzer -> CommentJudge -> quote_candidates -> ScriptWriter
```

Downstream script generation consumes `quote_candidates` directly. It should
not independently reselect comments.

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

## Remotion Renderer

```text
src/providers/renderer/
|-- remotion_renderer.py
|-- remotion_props.py
|-- cue_builder.py
|-- chunk_planner.py
`-- remotion/
```

The Remotion app lives at:

```text
src/providers/renderer/remotion/
```

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

Most runtime outputs live under:

```text
data/{date}/
```

Common pipeline artifacts:

```text
content.json
script.json
title.json
cover_props.json
publish_guide.md
```

Agent artifacts:

```text
pipeline_state.json
agent_events.jsonl
agent_tasks.json
agent_decision.json
agent_variant_decision.json
selected_variant.json
variants/
```

Variant artifacts:

```text
variants/index.json
variants/selection_brief.md
variants/{variant_id}/script.json
variants/{variant_id}/scorecard.json
```

Artifact manifests are written next to key outputs:

```text
content.json.manifest.json
script.json.manifest.json
title.json.manifest.json
cover_props.json.manifest.json
publish_guide.md.manifest.json
```

The Remotion props manifest lives beside the canonical render props file:

```text
data/YYYY-MM-DD/cli_props.json.manifest.json
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
