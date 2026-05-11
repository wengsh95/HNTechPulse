from src.core.models import ContentComment, ContentItem, ContentPackage
from src.pipeline.comment_judgement import (
    candidate_ids_for_story,
    normalize_story_judgement,
    selected_ids_from_judgements,
    save_comment_judgements,
)
from src.pipeline.comment_selection import select_quote_comments


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


def test_selected_ids_from_judgements_loads_stable_cache(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    content = ContentPackage(date="2026-05-11", items=[_item()])
    save_comment_judgements(
        content.date,
        {
            "story": {
                "story_id": "story",
                "quote_candidates": [
                    {"comment_id": "skeptic", "quote_score": 0.9, "has_viewpoint": True},
                    {"comment_id": "ops", "quote_score": 0.8, "has_viewpoint": True},
                ],
            }
        },
    )
    assert selected_ids_from_judgements(content.date, content) == {0: ["skeptic", "ops"]}


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
