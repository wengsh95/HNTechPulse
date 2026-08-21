from __future__ import annotations

import json

from src.workflow.reporting import load_workflow_report
from src.workflow.machine import WorkflowMachine
from src.workflow.video import VIDEO_WORKFLOW_STEPS


DATE = "2026-08-20"


def test_load_workflow_report_distinguishes_missing_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert load_workflow_report(DATE) is None


def test_load_workflow_report_reads_native_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    machine = WorkflowMachine(DATE, VIDEO_WORKFLOW_STEPS)
    machine.ensure()

    report = load_workflow_report(DATE)

    assert report is not None
    assert report["status"] == "pending"
    assert report["states"]["ingest"]["status"] == "pending"


def test_load_workflow_report_marks_corrupt_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    machine = WorkflowMachine(DATE, VIDEO_WORKFLOW_STEPS)
    machine.ensure()
    machine.path.write_text(json.dumps({"schema_version": 999}), encoding="utf-8")

    report = load_workflow_report(DATE)

    assert report is not None
    assert report["status"] == "corrupt"
    assert report["workflow_file"].endswith("workflow_video.json")
    assert report["error"]
