from src.core.models import SceneElement, Script, ScriptSegment
from src.pipeline.paths import pipeline_path
from src.pipeline.video_structure import prepare_video_structure


def _script() -> Script:
    return Script(
        title="Test",
        description="",
        tags=[],
        segments=[
            ScriptSegment(
                segment_type="story_scan",
                audio_text="故事",
                duration=10,
                scene_elements=[
                    SceneElement("event_card", 0, 4, {"story_index": 0}),
                    SceneElement("atmosphere_card", 4, 8, {"story_index": 0}),
                    SceneElement("event_card", 8, 10, {"story_index": 1}),
                ],
            ),
            ScriptSegment(
                segment_type="quick_news",
                audio_text="速览",
                duration=5,
                scene_elements=[
                    SceneElement(
                        "quick_card",
                        0,
                        5,
                        {"quick_story_id": "q1"},
                    )
                ],
            ),
        ],
    )


def test_prepare_video_structure_assigns_roles_and_writes_artifact(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    script = _script()

    result = prepare_video_structure(script, "2026-04-26")

    assert result.changed is True
    assert result.deep_story_count == 2
    assert result.quick_story_count == 1
    props = script.segments[0].scene_elements
    assert props[0].props == {
        "story_index": 0,
        "section_label": "头条",
        "story_role": "evidence",
        "image_target": True,
    }
    assert props[1].props["story_role"] == "comment"
    assert props[1].props["image_target"] is False
    assert props[2].props["section_label"] == "重点 01"
    assert script.segments[1].scene_elements[0].props["story_role"] == "quick"
    assert pipeline_path("2026-04-26", "video_structure.json").exists()


def test_prepare_video_structure_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = _script()

    first = prepare_video_structure(script, "2026-04-26")
    narration = script.segments[0].audio_text
    second = prepare_video_structure(script, "2026-04-26")

    assert first.changed is True
    assert second.changed is False
    assert script.segments[0].audio_text == narration
