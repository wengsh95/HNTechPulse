"""Apply an editor-authored storyboard to a generated video script.

The storyboard is deliberately a thin layer over ``script.json``.  It selects
which Remotion shot template renders an existing scene element and may provide
visual props, but it does not create narration or change subtitle/timing data.
That keeps editorial, audio, and visual decisions independently rerunnable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.models import SceneElement, Script
from src.pipeline.paths import pipeline_path


STORYBOARD_SCHEMA_VERSION = 1

# Python mirror of the Remotion catalog.  The renderer is TypeScript, so the
# pipeline must not import it at runtime; keeping the semantic IDs here makes
# storyboard files stable even if component names change later.
TEMPLATE_ID_TO_ELEMENT_TYPE: dict[str, str] = {
    "cover_v1": "cover_card",
    "headline_v1": "headline_card",
    "event_v1": "event_card",
    "source_evidence_v1": "source_evidence_card",
    "discussion_v1": "atmosphere_card",
    "comment_single_v1": "comment_card",
    "comment_dual_v1": "comment_dual_card",
    "data_number_v1": "data_number_card",
    "quick_news_v1": "quick_card",
    "closing_v1": "closing_card",
    "closing_signals_v1": "signals_card",
}

TEMPLATE_REQUIRED_PROPS: dict[str, tuple[str, ...]] = {
    "headline_card": ("title",),
    "source_evidence_card": ("title",),
    "comment_card": ("quote",),
    "comment_dual_card": ("left_summary", "right_summary"),
    "data_number_card": ("value", "label"),
    "quick_card": ("title", "fact"),
    "signals_card": ("items",),
}

VALID_ELEMENT_TYPES = frozenset(
    {
        "cover_card",
        "headline_card",
        "event_card",
        "source_evidence_card",
        "atmosphere_card",
        "comment_card",
        "comment_dual_card",
        "data_number_card",
        "quick_card",
        "closing_card",
        "signals_card",
    }
)

# These are derived by subtitle selection, TTS, and the timing engine.  A
# storyboard is visual-only; allowing them here would make a template switch
# silently invalidate or misalign audio.
PROTECTED_PROPS = frozenset({"subtitle_texts", "audio_duration"})


@dataclass(frozen=True)
class StoryboardApplication:
    """Summary of one storyboard application pass."""

    path: Path
    applied_count: int
    changed_count: int
    shot_ids: tuple[str, ...]


def storyboard_path(date: str) -> Path:
    return pipeline_path(date, "storyboard.json")


def load_storyboard(date: str) -> dict[str, Any] | None:
    """Load and validate the optional per-date storyboard."""

    path = storyboard_path(date)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid storyboard JSON: {path}") from exc
    _validate_storyboard(payload, path)
    storyboard_date = payload.get("date")
    if storyboard_date not in (None, date):
        raise ValueError(
            f"Storyboard date mismatch: expected {date}, got {storyboard_date!r}: {path}"
        )
    return payload


def apply_storyboard(
    script: Script,
    date: str,
    *,
    logger=None,
) -> tuple[Script, StoryboardApplication | None]:
    """Apply the optional storyboard to ``script`` in place.

    No storyboard is a valid no-op.  When present, every shot must resolve to
    exactly one existing scene element.  Failing fast is intentional: a
    silently dropped shot is much harder to catch in a finished video.
    """

    path = storyboard_path(date)
    payload = load_storyboard(date)
    if payload is None:
        if logger:
            logger.info("  No storyboard.json; keeping generated scene templates")
        return script, None

    shots = payload["shots"]
    shot_ids: list[str] = []
    changed_count = 0

    for shot_number, raw_shot in enumerate(shots, start=1):
        shot = raw_shot
        shot_id = str(shot["shot_id"])
        element = _resolve_element(
            script, shot, shot_id=shot_id, shot_number=shot_number
        )
        template_type = _resolve_template_type(shot, shot_id, shot_number)
        visual_props = _visual_props(shot, shot_id, shot_number)

        merged_props = dict(element.props or {})
        merged_props.update(visual_props)
        merged_props["template_id"] = str(shot.get("template_id") or "")
        merged_props["shot_id"] = shot_id
        merged_props["storyboard_schema_version"] = STORYBOARD_SCHEMA_VERSION

        _validate_required_props(template_type, merged_props, shot_id)

        before_type = element.element_type
        before_props = dict(element.props or {})
        element.element_type = template_type
        element.props = merged_props
        shot_ids.append(shot_id)
        if before_type != template_type or before_props != merged_props:
            changed_count += 1

    application = StoryboardApplication(
        path=path,
        applied_count=len(shots),
        changed_count=changed_count,
        shot_ids=tuple(shot_ids),
    )
    if logger:
        logger.info(
            "  Applied %d storyboard shot(s), changed %d scene element(s)",
            application.applied_count,
            application.changed_count,
        )
    return script, application


def _validate_storyboard(payload: Any, path: Path) -> None:
    if not isinstance(payload, dict):
        raise ValueError(f"Storyboard must be a JSON object: {path}")
    if payload.get("schema_version") != STORYBOARD_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported storyboard schema_version={payload.get('schema_version')!r}; "
            f"expected {STORYBOARD_SCHEMA_VERSION}: {path}"
        )
    shots = payload.get("shots")
    if not isinstance(shots, list):
        raise ValueError(f"Storyboard shots must be a list: {path}")

    seen: set[str] = set()
    for index, shot in enumerate(shots, start=1):
        if not isinstance(shot, dict):
            raise ValueError(f"Storyboard shot #{index} must be an object: {path}")
        shot_id = shot.get("shot_id")
        if not isinstance(shot_id, str) or not shot_id.strip():
            raise ValueError(f"Storyboard shot #{index} needs a non-empty shot_id")
        if shot_id in seen:
            raise ValueError(f"Duplicate storyboard shot_id: {shot_id}")
        seen.add(shot_id)

        if not (shot.get("template_id") or shot.get("element_type")):
            raise ValueError(f"Storyboard shot {shot_id} needs template_id")
        props = shot.get("props", {})
        if not isinstance(props, dict):
            raise ValueError(f"Storyboard shot {shot_id}.props must be an object")

        has_direct_target = "segment_index" in shot or "element_index" in shot
        has_story_target = "story_index" in shot
        if not has_direct_target and not has_story_target and "shot_id" not in shot:
            raise ValueError(
                f"Storyboard shot {shot_id} needs segment_index+element_index "
                "or story_index target"
            )
        if has_direct_target and (
            not _is_int(shot.get("segment_index"))
            or not _is_int(shot.get("element_index"))
        ):
            raise ValueError(
                f"Storyboard shot {shot_id} requires integer segment_index and element_index"
            )


def _resolve_template_type(shot: dict[str, Any], shot_id: str, shot_number: int) -> str:
    template_id = shot.get("template_id")
    element_type = shot.get("element_type")

    resolved_from_id = None
    if template_id:
        if not isinstance(template_id, str):
            raise ValueError(f"Storyboard shot {shot_id} template_id must be a string")
        resolved_from_id = TEMPLATE_ID_TO_ELEMENT_TYPE.get(template_id)
        if resolved_from_id is None:
            raise ValueError(
                f"Storyboard shot {shot_id} uses unknown template_id={template_id!r}"
            )

    if element_type:
        if not isinstance(element_type, str) or element_type not in VALID_ELEMENT_TYPES:
            raise ValueError(
                f"Storyboard shot {shot_id} uses unknown element_type={element_type!r}"
            )
        if resolved_from_id and resolved_from_id != element_type:
            raise ValueError(
                f"Storyboard shot {shot_id} template_id and element_type disagree"
            )
        return element_type

    if resolved_from_id:
        return resolved_from_id
    raise ValueError(f"Storyboard shot #{shot_number} needs template_id")


def _visual_props(
    shot: dict[str, Any], shot_id: str, shot_number: int
) -> dict[str, Any]:
    props = shot.get("props") or {}
    protected = sorted(PROTECTED_PROPS.intersection(props))
    if protected:
        raise ValueError(
            f"Storyboard shot {shot_id} attempts to edit derived props "
            f"{protected}; change narration/subtitles in script.json instead"
        )
    return props


def _validate_required_props(
    template_type: str, props: dict[str, Any], shot_id: str
) -> None:
    missing = [
        name
        for name in TEMPLATE_REQUIRED_PROPS.get(template_type, ())
        if name not in props or props[name] in (None, "", [])
    ]
    if missing:
        raise ValueError(
            f"Storyboard shot {shot_id} is missing required props for "
            f"{template_type}: {', '.join(missing)}"
        )


def _resolve_element(
    script: Script,
    shot: dict[str, Any],
    *,
    shot_id: str,
    shot_number: int,
) -> SceneElement:
    # Stable shot IDs make repeated runs idempotent after the element type has
    # already been changed from event_card/atmosphere_card.
    by_id = [
        element
        for segment in script.segments
        for element in segment.scene_elements
        if (element.props or {}).get("shot_id") == shot_id
    ]
    if len(by_id) == 1:
        return by_id[0]
    if len(by_id) > 1:
        raise ValueError(f"Storyboard shot {shot_id} matches multiple existing shots")

    if "segment_index" in shot or "element_index" in shot:
        segment_index = shot.get("segment_index")
        element_index = shot.get("element_index")
        if not _is_int(segment_index) or not _is_int(element_index):
            raise ValueError(
                f"Storyboard shot {shot_id} requires integer segment_index and element_index"
            )
        if not 0 <= segment_index < len(script.segments):
            raise ValueError(
                f"Storyboard shot {shot_id} segment_index out of range: {segment_index}"
            )
        elements = script.segments[segment_index].scene_elements
        if not 0 <= element_index < len(elements):
            raise ValueError(
                f"Storyboard shot {shot_id} element_index out of range: {element_index}"
            )
        return elements[element_index]

    story_index = shot.get("story_index")
    if not _is_int(story_index):
        raise ValueError(f"Storyboard shot {shot_id} needs integer story_index")
    candidates: list[SceneElement] = []
    source_type = shot.get("source_element_type")
    for segment in script.segments:
        for element in segment.scene_elements:
            props = element.props or {}
            if props.get("story_index") != story_index:
                continue
            if source_type and element.element_type != source_type:
                continue
            candidates.append(element)

    source_element_index = shot.get("source_element_index")
    if source_element_index is not None:
        if not _is_int(source_element_index):
            raise ValueError(
                f"Storyboard shot {shot_id} source_element_index must be an integer"
            )
        if not 0 <= source_element_index < len(candidates):
            raise ValueError(
                f"Storyboard shot {shot_id} source_element_index out of range: "
                f"{source_element_index} (matches={len(candidates)})"
            )
        return candidates[source_element_index]

    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ValueError(
            f"Storyboard shot {shot_id} did not match story_index={story_index}"
        )
    raise ValueError(
        f"Storyboard shot {shot_id} is ambiguous: story_index={story_index} "
        "matches multiple elements; add source_element_type and "
        "source_element_index"
    )


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
