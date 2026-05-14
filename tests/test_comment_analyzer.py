import json
from pathlib import Path
from unittest.mock import patch


from src.core.models import ContentComment, ContentItem, ContentPackage
from src.pipeline.comment_analyzer import CommentAnalyzer, ANALYSIS_SCHEMA_VERSION


def _make_config(**overrides):
    cfg = {
        "logging": {"level": "WARNING"},
        "analyze": {
            "enabled": True,
            "min_quality_score": 0.1,
            "max_comments_for_llm": 10,
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


class TestAnalyze:
    def test_analyze_sets_sentiment_and_quality_score(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("src.pipeline.comment_analyzer.setup_logger"):
            analyzer = CommentAnalyzer(_make_config())
        comment = _make_comment()
        content = _make_content_package([_make_item(comments=[comment])])

        result = analyzer.analyze(content, "2026-04-26")

        assert result.items[0].comments[0].sentiment is not None
        assert result.items[0].comments[0].quality_score is not None
        assert result.items[0].comments[0].quality_score > 0

    def test_analyze_disabled_returns_unchanged(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("src.pipeline.comment_analyzer.setup_logger"):
            analyzer = CommentAnalyzer(_make_config(enabled=False))
        content = _make_content_package()

        result = analyzer.analyze(content, "2026-04-26")
        assert result is content

    def test_analyze_uses_cache_when_exists(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        comment = _make_comment()
        item = _make_item(comments=[comment])
        content = _make_content_package([item])

        # Create cache
        cache_path = Path("data/2026-04-26/comment_analysis.json")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_data = {
            "schema_version": ANALYSIS_SCHEMA_VERSION,
            "date": "2026-04-26",
            "items": [
                {
                    "source_id": "100",
                    "comments": [
                        {
                            "source_id": "c1",
                            "sentiment": 0.99,
                            "quality_score": 0.88,
                        }
                    ],
                }
            ],
        }
        cache_path.write_text(json.dumps(cache_data), encoding="utf-8")

        with patch("src.pipeline.comment_analyzer.setup_logger"):
            analyzer = CommentAnalyzer(_make_config())
        result = analyzer.analyze(content, "2026-04-26")

        assert result.items[0].comments[0].sentiment == 0.99
        assert result.items[0].comments[0].quality_score == 0.88


class TestGetTopComments:
    def test_returns_highest_quality(self):
        with patch("src.pipeline.comment_analyzer.setup_logger"):
            analyzer = CommentAnalyzer(_make_config(min_quality_score=0.0))
        comments = [
            _make_comment(
                content="Low quality short", source_id="c1", quality_score=0.1
            ),
            _make_comment(
                content="High quality comment with enough length to score well",
                source_id="c2",
                quality_score=0.9,
            ),
            _make_comment(
                content="Medium quality comment with enough length to score well",
                source_id="c3",
                quality_score=0.5,
            ),
        ]
        item = _make_item(comments=comments)

        top = analyzer.get_top_comments(item, n=2)
        assert len(top) == 2
        assert top[0].quality_score >= top[1].quality_score

    def test_respects_n_limit(self):
        with patch("src.pipeline.comment_analyzer.setup_logger"):
            analyzer = CommentAnalyzer(_make_config())
        comments = [
            _make_comment(
                content=f"Comment {i} with enough length",
                source_id=f"c{i}",
                quality_score=0.5,
            )
            for i in range(10)
        ]
        item = _make_item(comments=comments)

        top = analyzer.get_top_comments(item, n=3)
        assert len(top) == 3

    def test_filters_below_min_quality(self):
        with patch("src.pipeline.comment_analyzer.setup_logger"):
            analyzer = CommentAnalyzer(_make_config(min_quality_score=0.5))
        comments = [
            _make_comment(
                content="Low quality short", source_id="c1", quality_score=0.1
            ),
            _make_comment(
                content="High quality comment with enough length to score well",
                source_id="c2",
                quality_score=0.8,
            ),
        ]
        item = _make_item(comments=comments)

        top = analyzer.get_top_comments(item, n=10)
        assert len(top) == 1
        assert top[0].source_id == "c2"
