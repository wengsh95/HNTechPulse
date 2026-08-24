from src.core.models import SceneElement, Script, ScriptSegment
from src.pipeline.script.reviser import (
    apply_script_review_revisions,
    apply_subtitle_revisions,
    collect_script_review_units,
)


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


def test_full_review_covers_opening_story_quick_news_and_closing():
    script = _script()
    script.segments.insert(0, ScriptSegment("opening", "开场原文", 2.0))
    script.segments.extend(
        [
            ScriptSegment(
                "quick_news",
                "接下来是两条速览。 速览一。 速览二。",
                6.0,
                scene_elements=[
                    SceneElement(
                        "quick_card",
                        0,
                        3,
                        {"subtitle_texts": ["速览一。"]},
                        sub_segment_index=0,
                    ),
                    SceneElement(
                        "quick_card",
                        3,
                        6,
                        {"subtitle_texts": ["速览二。"]},
                        sub_segment_index=1,
                    ),
                ],
                meta={
                    "intro_text": "接下来是两条速览。",
                    "sub_segment_subtitle_texts": [["速览一。"], ["速览二。"]],
                },
            ),
            ScriptSegment("closing", "结尾原文", 2.0),
        ]
    )

    units = collect_script_review_units(script)
    assert {unit["segment_type"] for unit in units} == {
        "opening",
        "story_scan",
        "quick_news",
        "closing",
    }
    quick_index = next(
        unit["index"]
        for unit in units
        if unit["segment_type"] == "quick_news" and unit["local_index"] == 0
    )
    changed, warnings = apply_script_review_revisions(
        script, {quick_index: ["速览一。", "速览一的具体事实。"]}
    )

    quick = next(
        segment for segment in script.segments if segment.segment_type == "quick_news"
    )
    assert changed == 1
    assert warnings == []
    assert quick.audio_text.startswith("接下来是两条速览。")
    assert "具体事实" in quick.audio_text
    assert quick.scene_elements[0].props["fact"] == "速览一的具体事实。"
