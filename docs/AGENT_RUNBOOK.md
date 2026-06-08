# Agent Runbook

This project is intended to be operable by coding agents. Prefer the commands
and state files in this document over scraping human-readable logs.

## Standard Flow

Run a preflight first:

```bash
uv run python scripts/agent_preflight.py --date YYYY-MM-DD
```

If preflight returns `status=ok`, run the pipeline in agent mode:

```bash
uv run python main.py --date YYYY-MM-DD --agent
```

If the pipeline blocks or fails, inspect:

```text
data/YYYY-MM-DD/pipeline_state.json
data/YYYY-MM-DD/agent_events.jsonl
data/YYYY-MM-DD/agent_tasks.json
```

After repairing the issue, resume:

```bash
uv run python main.py --date YYYY-MM-DD --resume --agent
```

`--resume` reads `pipeline_state.json` and restores the original step chain.
Earlier steps should hit caches; the blocked or failed point is retried and the
remaining steps continue.

## Agent Mode Flags

```bash
--agent
```

Enables machine-readable state tracking and structured blocking.

```bash
--resume
```

Resumes from `pipeline_state.json`.

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

### `pipeline_state.json`

The primary state contract. Important fields:

```json
{
  "status": "running | complete | degraded | blocked | failed",
  "steps": ["fetch", "prefilter"],
  "current_step": "enrich_articles",
  "completed_steps": ["fetch", "prefilter"],
  "failed_step": "enrich_articles",
  "blocked_reason": "manual_download_required",
  "blocked_items": [],
  "missing_manual_files": [],
  "agent_task_file": "data/YYYY-MM-DD/agent_tasks.json",
  "next_recommended_command": "uv run python main.py --date YYYY-MM-DD --resume --agent",
  "artifacts": {
    "content": "data/YYYY-MM-DD/content.json",
    "script": "data/YYYY-MM-DD/script.json"
  }
}
```

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

Created when the pipeline blocks on article fetching. Example task:

```json
{
  "task_type": "fetch_article",
  "status": "pending",
  "story_id": "123",
  "title": "Story title",
  "url": "https://example.com/article",
  "save_as": {
    "html": "data/YYYY-MM-DD/downloaded_pages/123.html",
    "pdf": "data/YYYY-MM-DD/downloaded_pages/123.pdf"
  }
}
```

Use browser/MCP tools to fetch the URL. Save an HTML page when possible; save a
PDF when the URL is a PDF. Then run `--resume --agent`.

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
   uv run python main.py --date YYYY-MM-DD --resume --agent
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

1. Read `data/YYYY-MM-DD/agent_decision.json`.
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
data/YYYY-MM-DD/content.json.manifest.json
data/YYYY-MM-DD/script.json.manifest.json
data/YYYY-MM-DD/title.json.manifest.json
data/YYYY-MM-DD/cover_props.json.manifest.json
data/YYYY-MM-DD/publish_guide.md.manifest.json
data/YYYY-MM-DD/cli_props.json.manifest.json
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

## Agent Decisions

Agent mode writes:

```text
data/YYYY-MM-DD/agent_decision.json
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

When `config/agent.yaml` has `agent.variants.enabled=true` and `count > 1`,
agent mode generates multiple script candidates during `write_script`.

Current scope:

```text
Multiple script variants are generated.
Each variant gets a scorecard.
The agent selects one automatically.
The selected script is promoted to data/YYYY-MM-DD/script.json.
Downstream steps still run once against the selected script.
```

Variant files:

```text
data/YYYY-MM-DD/variants/index.json
data/YYYY-MM-DD/variants/{variant_id}/variant.json
data/YYYY-MM-DD/variants/{variant_id}/script.json
data/YYYY-MM-DD/variants/{variant_id}/scorecard.json
data/YYYY-MM-DD/variants/selection_brief.md
data/YYYY-MM-DD/selected_variant.json
data/YYYY-MM-DD/agent_variant_decision.json
```

Do not ask the user to choose between variants by default. Read
`agent_variant_decision.json`. If `status=continue`, proceed with the selected
variant. If `status=blocked`, inspect `blocked_reason` and follow the blocked
reason policy.

Current variants do not generate multiple audio tracks, covers, thumbnails, or
videos. TTS and render happen only after the selected script has been promoted.

To force a fresh variant run without refetching facts:

```bash
uv run python main.py --date YYYY-MM-DD --steps write_script --agent --refresh-variants
```

Read `variants/selection_brief.md` for a compact review of the selected variant,
scores, and rejected candidates. This is for audit/tuning, not for routine
manual selection.

## Step Handling Policy

Agent can usually repair or rerun:

```text
fetch
prefilter
fetch_comments
translate_titles
analyze_comments
judge_comments
translate_comments
prepare_render
cover_thumbnail
```

Agent should stop and repair source context:

```text
enrich_articles
write_script when source context is insufficient
```

Agent can generate drafts but should not assume final quality:

```text
synthesize_audio
title
cover_image
publish_guide
render
preview
```

Final video, audio, cover, title, and publication copy may still require human
review.

## Common Recipes

### Start a Date

```bash
uv run python scripts/agent_preflight.py --date YYYY-MM-DD
uv run python main.py --date YYYY-MM-DD --agent
```

### Continue After Article Repair

```bash
uv run python main.py --date YYYY-MM-DD --resume --agent
```

### Force a Degraded Draft

Use only when the user explicitly accepts incomplete source context:

```bash
uv run python main.py --date YYYY-MM-DD --resume --agent --allow-degraded-enrichment
```

### Inspect Agent State

```bash
uv run python scripts/agent_preflight.py --date YYYY-MM-DD
```

The command prints JSON. Prefer this over reading logs when choosing the next
action.
