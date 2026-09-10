# Domain Context

This project turns Hacker News stories into narrated tech videos.  The
glossary below records domain terms as they crystallize; ADRs in
`docs/adr/` would record decisions worth not re-litigating (none exist yet).

## Workflow terms

- **StepSpec (步骤描述符)**: one declarative descriptor per low-level pipeline
  step (fetch … render/preview).  Declares phase membership, chain order, and
  execution flags (optional, standalone, consumes/mutates script,
  human-review-protected, direct prerequisites).  Lives in
  `src/workflow/steps.py`; it is the single source of truth for step order and
  policy.
- **planner (步骤解析器)**: the pure derivation module (`src/workflow/planner.py`)
  that answers "which steps run" for a request, a recovery, a `--from`, or a
  resume.  One resolver is shared by the workflow registry, the orchestrator,
  the agent scripts, and `main.py --resume`.
- **REVISION_ENTRY_POINTS → DOWNSTREAM_REENTRY / FAILURE_REENTRY (恢复入口点)**: the
  explicit recovery re-anchoring tables.  CLI `--from` re-anchors
  audio/render entry points to `prepare_subtitles`; a failed
  `prepare_story_images` rehydrates `draft_quick_news`.  They are separate on
  purpose: the two recovery paths behaved differently and tests pin that.
- **WorkflowStep (工作流阶段)**: the coarse agent-facing phase (ingest /
  research / editorial / human_review / produce).  Carries machine-facing
  state (deps, produces, consumes); its pipeline_steps are derived from
  StepSpec by phase.

## Pipeline terms

- **judgement (评论判定)**: the comment-analysis result schema produced by the
  judge stage and consumed by editorial, the renderer, and LLM providers.
- **freshness (新鲜度判定)**: the (still-to-be-unified) notion of which
  artifact is stale and which step repairs it; currently the agent scripts and
  pipeline_progress each keep their own copy.  Tracking candidate 2 of the
  architecture review.