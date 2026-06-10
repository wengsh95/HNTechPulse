from unittest.mock import patch, MagicMock

import pytest

from src.core.interfaces import LLMProvider
from src.core.models import ContentComment, ContentItem, ContentPackage
from src.pipeline.comment import CommentJudge, comment_judgement_key


def _make_config(**overrides):
    cfg = {
        "logging": {"level": "WARNING"},
        "analyze": {
            "comment_judge_enabled": True,
            "comment_judge_max_workers": 1,
            "max_comments_for_judge": 8,
        },
    }
    cfg["analyze"].update(overrides)
    return cfg


def _make_comment(
    content="This is a test comment with enough length to score well", **kwargs
):
    defaults = {
        "author": "user",
        "content": content,
        "source_id": "c1",
        "quality_score": 0.5,
    }
    defaults.update(kwargs)
    return ContentComment(**defaults)


def _make_item(comments=None, **kwargs):
    defaults = {
        "source": "hackernews",
        "source_id": "100",
        "title": "Test Story",
        "url": "https://example.com",
        "score": 50,
        "comment_count": len(comments or []),
        "published_at": 1700000000,
        "comments": comments or [],
    }
    defaults.update(kwargs)
    return ContentItem(**defaults)


def _make_content_package(items=None):
    if items is None:
        items = [_make_item()]
    return ContentPackage(date="2026-04-26", items=items)


def _make_judge(**config_overrides):
    mock_llm = MagicMock(spec=LLMProvider)
    with patch("src.pipeline.comment.judge.setup_logger"):
        judge = CommentJudge(mock_llm, _make_config(**config_overrides))
    return judge, mock_llm


class TestJudge:
    def test_disabled_raises_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        comment = _make_comment(source_id="c1", quality_score=0.6)
        item = _make_item(comments=[comment], source_id="100")
        content = _make_content_package([item])

        judge, mock_llm = _make_judge(comment_judge_enabled=False)
        with pytest.raises(RuntimeError, match="Comment judge disabled"):
            judge.judge(content, "2026-04-26")
        mock_llm.judge_story_comments.assert_not_called()

    def judge_uses_llm_provider(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        comment = _make_comment(source_id="c1", quality_score=0.6)
        item = _make_item(comments=[comment], source_id="100")
        content = _make_content_package([item])

        mock_llm = MagicMock(spec=LLMProvider)
        mock_llm.judge_story_comments.return_value = {
            "selected_comment_ids": ["c1"],
            "quote_candidates": [
                {"comment_id": "c1", "quote_score": 0.9, "has_viewpoint": True}
            ],
            "debate_focus": [],
            "stance_distribution": {},
        }

        with patch("src.pipeline.comment.judge.setup_logger"):
            judge = CommentJudge(mock_llm, _make_config())
        result = judge.judge(content, "2026-04-26")

        mock_llm.judge_story_comments.assert_called_once()
        key = comment_judgement_key(item)
        assert key in result
        assert len(result[key]["quote_candidates"]) > 0

    def test_raises_on_llm_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        comment = _make_comment(source_id="c1", quality_score=0.6)
        item = _make_item(comments=[comment], source_id="100")
        content = _make_content_package([item])

        mock_llm = MagicMock(spec=LLMProvider)
        mock_llm.judge_story_comments.side_effect = RuntimeError("LLM failed")

        with patch("src.pipeline.comment.judge.setup_logger"):
            judge = CommentJudge(mock_llm, _make_config())
        with pytest.raises(RuntimeError, match="LLM failed"):
            judge.judge(content, "2026-04-26")

    def test_uses_balanced_prefilter_when_available(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        comment = _make_comment(source_id="c1", quality_score=0.6)
        item = _make_item(comments=[comment], source_id="100")
        content = _make_content_package([item])

        mock_llm = MagicMock(spec=LLMProvider)
        mock_llm.judge_story_comments.return_value = {
            "quote_candidates": [
                {"comment_id": "c1", "quote_score": 0.9, "has_viewpoint": True}
            ]
        }
        analyzer = MagicMock()
        analyzer.get_judge_candidates.return_value = [comment]

        with patch("src.pipeline.comment.judge.setup_logger"):
            judge = CommentJudge(mock_llm, _make_config(), comment_analyzer=analyzer)

        judge.judge(content, "2026-04-26")

        analyzer.get_judge_candidates.assert_called_once_with(
            item, n=judge.judge_candidate_count
        )
        mock_llm.judge_story_comments.assert_called_once()
        assert mock_llm.judge_story_comments.call_args.kwargs["candidates"] == [comment]
