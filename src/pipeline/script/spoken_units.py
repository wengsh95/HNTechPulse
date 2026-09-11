"""One place that owns the per-segment spoken-unit lists.

A segment's narration-by-card is persisted in two parallel meta lists:

- ``meta["sub_segment_subtitle_texts"]`` — ``list[list[str]]``, one entry per
  sub-segment holding that sub-segment's subtitle cue strings;
- ``meta["sub_segment_estimated_durations"]`` — ``list[float]``, indexed 1:1.

Each sub-segment corresponds to exactly one ``scene_element`` addressed by its
``sub_segment_index``.  The reviser and the subtitle planner both read and
repair these lists, and the reviser's two review-application paths both rewrite
a group, sync the matching element's props (including the quick_news
title/fact split), recompute durations/audio_text, and invalidate stale
``subtitle_audios`` entries.  Before this module those three write-backs were
re-implemented in both reviser functions (and the duration estimate was inline
in the composer too).

The accessor is deliberately narrow: it owns the list read/repair/sync and the
duration estimate, not every consumer's policy on top of them.
"""

from __future__ import annotations


from src.core.models import ScriptSegment
from src.pipeline.script.composer import SPEECH_CPS

#: meta key for the per-sub-segment subtitle cue groups.
SUBTITLE_TEXTS_KEY = "sub_segment_subtitle_texts"
#: meta key for the per-sub-segment estimated durations.
ESTIMATED_DURATIONS_KEY = "sub_segment_estimated_durations"
#: meta key for the runtime audio records (stripped from script.json on save).
SUBTITLE_AUDIOS_KEY = "subtitle_audios"


def estimate_duration(texts: list[str]) -> float:
    """Estimate narration seconds for a group of cue strings."""
    return sum(max(2.0, len(t) / SPEECH_CPS) for t in texts)


def groups_for(segment: ScriptSegment) -> list[list[str]]:
    """Return the sub-segment subtitle groups (empty list when absent)."""
    return segment.meta.get(SUBTITLE_TEXTS_KEY) or []


def apply_group_texts(segment: ScriptSegment, index: int, cleaned: list[str]) -> bool:
    """Write ``cleaned`` as sub-segment ``index`` across all derived locations.

    Updates the meta groups and the matching scene element's
    ``props["subtitle_texts"]`` (by ``sub_segment_index``), splitting
    quick_news narration into title/fact as the review flow expects.  Returns
    whether an element matched the index (the caller may warn otherwise).
    """
    groups = groups_for(segment)
    if index < 0 or index >= len(groups):
        return False
    groups[index] = cleaned
    segment.meta[SUBTITLE_TEXTS_KEY] = groups

    matched = False
    for element in segment.scene_elements:
        if element.sub_segment_index != index:
            continue
        matched = True
        element.props["subtitle_texts"] = cleaned
        if segment.segment_type == "quick_news":
            if len(cleaned) > 1:
                element.props["title"] = cleaned[0].rstrip("。！？.!?")
                element.props["fact"] = "".join(cleaned[1:])
            else:
                element.props["fact"] = cleaned[0]
    return matched


def recompute_segment(segment: ScriptSegment, *, include_intro: bool = False) -> None:
    """Recompute durations, ``audio_text`` and ``duration`` for a segment.

    ``include_intro`` restores the quick_news form (``"{intro} {body}"`` plus
    the intro's own duration); otherwise the segment is a plain
    ``" ".join`` of every cue with ``duration = sum(durations)``.
    """
    groups = groups_for(segment)
    if not groups:
        return
    durations = [estimate_duration(texts) for texts in groups]
    segment.meta[ESTIMATED_DURATIONS_KEY] = durations
    body = " ".join(text for texts in groups for text in texts)
    if include_intro:
        intro = str(segment.meta.get("intro_text") or "").strip()
        segment.audio_text = f"{intro} {body}".strip()
        segment.duration = sum(durations) + (estimate_duration([intro]) if intro else 0)
    else:
        segment.audio_text = body
        segment.duration = sum(durations)


def invalidate_audio(segment: ScriptSegment, indices: list[int]) -> int:
    """Null the ``subtitle_audios`` entries for changed sub-segments.

    Returns how many entries were cleared.  The runtime audio records are
    indexed 1:1 with the sub-segment lists, so a changed sub-segment's cached
    audio must be dropped for a later synthesize pass to regenerate it.
    """
    subtitle_audios = segment.meta.get(SUBTITLE_AUDIOS_KEY)
    if not isinstance(subtitle_audios, list) or not subtitle_audios:
        return 0
    cleared = 0
    for index in indices:
        if 0 <= index < len(subtitle_audios):
            subtitle_audios[index] = None
            cleared += 1
    return cleared


__all__ = [
    "SUBTITLE_TEXTS_KEY",
    "ESTIMATED_DURATIONS_KEY",
    "SUBTITLE_AUDIOS_KEY",
    "estimate_duration",
    "groups_for",
    "apply_group_texts",
    "recompute_segment",
    "invalidate_audio",
]
