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

    changed_prefilter = Prefilter(llm, {
        **prefilter.config,
        "prefilter": {
            **prefilter.config["prefilter"],
            "comment_preview_count": 3,
        },
    })
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
        },
        {
            "index": 1,
            "keep": True,
            "reason": "strong news event",
            "category": "ai_company",
            "news_focus": 5,
            "newsworthiness": 4,
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
        },
        {
            "index": 1,
            "keep": True,
            "reason": "specific API behavior change",
            "category": "infra",
            "news_focus": 4,
            "newsworthiness": 3,
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
            "category": "security",
            "news_focus": 4,
            "newsworthiness": 3,
        },
        {
            "index": 1,
            "keep": True,
            "reason": "good tutorial but not news",
            "category": "developer_tools",
            "news_focus": 2,
            "newsworthiness": 4,
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
