"""Normalize the visual grammar of the video without rewriting narration.

The script composer intentionally keeps the three deep stories in one
``story_scan`` segment because that is the unit used by per-card TTS and
subtitle alignment.  This module adds the editorial structure as durable
visual props instead of splitting that audio segment and risking drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.core.models import Script
from src.pipeline.agent_io import write_artifact_manifest
from src.pipeline.paths import pipeline_path
from src.pipeline.script.io import save_script_lock, script_editorial_hash
from src.utils.atomic_io import atomic_write_json


VIDEO_STRUCTURE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class VideoStructurePreparation:
    deep_story_count: int
    quick_story_count: int
    changed: bool


def _story_index(props: dict[str, Any]) -> int | None:
    value = props.get("story_index")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def prepare_video_structure(
    script: Script,
    date: str,
    *,
    config: dict[str, Any] | None = None,
    logger=None,
) -> VideoStructurePreparation:
    """Attach explicit section/role metadata to every renderable story beat.

    Deep-story images belong to the evidence/hook beat only.  Comment beats
    remain text-first, while every quick-news card is its own image-bearing
    story.  The operation is idempotent and does not touch narration or timing.
    """

    deep_indices: list[int] = []
    quick_count = 0
    for segment in script.segments:
        for element in segment.scene_elements:
            props = element.props or {}
            index = _story_index(props)
            if index is not None and index not in deep_indices:
                deep_indices.append(index)
            if props.get("quick_story_id"):
                quick_count += 1

    index_to_ordinal = {
        story_index: ordinal for ordinal, story_index in enumerate(deep_indices, 1)
    }
    seen_elements: dict[int, int] = {}
    changed = False
    structure_elements: list[dict[str, Any]] = []

    for segment_index, segment in enumerate(script.segments):
        for element_index, element in enumerate(segment.scene_elements):
            props = dict(element.props or {})
            index = _story_index(props)
            quick_id = props.get("quick_story_id")

            if quick_id:
                label = "速览"
                role = "quick"
                image_target = True
                ordinal = None
            elif index is not None and index in index_to_ordinal:
                ordinal = index_to_ordinal[index]
                label = "头条" if ordinal == 1 else f"重点 {ordinal - 1:02d}"
                beat = seen_elements.get(index, 0)
                seen_elements[index] = beat + 1
                role = "evidence" if beat == 0 else "comment"
                image_target = role == "evidence"
            else:
                continue

            desired = {
                "section_label": label,
                "story_role": role,
                "image_target": image_target,
            }
            for key, value in desired.items():
                if props.get(key) != value:
                    props[key] = value
                    changed = True

            if props != (element.props or {}):
                element.props = props

            structure_elements.append(
                {
                    "segment_index": segment_index,
                    "element_index": element_index,
                    "story_index": index,
                    "quick_story_id": str(quick_id) if quick_id else None,
                    "section_label": label,
                    "story_role": role,
                    "image_target": image_target,
                }
            )

    artifact = pipeline_path(date, "video_structure.json")
    atomic_write_json(
        artifact,
        {
            "schema_version": VIDEO_STRUCTURE_SCHEMA_VERSION,
            "date": date,
            "sections": {
                "headline": 1 if deep_indices else 0,
                "focus": max(0, len(deep_indices) - 1),
                "quick": quick_count,
            },
            "deep_story_count": len(deep_indices),
            "quick_story_count": quick_count,
            "elements": structure_elements,
        },
    )
    write_artifact_manifest(
        artifact,
        step="normalize_video_structure",
        date=date,
        config=config,
        inputs={"script_editorial_hash": script_editorial_hash(script)},
    )
    if changed:
        save_script_lock(script, date, source="normalize_video_structure")
        if logger:
            logger.info(
                "  Video structure normalized: headline=1 focus=%d quick=%d",
                max(0, len(deep_indices) - 1),
                quick_count,
            )
    return VideoStructurePreparation(
        deep_story_count=len(deep_indices),
        quick_story_count=quick_count,
        changed=changed,
    )
