import json

from src.core.models import ContentComment, ContentItem, ContentPackage
from src.pipeline.comment.stance_classifier import (
    StanceExample,
    append_labeled_examples,
    embedding_ready_text,
    iter_comment_examples,
    load_labeled_examples,
    predict_item_stance_distribution,
    train_stance_classifier,
)


def _comment(source_id, content, **kwargs):
    defaults = {
        "author": "user",
        "content": content,
        "source_id": source_id,
        "quality_score": 0.4,
        "depth": 0,
    }
    defaults.update(kwargs)
    return ContentComment(**defaults)


def _item(comments):
    return ContentItem(
        source="hackernews",
        source_id="story",
        title="A deployment tool claims safer rollbacks",
        url="https://example.com",
        article_summary="The story claims the tool makes production rollback safer.",
        published_at=1700000000,
        comments=comments,
    )


def _examples():
    rows = []
    for i in range(6):
        rows.append(
            StanceExample(
                id=f"s:sup{i}",
                story_id="s",
                comment_id=f"sup{i}",
                text=(
                    "[STORY]\nA tool improves production rollback.\n\n"
                    "[COMMENT]\nThis is useful and makes rollback simpler."
                ),
                label="support",
                confidence=0.9,
            )
        )
        rows.append(
            StanceExample(
                id=f"s:sk{i}",
                story_id="s",
                comment_id=f"sk{i}",
                text=(
                    "[STORY]\nA tool improves production rollback.\n\n"
                    "[COMMENT]\nI am skeptical because this breaks production rollback."
                ),
                label="skeptic",
                confidence=0.9,
            )
        )
        rows.append(
            StanceExample(
                id=f"s:neu{i}",
                story_id="s",
                comment_id=f"neu{i}",
                text=(
                    "[STORY]\nA tool improves production rollback.\n\n"
                    "[COMMENT]\nActually this is similar to an older deployment tool."
                ),
                label="neutral",
                confidence=0.9,
            )
        )
    return rows


def test_label_file_append_deduplicates(tmp_path):
    path = tmp_path / "labels.jsonl"
    examples = _examples()[:2]

    append_labeled_examples(path, examples)
    append_labeled_examples(path, examples)

    loaded = load_labeled_examples(path)
    assert [example.id for example in loaded] == [example.id for example in examples]
    assert len(path.read_text(encoding="utf-8").strip().splitlines()) == 2


def test_iter_comment_examples_filters_short_and_resource_only():
    content = ContentPackage(
        date="2026-04-26",
        items=[
            _item(
                [
                    _comment("short", "ok"),
                    _comment("link", "Related: https://example.com/writeup"),
                    _comment("good", "This is useful because rollback is hard."),
                ]
            )
        ],
    )

    examples = list(iter_comment_examples(content))

    assert [example.comment_id for example in examples] == ["good"]


def test_trained_classifier_outputs_zh_distribution():
    model = train_stance_classifier(_examples(), backend="tfidf")
    item = _item(
        [
            _comment("support", "This is useful and makes rollback simpler."),
            _comment("skeptic", "I am skeptical because this breaks rollback."),
            _comment("neutral", "Actually this is similar to an older tool."),
        ]
    )

    distribution = predict_item_stance_distribution(model, item)

    assert set(distribution) == {"支持", "质疑", "中立"}
    assert abs(sum(distribution.values()) - 1.0) < 0.001


def test_unknown_training_backend_rejected():
    try:
        train_stance_classifier(_examples(), backend="unknown")
    except ValueError as exc:
        assert "Unknown stance classifier backend" in str(exc)
    else:
        raise AssertionError("expected unknown backend to fail")


def test_embedding_ready_text_moves_comment_before_story():
    text = "[STORY]\nLong story context\n\n[COMMENT]\nThis is the actual stance."

    prepared = embedding_ready_text(text)

    assert prepared.startswith("[COMMENT]\nThis is the actual stance.")
    assert "[STORY]\nLong story context" in prepared
