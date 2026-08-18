from pathlib import Path

import json

import pytest

from src.core.models import Cue, SceneElement, Script, ScriptSegment
from src.pipeline.script.io import (
    apply_audio_manifest,
    audio_manifest_is_usable,
    load_script,
    load_audio_manifest,
    save_audio_manifest,
    save_script,
    save_script_to_path,
)


def test_script_io_preserves_cover_fields(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = Path("data/2026-06/2026-06-08/pipeline/script.json")
    script = Script(
        title="发布标题",
        description="简介",
        tags=["AI"],
        segments=[],
        cover_subtitle="— 审查成本\n— Steam延迟",
        cover_title="AI写代码贵在审查",
        cover_tags=["六成Token", "Steam延迟"],
    )

    save_script_to_path(script, path, date="2026-06-08")
    loaded = load_script("2026-06-08")

    assert loaded.cover_subtitle == "— 审查成本\n— Steam延迟"
    assert loaded.cover_title == "AI写代码贵在审查"
    assert loaded.cover_tags == ["六成Token", "Steam延迟"]


def test_save_script_keeps_runtime_audio_data_out_of_editorial_file(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    path = Path("data/2026-06/2026-06-08/pipeline/script.json")
    script = Script(
        title="标题",
        description="简介",
        tags=[],
        total_duration=12.5,
        segments=[
            ScriptSegment(
                segment_type="opening",
                audio_text="旁白",
                duration=10.0,
                actual_duration=12.5,
                start_time=0.0,
                end_time=12.5,
                audio_path="data/audio/segment_00.mp3",
                cues=[Cue(text="旁白", start_time=0.0, end_time=12.5)],
                scene_elements=[
                    SceneElement(
                        element_type="event_card",
                        start_time=1.0,
                        end_time=12.5,
                        props={"subtitle_texts": ["旁白"], "audio_duration": 11.5},
                    )
                ],
            )
        ],
    )

    save_script_to_path(script, path, date="2026-06-08")
    payload = json.loads(path.read_text(encoding="utf-8"))
    segment = payload["segments"][0]
    element = segment["scene_elements"][0]

    assert "actual_duration" not in segment
    assert "audio_path" not in segment
    assert "cues" not in segment
    assert "start_time" not in segment
    assert "end_time" not in segment
    assert "audio_duration" not in element["props"]


def test_audio_manifest_round_trip_hydrates_runtime_fields(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-06-08"
    Path("data/audio").mkdir(parents=True, exist_ok=True)
    Path("data/audio/segment_00.mp3").write_bytes(b"audio")
    path = Path(f"data/{date[:7]}/{date}/pipeline/script.json")
    script = Script(
        title="标题",
        description="简介",
        tags=[],
        total_duration=12.5,
        segments=[
            ScriptSegment(
                segment_type="opening",
                audio_text="旁白",
                duration=10.0,
                actual_duration=12.5,
                start_time=0.0,
                end_time=12.5,
                audio_path="data/audio/segment_00.mp3",
                cues=[Cue(text="旁白", start_time=0.0, end_time=12.5)],
                scene_elements=[
                    SceneElement(
                        element_type="event_card",
                        start_time=1.0,
                        end_time=12.5,
                        props={"subtitle_texts": ["旁白"], "audio_duration": 11.5},
                    )
                ],
            )
        ],
    )

    save_script_to_path(script, path, date=date)
    save_audio_manifest(script, date)
    loaded = load_script(date, with_audio=True)

    assert loaded.total_duration == 12.5
    assert loaded.segments[0].actual_duration == 12.5
    assert loaded.segments[0].audio_path == "data/audio/segment_00.mp3"
    assert loaded.segments[0].cues[0].text == "旁白"
    assert loaded.segments[0].scene_elements[0].props["audio_duration"] == 11.5
    manifest = load_audio_manifest(date)
    assert manifest is not None
    assert audio_manifest_is_usable(manifest)


def test_audio_manifest_rejects_changed_narration(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-06-08"
    script = Script(
        title="标题",
        description="简介",
        tags=[],
        segments=[
            ScriptSegment(segment_type="opening", audio_text="原文", duration=1.0)
        ],
    )
    save_audio_manifest(script, date)
    script.segments[0].audio_text = "改过的文案"

    manifest = load_audio_manifest(date)
    assert manifest is not None
    with pytest.raises(ValueError, match="Audio manifest is stale"):
        apply_audio_manifest(script, manifest)


def test_audio_manifest_rejects_changed_emotion(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-06-08"
    script = Script(
        title="标题",
        description="简介",
        tags=[],
        segments=[
            ScriptSegment(
                segment_type="opening",
                audio_text="旁白",
                duration=1.0,
                emotion="warm",
            )
        ],
    )
    save_audio_manifest(script, date)
    script.segments[0].emotion = "excited"

    manifest = load_audio_manifest(date)
    assert manifest is not None
    with pytest.raises(ValueError, match="Audio manifest is stale"):
        apply_audio_manifest(script, manifest)


def test_audio_manifest_rejects_missing_audio_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-06-08"
    script = Script(
        title="标题",
        description="简介",
        tags=[],
        segments=[
            ScriptSegment(segment_type="opening", audio_text="旁白", duration=1.0)
        ],
    )
    script.segments[0].audio_path = "data/audio/missing.mp3"
    save_audio_manifest(script, date)

    manifest = load_audio_manifest(date)
    assert manifest is not None
    assert not audio_manifest_is_usable(manifest)
    with pytest.raises(ValueError, match="missing audio files"):
        apply_audio_manifest(script, manifest)


def test_audio_manifest_rejects_truncated_segments(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-06-08"
    script = Script(
        title="标题",
        description="简介",
        tags=[],
        segments=[
            ScriptSegment(segment_type="opening", audio_text="旁白", duration=1.0),
            ScriptSegment(segment_type="closing", audio_text="结尾", duration=1.0),
        ],
    )
    save_audio_manifest(script, date)
    manifest = load_audio_manifest(date)
    assert manifest is not None
    manifest["segments"] = manifest["segments"][:1]
    assert not audio_manifest_is_usable(manifest, expected_segment_count=2)
    with pytest.raises(ValueError, match="incomplete"):
        apply_audio_manifest(script, manifest)


def test_canonical_script_save_creates_editorial_lock(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-06-08"
    script = Script(
        title="标题",
        description="简介",
        tags=[],
        segments=[
            ScriptSegment(segment_type="opening", audio_text="旁白", duration=1.0)
        ],
    )

    save_script(script, date)
    lock = json.loads(
        Path(f"data/{date[:7]}/{date}/agent/script_lock.json").read_text(
            encoding="utf-8"
        )
    )

    assert lock["script_hash"]
    assert lock["source"] == "pipeline"
