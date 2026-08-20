import json

from src.core.models import SceneElement, Script, ScriptSegment
from src.pipeline.paths import pipeline_path
from src.pipeline.storyboard_draft import draft_storyboard


class FakeStoryboardAgent:
    fast_model = "fake-fast"
    fast_temperature = 0.2

    def __init__(self):
        self.calls = []

    def complete_prompt(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return {
            "shots": [
                {
                    "shot_id": "S01-01",
                    "segment_index": 0,
                    "element_index": 0,
                    "template_id": "cover_v1",
                    "props": {},
                },
                {
                    "shot_id": "S02-01",
                    "segment_index": 1,
                    "element_index": 0,
                    "template_id": "headline_v1",
                    "props": {"title": "头条"},
                },
                {
                    "shot_id": "S02-02",
                    "segment_index": 1,
                    "element_index": 1,
                    "template_id": "discussion_v1",
                    "props": {},
                },
            ]
        }


def _script() -> Script:
    return Script(
        title="测试台本",
        description="测试",
        tags=[],
        segments=[
            ScriptSegment(
                segment_type="opening",
                audio_text="开场。",
                duration=2,
                scene_elements=[SceneElement("cover_card", 0, 2, {"headline": "HN"})],
            ),
            ScriptSegment(
                segment_type="story_scan",
                audio_text="头条。评论。",
                duration=4,
                scene_elements=[
                    SceneElement(
                        "event_card",
                        0,
                        2,
                        {
                            "story_index": 0,
                            "editor_angle": "事件标题",
                            "subtitle_texts": ["头条。"],
                        },
                    ),
                    SceneElement(
                        "atmosphere_card",
                        2,
                        4,
                        {
                            "story_index": 0,
                            "subtitle_texts": ["评论。"],
                        },
                    ),
                ],
            ),
        ],
    )


def test_agent_draft_writes_complete_storyboard(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    provider = FakeStoryboardAgent()

    result = draft_storyboard(_script(), "2026-08-18", llm_provider=provider)

    assert result.created is True
    payload = json.loads(
        pipeline_path("2026-08-18", "storyboard.json").read_text(encoding="utf-8")
    )
    assert payload["generated_by"]["kind"] == "agent"
    assert [shot["template_id"] for shot in payload["shots"]] == [
        "cover_v1",
        "headline_v1",
        "discussion_v1",
    ]
    assert "subtitle_texts" not in payload["shots"][1]["props"]
    assert provider.calls[0][0][0] == "prompts/storyboard_draft.md"


def test_agent_draft_preserves_existing_editorial_storyboard(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    first = draft_storyboard(_script(), "2026-08-18")
    provider = FakeStoryboardAgent()

    second = draft_storyboard(_script(), "2026-08-18", llm_provider=provider)

    assert first.created is True
    assert second.created is False
    assert provider.calls == []
