import json

import numpy as np
import pytest

from src.core.models import ContentItem
from src.pipeline.comment.stance_v2 import (
    StanceV2Record,
    assign_splits,
    build_v2_input,
    core_claim_for_item,
    distribution_from_probabilities,
    distribution_mae_pp,
    load_records,
    sample_records,
    save_records,
    split_story_ids,
)


def _record(story_id: str, comment_id: str, label: str | None = None):
    return StanceV2Record(
        id=f"{story_id}:{comment_id}",
        story_id=story_id,
        comment_id=comment_id,
        story_title=f"Story {story_id}",
        core_claim=f"Claim for {story_id}",
        comment_text=f"Comment {comment_id} with enough context to evaluate.",
        label=label,
    )


def test_core_claim_prefers_existing_editor_angle():
    item = ContentItem(
        source="hackernews",
        source_id="story",
        title="A title",
        url=None,
        editor_angle="The editor angle is the core claim.",
        why_it_matters="A different explanation.",
    )

    assert core_claim_for_item(item) == "The editor angle is the core claim."


def test_v2_input_keeps_story_claim_and_comment_separate():
    text = build_v2_input("A story", "The core claim", "A comment")

    assert "[STORY TITLE]\nA story" in text
    assert "[CORE CLAIM]\nThe core claim" in text
    assert text.endswith("[COMMENT]\nA comment")


def test_v2_input_includes_parent_context_when_available():
    text = build_v2_input(
        "A story",
        "The core claim",
        "A reply",
        parent_text="The parent comment",
    )

    assert "[PARENT COMMENT]\nThe parent comment" in text


def test_record_round_trip_keeps_parent_context(tmp_path):
    path = tmp_path / "dataset.json"
    original = _record("a", "1", "support")
    original.parent_id = "0"
    original.parent_text = "Parent context"
    save_records(path, [original])

    loaded = load_records(path)

    assert loaded[0].parent_id == "0"
    assert loaded[0].parent_text == "Parent context"


def test_split_story_ids_is_deterministic_and_disjoint():
    stories = [f"story-{index}" for index in range(10)]
    first = split_story_ids(stories, seed=7)
    second = split_story_ids(stories, seed=7)

    assert first == second
    assert set(first.values()) == {"train", "validation", "test"}
    assert (
        len(set(first) & {story for story, split in first.items() if split == "test"})
        > 0
    )
    assert sum(value == "train" for value in first.values()) >= 1
    assert sum(value == "validation" for value in first.values()) >= 1
    assert sum(value == "test" for value in first.values()) >= 1


def test_assign_splits_assigns_one_split_per_story():
    records = [_record("a", str(index)) for index in range(3)]
    records.extend(_record("b", str(index)) for index in range(3))
    records.extend(_record("c", str(index)) for index in range(3))

    assign_splits(records, seed=9)

    assert all(record.split in {"train", "validation", "test"} for record in records)
    assert len({record.split for record in records if record.story_id == "a"}) == 1
    assert len({record.split for record in records if record.story_id == "b"}) == 1
    assert len({record.split for record in records if record.story_id == "c"}) == 1


def test_sample_records_is_stable_and_caps_each_story():
    records = [_record("a", str(index)) for index in range(8)]
    records.extend(_record("b", str(index)) for index in range(4))

    first = sample_records(records, sample_per_story=3, seed=11)
    second = sample_records(records, sample_per_story=3, seed=11)

    assert [record.id for record in first] == [record.id for record in second]
    assert len(first) == 6
    assert {record.story_id for record in first} == {"a", "b"}


def test_save_and_load_records_round_trip(tmp_path):
    path = tmp_path / "dataset.json"
    original = [_record("a", "1", "support"), _record("b", "2")]
    original[0].confidence = 0.82
    original[0].split = "train"
    save_records(path, original)

    payload = json.loads(path.read_text(encoding="utf-8"))
    loaded = load_records(path)

    assert payload["schema_version"] == 1
    assert loaded[0].to_dict() == original[0].to_dict()
    assert loaded[1].label is None


def test_load_records_rejects_unknown_label(tmp_path):
    path = tmp_path / "dataset.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "records": [_record("a", "1").to_dict() | {"label": "unknown"}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unknown stance V2 label"):
        load_records(path)


def test_distribution_uses_soft_probabilities_and_sums_to_one():
    probabilities = np.array(
        [
            [0.8, 0.1, 0.1],
            [0.2, 0.7, 0.1],
        ]
    )
    distribution = distribution_from_probabilities(
        probabilities,
        ["support", "skeptic", "neutral"],
        prior=1.0,
    )

    assert set(distribution) == {"support", "skeptic", "neutral"}
    assert abs(sum(distribution.values()) - 1.0) < 0.001
    assert distribution["support"] > distribution["neutral"]


def test_distribution_mae_is_in_percentage_points():
    predicted = {"support": 0.5, "skeptic": 0.25, "neutral": 0.25}

    assert distribution_mae_pp(
        ["support", "support", "skeptic", "neutral"], predicted
    ) == pytest.approx(0.0)
