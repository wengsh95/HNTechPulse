from src.core.models import SceneElement, Script, ScriptSegment
from src.pipeline.script.reviser import apply_subtitle_revisions


def _script(with_audio: bool = False) -> Script:
    segment = ScriptSegment(
        segment_type="story_scan",
        audio_text="旧字幕一。 旧字幕二。",
        duration=8.0,
        scene_elements=[
            SceneElement(
                "event_card",
                0,
                4,
                {"subtitle_texts": ["旧字幕一。"]},
                sub_segment_index=0,
            ),
            SceneElement(
                "atmosphere_card",
                4,
                8,
                {"subtitle_texts": ["旧字幕二。"]},
                sub_segment_index=1,
            ),
        ],
        meta={
            "sub_segment_subtitle_texts": [["旧字幕一。"], ["旧字幕二。"]],
            "sub_segment_estimated_durations": [4.0, 4.0],
        },
    )
    if with_audio:
        segment.meta["subtitle_audios"] = ["audio-0", "audio-1"]
    return Script(title="Test", description="", tags=[], segments=[segment])


def test_missing_story_scan_returns_warning():
    script = Script(
        title="Test",
        description="",
        tags=[],
        segments=[ScriptSegment("opening", "开场", 1.0)],
    )

    changed, warnings = apply_subtitle_revisions(script, {0: ["新字幕"]})

    assert changed == 0
    assert "no story_scan" in warnings[0]


def test_revision_updates_metadata_elements_audio_and_invalidates_cached_audio():
    script = _script(with_audio=True)

    changed, warnings = apply_subtitle_revisions(
        script,
        {0: ["新的字幕。"], 1: ["第二条", "补充"], 9: ["越界"]},
    )

    segment = script.segments[0]
    assert changed == 2
    assert segment.meta["sub_segment_subtitle_texts"] == [
        ["新的字幕。"],
        ["第二条。", "补充。"],
    ]
    assert segment.scene_elements[0].props["subtitle_texts"] == ["新的字幕。"]
    assert segment.scene_elements[1].props["subtitle_texts"] == ["第二条。", "补充。"]
    assert segment.audio_text == "新的字幕。 第二条。 补充。"
    assert segment.meta["subtitle_audios"] == [None, None]
    assert any("out of range" in warning for warning in warnings)
    assert any("cleared" in warning for warning in warnings)


def test_empty_or_unchanged_revision_does_not_mutate_script():
    script = _script()
    original = script.segments[0].meta["sub_segment_subtitle_texts"]

    changed, warnings = apply_subtitle_revisions(
        script,
        {0: ["旧字幕一。"], 1: ["", "  "]},
    )

    assert changed == 0
    assert script.segments[0].meta["sub_segment_subtitle_texts"] == original
    assert any("cleaned to empty" in warning for warning in warnings)
