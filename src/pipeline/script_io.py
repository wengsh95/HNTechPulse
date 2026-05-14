import json
from dataclasses import asdict
from pathlib import Path

from src.core.models import Script, ScriptSegment, SceneElement, Cue


def save_script(script: Script, date: str, logger=None) -> None:
    path = Path(f"data/{date}/script.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    script_dict = asdict(script)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(script_dict, f, ensure_ascii=False, indent=2)
    if logger:
        logger.info(f"Saved script to {path}")


def load_script(date: str) -> Script:
    path = Path(f"data/{date}/script.json")
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
            segments=[
                ScriptSegment(
                    segment_type=s["segment_type"],
                    audio_text=s["audio_text"],
                    estimated_duration=s["estimated_duration"],
                    actual_duration=s.get("actual_duration"),
                    emotion=s.get("emotion", "neutral"),
                    scene_elements=[
                        SceneElement(
                            element_type=e["element_type"],
                            start_time=e["start_time"],
                            end_time=e["end_time"],
                            props=e["props"],
                            sub_segment_index=e.get("sub_segment_index"),
                        )
                        for e in s.get("scene_elements", [])
                    ],
                    meta=s.get("meta", {}),
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
                )
                for s in script_dict["segments"]
            ],
            total_duration=script_dict.get("total_duration"),
        )
    except (KeyError, TypeError) as e:
        raise ValueError(f"Script file {path} has unexpected structure: {e}") from e
