import json

import pytest

from src.core.models import Script, ScriptSegment
from src.pipeline.paths import pipeline_path, raw_path
from src.pipeline.quick_news import (
    _build_segment,
    _normalize_agent_result,
    draft_quick_news,
)


def _script_with_closing() -> Script:
    return Script(
        title="Test",
        description="",
        tags=[],
        segments=[
            ScriptSegment(segment_type="opening", audio_text="开场", duration=2),
            ScriptSegment(segment_type="closing", audio_text="结尾", duration=2),
        ],
    )


def _candidates() -> list[dict]:
    return [
        {
            "story_id": "1",
            "title": "第一条",
            "url": "https://example.com/1",
            "score": 100,
            "comment_count": 10,
            "news_focus": 3,
        },
        {
            "story_id": "2",
            "title": "第二条",
            "url": "https://example.com/2",
            "score": 90,
            "comment_count": 8,
            "news_focus": 2,
        },
        {
            "story_id": "3",
            "title": "第三条",
            "url": "https://example.com/3",
            "score": 80,
            "comment_count": 5,
            "news_focus": 1,
        },
    ]


class TestNormalizeAgentResult:
    def test_accepts_wrapped_result_filters_unknown_and_deduplicates(self):
        result = _normalize_agent_result(
            {
                "quick_news": [
                    {"story_id": "1", "title": "一", "fact": "事实"},
                    {"story_id": "1", "title": "重复", "fact": "重复"},
                    {"story_id": "missing", "title": "未知", "fact": "未知"},
                    {"story_id": "2", "title": "二", "fact": "第二个事实"},
                ]
            },
            _candidates(),
        )

        assert [item["story_id"] for item in result] == ["1", "2"]
        assert result[0]["fact"] == "事实。"
        assert result[1]["source_url"] == "https://example.com/2"

    def test_falls_back_to_prefilter_candidates_when_agent_returns_too_few(self):
        result = _normalize_agent_result([], _candidates())

        assert len(result) == 3
        assert result[0]["story_id"] == "1"
        assert all(item["fact"].endswith("。") for item in result)

    def test_raises_when_fewer_than_two_candidates_exist(self):
        with pytest.raises(ValueError, match="Not enough"):
            _normalize_agent_result([], _candidates()[:1])


class TestQuickNewsDraft:
    def test_existing_segment_is_idempotent(self):
        script = _script_with_closing()
        script.segments.insert(
            1, _build_segment([{"story_id": "1", "title": "一", "fact": "事实"}])
        )

        result = draft_quick_news(script, "2026-04-26", llm_provider=None, config={})

        assert result.changed is False
        assert result.items == []
        assert [segment.segment_type for segment in script.segments] == [
            "opening",
            "quick_news",
            "closing",
        ]

    def test_restores_cached_items_before_closing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        date = "2026-04-26"
        artifact = pipeline_path(date, "quick_news.json")
        artifact.parent.mkdir(parents=True)
        artifact.write_text(
            json.dumps(
                {
                    "items": [
                        {
                            "story_id": "7",
                            "title": "缓存速览",
                            "fact": "缓存事实",
                            "source_url": "https://example.com/7",
                        },
                        {
                            "story_id": "8",
                            "title": "第二速览",
                            "fact": "第二事实",
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        script = _script_with_closing()
        result = draft_quick_news(script, date, llm_provider=None, config={})

        assert result.changed is True
        assert [item["story_id"] for item in result.items] == ["7", "8"]
        assert script.segments[1].segment_type == "quick_news"
        assert script.segments[1].scene_elements[0].props["quick_story_id"] == "7"

    def test_generates_from_approved_candidates_and_writes_artifact(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        date = "2026-04-26"
        raw_path(date, "raw_stories.json").parent.mkdir(parents=True)
        raw_path(date, "raw_stories.json").write_text(
            json.dumps(
                {
                    "stories": [
                        {"id": 1, "title": "深讲", "url": "https://deep"},
                        {"id": 2, "title": "速览一", "url": "https://quick-1"},
                        {"id": 3, "title": "速览二", "url": "https://quick-2"},
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        prefilter_path = pipeline_path(date, "prefilter.json")
        prefilter_path.parent.mkdir(parents=True, exist_ok=True)
        prefilter_path.write_text(
            json.dumps(
                {
                    "decisions": {
                        "1": {"keep": True},
                        "2": {"keep": True, "news_focus": 3},
                        "3": {"keep": True, "news_focus": 2},
                    }
                }
            ),
            encoding="utf-8",
        )
        content_path = pipeline_path(date, "content.json")
        content_path.write_text(
            json.dumps({"date": date, "items": [{"source_id": "1"}]}),
            encoding="utf-8",
        )

        class Provider:
            fast_model = "test"
            fast_temperature = 0.1

            def complete_prompt(self, *args, **kwargs):
                return {
                    "items": [
                        {"story_id": "2", "title": "速览一", "fact": "事实一"},
                        {"story_id": "3", "title": "速览二", "fact": "事实二"},
                    ]
                }

        script = _script_with_closing()
        result = draft_quick_news(script, date, llm_provider=Provider(), config={})

        assert result.changed is True
        artifact = pipeline_path(date, "quick_news.json")
        assert artifact.exists()
        assert (
            json.loads(artifact.read_text(encoding="utf-8"))["items"][0]["story_id"]
            == "2"
        )
