"""Execution planning for the video pipeline.

Every function here is a pure derivation over the step tables in
``src.workflow.steps``: it decides *which* steps run for a given request,
recovery, or resume, and validates the table invariants.  Handing back the
step list (instead of pushing steps into callers) is what lets the workflow
registry, the orchestrator, the agent scripts, and ``main.py --resume`` share
one source of truth.

``resolve_steps`` mirrors the legacy orchestrator behaviour exactly:
single-level prereq expansion, core-prefix expansion, and human-review
injection.  Do not change those outputs without changing the tests that pin
them.
"""

from __future__ import annotations

from src.workflow.steps import (
    PLANNED_STEPS,
    STEP_SPECS,
    STEP_SPECS_BY_NAME,
    CORE_PIPELINE_STEPS,
    OPTIONAL_PRODUCTION_STEPS,
    VIDEO_STANDALONE_STEPS,
    DOWNSTREAM_REENTRY,
    FAILURE_REENTRY,
    SCRIPT_CONSUMING_STEPS,
    SCRIPT_MUTATING_STEPS,
    HUMAN_REVIEW_PROTECTED_STEPS,
)

__all__ = [
    "resolve_steps",
    "downstream_tail",
    "from_step_tail",
    "fail_recovery_slice",
    "resume_tail",
    "validation_errors",
    "planned_steps",
    "execution_steps",
    "downstream_reentry",
    "failure_reentry",
    "core_pipeline_steps",
    "optional_production_steps",
    "script_consuming_steps",
    "script_mutating_steps",
    "human_review_protected_steps",
]


def planned_steps() -> tuple[str, ...]:
    """The full flattened video chain (render included), in order."""
    return PLANNED_STEPS


def execution_steps() -> tuple[str, ...]:
    """The managed pipeline chain excluding standalone CLI actions."""
    return tuple(step for step in PLANNED_STEPS if step not in VIDEO_STANDALONE_STEPS)


def core_pipeline_steps() -> frozenset[str]:
    return frozenset(CORE_PIPELINE_STEPS)


def optional_production_steps() -> frozenset[str]:
    return OPTIONAL_PRODUCTION_STEPS


def script_consuming_steps() -> frozenset[str]:
    return SCRIPT_CONSUMING_STEPS


def script_mutating_steps() -> frozenset[str]:
    return SCRIPT_MUTATING_STEPS


def human_review_protected_steps() -> frozenset[str]:
    return HUMAN_REVIEW_PROTECTED_STEPS


def resolve_steps(requested: list[str]) -> list[str]:
    """Expand a requested step list to the full execution plan.

    Mirrors the legacy ``orchestrator._resolve_steps``:

    - validates against the known step set
    - expands the core prefix up to the furthest requested core step
    - expands the direct prerequisites of the optional steps
    - injects ``human_review`` ahead of any protected step
    - orders everything by the canonical chain order

    ``synthesize_audio``/``prepare_render`` alone never expand back through
    the editorial chain (a downstream recovery keeps the already-approved
    script).
    """
    all_steps = frozenset(STEP_SPECS_BY_NAME)
    invalid = [s for s in requested if s not in all_steps]
    if invalid:
        raise ValueError(
            "Unknown pipeline step(s): "
            + ", ".join(invalid)
            + ". Use the canonical workflow steps."
        )
    valid = list(requested)
    if not valid:
        return []

    core_requested = [s for s in valid if s in CORE_PIPELINE_STEPS]
    optional_requested = [s for s in valid if s in OPTIONAL_PRODUCTION_STEPS]
    standalone_requested = [s for s in valid if s in VIDEO_STANDALONE_STEPS]

    resolved: list[str] = []
    if core_requested:
        max_idx = max(CORE_PIPELINE_STEPS.index(s) for s in core_requested)
        resolved.extend(CORE_PIPELINE_STEPS[: max_idx + 1])

    # cover_thumbnail needs cover_image even when not explicitly requested.
    if (
        "cover_thumbnail" in optional_requested
        and "cover_image" not in optional_requested
    ):
        optional_requested = ["cover_image", *optional_requested]

    # prepare_render needs audio synthesis, but it is itself a downstream step.
    # An explicit prepare_render/render recovery must not expand back through
    # the editorial chain and overwrite a manually edited script.
    if (
        "prepare_render" in optional_requested
        and "synthesize_audio" not in optional_requested
    ):
        optional_requested = ["synthesize_audio", *optional_requested]

    # Subtitle selection is a local-agent prerequisite for every video-side
    # audio/render recovery. It never expands into the editorial chain.
    if (
        any(
            step in optional_requested
            for step in ("synthesize_audio", "prepare_render")
        )
        and "prepare_subtitles" not in optional_requested
    ):
        optional_requested = ["prepare_subtitles", *optional_requested]

    for step in optional_requested:
        if step not in resolved:
            resolved.append(step)

    for step in standalone_requested:
        if step not in resolved:
            resolved.append(step)

    if (
        HUMAN_REVIEW_PROTECTED_STEPS.intersection(resolved)
        and "human_review" not in resolved
    ):
        resolved.append("human_review")

    # Reorder the final set by the real pipeline order so a video run always
    # synthesizes audio before prepare_render.
    if any(
        step in resolved
        for step in (
            "prepare_subtitles",
            "synthesize_audio",
            "prepare_render",
            "render",
        )
    ):
        ordered = [step for step in PLANNED_STEPS if step in resolved]
    else:
        ordered = [
            step
            for step in PLANNED_STEPS
            if step in resolved and step not in VIDEO_STANDALONE_STEPS
        ]
    ordered.extend(step for step in standalone_requested if step not in ordered)
    return ordered


def downstream_tail(step: str) -> list[str]:
    """Execution tail (chain order) starting at ``step``, no re-anchoring.

    This is the literal chain slice used by the stale-recovery path.  The
    caller (agent_run) re-anchors audio/render entry points via
    ``from_step_tail`` when recovery comes from an explicit ``--from``.
    """
    if step not in PLANNED_STEPS:
        raise ValueError(f"Unknown pipeline step: {step}")
    idx = PLANNED_STEPS.index(step)
    return list(PLANNED_STEPS[idx:])


def from_step_tail(step: str) -> list[str]:
    """Execution tail for an explicit CLI ``--from`` recovery.

    Audio/render entry points re-anchor to ``prepare_subtitles`` (subtitle
    selection is a local-agent prerequisite for every downstream video
    recovery), matching the legacy ``--from`` behaviour.
    """
    if step not in PLANNED_STEPS:
        raise ValueError(f"Unknown pipeline step: {step}")
    anchor = DOWNSTREAM_REENTRY.get(step, step)
    idx = PLANNED_STEPS.index(anchor)
    return list(PLANNED_STEPS[idx:])


def fail_recovery_slice(failed_step: str) -> list[str]:
    """Execution tail after a failed step.

    A failed ``prepare_story_images`` rehydrates quick news (its entry point
    re-anchors to ``draft_quick_news``) before continuing the video tail;
    every other step just resumes from itself.
    """
    if failed_step not in PLANNED_STEPS:
        return list(PLANNED_STEPS)
    anchor = FAILURE_REENTRY.get(failed_step, failed_step)
    idx = PLANNED_STEPS.index(anchor)
    return list(PLANNED_STEPS[idx:])


def resume_tail(resume_step: str, context: list[str] | None = None) -> list[str]:
    """Tail from a resume point, scoped to the given execution context.

    Mirrors ``main.py --resume``: when the resume step appears in ``context``
    the tail is that context sliced from the step onward; otherwise just the
    single step.  ``context`` defaults to the full planned chain.
    """
    if context is None:
        context = list(PLANNED_STEPS)
    if resume_step in context:
        return context[context.index(resume_step) :]
    return [resume_step]


def downstream_reentry() -> dict[str, str]:
    """CLI ``--from`` re-anchoring map (audio/render → prepare_subtitles)."""
    return DOWNSTREAM_REENTRY


def failure_reentry() -> dict[str, str]:
    """Failed-step re-anchoring map (prepare_story_images → draft_quick_news)."""
    return FAILURE_REENTRY


_VALID_PHASES = frozenset(
    {"ingest", "research", "editorial", "human_review", "produce"}
)


def validation_errors() -> list[str]:
    """Table invariants; returns a list of problems (empty when healthy)."""
    from src.workflow.video import VIDEO_WORKFLOW_STEPS

    problems: list[str] = []
    seen_order: dict[int, str] = {}
    for spec in STEP_SPECS:
        if spec.order in seen_order:
            problems.append(
                f"duplicate order {spec.order} ({seen_order[spec.order]}, {spec.name})"
            )
        seen_order[spec.order] = spec.name
        if spec.phase not in _VALID_PHASES:
            problems.append(f"step {spec.name!r} has invalid phase {spec.phase!r}")

    if sorted(spec.order for spec in STEP_SPECS) != list(range(len(STEP_SPECS))):
        problems.append("step orders are not contiguous 0..N-1")

    specs_by_name = {spec.name for spec in STEP_SPECS}
    for spec in STEP_SPECS:
        for prereq in spec.prereqs:
            if prereq not in specs_by_name:
                problems.append(
                    f"step {spec.name!r} references unknown prereq {prereq!r}"
                )

    # Phase membership must agree with the high-level workflow steps.
    expected_phase: dict[str, str] = {}
    for wf_step in VIDEO_WORKFLOW_STEPS:
        for pipeline_step in wf_step.pipeline_steps:
            if (
                pipeline_step in expected_phase
                and expected_phase[pipeline_step] != wf_step.name
            ):
                problems.append(
                    f"step {pipeline_step!r} belongs to both "
                    f"{expected_phase[pipeline_step]!r} and {wf_step.name!r}"
                )
            expected_phase[pipeline_step] = wf_step.name
    for spec in STEP_SPECS:
        if spec.name in expected_phase and spec.phase != expected_phase[spec.name]:
            problems.append(
                f"step {spec.name!r} phase {spec.phase!r} != workflow phase "
                f"{expected_phase[spec.name]!r}"
            )
    return problems
