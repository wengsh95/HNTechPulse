import json
from pathlib import Path
from unittest.mock import patch


from src.core.models import ContentComment, ContentItem, ContentPackage
from src.pipeline.comment import CommentAnalyzer, ANALYSIS_SCHEMA_VERSION


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
        with patch("src.pipeline.comment.judge.setup_logger"):
            analyzer = CommentAnalyzer(_make_config())
        comment = _make_comment()
        content = _make_content_package([_make_item(comments=[comment])])

        result = analyzer.analyze(content, "2026-04-26")

        assert result.items[0].comments[0].sentiment is not None
        assert result.items[0].comments[0].quality_score is not None
        assert result.items[0].comments[0].quality_score > 0

    def test_analyze_disabled_returns_unchanged(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("src.pipeline.comment.judge.setup_logger"):
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

        with patch("src.pipeline.comment.judge.setup_logger"):
            analyzer = CommentAnalyzer(_make_config())
        result = analyzer.analyze(content, "2026-04-26")

        assert result.items[0].comments[0].sentiment == 0.99
        assert result.items[0].comments[0].quality_score == 0.88


class TestGetTopComments:
    def test_returns_highest_quality(self):
        with patch("src.pipeline.comment.judge.setup_logger"):
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
        with patch("src.pipeline.comment.judge.setup_logger"):
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
        with patch("src.pipeline.comment.judge.setup_logger"):
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


class TestGetJudgeCandidates:
    def test_balanced_keeps_minority_negative_and_deep_replies(self):
        with patch("src.pipeline.comment.judge.setup_logger"):
            analyzer = CommentAnalyzer(
                _make_config(
                    judge_candidate_strategy="balanced",
                    judge_candidate_min_quality=0.05,
                )
            )
        comments = [
            _make_comment(
                content=(
                    "This is a strong positive comment about the design because it "
                    "makes the common path much simpler for teams."
                ),
                source_id=f"pos{i}",
                quality_score=0.8 - i * 0.01,
                sentiment=0.6,
                depth=0,
            )
            for i in range(8)
        ]
        comments.extend(
            [
                _make_comment(
                    content=(
                        "I am skeptical because this can fail in production when "
                        "deployment and rollback behavior diverge."
                    ),
                    source_id="neg",
                    quality_score=0.45,
                    sentiment=-0.7,
                    depth=0,
                ),
                _make_comment(
                    content=(
                        "In production we used a similar approach and the hard part "
                        "was debugging state after partial migrations."
                    ),
                    source_id="deep",
                    quality_score=0.42,
                    sentiment=-0.1,
                    depth=3,
                ),
            ]
        )
        item = _make_item(
            title="Production deployment migration tool",
            article_summary="A tool changes deployment and rollback behavior.",
            comments=comments,
        )

        selected = analyzer.get_judge_candidates(item, n=8)
        selected_ids = {c.source_id for c in selected}

        assert "neg" in selected_ids
        assert "deep" in selected_ids
        assert len(selected) <= 8

    def test_balanced_filters_resource_only_comments(self):
        with patch("src.pipeline.comment.judge.setup_logger"):
            analyzer = CommentAnalyzer(
                _make_config(judge_candidate_strategy="balanced")
            )
        item = _make_item(
            comments=[
                _make_comment(
                    content="Related article: https://example.com/writeup",
                    source_id="link",
                    quality_score=0.95,
                ),
                _make_comment(
                    content=(
                        "The practical concern is that this changes operational "
                        "failure modes for the team maintaining it."
                    ),
                    source_id="view",
                    quality_score=0.55,
                ),
            ]
        )

        selected = analyzer.get_judge_candidates(item, n=5)

        assert [c.source_id for c in selected] == ["view"]

    def test_top_quality_strategy_uses_original_ranking(self):
        with patch("src.pipeline.comment.judge.setup_logger"):
            analyzer = CommentAnalyzer(
                _make_config(
                    judge_candidate_strategy="top_quality",
                    min_quality_score=0.0,
                )
            )
        item = _make_item(
            comments=[
                _make_comment(source_id="low", quality_score=0.2),
                _make_comment(source_id="high", quality_score=0.9),
            ]
        )

        selected = analyzer.get_judge_candidates(item, n=1)

        assert selected[0].source_id == "high"
