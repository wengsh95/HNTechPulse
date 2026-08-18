"""Local-agent subtitle selection for the video flow.

This step does not call an LLM and does not rewrite narration.  It only turns
the human/LLM-provided subtitle fragments into safe display units before TTS
and records the selected result as a date-scoped artifact.
"""

from __future__ import annotations

import re
from typing import Any

from src.core.models import Script
from src.pipeline.agent_io import write_artifact_manifest
from src.pipeline.paths import pipeline_path
from src.pipeline.script.io import script_audio_input_hash, script_editorial_hash
from src.utils.atomic_io import atomic_write_json
from src.utils.subtitles import (
    SUBTITLE_POLICY_VERSION,
    split_subtitle_texts,
    subtitle_boundary_is_safe,
    subtitle_display_weight,
)


def _content_key(texts: list[str]) -> str:
    return re.sub(r"\s+", "", "".join(str(text or "") for text in texts))


def _validate_units(source: list[str], selected: list[str]) -> None:
    if _content_key(source) != _content_key(selected):
        raise ValueError("subtitle selection changed narration content")
    if not selected:
        raise ValueError("subtitle selection is empty")
    for text in selected:
        if not text.strip():
            raise ValueError("subtitle selection contains an empty cue")
        if len(text) > 52 or subtitle_display_weight(text) > 24:
            raise ValueError(f"subtitle cue exceeds display width: {text}")
        if text[0] in "，。！？、；：,.!?;:":
            raise ValueError(f"subtitle cue starts with punctuation: {text}")
    for left, right in zip(selected, selected[1:]):
        if not subtitle_boundary_is_safe(left, right):
            raise ValueError(f"subtitle cue splits a protected token: {left} | {right}")


def prepare_subtitles(
    script: Script, date: str, config: dict[str, Any] | None = None
) -> dict:
    """Let the local execution agent select safe subtitle display units."""
    script_hash_before = script_editorial_hash(script)
    audio_input_hash_before = script_audio_input_hash(script)
    entries: list[dict[str, Any]] = []
    changed_count = 0

    for segment_index, segment in enumerate(script.segments):
        if segment.segment_type == "story_scan":
            for element_index, element in enumerate(segment.scene_elements):
                raw = [
                    str(text).strip()
                    for text in (element.props.get("subtitle_texts", []) or [])
                    if str(text).strip()
                ]
                if not raw:
                    continue
                selected = split_subtitle_texts(raw)
                _validate_units(raw, selected)
                element.props["subtitle_texts"] = selected

                sub_index = element.sub_segment_index
                meta_units = segment.meta.get("sub_segment_subtitle_texts")
                if (
                    isinstance(sub_index, int)
                    and isinstance(meta_units, list)
                    and 0 <= sub_index < len(meta_units)
                ):
                    meta_units[sub_index] = selected

                if selected != raw:
                    changed_count += 1
                entries.append(
                    {
                        "segment_index": segment_index,
                        "element_index": element_index,
                        "sub_segment_index": sub_index,
                        "source": raw,
                        "selected": selected,
                        "changed": selected != raw,
                    }
                )
        else:
            raw = [segment.audio_text.strip()] if segment.audio_text.strip() else []
            if not raw:
                continue
            selected = split_subtitle_texts(raw)
            _validate_units(raw, selected)
            entries.append(
                {
                    "segment_index": segment_index,
                    "element_index": None,
                    "sub_segment_index": None,
                    "source": raw,
                    "selected": selected,
                    "changed": selected != raw,
                }
            )
            if selected != raw:
                changed_count += 1

    script_hash_after = script_editorial_hash(script)
    audio_input_hash_after = script_audio_input_hash(script)
    payload = {
        "schema_version": 2,
        "date": date,
        "selection_source": "agent_local",
        "policy_version": SUBTITLE_POLICY_VERSION,
        "script_hash_before": script_hash_before,
        "script_hash_after": script_hash_after,
        "audio_input_hash_before": audio_input_hash_before,
        "audio_input_hash_after": audio_input_hash_after,
        "changed_count": changed_count,
        "entries": entries,
    }
    path = pipeline_path(date, "subtitle_plan.json")
    atomic_write_json(path, payload)
    write_artifact_manifest(
        path,
        step="prepare_subtitles",
        date=date,
        inputs={
            "script_hash": script_hash_before,
            "policy_version": SUBTITLE_POLICY_VERSION,
        },
        config=config,
        extra={"selected_script_hash": script_hash_after},
    )
    return payload
