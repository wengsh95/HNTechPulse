from unittest.mock import MagicMock

from src.core.models import ContentComment, ContentItem, ContentPackage
from src.pipeline.prefilter import Prefilter


def _make_content(comment_text: str = "This is technically interesting."):
    return ContentPackage(
        date="2026-04-26",
        items=[
            ContentItem(
                source="hackernews",
                source_id="1",
                title="Story 1",
                url="https://example.com/1",
                score=10,
                comment_count=1,
                comments=[
                    ContentComment(
                        author="u",
                        content=comment_text,
                        source_id="c1",
                        depth=1,
                    )
                ],
                comments_partial=True,
            )
        ],
    )


def _make_prefilter(comment_preview_count: int = 5):
    llm = MagicMock()
    llm.prefilter_stories.return_value = [
        {
            "index": 0,
            "keep": True,
            "reason": "good",
            "category": "developer_tools",
            "news_focus": 4,
            "newsworthiness": 4,
            "audience_interest": 4,
            "discussion_heat": 4,
        }
    ]
    config = {
        "logging": {"level": "WARNING"},
        "pipeline": {"target_story_count": 1},
        "prefilter": {
            "enabled": True,
            "min_keep": 1,
            "min_news_focus": 4,
            "min_newsworthiness": 1,
            "temperature": 0.1,
            "comment_preview_enabled": True,
            "comment_preview_count": comment_preview_count,
        },
        "llm": {"provider": "test", "model": "test-model"},
    }
    return Prefilter(llm, config, debug=True), llm


def test_prefilter_cache_reused_when_fingerprints_match(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    prefilter, llm = _make_prefilter()
    prefilter.filter(_make_content(), "2026-04-26")
    prefilter.filter(_make_content(), "2026-04-26")

    assert llm.prefilter_stories.call_count == 1


def test_prefilter_cache_invalidates_when_comment_preview_count_changes(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    prefilter, llm = _make_prefilter(comment_preview_count=5)
    prefilter.filter(_make_content(), "2026-04-26")

    changed_prefilter = Prefilter(
        llm,
        {
            **prefilter.config,
            "prefilter": {
                **prefilter.config["prefilter"],
                "comment_preview_count": 3,
            },
        },
    )
    changed_prefilter.filter(_make_content(), "2026-04-26")

    assert llm.prefilter_stories.call_count == 2


def test_prefilter_cache_invalidates_when_preview_comment_changes(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    prefilter, llm = _make_prefilter()
    prefilter.filter(_make_content("First comment."), "2026-04-26")
    prefilter.filter(_make_content("Different comment."), "2026-04-26")

    assert llm.prefilter_stories.call_count == 2


def test_prefilter_prefers_bilibili_video_score_over_hn_score(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    content = ContentPackage(
        date="2026-04-26",
        items=[
            ContentItem(
                source="hackernews",
                source_id="1",
                title="High HN score but weak video topic",
                url="https://example.com/1",
                score=500,
                comment_count=100,
            ),
            ContentItem(
                source="hackernews",
                source_id="2",
                title="Lower HN score but strong Bilibili hook",
                url="https://example.com/2",
                score=50,
                comment_count=10,
            ),
        ],
    )
    llm = MagicMock()
    llm.prefilter_stories.return_value = [
        {
            "index": 0,
            "keep": True,
            "reason": "technical but dry",
            "category": "infra",
            "news_focus": 2,
            "newsworthiness": 3,
            "audience_interest": 2,
            "discussion_heat": 5,
        },
        {
            "index": 1,
            "keep": True,
            "reason": "strong news event",
            "category": "ai_company",
            "news_focus": 5,
            "newsworthiness": 4,
            "audience_interest": 5,
            "discussion_heat": 4,
        },
    ]
    prefilter = Prefilter(
        llm,
        {
            "logging": {"level": "WARNING"},
            "pipeline": {"target_story_count": 2},
            "prefilter": {
                "enabled": True,
                "min_keep": 1,
                "min_news_focus": 1,
                "min_newsworthiness": 3,
                "temperature": 0.1,
                "comment_preview_enabled": False,
                "comment_preview_count": 0,
            },
            "llm": {"provider": "test", "model": "test-model"},
        },
        debug=True,
    )

    filtered = prefilter.filter(content, "2026-04-26")

    assert [item.source_id for item in filtered.items] == ["2", "1"]
    assert filtered.items[0].category == "ai_company"


def test_prefilter_requires_news_focus_even_when_hn_score_is_high(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    content = ContentPackage(
        date="2026-04-26",
        items=[
            ContentItem(
                source="hackernews",
                source_id="opinion",
                title="A personal essay about software engineering careers",
                url="https://example.com/opinion",
                score=999,
                comment_count=500,
            ),
            ContentItem(
                source="hackernews",
                source_id="news",
                title="Vendor changes API behavior after outage",
                url="https://example.com/news",
                score=50,
                comment_count=10,
            ),
        ],
    )
    llm = MagicMock()
    llm.prefilter_stories.return_value = [
        {
            "index": 0,
            "keep": True,
            "reason": "popular but mostly opinion",
            "category": "developer_tools",
            "news_focus": 2,
            "newsworthiness": 5,
            "audience_interest": 5,
            "discussion_heat": 5,
        },
        {
            "index": 1,
            "keep": True,
            "reason": "specific API behavior change",
            "category": "infra",
            "news_focus": 4,
            "newsworthiness": 3,
            "audience_interest": 4,
            "discussion_heat": 3,
        },
    ]
    prefilter = Prefilter(
        llm,
        {
            "logging": {"level": "WARNING"},
            "pipeline": {"target_story_count": 2},
            "prefilter": {
                "enabled": True,
                "min_keep": 1,
                "min_news_focus": 4,
                "min_newsworthiness": 3,
                "temperature": 0.1,
                "comment_preview_enabled": False,
                "comment_preview_count": 0,
            },
            "llm": {"provider": "test", "model": "test-model"},
        },
        debug=True,
    )

    filtered = prefilter.filter(content, "2026-04-26")

    assert [item.source_id for item in filtered.items] == ["news"]


def test_prefilter_keeps_high_value_non_news_technical_story(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    content = ContentPackage(
        date="2026-04-26",
        items=[
            ContentItem(
                source="hackernews",
                source_id="experiment",
                title="A reproducible benchmark makes a kernel 232x faster",
                url="https://example.com/experiment",
                score=400,
                comment_count=90,
            ),
            ContentItem(
                source="hackernews",
                source_id="tutorial",
                title="A detailed technical tutorial",
                url="https://example.com/tutorial",
                score=500,
                comment_count=100,
            ),
        ],
    )
    llm = MagicMock()
    llm.prefilter_stories.return_value = [
        {
            "index": 0,
            "keep": True,
            "reason": "reproducible benchmark with a 232x performance improvement",
            "content_type": "technical_experiment",
            "category": "developer_tools",
            "news_focus": 2,
            "newsworthiness": 2,
            "audience_interest": 5,
            "discussion_heat": 4,
            "project_fit": 5,
        },
        {
            "index": 1,
            "keep": True,
            "reason": "useful tutorial but no new result or event",
            "content_type": "tutorial",
            "category": "developer_tools",
            "news_focus": 2,
            "newsworthiness": 4,
            "audience_interest": 5,
            "discussion_heat": 5,
        },
    ]
    prefilter = Prefilter(
        llm,
        {
            "logging": {"level": "WARNING"},
            "pipeline": {"target_story_count": 2},
            "prefilter": {
                "enabled": True,
                "min_keep": 1,
                "min_news_focus": 4,
                "min_newsworthiness": 3,
                "allow_shareable_non_news": True,
                "min_non_news_audience_interest": 4,
                "min_non_news_discussion_heat": 3,
                "temperature": 0.1,
                "comment_preview_enabled": False,
                "comment_preview_count": 0,
            },
            "llm": {"provider": "test", "model": "test-model"},
        },
        debug=True,
    )

    filtered = prefilter.filter(content, "2026-04-26")

    assert [item.source_id for item in filtered.items] == ["experiment"]


def test_prefilter_drops_broad_research_without_project_fit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    content = ContentPackage(
        date="2026-04-26",
        items=[
            ContentItem(
                source="hackernews",
                source_id="health",
                title="A health correlation study without a technology angle",
                url="https://example.com/health",
                score=500,
                comment_count=200,
            )
        ],
    )
    llm = MagicMock()
    llm.prefilter_stories.return_value = [
        {
            "index": 0,
            "keep": True,
            "reason": "popular research result but no technical mechanism",
            "content_type": "research_science",
            "category": "research",
            "news_focus": 4,
            "newsworthiness": 4,
            "audience_interest": 5,
            "discussion_heat": 5,
            "project_fit": 2,
        }
    ]
    prefilter = Prefilter(
        llm,
        {
            "logging": {"level": "WARNING"},
            "pipeline": {"target_story_count": 1},
            "prefilter": {
                "enabled": True,
                "min_keep": 1,
                "min_news_focus": 4,
                "min_newsworthiness": 3,
                "min_project_fit": 3,
                "min_research_project_fit": 4,
                "comment_preview_enabled": False,
                "comment_preview_count": 0,
            },
            "llm": {"provider": "test", "model": "test-model"},
        },
        debug=True,
    )

    filtered = prefilter.filter(content, "2026-04-26")

    assert filtered.items == []


def test_prefilter_does_not_backfill_non_news_to_reach_target_count(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    content = ContentPackage(
        date="2026-04-26",
        items=[
            ContentItem(
                source="hackernews",
                source_id="news",
                title="Project releases a security fix",
                url="https://example.com/news",
                score=50,
                comment_count=10,
            ),
            ContentItem(
                source="hackernews",
                source_id="tutorial",
                title="A detailed technical tutorial",
                url="https://example.com/tutorial",
                score=500,
                comment_count=100,
            ),
        ],
    )
    llm = MagicMock()
    llm.prefilter_stories.return_value = [
        {
            "index": 0,
            "keep": True,
            "reason": "security fix release",
            "content_type": "news_event",
            "category": "security",
            "news_focus": 4,
            "newsworthiness": 3,
            "audience_interest": 4,
            "discussion_heat": 3,
        },
        {
            "index": 1,
            "keep": True,
            "reason": "good tutorial but not news",
            "content_type": "tutorial",
            "category": "developer_tools",
            "news_focus": 2,
            "newsworthiness": 4,
            "audience_interest": 5,
            "discussion_heat": 5,
        },
    ]
    prefilter = Prefilter(
        llm,
        {
            "logging": {"level": "WARNING"},
            "pipeline": {"target_story_count": 2},
            "prefilter": {
                "enabled": True,
                "min_keep": 1,
                "min_news_focus": 4,
                "min_newsworthiness": 3,
                "temperature": 0.1,
                "comment_preview_enabled": False,
                "comment_preview_count": 0,
            },
            "llm": {"provider": "test", "model": "test-model"},
        },
        debug=True,
    )

    filtered = prefilter.filter(content, "2026-04-26")

    assert [item.source_id for item in filtered.items] == ["news"]


def test_prefilter_ranks_by_bilibili_interest_after_news_gate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    content = ContentPackage(
        date="2026-04-26",
        items=[
            ContentItem(
                source="hackernews",
                source_id="dry",
                title="Important but dry standard update",
                url="https://example.com/dry",
                score=300,
                comment_count=80,
            ),
            ContentItem(
                source="hackernews",
                source_id="hook",
                title="Platform outage hits developers in production",
                url="https://example.com/hook",
                score=180,
                comment_count=120,
            ),
        ],
    )
    llm = MagicMock()
    llm.prefilter_stories.return_value = [
        {
            "index": 0,
            "keep": True,
            "reason": "standard update",
            "category": "policy",
            "news_focus": 5,
            "newsworthiness": 4,
            "audience_interest": 2,
            "discussion_heat": 2,
        },
        {
            "index": 1,
            "keep": True,
            "reason": "developer-facing platform outage",
            "category": "infra",
            "news_focus": 4,
            "newsworthiness": 4,
            "audience_interest": 5,
            "discussion_heat": 5,
        },
    ]
    prefilter = Prefilter(
        llm,
        {
            "logging": {"level": "WARNING"},
            "pipeline": {"target_story_count": 2},
            "prefilter": {
                "enabled": True,
                "min_keep": 1,
                "min_news_focus": 4,
                "min_newsworthiness": 3,
                "temperature": 0.1,
                "comment_preview_enabled": False,
                "comment_preview_count": 0,
                "audience_interest_weight": 1.8,
                "discussion_heat_weight": 1.2,
            },
            "llm": {"provider": "test", "model": "test-model"},
        },
        debug=True,
    )

    filtered = prefilter.filter(content, "2026-04-26")

    assert [item.source_id for item in filtered.items] == ["hook", "dry"]


def test_prefilter_caps_valid_news_to_daily_three(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    content = ContentPackage(
        date="2026-04-26",
        items=[
            ContentItem(
                source="hackernews",
                source_id=f"story-{idx}",
                title=f"News story {idx}",
                url=f"https://example.com/{idx}",
                score=100 - idx,
                comment_count=10 + idx,
            )
            for idx in range(5)
        ],
    )
    llm = MagicMock()
    llm.prefilter_stories.return_value = [
        {
            "index": idx,
            "keep": True,
            "reason": "valid news item",
            "category": "tech_news",
            "news_focus": 4,
            "newsworthiness": 3,
            "audience_interest": 5 - idx,
            "discussion_heat": 5 - idx,
        }
        for idx in range(5)
    ]
    prefilter = Prefilter(
        llm,
        {
            "logging": {"level": "WARNING"},
            "pipeline": {"target_story_count": 3},
            "prefilter": {
                "enabled": True,
                "min_keep": 1,
                "min_news_focus": 4,
                "min_newsworthiness": 3,
                "temperature": 0.1,
                "comment_preview_enabled": False,
                "comment_preview_count": 0,
                "audience_interest_weight": 1.8,
                "discussion_heat_weight": 1.2,
            },
            "llm": {"provider": "test", "model": "test-model"},
        },
        debug=True,
    )

    filtered = prefilter.filter(content, "2026-04-26")

    assert [item.source_id for item in filtered.items] == [
        "story-0",
        "story-1",
        "story-2",
    ]


def test_prefilter_uses_deterministic_source_id_tiebreaker(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    content = ContentPackage(
        date="2026-04-26",
        items=[
            ContentItem(
                source="hackernews",
                source_id="z-story",
                title="Story Z",
                url="https://example.com/z",
                score=100,
                comment_count=10,
            ),
            ContentItem(
                source="hackernews",
                source_id="a-story",
                title="Story A",
                url="https://example.com/a",
                score=100,
                comment_count=10,
            ),
        ],
    )
    llm = MagicMock()
    llm.prefilter_stories.return_value = [
        {
            "index": idx,
            "keep": True,
            "reason": "same editorial score",
            "content_type": "news_event",
            "category": "infra",
            "news_focus": 4,
            "newsworthiness": 3,
            "audience_interest": 4,
            "discussion_heat": 3,
        }
        for idx in range(2)
    ]
    prefilter = Prefilter(
        llm,
        {
            "logging": {"level": "WARNING"},
            "pipeline": {"target_story_count": 2},
            "prefilter": {
                "enabled": True,
                "min_keep": 1,
                "min_news_focus": 4,
                "min_newsworthiness": 3,
                "comment_preview_enabled": False,
                "comment_preview_count": 0,
            },
            "llm": {"provider": "test", "model": "test-model"},
        },
        debug=True,
    )

    filtered = prefilter.filter(content, "2026-04-26")

    assert [item.source_id for item in filtered.items] == ["a-story", "z-story"]


def test_prefilter_prioritizes_ai_direction_when_other_scores_match(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    content = ContentPackage(
        date="2026-04-26",
        items=[
            ContentItem(
                source="hackernews",
                source_id="a-general",
                title="A general technology policy event",
                url="https://example.com/general",
                score=100,
                comment_count=10,
            ),
            ContentItem(
                source="hackernews",
                source_id="z-ai",
                title="A new model API changes developer workflows",
                url="https://example.com/ai",
                score=100,
                comment_count=10,
            ),
        ],
    )
    llm = MagicMock()
    llm.prefilter_stories.return_value = [
        {
            "index": 0,
            "keep": True,
            "reason": "specific policy event",
            "content_type": "news_event",
            "category": "policy",
            "news_focus": 4,
            "newsworthiness": 3,
            "audience_interest": 4,
            "discussion_heat": 3,
            "project_fit": 4,
            "ai_relevance": 1,
        },
        {
            "index": 1,
            "keep": True,
            "reason": "specific model API change",
            "content_type": "news_event",
            "category": "ai_product",
            "news_focus": 4,
            "newsworthiness": 3,
            "audience_interest": 4,
            "discussion_heat": 3,
            "project_fit": 4,
            "ai_relevance": 5,
        },
    ]
    prefilter = Prefilter(
        llm,
        {
            "logging": {"level": "WARNING"},
            "pipeline": {"target_story_count": 2},
            "prefilter": {
                "enabled": True,
                "min_keep": 1,
                "min_news_focus": 4,
                "min_newsworthiness": 3,
                "ai_relevance_weight": 1.5,
                "comment_preview_enabled": False,
                "comment_preview_count": 0,
            },
            "llm": {"provider": "test", "model": "test-model"},
        },
        debug=True,
    )

    filtered = prefilter.filter(content, "2026-04-26")

    assert [item.source_id for item in filtered.items] == ["z-ai", "a-general"]
