# Agent Runbook

This project is intended to be operable by coding agents. Prefer the commands
and state files in this document over scraping human-readable logs.

## Standard Flow

Agents must use the managed wrapper:

```bash
uv run python scripts/internal/agent/agent_run.py --date YYYY-MM-DD
```

`internal/agent/agent_run.py` performs the agent contract in order:

```text
agent_preflight -> agent_status -> choose safe steps -> main.py --agent -> agent_status -> agent_audit
```

For routine operation, the wrapper exposes the five high-level phases directly.
Use `--phase` when an upstream phase is already complete and only one phase
needs to be retried:

```bash
uv run python scripts/internal/agent/agent_run.py --date YYYY-MM-DD --phase ingest
uv run python scripts/internal/agent/agent_run.py --date YYYY-MM-DD --phase research
uv run python scripts/internal/agent/agent_run.py --date YYYY-MM-DD --phase editorial
uv run python scripts/internal/agent/agent_run.py --date YYYY-MM-DD --phase human_review
uv run python scripts/internal/agent/agent_run.py --date YYYY-MM-DD --phase produce
```

`--phase` is an alias for the registered step slice in
`src/workflow/video.py`; it does not create a second execution plan. The native
workflow state machine still enforces phase dependencies, and `--dry-run` can
be used to inspect the expanded command first. Use `--from STEP` for a narrow
artifact recovery that crosses phase boundaries.

The managed product is a narrated video. The managed chain runs the upstream
editorial steps, then continues through TTS and the Remotion renderer:

```text
fetch -> prefilter -> fetch_comments -> enrich_articles -> judge_comments
  -> write_script -> draft_quick_news -> prepare_story_images
  -> title -> cover_image -> cover_thumbnail -> draft_storyboard
  -> human_review -> apply_storyboard
  -> prepare_subtitles -> synthesize_audio -> prepare_render -> render
```

Title translation is performed inside `enrich_articles`, and local comment
scoring/cache hydration is performed by `judge_comments` before its LLM calls.
Automatic script review is prepared inside `human_review` immediately before
the approval page is generated.
The opening line is assembled locally from selected story hooks; the managed
chain no longer spends a separate one-line LLM call for it.
`draft_quick_news` also persists the deterministic `video_structure.json`
normalization in the same tracked step; structure normalization is not a
standalone pipeline step.
After that structure pass, the same tracked step translates the exact
atmosphere-card comments selected for rendering. Comment translation is an
internal operation of the quick-news step.
`prepare_render` also writes the final `publish_guide.md` before producing
`cli_props.json`; guide generation is an internal operation of render
preparation.
The `title` call also returns the three cover-copy angles and the visual image
prompt cached in `publish/title.json`; `cover_image` only sends that prompt to
the image provider, so it does not repeat the editorial LLM call.
Title translation, comment scoring and automatic script review are internal
operations of their owning phase and are not standalone pipeline steps.

The agent-facing workflow has five states:

```text
ingest -> research -> editorial -> human_review -> produce
```

`workflow_video.json` is the only execution state record. Step-level events are
append-only in `agent_events.jsonl`; blocked repair work is described in
`agent_tasks.json`.

Video rendering is provided by Remotion; render recovery commands do not need a
renderer selector.

Successful output:

```text
data/YYYY-MM/YYYY-MM-DD/publish/output.mp4
data/YYYY-MM/YYYY-MM-DD/publish/title.json
data/YYYY-MM/YYYY-MM-DD/publish/publish_guide.md
data/YYYY-MM/YYYY-MM-DD/publish/cover.png
```

Do not call `main.py --agent` directly. `main.py --agent` is guarded and will
reject direct agent calls unless `--direct-agent-run` is passed for manual
debugging. Autonomous agents should not use `--direct-agent-run`.

To inspect state without running the pipeline:

```bash
uv run python scripts/internal/agent/agent_status.py --date YYYY-MM-DD
```

To preview the managed command without mutating state:

```bash
uv run python scripts/internal/agent/agent_run.py --date YYYY-MM-DD --dry-run
```

If the pipeline blocks or fails, inspect JSON files:

```text
data/YYYY-MM/YYYY-MM-DD/agent/workflow_video.json
data/YYYY-MM/YYYY-MM-DD/agent/agent_events.jsonl
data/YYYY-MM/YYYY-MM-DD/agent/agent_tasks.json
```

After repairing the issue, resume:

```bash
uv run python scripts/internal/agent/agent_run.py --date YYYY-MM-DD --resume
```

The managed wrapper resumes from the current native workflow metadata and
does not rerun earlier states unless the selected repair path requires it.

`main.py --resume` also resumes from the failed/current step when used manually
with `--direct-agent-run`; it no longer restores the full original step chain.

For an intentional downstream rerun, use `--from STEP`. It resolves only that
step and its downstream steps. For example, a manually edited video script
should use:

```bash
uv run python scripts/internal/agent/agent_run.py --date YYYY-MM-DD --from synthesize_audio
```

`--steps` remains an explicit step list and does not implicitly run the
editorial chain.

## Agent Mode Flags

```bash
--agent
```

Enables machine-readable state tracking and structured blocking.
In normal agent operation, this flag is supplied by `scripts/internal/agent/agent_run.py`.
Direct `main.py --agent` calls are rejected unless `--direct-agent-run` is also
present for manual debugging.

```bash
--resume
```

On `scripts/internal/agent/agent_run.py`, resumes from the native workflow state after
preflight and status checks. On `main.py`, resumes from the failed/current step
and should only be used with `--direct-agent-run` for manual debugging.

```bash
--direct-agent-run
```

Manual-debug escape hatch for `main.py --agent`. Agents should not use it.

```bash
--allow-degraded-enrichment
```

Allows the pipeline to continue after article enrichment failures. Do not use
this for final publishable output unless the user explicitly accepts degraded
context. Without this flag, agent mode stops on article context gaps.

```bash
--refresh-variants
```

Clears script and variant outputs before `write_script` in agent mode. This
keeps the fact-gathering layer intact while forcing the creative layer to be
regenerated.

## State Files

### `workflow_video.json`

The authoritative five-state workflow contract. It records the status of
`ingest`, `research`, `editorial`, `human_review`, and `produce`, including
dependencies, blocking errors, and the artifacts produced by each state. A
schema or state-model mismatch is reported as corrupt and is not silently
converted.

### `agent_events.jsonl`

Append-only event log for agents. Each line is JSON. Common events:

```text
run_started
step_started
step_completed
step_failed
run_blocked
run_finished
artifact_manifest_written
agent_decision_written
```

Use this to reconstruct what happened without parsing regular logs.

### `agent_tasks.json`

Created when the pipeline blocks on article fetching or image review. Example
article task:

```json
{
  "task_type": "fetch_article",
  "status": "pending",
  "story_id": "123",
  "title": "Story title",
  "url": "https://example.com/article",
  "save_as": {
    "html": "data/YYYY-MM/YYYY-MM-DD/downloaded_pages/123.html",
    "pdf": "data/YYYY-MM/YYYY-MM-DD/downloaded_pages/123.pdf"
  }
}
```

Use browser/MCP tools to fetch the URL. Save an HTML page when possible; save a
PDF when the URL is a PDF. Then run `scripts/internal/agent/agent_run.py --resume`.

For image review, a task has `task_type: "select_image"`, a `candidates` list,
and a `selection_file`. Inspect each candidate's `local_path` with `view_image`,
then set `items[{story_id}].selected_image` to an exact candidate `path` in the
selection file. Mark the selected candidate (or the entry) with
`selection_source: "agent"`, and resume the pipeline.

## Blocked Reasons

### `manual_download_required`

The automatic article fetch failed, but the story has enough discussion context
to justify an agent repair attempt.

Agent action:

1. Read `agent_tasks.json`.
2. Fetch each URL with browser/MCP.
3. Save to the indicated `downloaded_pages/{source_id}.html` or `.pdf`.
4. Run:

   ```bash
   uv run python scripts/internal/agent/agent_run.py --date YYYY-MM-DD --resume
   ```

### `manual_image_selection_required`

The pipeline collected candidate images but intentionally did not make the
semantic choice in agent mode. This prevents a screenshot, logo, or unrelated
Bing result from silently becoming the story visual.

Agent action:

1. Read the `select_image` tasks in `agent_tasks.json`.
2. Inspect every candidate `local_path` with `view_image`.
3. Select the candidate that visibly matches the story. A subject/concept logo
   is acceptable only when no better article image, screenshot, or concept
   image exists.
4. Write the exact candidate `path` to `image_selection.json` and mark it as
   an agent selection.
5. Resume:

   ```bash
   uv run python scripts/internal/agent/agent_run.py --date YYYY-MM-DD --resume
   ```

### `insufficient_story_context`

The article is unavailable and comments are too sparse. Do not continue into
script generation. A title-only story is not enough for a publishable script.

Agent action:

1. Try to gather more source context, such as the original page, related docs,
   repository README, official announcement, or reliable cached page.
2. Save source HTML/PDF where applicable.
3. Resume only after source context exists.
4. If context cannot be found, report the blocker to the user.

### `low_decision_confidence`

The agent decision gate scored the current source context or script below the
configured confidence/readiness threshold.

Agent action:

1. Read `data/YYYY-MM/YYYY-MM-DD/agent_decision.json`.
2. Inspect `scores`, `thresholds`, and `rationale`.
3. Repair the weak input if possible: gather source context, rerun comment
   judgement, or regenerate the script.
4. Resume only after the score-limiting issue has been addressed.

### `source_risk_high`

The available source basis is too risky for automatic continuation. This is
usually caused by too much discussion-only coverage or missing article context.

Agent action:

1. Gather more primary source material.
2. Avoid script generation based only on title-level facts.
3. Resume after source risk is reduced.

### `human_review_required`

The pipeline can produce an artifact, but the decision layer determined that
human review is required before continuing.

Agent action:

1. Summarize the decision file and the risky artifact.
2. Ask the user for review or approval.
3. Do not auto-continue unless the user explicitly grants permission.

### `missing_credentials`

Preflight found a missing environment variable required by the configured
provider.

Agent action:

1. Do not invent or hard-code credentials.
2. Report the missing env var to the user.
3. Resume after the environment is fixed.

### `external_tool_missing`

Preflight found a missing local tool, such as `ffmpeg` or `npx`.

Agent action:

1. If allowed, install or repair the toolchain.
2. If installation requires approval, request it.
3. Rerun preflight.

## Artifact Manifests

Key artifacts get adjacent manifests:

```text
data/YYYY-MM/YYYY-MM-DD/pipeline/content.json.manifest.json
data/YYYY-MM/YYYY-MM-DD/pipeline/script.json.manifest.json
data/YYYY-MM/YYYY-MM-DD/publish/title.json.manifest.json
data/YYYY-MM/YYYY-MM-DD/render/cover_props_v1.json.manifest.json
data/YYYY-MM/YYYY-MM-DD/publish/publish_guide.md.manifest.json
data/YYYY-MM/YYYY-MM-DD/render/cli_props.json.manifest.json
data/YYYY-MM/YYYY-MM-DD/pipeline/audio_manifest.json.manifest.json
```

Manifests include:

```text
artifact path
artifact hash
input hash
step
date
model / fast model / target story count
```

Use manifests to decide whether an artifact was produced from the current
inputs. Do not delete caches or manifests casually; prefer rerunning the
relevant step.

### Editorial script and audio runtime

`pipeline/script.json` is the human-editable editorial copy. Audio paths,
durations, timing, and subtitle cues live in `pipeline/audio_manifest.json` and
are hydrated only when a downstream renderer needs them. The agent records the
current editorial hash in `agent/script_lock.json`.

If the script changes after it was locked, the write-script step stops instead
of silently overwriting the manual edit. Continue from audio with `--from
synthesize_audio`, or pass `--refresh-script` only when regeneration is
intentional.

If `agent/script_lock.json` is missing, the write-script step stops. Continue
from a downstream step or explicitly pass `--refresh-script` to regenerate the
canonical script and lock it again.

## Agent Decisions

Agent mode writes:

```text
data/YYYY-MM/YYYY-MM-DD/agent_decision.json
```

The decision layer runs after source enrichment and after script generation.
It is deliberately separate from ordinary step success: a step can complete but
still be blocked by a low-quality decision.

Important fields:

```json
{
  "gate": "source_context | script_quality",
  "status": "continue | degraded | blocked",
  "confidence": 0.82,
  "blocked_reason": null,
  "scores": {
    "factual_grounding": 0.88,
    "story_coherence": 0.81,
    "comment_usage": 0.77,
    "source_risk": 0.18,
    "publish_readiness": 0.8
  },
  "thresholds": {
    "min_confidence_to_continue": 0.75,
    "min_factual_grounding": 0.8,
    "max_source_risk": 0.3,
    "min_script_publish_readiness": 0.7
  },
  "rationale": "Source context is sufficient for script generation."
}
```

Decision thresholds live in `config/agent.yaml`. Tune these instead of asking
the user to repeatedly choose between intermediate artifacts.

Default policy:

```text
High confidence -> continue automatically.
Low confidence -> blocked with low_decision_confidence.
High source risk -> blocked with source_risk_high.
Insufficient source context -> blocked with insufficient_story_context.
```

Use `--allow-degraded-enrichment` only when the user explicitly accepts a draft
that may have incomplete source context.

## Script Variants

The default configuration uses one canonical script (`enabled=false`,
`count=1`). Variant generation is an explicit experiment or recovery option;
it is not part of the normal daily run.

When `config/agent.yaml` has `agent.variants.enabled=true` and `count > 1`,
agent mode generates multiple script candidates during `write_script`.

Current scope:

```text
Multiple script variants are generated.
Each variant gets a scorecard.
The agent selects one automatically.
The selected script is promoted to data/YYYY-MM/YYYY-MM-DD/script.json.
Downstream steps still run once against the selected script.
```

Variant files:

```text
data/YYYY-MM/YYYY-MM-DD/variants/index.json
data/YYYY-MM/YYYY-MM-DD/variants/{variant_id}/variant.json
data/YYYY-MM/YYYY-MM-DD/variants/{variant_id}/script.json
data/YYYY-MM/YYYY-MM-DD/variants/{variant_id}/scorecard.json
data/YYYY-MM/YYYY-MM-DD/variants/selection_brief.md
data/YYYY-MM/YYYY-MM-DD/agent_variant_decision.json
```

Do not ask the user to choose between variants by default. Read
`agent_variant_decision.json`. If `status=continue`, proceed with the selected
variant. If `status=blocked`, inspect `blocked_reason` and follow the blocked
reason policy.

Current variants do not generate multiple audio tracks, covers, thumbnails, or
videos. TTS and render happen only after the selected script has been promoted.

To force a fresh variant run without refetching facts:

```bash
uv run python scripts/internal/agent/agent_run.py --date YYYY-MM-DD --steps write_script --refresh-variants
```

```bash
uv run python scripts/internal/agent/agent_run.py --date YYYY-MM-DD --refresh-script
```

`--refresh-script` is the explicit opt-in for replacing a changed editorial
script. It should not be used for a normal TTS or render retry.

Read `variants/selection_brief.md` for a compact review of the selected variant,
scores, and rejected candidates. This is for audit/tuning, not for routine
manual selection.

## Step Handling Policy

Agent can usually repair or rerun:

```text
fetch
prefilter
fetch_comments
judge_comments
```

Agent should stop and repair source context:

```text
enrich_articles
```

The rendered video still requires visual review for subtitle overflow, image
crop, factual wording, and pacing.

## Common Recipes

### Start a Date

```bash
uv run python scripts/internal/agent/agent_run.py --date YYYY-MM-DD
```

### Continue After Article Repair

```bash
uv run python scripts/internal/agent/agent_run.py --date YYYY-MM-DD --resume
```

### Force a Degraded Draft

Use only when the user explicitly accepts incomplete source context:

```bash
uv run python scripts/internal/agent/agent_run.py --date YYYY-MM-DD --resume --allow-degraded-enrichment
```

### Inspect Agent State

```bash
uv run python scripts/internal/agent/agent_status.py --date YYYY-MM-DD
```

The command prints JSON. Prefer this over reading logs when choosing the next
action.

### Manual Debugging Only

```bash
uv run python scripts/internal/agent/agent_preflight.py --date YYYY-MM-DD
uv run python main.py --date YYYY-MM-DD --agent --direct-agent-run --steps render
```

Use this only when intentionally bypassing the wrapper during development.
