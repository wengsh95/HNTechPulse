"""Script I/O: save/load Script to/from JSON."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.core.models import Script, ScriptSegment, SceneElement, Cue
from src.pipeline.agent_io import stable_hash, write_artifact_manifest
from src.pipeline.paths import agent_path, pipeline_path
from src.utils.atomic_io import atomic_write_json
from src.utils.subtitles import SUBTITLE_POLICY_VERSION


_RUNTIME_SEGMENT_FIELDS = {
    "actual_duration",
    "start_time",
    "end_time",
    "audio_path",
    "cues",
}


def script_editorial_payload(script: Script) -> dict[str, Any]:
    """Return the durable, human-editable part of a script.

    Audio paths, alignment cues, timing, and renderer-only scene props are
    derived data. Keeping them out of ``script.json`` prevents a TTS or render
    retry from rewriting an author's copy.
    """
    payload = asdict(script)
    payload["total_duration"] = None
    for segment in payload.get("segments", []):
        for field in _RUNTIME_SEGMENT_FIELDS:
            segment.pop(field, None)
        meta = segment.get("meta")
        if isinstance(meta, dict):
            meta.pop("subtitle_audios", None)
        for element in segment.get("scene_elements", []):
            element.pop("start_time", None)
            element.pop("end_time", None)
            props = element.get("props")
            if isinstance(props, dict):
                props.pop("audio_duration", None)
    return payload


def script_editorial_hash(script: Script) -> str:
    return stable_hash(script_editorial_payload(script))


def script_audio_input_hash(script: Script) -> str:
    """Hash only narration/subtitle inputs that determine synthesized audio."""
    payload = {
        "subtitle_policy_version": SUBTITLE_POLICY_VERSION,
        "segments": [
            {
                "segment_type": segment.segment_type,
                "audio_text": segment.audio_text,
                "emotion": segment.emotion,
                "subtitle_texts": [
                    text
                    for element in segment.scene_elements
                    for text in (element.props.get("subtitle_texts", []) or [])
                    if text
                ],
            }
            for segment in script.segments
        ],
    }
    return stable_hash(payload)


def audio_manifest_payload(script: Script, date: str) -> dict[str, Any]:
    """Serialize runtime audio/timing data without copying editorial text."""
    return {
        "schema_version": 1,
        "date": date,
        "audio_input_hash": script_audio_input_hash(script),
        "total_duration": script.total_duration,
        "segments": [
            {
                "index": index,
                "actual_duration": segment.actual_duration,
                "start_time": segment.start_time,
                "end_time": segment.end_time,
                "audio_path": segment.audio_path,
                "cues": [asdict(cue) for cue in segment.cues],
                "subtitle_audios": segment.meta.get("subtitle_audios", []),
                "scene_elements": [
                    {
                        "index": element_index,
                        "start_time": element.start_time,
                        "end_time": element.end_time,
                        "audio_duration": element.props.get("audio_duration"),
                    }
                    for element_index, element in enumerate(segment.scene_elements)
                    if "audio_duration" in element.props
                    or element.start_time
                    or element.end_time
                ],
            }
            for index, segment in enumerate(script.segments)
        ],
    }


def save_audio_manifest(script: Script, date: str, config: dict | None = None) -> Path:
    path = pipeline_path(date, "audio_manifest.json")
    payload = audio_manifest_payload(script, date)
    atomic_write_json(path, payload)
    write_artifact_manifest(
        path,
        step="synthesize_audio",
        date=date,
        inputs={
            "audio_input_hash": payload["audio_input_hash"],
            "segment_count": len(script.segments),
        },
        config=config,
    )
    return path


def save_script_lock(script: Script, date: str, source: str = "pipeline") -> Path:
    path = agent_path(date, "script_lock.json")
    payload = {
        "schema_version": 1,
        "date": date,
        "script_hash": script_editorial_hash(script),
        "source": source,
    }
    atomic_write_json(path, payload)
    return path


def load_script_lock(date: str) -> dict[str, Any] | None:
    path = agent_path(date, "script_lock.json")
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Script lock {path} contains invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Script lock {path} has unexpected structure")
    return payload


def load_audio_manifest(date: str) -> dict[str, Any] | None:
    path = pipeline_path(date, "audio_manifest.json")
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Audio manifest {path} contains invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Audio manifest {path} has unexpected structure")
    return payload


def audio_manifest_audio_paths(manifest: dict[str, Any]) -> list[Path]:
    """Return every concrete audio file referenced by a runtime manifest."""
    paths: list[Path] = []
    for entry in manifest.get("segments", []) or []:
        if not isinstance(entry, dict):
            continue
        audio_path = entry.get("audio_path")
        if audio_path:
            paths.append(Path(str(audio_path)))
        for subtitle_audio in entry.get("subtitle_audios", []) or []:
            if isinstance(subtitle_audio, dict) and subtitle_audio.get("audio_path"):
                paths.append(Path(str(subtitle_audio["audio_path"])))
    return paths


def audio_manifest_is_usable(
    manifest: dict[str, Any], expected_segment_count: int | None = None
) -> bool:
    """Return whether a manifest is complete, coherent, and files still exist."""
    segments = manifest.get("segments")
    if not isinstance(segments, list):
        return False
    if expected_segment_count is not None and len(segments) != expected_segment_count:
        return False
    if not all(path.is_file() for path in audio_manifest_audio_paths(manifest)):
        return False
    for entry in segments:
        if not isinstance(entry, dict):
            return False
        cues = entry.get("cues") or []
        if not cues:
            continue
        try:
            actual_duration = float(entry.get("actual_duration") or 0.0)
            cue_end = max(float(cue.get("end_time", 0.0)) for cue in cues)
        except (AttributeError, TypeError, ValueError):
            return False
        # A truncated MP3 can leave a valid-looking manifest behind. Allow a
        # small encoder tail, but never accept cues that extend far beyond the
        # media file's recorded duration.
        if actual_duration <= 0.0 or cue_end > actual_duration + 0.75:
            return False
    return True


def apply_audio_manifest(script: Script, manifest: dict[str, Any]) -> Script:
    """Hydrate runtime fields onto an editorial script for rendering."""
    expected = script_audio_input_hash(script)
    actual = manifest.get("audio_input_hash")
    if actual and actual != expected:
        raise ValueError(
            "Audio manifest is stale for the current script; rerun synthesize_audio"
        )
    if not audio_manifest_is_usable(
        manifest, expected_segment_count=len(script.segments)
    ):
        raise ValueError(
            "Audio manifest is incomplete or references missing audio files"
        )
    missing = [
        str(path) for path in audio_manifest_audio_paths(manifest) if not path.is_file()
    ]
    if missing:
        raise ValueError(
            "Audio manifest references missing audio files: " + ", ".join(missing[:3])
        )
    script.total_duration = manifest.get("total_duration")
    for entry in manifest.get("segments", []) or []:
        index = entry.get("index")
        if not isinstance(index, int) or not 0 <= index < len(script.segments):
            continue
        segment = script.segments[index]
        segment.actual_duration = entry.get("actual_duration")
        segment.start_time = entry.get("start_time")
        segment.end_time = entry.get("end_time")
        segment.audio_path = entry.get("audio_path")
        segment.cues = [
            Cue(
                text=cue["text"],
                start_time=cue["start_time"],
                end_time=cue["end_time"],
            )
            for cue in entry.get("cues", []) or []
        ]
        subtitle_audios = entry.get("subtitle_audios")
        if subtitle_audios:
            segment.meta["subtitle_audios"] = subtitle_audios
        for element_entry in entry.get("scene_elements", []) or []:
            element_index = element_entry.get("index")
            if not isinstance(element_index, int) or not 0 <= element_index < len(
                segment.scene_elements
            ):
                continue
            element = segment.scene_elements[element_index]
            element.start_time = element_entry.get("start_time", 0.0)
            element.end_time = element_entry.get("end_time", 0.0)
            if element_entry.get("audio_duration") is not None:
                element.props["audio_duration"] = element_entry["audio_duration"]
    return script


def save_script_to_path(
    script: Script,
    path: Path,
    *,
    date: str,
    step: str = "write_script",
    inputs: dict | None = None,
    include_runtime: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    script_dict = (
        asdict(script) if include_runtime else script_editorial_payload(script)
    )
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
    save_script_lock(script, date)
    if logger:
        logger.info(f"Saved script to {path}")


def load_script(date: str, *, with_audio: bool = False) -> Script:
    path = pipeline_path(date, "script.json")
    if not path.exists():
        raise FileNotFoundError(f"Script not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            script_dict = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Script file {path} contains invalid JSON: {e}") from e

    try:
        script = Script(
            title=script_dict["title"],
            description=script_dict["description"],
            tags=script_dict["tags"],
            total_duration=script_dict.get("total_duration"),
            cover_subtitle=script_dict.get("cover_subtitle", ""),
            cover_title=script_dict.get("cover_title", ""),
            cover_tags=list(script_dict.get("cover_tags") or []),
            cover_highlights=list(script_dict.get("cover_highlights") or []),
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
        if with_audio:
            manifest = load_audio_manifest(date)
            if manifest is not None:
                apply_audio_manifest(script, manifest)
        return script
    except (KeyError, TypeError) as e:
        raise ValueError(f"Script file {path} has unexpected structure: {e}") from e
