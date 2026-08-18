from src.core.models import ContentComment, ContentItem
from src.pipeline.comment import (
    candidate_ids_for_story,
    comment_judgement_key,
    distribution_sample_size,
    normalize_story_judgement,
    select_quote_comments,
    select_distribution_comments,
)


def test_distribution_sample_size_scales_with_population():
    assert distribution_sample_size(200) == 200
    assert distribution_sample_size(300) == 169
    assert distribution_sample_size(1000) == 278
    assert distribution_sample_size(10_000_000) == 385


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


def test_normalize_story_judgement_recovers_unique_author_alias():
    item = _item()
    item.comments[1].author = "alice"
    result = normalize_story_judgement(
        {
            "comment_lanes": {
                "representative": [
                    {
                        "comment_id": "alice",
                        "claim": "作者名误填时也应恢复真实评论",
                        "quote_score": 0.8,
                    }
                ]
            }
        },
        item,
    )

    assert result["quote_candidates"][0]["comment_id"] == "skeptic"


def test_normalize_story_judgement_falls_back_to_story_title_target():
    result = normalize_story_judgement({}, _item())

    assert result["discussion_target"] == "Story"


def test_normalize_story_judgement_promotes_strong_color_quote():
    item = _item()
    result = normalize_story_judgement(
        {
            "comment_lanes": {
                "color": [
                    {
                        "comment_id": "support",
                        "role": "memorable_line",
                        "stance": "中立",
                        "claim": "把平台权限当自由证明，多少有点荒诞",
                        "quote_score": 0.82,
                    }
                ]
            },
            "quote_candidates": [
                {"comment_id": "skeptic", "quote_score": 0.95, "has_viewpoint": True},
                {"comment_id": "ops", "quote_score": 0.9, "has_viewpoint": True},
            ],
        },
        item,
    )

    assert [c["comment_id"] for c in result["quote_candidates"]][:3] == [
        "support",
        "skeptic",
        "ops",
    ]


def test_normalize_story_judgement_caps_overheated_quote_claims():
    item = _item()
    result = normalize_story_judgement(
        {
            "comment_lanes": {
                "color": [
                    {
                        "comment_id": "support",
                        "role": "memorable_line",
                        "stance": "质疑",
                        "claim": "这产品完蛋了只剩垃圾决策",
                        "quote_score": 0.98,
                    }
                ]
            },
            "quote_candidates": [
                {"comment_id": "skeptic", "quote_score": 0.9, "has_viewpoint": True},
            ],
        },
        item,
    )

    by_id = {c["comment_id"]: c for c in result["quote_candidates"]}
    assert by_id["support"]["quote_score"] == 0.68
    assert result["quote_candidates"][0]["comment_id"] == "skeptic"
    assert result["comment_lanes"]["color"] == []


def test_normalize_story_judgement_caps_lazy_color_labels():
    item = _item()
    result = normalize_story_judgement(
        {
            "comment_lanes": {
                "color": [
                    {
                        "comment_id": "support",
                        "role": "memorable_line",
                        "stance": "质疑",
                        "claim": "政客自己免扫描，讽刺",
                        "quote_score": 0.94,
                    }
                ]
            },
            "quote_candidates": [
                {"comment_id": "skeptic", "quote_score": 0.86, "has_viewpoint": True},
            ],
        },
        item,
    )

    by_id = {c["comment_id"]: c for c in result["quote_candidates"]}
    assert by_id["support"]["quote_score"] == 0.72
    assert result["quote_candidates"][0]["comment_id"] == "skeptic"
    assert result["comment_lanes"]["color"] == []


def test_normalize_story_judgement_caps_overlong_quote_claims():
    item = _item()
    result = normalize_story_judgement(
        {
            "quote_candidates": [
                {
                    "comment_id": "support",
                    "claim": "这是一条长度明显超过软上限的金句候选因为它把太多解释都塞进同一句里所以读起来像段长摘要",
                    "quote_score": 0.95,
                    "has_viewpoint": True,
                },
                {"comment_id": "skeptic", "quote_score": 0.86, "has_viewpoint": True},
            ],
        },
        item,
    )

    by_id = {c["comment_id"]: c for c in result["quote_candidates"]}
    assert by_id["support"]["quote_score"] == 0.76
    assert result["quote_candidates"][0]["comment_id"] == "skeptic"


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


def test_normalize_story_judgement_aggregates_per_comment_stance_labels():
    item = _item()
    item.comments[2].depth = 2
    item.comments[2].parent_text = "The parent comment gives context."
    result = normalize_story_judgement(
        {
            "stance_labels": [
                {
                    "comment_id": "ops",
                    "stance": "support",
                    "confidence": 0.9,
                    "context_sufficient": True,
                },
                {
                    "comment_id": "support",
                    "stance": "skeptic",
                    "confidence": 0.8,
                    "context_sufficient": True,
                },
            ]
        },
        item,
        distribution_ids={"ops", "support"},
    )

    assert result["stance_distribution_meta"]["source"] == "llm_per_comment"
    assert result["stance_distribution_meta"]["context_sufficient_count"] == 2
    assert set(result["stance_distribution"]) == {"支持", "质疑", "中立"}


def test_distribution_sample_is_stable_and_excludes_contextless_replies():
    item = _item()
    item.comments[0].depth = 2
    item.comments[0].parent_text = None
    item.comments[1].depth = 2
    item.comments[1].parent_text = "The parent gives the missing context."

    first = select_distribution_comments(item, max_n=2)
    second = select_distribution_comments(item, max_n=2)

    assert [comment.source_id for comment in first] == [
        comment.source_id for comment in second
    ]
    assert "link" not in {comment.source_id for comment in first}
