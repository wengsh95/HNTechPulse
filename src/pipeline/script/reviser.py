"""Apply LLM subtitle revisions back into a composed Script.

The automatic human-review pass (``orchestrator._auto_review_script``) asks the model to
rewrite weak sub-segment narration. This module re-applies those rewrites into
the composed ``story_scan`` segment, keeping the three derived locations in sync:
``meta["sub_segment_subtitle_texts"]``, ``meta["sub_segment_estimated_durations"]``,
and each ``scene_element.props["subtitle_texts"]`` (matched by ``sub_segment_index``).

It deliberately does NOT touch ``card_narrations`` — the composed segment that
persists to ``script.json`` does not carry that field; the persisted source of
truth is ``sub_segment_subtitle_texts``.

The shared read/repair/write-back of the spoken-unit lists lives in
``src.pipeline.script.spoken_units``; this module keeps only the two review
entry points and their differing index conventions.
"""

from src.core.models import Script
from src.pipeline.script.cards import extract_subtitle_texts
from src.pipeline.script.spoken_units import (
    ESTIMATED_DURATIONS_KEY,
    apply_group_texts,
    estimate_duration,
    groups_for,
    invalidate_audio,
    recompute_segment,
)


def collect_script_review_units(script: Script) -> list[dict]:
    """Flatten every spoken section into stable, globally indexed review units."""

    units: list[dict] = []
    for segment_index, segment in enumerate(script.segments):
        groups = groups_for(segment)
        if groups:
            for local_index, texts in enumerate(groups):
                cleaned = extract_subtitle_texts({"subtitle_texts": texts})
                if cleaned:
                    units.append(
                        {
                            "index": len(units),
                            "segment_index": segment_index,
                            "segment_type": segment.segment_type,
                            "local_index": local_index,
                            "element_index": None,
                            "subtitle_texts": cleaned,
                        }
                    )
            continue

        element_units = 0
        for element_index, element in enumerate(segment.scene_elements):
            cleaned = extract_subtitle_texts(
                {"subtitle_texts": element.props.get("subtitle_texts") or []}
            )
            if not cleaned:
                continue
            units.append(
                {
                    "index": len(units),
                    "segment_index": segment_index,
                    "segment_type": segment.segment_type,
                    "local_index": None,
                    "element_index": element_index,
                    "subtitle_texts": cleaned,
                }
            )
            element_units += 1
        if not element_units and segment.audio_text.strip():
            units.append(
                {
                    "index": len(units),
                    "segment_index": segment_index,
                    "segment_type": segment.segment_type,
                    "local_index": None,
                    "element_index": None,
                    "subtitle_texts": [segment.audio_text.strip()],
                }
            )
    return units


def apply_script_review_revisions(
    script: Script, revisions: dict[int, list[str]]
) -> tuple[int, list[str]]:
    """Apply global review-unit revisions across opening, stories, quick news, and closing."""

    units = collect_script_review_units(script)
    by_index = {unit["index"]: unit for unit in units}
    changed_segments: set[int] = set()
    changed_locals: dict[int, set[int]] = {}
    warnings: list[str] = []
    changed = 0

    for index, raw in revisions.items():
        unit = by_index.get(index)
        if unit is None:
            warnings.append(f"index {index} out of range; skipped")
            continue
        cleaned = extract_subtitle_texts({"subtitle_texts": raw})
        if not cleaned:
            warnings.append(f"index {index} revision cleaned to empty; kept original")
            continue
        if cleaned == unit["subtitle_texts"]:
            continue

        segment_index = unit["segment_index"]
        segment = script.segments[segment_index]
        local_index = unit["local_index"]
        element_index = unit["element_index"]
        if local_index is not None:
            if not apply_group_texts(segment, local_index, cleaned):
                warnings.append(f"index {index} local group disappeared; skipped")
                continue
            changed_locals.setdefault(segment_index, set()).add(local_index)
        elif element_index is not None and element_index < len(segment.scene_elements):
            segment.scene_elements[element_index].props["subtitle_texts"] = cleaned
        else:
            segment.audio_text = " ".join(cleaned)

        changed += 1
        changed_segments.add(segment_index)

    for segment_index in changed_segments:
        segment = script.segments[segment_index]
        if groups_for(segment):
            recompute_segment(segment, include_intro=True)
        else:
            element_texts = [
                text
                for element in segment.scene_elements
                for text in extract_subtitle_texts(
                    {"subtitle_texts": element.props.get("subtitle_texts") or []}
                )
            ]
            if element_texts:
                segment.audio_text = " ".join(element_texts)
                segment.duration = estimate_duration(element_texts)

        subtitle_audios = segment.meta.get("subtitle_audios")
        if isinstance(subtitle_audios, list):
            for local_index in changed_locals.get(segment_index, set()):
                if 0 <= local_index < len(subtitle_audios):
                    subtitle_audios[local_index] = None

    return changed, warnings


def apply_subtitle_revisions(
    script: Script, revisions: dict[int, list[str]]
) -> tuple[int, list[str]]:
    """Apply ``{sub_segment_index: [revised subtitle texts]}`` to the script.

    Returns ``(changed_count, warnings)``. Revisions whose index is out of range
    or whose cleaned text is empty are skipped with a warning; the rest update
    the subtitle texts, the estimated duration, and the matching scene element.
    The story_scan segment's ``duration`` and ``audio_text`` are recomputed.

    If the segment already carries ``subtitle_audios`` (i.e. audio was synthesized
    before this review ran), the entries for changed indices are dropped so a
    subsequent ``synthesize_audio`` re-run regenerates them (the TTS cache is keyed
    on the subtitle text hash, so changed elements miss the cache automatically).
    """
    warnings: list[str] = []

    segment = next((s for s in script.segments if s.segment_type == "story_scan"), None)
    if segment is None:
        return 0, ["no story_scan segment found; nothing to revise"]

    groups = groups_for(segment)
    if not groups:
        return 0, ["story_scan segment has no sub_segment_subtitle_texts"]

    # Local parallel durations list; repaired in place, persisted only when a
    # revision actually changes something (matches legacy).
    durations: list[float] = segment.meta.get(ESTIMATED_DURATIONS_KEY) or []
    if len(durations) != len(groups):
        durations = [estimate_duration(texts) for texts in groups]

    changed = 0
    changed_indices: set[int] = set()
    for idx, raw in revisions.items():
        if not isinstance(idx, int) or idx < 0 or idx >= len(groups):
            warnings.append(f"index {idx} out of range; skipped")
            continue
        cleaned = extract_subtitle_texts({"subtitle_texts": raw})
        if not cleaned:
            warnings.append(f"index {idx} revision cleaned to empty; kept original")
            continue
        if cleaned == groups[idx]:
            continue

        matched = apply_group_texts(segment, idx, cleaned)
        if not matched:
            warnings.append(f"index {idx} has no matching scene_element")
        durations[idx] = estimate_duration(cleaned)
        changed += 1
        changed_indices.add(idx)

    if changed == 0:
        return 0, warnings

    # story_scan has no intro: audio_text is the plain join and duration is
    # the sum of the (now updated) estimated durations.
    segment.meta[ESTIMATED_DURATIONS_KEY] = durations
    segment.duration = sum(durations)
    segment.audio_text = " ".join(
        text for texts in groups_for(segment) for text in texts
    )

    # Invalidate stale per-subtitle audio for changed indices so a re-run of
    # synthesize_audio regenerates them. Indexed 1:1 with sub_segment lists.
    cleared = invalidate_audio(segment, sorted(changed_indices))
    if cleared:
        warnings.append(
            "subtitle_audios was present (audio already synthesized); cleared "
            f"{cleared} changed entries — re-run synthesize_audio"
        )

    return changed, warnings
