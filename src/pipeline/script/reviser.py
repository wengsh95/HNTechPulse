"""Apply LLM subtitle revisions back into a composed Script.

The automatic human-review pass (``orchestrator._auto_review_script``) asks the model to
rewrite weak sub-segment narration. This module re-applies those rewrites into
the composed ``story_scan`` segment, keeping the three derived locations in sync:
``meta["sub_segment_subtitle_texts"]``, ``meta["sub_segment_estimated_durations"]``,
and each ``scene_element.props["subtitle_texts"]`` (matched by ``sub_segment_index``).

It deliberately does NOT touch ``card_narrations`` — the composed segment that
persists to ``script.json`` does not carry that field; the persisted source of
truth is ``sub_segment_subtitle_texts``.
"""

from src.core.models import Script
from src.pipeline.script.cards import extract_subtitle_texts
from src.pipeline.script.composer import SPEECH_CPS


def _estimate_duration(texts: list[str]) -> float:
    return sum(max(2.0, len(t) / SPEECH_CPS) for t in texts)


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

    sub_texts: list[list[str]] = segment.meta.get("sub_segment_subtitle_texts") or []
    durations: list[float] = segment.meta.get("sub_segment_estimated_durations") or []
    if not sub_texts:
        return 0, ["story_scan segment has no sub_segment_subtitle_texts"]

    # Ensure durations list is parallel to sub_texts.
    if len(durations) != len(sub_texts):
        durations = [_estimate_duration(t) for t in sub_texts]

    elem_by_index = {
        elem.sub_segment_index: elem
        for elem in segment.scene_elements
        if elem.sub_segment_index is not None
    }

    changed = 0
    changed_indices: set[int] = set()
    for idx, raw in revisions.items():
        if not isinstance(idx, int) or idx < 0 or idx >= len(sub_texts):
            warnings.append(f"index {idx} out of range; skipped")
            continue
        cleaned = extract_subtitle_texts({"subtitle_texts": raw})
        if not cleaned:
            warnings.append(f"index {idx} revision cleaned to empty; kept original")
            continue
        if cleaned == sub_texts[idx]:
            continue

        sub_texts[idx] = cleaned
        durations[idx] = _estimate_duration(cleaned)
        elem = elem_by_index.get(idx)
        if elem is not None:
            elem.props["subtitle_texts"] = cleaned
        else:
            warnings.append(f"index {idx} has no matching scene_element")
        changed += 1
        changed_indices.add(idx)

    if changed == 0:
        return 0, warnings

    segment.meta["sub_segment_subtitle_texts"] = sub_texts
    segment.meta["sub_segment_estimated_durations"] = durations
    segment.duration = sum(durations)
    segment.audio_text = " ".join(t for texts in sub_texts for t in texts)

    # Invalidate stale per-subtitle audio for changed indices so a re-run of
    # synthesize_audio regenerates them. Indexed 1:1 with sub_segment lists.
    subtitle_audios = segment.meta.get("subtitle_audios")
    if isinstance(subtitle_audios, list) and subtitle_audios:
        for idx in changed_indices:
            if 0 <= idx < len(subtitle_audios):
                subtitle_audios[idx] = None
        warnings.append(
            "subtitle_audios was present (audio already synthesized); cleared "
            f"{len(changed_indices)} changed entries — re-run synthesize_audio"
        )

    return changed, warnings
