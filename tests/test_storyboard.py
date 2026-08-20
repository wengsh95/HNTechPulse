import pytest

from src.core.models import SceneElement, Script, ScriptSegment
from src.pipeline.paths import pipeline_path
from src.pipeline.storyboard import apply_storyboard
from src.utils.atomic_io import atomic_write_json


def _script() -> Script:
    return Script(
        title="Test",
        description="",
        tags=[],
        segments=[
            ScriptSegment(
                segment_type="story_scan",
                audio_text="头条内容。评论内容。",
                duration=8,
                scene_elements=[
                    SceneElement(
                        element_type="event_card",
                        start_time=0,
                        end_time=4,
                        props={
                            "story_index": 0,
                            "subtitle_texts": ["头条内容。"],
                        },
                    ),
                    SceneElement(
                        element_type="atmosphere_card",
                        start_time=4,
                        end_time=8,
                        props={
                            "story_index": 0,
                            "subtitle_texts": ["评论内容。"],
                        },
                    ),
                ],
            )
        ],
    )


def test_apply_storyboard_maps_templates_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    atomic_write_json(
        pipeline_path("2026-08-18", "storyboard.json"),
        {
            "schema_version": 1,
            "date": "2026-08-18",
            "shots": [
                {
                    "shot_id": "H01-01",
                    "story_index": 0,
                    "source_element_type": "event_card",
                    "source_element_index": 0,
                    "template_id": "headline_v1",
                    "props": {"title": "头条钩子", "eyebrow": "头条"},
                },
                {
                    "shot_id": "H01-02",
                    "story_index": 0,
                    "source_element_type": "atmosphere_card",
                    "source_element_index": 0,
                    "template_id": "comment_dual_v1",
                    "props": {
                        "left_summary": "支持",
                        "right_summary": "质疑",
                    },
                },
            ],
        },
    )

    script = _script()
    script, application = apply_storyboard(script, "2026-08-18")

    assert [e.element_type for e in script.segments[0].scene_elements] == [
        "headline_card",
        "comment_dual_card",
    ]
    assert script.segments[0].scene_elements[0].props["subtitle_texts"] == [
        "头条内容。"
    ]
    assert application is not None
    assert application.applied_count == 2
    assert application.changed_count == 2

    script, second = apply_storyboard(script, "2026-08-18")
    assert second is not None
    assert second.changed_count == 0


def test_apply_storyboard_rejects_audio_props(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    atomic_write_json(
        pipeline_path("2026-08-18", "storyboard.json"),
        {
            "schema_version": 1,
            "shots": [
                {
                    "shot_id": "H01-01",
                    "segment_index": 0,
                    "element_index": 0,
                    "template_id": "headline_v1",
                    "props": {
                        "title": "头条",
                        "subtitle_texts": ["不允许覆盖"],
                    },
                }
            ],
        },
    )

    with pytest.raises(ValueError, match="derived props"):
        apply_storyboard(_script(), "2026-08-18")


def test_apply_storyboard_requires_template_props(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    atomic_write_json(
        pipeline_path("2026-08-18", "storyboard.json"),
        {
            "schema_version": 1,
            "shots": [
                {
                    "shot_id": "H01-01",
                    "segment_index": 0,
                    "element_index": 0,
                    "template_id": "data_number_v1",
                    "props": {"label": "成本"},
                }
            ],
        },
    )

    with pytest.raises(ValueError, match="value"):
        apply_storyboard(_script(), "2026-08-18")


def test_build_storyboard_preserves_card_props():
    from src.pipeline.storyboard_draft import build_storyboard

    script = Script(
        title="Test",
        description="",
        tags=[],
        segments=[
            ScriptSegment(
                segment_type="opening",
                audio_text="开场",
                duration=6,
                scene_elements=[
                    SceneElement(
                        element_type="cover_card",
                        start_time=0,
                        end_time=6,
                        props={
                            "headline": "每日HN日报",
                            "subtitle": "今日焦点",
                            "date": "2026-08-18",
                            "template_id": "cover_v1",
                        },
                    )
                ],
            ),
            ScriptSegment(
                segment_type="story_scan",
                audio_text="内容",
                duration=10,
                scene_elements=[
                    SceneElement(
                        element_type="atmosphere_card",
                        start_time=0,
                        end_time=5,
                        props={
                            "story_index": 0,
                            "template_id": "comment_single_v1",
                            "quotes": [
                                {
                                    "author": "alice",
                                    "text": "这是一条非常有深度的评论观点。",
                                    "stance": "质疑",
                                }
                            ],
                        },
                    ),
                ],
            ),
            ScriptSegment(
                segment_type="quick_news",
                audio_text="快讯",
                duration=10,
                scene_elements=[
                    SceneElement(
                        element_type="quick_card",
                        start_time=0,
                        end_time=5,
                        props={
                            "title": "DuckDB 2.0",
                            "fact": "新功能预览",
                            "template_id": "quick_news_v1",
                        },
                    )
                ],
            ),
            ScriptSegment(
                segment_type="closing",
                audio_text="结尾",
                duration=9,
                scene_elements=[
                    SceneElement(
                        element_type="closing_card",
                        start_time=0,
                        end_time=9,
                        props={
                            "template_id": "closing_v1",
                            "summary_items": [
                                {"title": "GPT-5.6 Sol 降价", "signal": "降价50%"}
                            ],
                            "takeaways": ["降价50%"],
                        },
                    )
                ],
            ),
        ],
    )

    draft = build_storyboard(script, "2026-08-18")
    shots = {s["shot_id"]: s for s in draft["shots"]}

    assert shots["S01-01"]["props"]["headline"] == "每日HN日报"
    assert shots["S01-01"]["props"]["subtitle"] == "今日焦点"
    assert shots["S02-01"]["props"]["quote"] == "这是一条非常有深度的评论观点。"
    assert shots["S02-01"]["props"]["author"] == "alice"
    assert shots["S03-01"]["props"]["title"] == "DuckDB 2.0"
    assert shots["S03-01"]["props"]["fact"] == "新功能预览"
    assert len(shots["S04-01"]["props"]["summary_items"]) == 1
    assert shots["S04-01"]["props"]["summary_items"][0]["title"] == "GPT-5.6 Sol 降价"
