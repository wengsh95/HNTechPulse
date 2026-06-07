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
            "china_interest": 4,
            "newsworthiness": 4,
            "click_potential": 4,
            "discussion_potential": 3,
            "creator_value": 4,
            "retention_value": 4,
            "headline_hook": "Meta 自家 AI 聊天机器人",
            "cover_hook": "Windows PC 造 CPU",
            "debate_angle": "AI 产品 新攻击面",
        }
    ]
    config = {
        "logging": {"level": "WARNING"},
        "pipeline": {"target_story_count": 1},
        "prefilter": {
            "enabled": True,
            "min_keep": 1,
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


def test_prefilter_normalizes_hook_spacing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    prefilter, _ = _make_prefilter()

    filtered = prefilter.filter(_make_content(), "2026-04-26")

    item = filtered.items[0]
    assert item.headline_hook == "Meta自家AI聊天机器人"
    assert item.cover_hook == "Windows PC造CPU"
    assert item.debate_angle == "AI产品新攻击面"


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
            "china_interest": 2,
            "newsworthiness": 3,
            "click_potential": 1,
            "discussion_potential": 1,
            "creator_value": 2,
            "retention_value": 2,
        },
        {
            "index": 1,
            "keep": True,
            "reason": "strong video topic",
            "category": "ai_company",
            "china_interest": 4,
            "newsworthiness": 4,
            "click_potential": 5,
            "discussion_potential": 5,
            "creator_value": 5,
            "retention_value": 4,
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
