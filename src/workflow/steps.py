"""Step descriptors for the video pipeline.

Declaration of every low-level pipeline step, its phase membership, ordering,
and execution flags.  This is the single source of truth for step order and
policy; ``src.workflow.video`` derives the high-level workflow steps and the
flattened chain from it, and ``src.workflow.planner`` resolves execution plans
against it.

Keep this file free of side effects: importing it must not validate or build
anything beyond the tables (``validate()`` lives in ``planner`` and runs at
package import).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StepSpec:
    """Execution-relevant descriptor for one pipeline step.

    ``order`` is the single ordering key for the video chain; ``prereqs`` lists
    the *direct* prerequisites the resolver pulls in (single-level, matching
    the legacy orchestrator expansion).  The boolean flags are the sinking of
    what used to be four hand-maintained policy frozensets in ``orchestrator``.
    """

    name: str
    phase: str
    order: int
    optional: bool = False
    standalone: bool = False
    consumes_script: bool = False
    mutates_script: bool = False
    human_review_protected: bool = False
    prereqs: tuple[str, ...] = ()


# The canonical step table.  ``order`` values are the single source for every
# flattened ordering below; keep them contiguous within the chain.
#
# Flag mapping notes (mirrored from the legacy orchestrator policy sets):
# - ``optional`` == membership in the old OPTIONAL_PRODUCTION_STEPS (editorial
#   + downstream production steps; render/preview were never in it).
# - ``standalone`` == the old VIDEO_STANDALONE_STEPS {render, preview}: CLI-only
#   actions.  render is still part of the flattened chain; preview is not.
# - prereqs encode the single-level expansions: cover_thumbnail pulls
#   cover_image; synthesize_audio pulls prepare_subtitles; prepare_render pulls
#   synthesize_audio and prepare_subtitles.
STEP_SPECS: tuple[StepSpec, ...] = (
    StepSpec("fetch", "ingest", 0),
    StepSpec("prefilter", "ingest", 1),
    StepSpec("fetch_comments", "ingest", 2),
    StepSpec("enrich_articles", "research", 3),
    StepSpec("judge_comments", "research", 4),
    StepSpec(
        "write_script",
        "editorial",
        5,
        optional=True,
        mutates_script=True,
    ),
    StepSpec(
        "draft_quick_news",
        "editorial",
        6,
        optional=True,
        consumes_script=True,
        mutates_script=True,
    ),
    StepSpec(
        "prepare_story_images",
        "editorial",
        7,
        optional=True,
        consumes_script=True,
        mutates_script=True,
    ),
    StepSpec(
        "title",
        "editorial",
        8,
        optional=True,
        consumes_script=True,
        mutates_script=True,
        human_review_protected=True,
    ),
    StepSpec(
        "cover_image",
        "editorial",
        9,
        optional=True,
        consumes_script=True,
        human_review_protected=True,
    ),
    StepSpec(
        "cover_thumbnail",
        "editorial",
        10,
        optional=True,
        consumes_script=True,
        human_review_protected=True,
        prereqs=("cover_image",),
    ),
    StepSpec(
        "human_review",
        "human_review",
        11,
        optional=True,
        consumes_script=True,
        mutates_script=True,
    ),
    StepSpec(
        "draft_storyboard",
        "produce",
        12,
        optional=True,
        consumes_script=True,
        human_review_protected=True,
    ),
    StepSpec(
        "apply_storyboard",
        "produce",
        13,
        optional=True,
        consumes_script=True,
        mutates_script=True,
        human_review_protected=True,
    ),
    StepSpec(
        "prepare_subtitles",
        "produce",
        14,
        optional=True,
        consumes_script=True,
        mutates_script=True,
        human_review_protected=True,
    ),
    StepSpec(
        "synthesize_audio",
        "produce",
        15,
        optional=True,
        consumes_script=True,
        mutates_script=True,
        human_review_protected=True,
        prereqs=("prepare_subtitles",),
    ),
    StepSpec(
        "prepare_render",
        "produce",
        16,
        optional=True,
        consumes_script=True,
        human_review_protected=True,
        prereqs=("synthesize_audio", "prepare_subtitles"),
    ),
    StepSpec(
        "render",
        "produce",
        17,
        standalone=True,
        consumes_script=True,
        human_review_protected=True,
    ),
    StepSpec(
        "preview",
        "produce",
        18,
        standalone=True,
        consumes_script=False,
        human_review_protected=True,
    ),
)

STEP_SPECS_BY_NAME: dict[str, StepSpec] = {spec.name: spec for spec in STEP_SPECS}

# The full flattened video chain: everything up to and including render.
# preview is a renderer-only action never present in the persisted workflow.
PLANNED_STEPS: tuple[str, ...] = tuple(
    spec.name for spec in STEP_SPECS if not spec.standalone or spec.name == "render"
)

# CLI-only actions; render is in the chain but excluded from the execution view.
VIDEO_STANDALONE_STEPS: frozenset[str] = frozenset(
    spec.name for spec in STEP_SPECS if spec.standalone
)

# Core steps (part of the chain, not optional), in chain order.
CORE_PIPELINE_STEPS: tuple[str, ...] = tuple(
    spec.name for spec in STEP_SPECS if not spec.optional and not spec.standalone
)

# Editorial + downstream production steps (the old OPTIONAL_PRODUCTION_STEPS).
OPTIONAL_PRODUCTION_STEPS: frozenset[str] = frozenset(
    spec.name for spec in STEP_SPECS if spec.optional
)

# Steps that need `script` in memory (consume from write_script or disk).
SCRIPT_CONSUMING_STEPS: frozenset[str] = frozenset(
    spec.name for spec in STEP_SPECS if spec.consumes_script
)

# Steps that mutate `script`; trigger transcript save.
SCRIPT_MUTATING_STEPS: frozenset[str] = frozenset(
    spec.name for spec in STEP_SPECS if spec.mutates_script
)

# Any production work after copy review must use the exact script version a
# human approved; the resolver injects ``human_review`` for these.
HUMAN_REVIEW_PROTECTED_STEPS: frozenset[str] = frozenset(
    spec.name for spec in STEP_SPECS if spec.human_review_protected
)

# Recovery re-anchoring.  These mirror the legacy behaviours and are
# intentionally context-specific (they are *not* one combined map):
# - CLI ``--from``: audio/render entry points start from prepare_subtitles
#   (subtitle selection is a local-agent prerequisite for every downstream
#   video recovery).
DOWNSTREAM_REENTRY: dict[str, str] = {
    "synthesize_audio": "prepare_subtitles",
    "prepare_render": "prepare_subtitles",
}

# - Failed-step recovery: a failed prepare_story_images rehydrates quick news
#   before continuing the video tail.
FAILURE_REENTRY: dict[str, str] = {
    "prepare_story_images": "draft_quick_news",
}
