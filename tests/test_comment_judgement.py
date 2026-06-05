from src.core.models import ContentComment, ContentItem
from src.pipeline.comment import (
    candidate_ids_for_story,
    comment_judgement_key,
    normalize_story_judgement,
    select_quote_comments,
)


def test_comment_judgement_key_rejects_none_source_id():
    """Items without source_id used to collide on the string 'None'."""
    item = ContentItem(
        source="hn",
        source_id=None,
        title="orphan",
        url=None,
        published_at=0,
        comments=[],
    )
    import pytest

    with pytest.raises(ValueError, match="source_id"):
        comment_judgement_key(item)


def _item():
    return ContentItem(
        source="hn",
        source_id="story",
        title="Story",
        url=None,
        published_at=0,
        comments=[
            ContentComment(
                author="linker",
                content="Here is a related article: https://example.com",
                source_id="link",
                quality_score=0.95,
            ),
            ContentComment(
                author="skeptic",
                content="I am skeptical because this moves the failure boundary from code to operations.",
                source_id="skeptic",
                quality_score=0.7,
            ),
            ContentComment(
                author="operator",
                content="In production this usually fails when the deploy process assumes one platform.",
                source_id="ops",
                quality_score=0.65,
            ),
            ContentComment(
                author="supporter",
                content="The idea is useful, but it should document unsupported cases clearly.",
                source_id="support",
                quality_score=0.6,
            ),
        ],
    )


def test_normalize_story_judgement_drops_unknown_ids_and_orders_by_score():
    item = _item()
    result = normalize_story_judgement(
        {
            "quote_candidates": [
                {"comment_id": "missing", "quote_score": 1},
                {"comment_id": "ops", "quote_score": 0.7, "has_viewpoint": True},
                {"comment_id": "skeptic", "quote_score": 0.9, "has_viewpoint": True},
            ]
        },
        item,
    )
    assert [c["comment_id"] for c in result["quote_candidates"]] == ["skeptic", "ops"]


def test_select_quote_comments_uses_judgement_before_heuristic_fallback():
    item = _item()
    judgement = normalize_story_judgement(
        {
            "quote_candidates": [
                {"comment_id": "support", "quote_score": 0.95, "has_viewpoint": True},
                {"comment_id": "ops", "quote_score": 0.9, "has_viewpoint": True},
            ]
        },
        item,
    )
    selected = select_quote_comments(
        item.comments,
        selected_ids=["skeptic"],
        judgement=judgement,
    )
    assert [c.source_id for c in selected] == ["skeptic", "support", "ops"]


def test_candidate_ids_skip_rejected_candidates():
    ids = candidate_ids_for_story(
        {
            "quote_candidates": [
                {"comment_id": "link", "reject_for_quote": True},
                {"comment_id": "view", "has_viewpoint": True},
            ]
        }
    )
    assert ids == ["view"]


def test_normalize_story_judgement_supports_discussion_modes_and_lanes():
    item = _item()
    result = normalize_story_judgement(
        {
            "discussion_mode": "field_notes",
            "discussion_summary": "评论区主要在补充生产经验",
            "confidence": 0.7,
            "comment_lanes": {
                "representative": [
                    {
                        "comment_id": "ops",
                        "role": "experience",
                        "stance": "中立",
                        "claim": "生产环境里部署假设最容易出问题",
                        "quote_score": 0.9,
                    }
                ],
                "color": [
                    {
                        "comment_id": "missing",
                        "role": "memorable_line",
                        "claim": "should be dropped",
                        "quote_score": 1.0,
                    }
                ],
            },
        },
        item,
    )

    assert result["discussion_mode"] == "field_notes"
    assert result["discussion_summary"] == "评论区主要在补充生产经验"
    assert result["comment_lanes"]["representative"][0]["comment_id"] == "ops"
    assert result["comment_lanes"]["color"] == []


def test_normalize_story_judgement_rejects_overlong_lane_claim():
    item = _item()
    try:
        normalize_story_judgement(
            {
                "comment_lanes": {
                    "representative": [
                        {
                            "comment_id": "ops",
                            "role": "experience",
                            "stance": "中立",
                            "claim": "这是一条故意写得非常非常长的观点摘要不应该被自动截断继续通过这是一条故意写得非常非常长的观点摘要不应该被自动截断继续通过",
                            "quote_score": 0.9,
                        }
                    ]
                },
            },
            item,
        )
    except ValueError as exc:
        assert "claim exceeds" in str(exc)
    else:
        raise AssertionError("expected overlong claim to fail")
