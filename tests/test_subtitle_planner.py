import json

from src.core.models import SceneElement, Script, ScriptSegment
from src.pipeline.paths import pipeline_path
from src.pipeline.subtitle_planner import prepare_subtitles


def test_prepare_subtitles_is_local_and_persists_selected_plan(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-08-17"
    segment = ScriptSegment(
        segment_type="story_scan",
        audio_text="据Bloomberg报道，Stripe已敲定以超过七十亿美元收购AI模型路由平台OpenRouter。",
        duration=10.0,
        scene_elements=[
            SceneElement(
                element_type="card",
                start_time=0.0,
                end_time=10.0,
                sub_segment_index=0,
                props={
                    "subtitle_texts": [
                        "据Bloomberg报道，Stripe已敲定以超过七十",
                        "亿美元收购AI模型路由平台OpenRouter。",
                    ]
                },
            )
        ],
        meta={
            "sub_segment_subtitle_texts": [
                [
                    "据Bloomberg报道，Stripe已敲定以超过七十",
                    "亿美元收购AI模型路由平台OpenRouter。",
                ]
            ]
        },
    )
    script = Script(title="T", description="D", tags=[], segments=[segment])

    plan = prepare_subtitles(script, date, config={})

    selected = segment.scene_elements[0].props["subtitle_texts"]
    assert plan["selection_source"] == "agent_local"
    assert plan["changed_count"] == 1
    assert selected == [
        "据Bloomberg报道，Stripe已敲定以超过七十亿美元",
        "收购AI模型路由平台OpenRouter。",
    ]
    assert segment.meta["sub_segment_subtitle_texts"][0] == selected

    plan_path = pipeline_path(date, "subtitle_plan.json")
    persisted = json.loads(plan_path.read_text(encoding="utf-8"))
    assert persisted["script_hash_after"] == plan["script_hash_after"]
    assert persisted["audio_input_hash_after"] == plan["audio_input_hash_after"]
    assert plan_path.with_suffix(".json.manifest.json").exists()
