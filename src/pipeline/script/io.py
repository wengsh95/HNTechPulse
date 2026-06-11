"""Script I/O: save/load Script to/from JSON."""

import json
from dataclasses import asdict
from pathlib import Path

from src.core.models import Script, ScriptSegment, SceneElement, Cue
from src.pipeline.agent_io import write_artifact_manifest
from src.pipeline.paths import pipeline_path
from src.utils.atomic_io import atomic_write_json


def save_script_to_path(
    script: Script,
    path: Path,
    *,
    date: str,
    step: str = "write_script",
    inputs: dict | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    script_dict = asdict(script)
    atomic_write_json(path, script_dict)
    write_artifact_manifest(
        path,
        step=step,
        date=date,
        inputs={
            "title": script.title,
            "segment_count": len(script.segments),
            "segment_types": [segment.segment_type for segment in script.segments],
            **(inputs or {}),
        },
    )


def save_script(script: Script, date: str, logger=None) -> None:
    path = pipeline_path(date, "script.json")
    save_script_to_path(script, path, date=date)
    if logger:
        logger.info(f"Saved script to {path}")


def load_script(date: str) -> Script:
    path = pipeline_path(date, "script.json")
    if not path.exists():
        raise FileNotFoundError(f"Script not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            script_dict = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Script file {path} contains invalid JSON: {e}") from e

    try:
        return Script(
            title=script_dict["title"],
            description=script_dict["description"],
            tags=script_dict["tags"],
            total_duration=script_dict.get("total_duration"),
            cover_subtitle=script_dict.get("cover_subtitle", ""),
            cover_title=script_dict.get("cover_title", ""),
            cover_tags=list(script_dict.get("cover_tags") or []),
            segments=[
                ScriptSegment(
                    segment_type=s["segment_type"],
                    audio_text=s["audio_text"],
                    duration=s["duration"],
                    emotion=s.get("emotion", "warm"),
                    actual_duration=s.get("actual_duration"),
                    start_time=s.get("start_time"),
                    end_time=s.get("end_time"),
                    audio_path=s.get("audio_path"),
                    cues=[
                        Cue(
                            text=c["text"],
                            start_time=c["start_time"],
                            end_time=c["end_time"],
                        )
                        for c in s.get("cues", [])
                    ],
                    scene_elements=[
                        SceneElement(
                            element_type=e["element_type"],
                            start_time=e.get("start_time", 0.0),
                            end_time=e.get("end_time", 0.0),
                            props=e["props"],
                            sub_segment_index=e.get("sub_segment_index"),
                        )
                        for e in s.get("scene_elements", [])
                    ],
                    meta=s.get("meta", {}),
                )
                for s in script_dict["segments"]
            ],
        )
    except (KeyError, TypeError) as e:
        raise ValueError(f"Script file {path} has unexpected structure: {e}") from e
