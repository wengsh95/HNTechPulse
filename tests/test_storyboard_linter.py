"""Unit tests for storyboard_linter."""

from src.pipeline.paths import pipeline_path
from src.pipeline.storyboard_linter import lint_storyboard_and_script
from src.utils.atomic_io import atomic_write_json


def test_storyboard_linter_catches_missing_props(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-08-18"

    # Create invalid storyboard where closing_v1 has empty props
    atomic_write_json(
        pipeline_path(date, "storyboard.json"),
        {
            "schema_version": 1,
            "date": date,
            "shots": [
                {
                    "shot_id": "S01-01",
                    "template_id": "cover_v1",
                    "props": {},  # missing headline
                },
                {
                    "shot_id": "S04-01",
                    "template_id": "closing_v1",
                    "props": {},  # empty closing
                },
            ],
        },
    )

    issues = lint_storyboard_and_script(date)
    errors = [i for i in issues if i.level == "error"]

    assert len(errors) >= 2
    categories = {e.category for e in errors}
    assert "missing_props" in categories
    assert "empty_closing" in categories


def test_storyboard_linter_passes_valid_storyboard(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-08-18"

    atomic_write_json(
        pipeline_path(date, "storyboard.json"),
        {
            "schema_version": 1,
            "date": date,
            "shots": [
                {
                    "shot_id": "S01-01",
                    "template_id": "cover_v1",
                    "props": {"headline": "每日HN日报"},
                },
                {
                    "shot_id": "S04-01",
                    "template_id": "closing_v1",
                    "props": {"summary_items": [{"title": "新闻1", "signal": "信号1"}]},
                },
            ],
        },
    )

    issues = lint_storyboard_and_script(date)
    errors = [i for i in issues if i.level == "error"]
    assert len(errors) == 0
