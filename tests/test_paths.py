from pathlib import Path

from src.pipeline.paths import date_root, pipeline_path


def test_date_root_groups_by_month():
    assert date_root("2026-07-09") == Path("data/2026-07/2026-07-09")


def test_artifact_paths_use_month_bucket():
    assert pipeline_path("2026-07-09", "script.json") == Path(
        "data/2026-07/2026-07-09/pipeline/script.json"
    )
