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
            "ai_relevance": 4,
            "newsworthiness": 4,
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
