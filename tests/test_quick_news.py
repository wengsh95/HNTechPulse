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

    def test_rejects_too_few_agent_items_instead_of_copying_titles(self):
        with pytest.raises(ValueError, match="at least two"):
            _normalize_agent_result([], _candidates())

    def test_rejects_a_fact_that_merely_repeats_the_source_title(self):
        with pytest.raises(ValueError, match="repeats its title"):
            _normalize_agent_result(
                {
                    "items": [
                        {"story_id": "1", "title": "第一条", "fact": "第一条"},
                        {"story_id": "2", "title": "第二条", "fact": "发布了新版本"},
                    ]
                },
                _candidates(),
            )

    def test_raises_when_fewer_than_two_candidates_exist(self):
        with pytest.raises(ValueError, match="Not enough"):
            _normalize_agent_result([], _candidates()[:1])


class TestQuickNewsDraft:
    def test_existing_segment_is_idempotent(self):
        script = _script_with_closing()
        script.segments.insert(
            1,
            _build_segment(
                [
                    {"story_id": "1", "title": "一", "fact": "第一个具体事实"},
                    {"story_id": "2", "title": "二", "fact": "第二个具体事实"},
                ]
            ),
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
                    "schema_version": 2,
                    "items": [
                        {
                            "story_id": "7",
                            "title": "缓存速览",
                            "fact": "缓存中保留了具体事实",
                            "source_url": "https://example.com/7",
                        },
                        {
                            "story_id": "8",
                            "title": "第二速览",
                            "fact": "第二条也有具体事实",
                        },
                    ],
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
        assert script.segments[1].audio_text.startswith("接下来是两条速览。")

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

        enriched_ids = []

        class Enricher:
            def enrich(self, package, run_date):
                assert run_date == date
                for item in package.items:
                    item.article_summary = f"{item.title}的正文摘要"
                    item.key_points = [{"fact": "具体变化"}]
                    item.enrichment_source = "test"
                    enriched_ids.append(item.source_id)
                return package

        script = _script_with_closing()
        result = draft_quick_news(
            script,
            date,
            llm_provider=Provider(),
            article_enricher=Enricher(),
            config={},
        )

        assert result.changed is True
        assert enriched_ids == ["2", "3"]
        artifact = pipeline_path(date, "quick_news.json")
        assert artifact.exists()
        payload = json.loads(artifact.read_text(encoding="utf-8"))
        assert payload["schema_version"] == 2
        assert payload["items"][0]["story_id"] == "2"
        assert payload["items"][0]["source_context"]["article_summary"]
