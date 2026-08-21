from __future__ import annotations

import json

import pytest

from src.pipeline.paths import date_root
from src.workflow.machine import WorkflowMachine
from src.workflow.model import FailureType, StateStatus
from src.workflow.persistence import WorkflowCorruptError
from src.workflow.video import VIDEO_WORKFLOW_STEPS


DATE = "2026-08-20"


def test_video_workflow_uses_five_compact_phases():
    assert [step.name for step in VIDEO_WORKFLOW_STEPS] == [
        "ingest",
        "research",
        "editorial",
        "human_review",
        "produce",
    ]
    assert VIDEO_WORKFLOW_STEPS[1].pipeline_steps == (
        "enrich_articles",
        "judge_comments",
    )
    assert "normalize_video_structure" not in VIDEO_WORKFLOW_STEPS[2].pipeline_steps
    assert "translate_comments" not in VIDEO_WORKFLOW_STEPS[2].pipeline_steps
    assert "publish_guide" not in VIDEO_WORKFLOW_STEPS[4].pipeline_steps
    assert "publish/publish_guide.md" in VIDEO_WORKFLOW_STEPS[4].produces
    assert "pipeline/video_structure.json" in VIDEO_WORKFLOW_STEPS[2].produces
    assert "review_script" not in VIDEO_WORKFLOW_STEPS[2].pipeline_steps
    assert "pipeline/script_review.json" in VIDEO_WORKFLOW_STEPS[3].produces
    assert VIDEO_WORKFLOW_STEPS[3].pipeline_steps == ("human_review",)
    assert VIDEO_WORKFLOW_STEPS[4].deps == ("human_review",)


def test_pipeline_order_is_derived_from_compact_workflow():
    from src.workflow.video import VIDEO_PIPELINE_STEPS

    assert VIDEO_PIPELINE_STEPS[-3:] == (
        "synthesize_audio",
        "prepare_render",
        "render",
    )


def test_phase_pipeline_aliases_are_derived_from_workflow():
    from src.workflow.video import VIDEO_PHASE_PIPELINE_STEPS

    assert VIDEO_PHASE_PIPELINE_STEPS["human_review"] == ("human_review",)
    assert VIDEO_PHASE_PIPELINE_STEPS["produce"][0] == "apply_storyboard"


def _machine(tmp_path, monkeypatch) -> WorkflowMachine:
    monkeypatch.chdir(tmp_path)
    return WorkflowMachine(DATE, VIDEO_WORKFLOW_STEPS)


def test_video_workflow_is_a_valid_dag_and_starts_at_ingest(tmp_path, monkeypatch):
    machine = _machine(tmp_path, monkeypatch)

    machine.ensure()

    assert machine.current_state() == "ingest"
    assert machine.ready_states() == ["ingest"]
    assert machine.status_report()["states"]["produce"]["status"] == "pending"


def test_done_state_unlocks_next_phase_and_persists(tmp_path, monkeypatch):
    machine = _machine(tmp_path, monkeypatch)
    machine.ensure()

    machine.mark_running("ingest")
    machine.mark_done("ingest")

    assert machine.snapshot is not None
    assert machine.snapshot.states["ingest"].status == StateStatus.DONE
    assert machine.current_state() == "research"
    assert machine.path.exists()

    reloaded = _machine(tmp_path, monkeypatch)
    assert reloaded.load() is True
    assert reloaded.current_state() == "research"


def test_reset_cascades_only_downstream_states(tmp_path, monkeypatch):
    machine = _machine(tmp_path, monkeypatch)
    machine.ensure()

    for name in ("ingest", "research", "editorial"):
        machine.mark_running(name)
        machine.mark_done(name)

    affected = machine.reset("research")

    assert affected == [
        "research",
        "editorial",
        "human_review",
        "produce",
    ]
    assert machine.snapshot is not None
    assert machine.snapshot.states["ingest"].status == StateStatus.DONE
    assert all(
        machine.snapshot.states[name].status == StateStatus.PENDING for name in affected
    )
    assert machine.current_state() == "research"


def test_integrity_detects_modified_predecessor_artifact(tmp_path, monkeypatch):
    machine = _machine(tmp_path, monkeypatch)
    machine.ensure()

    root = date_root(DATE)
    raw = root / "raw" / "raw_stories.json"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text('{"stories": []}', encoding="utf-8")

    machine.mark_running("ingest")
    machine.mark_done("ingest")
    machine.mark_running("research")
    assert machine.check_integrity("research") == []

    raw.write_text('{"stories": [1]}', encoding="utf-8")
    assert machine.check_integrity("research") == [
        "ingest:raw/raw_stories.json — file modified"
    ]


def test_failed_state_requires_reset_before_it_is_ready(tmp_path, monkeypatch):
    machine = _machine(tmp_path, monkeypatch)
    machine.ensure()
    machine.mark_failed("ingest", "missing source", failure_type=FailureType.VERIFY)

    assert machine.ready_states() == []
    assert machine.status_report()["states"]["ingest"]["failure_type"] == "verify"

    machine.reset("ingest")
    assert machine.current_state() == "ingest"


def test_corrupt_workflow_is_not_silently_accepted(tmp_path, monkeypatch):
    machine = _machine(tmp_path, monkeypatch)
    machine.ensure()
    machine.path.write_text(json.dumps({"schema_version": 999}), encoding="utf-8")

    reloaded = _machine(tmp_path, monkeypatch)
    with pytest.raises(WorkflowCorruptError):
        reloaded.load()
