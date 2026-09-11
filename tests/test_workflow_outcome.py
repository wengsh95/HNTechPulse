"""Typed run results: RunStatus and RunOutcome."""

from src.workflow import RunOutcome, RunStatus


class TestRunStatus:
    def test_values_are_wire_stable(self):
        assert RunStatus.COMPLETED.value == "completed"
        assert RunStatus.BLOCKED.value == "blocked"
        assert RunStatus.FAILED.value == "failed"


class TestRunOutcomeExitCode:
    def test_completed_exits_zero(self):
        assert RunOutcome.completed(["fetch"]).exit_code == 0

    def test_blocked_exits_two(self):
        outcome = RunOutcome.blocked(
            "write_script", "low_decision_confidence", ["write_script"]
        )
        assert outcome.exit_code == 2

    def test_failed_exits_one(self):
        outcome = RunOutcome.failed("render", ["render"], reason="boom")
        assert outcome.exit_code == 1


class TestRunOutcomeFactories:
    def test_completed_records_steps(self):
        outcome = RunOutcome.completed(["fetch", "prefilter"])
        assert outcome.status is RunStatus.COMPLETED
        assert outcome.steps == ("fetch", "prefilter")
        assert outcome.step is None
        assert outcome.reason is None
        assert outcome.items == []
        assert outcome.task_file is None

    def test_blocked_carries_payload(self):
        outcome = RunOutcome.blocked(
            "prepare_story_images",
            "manual_image_selection_required",
            ["prepare_story_images"],
            items=[{"story_id": "42"}],
            task_file="data/x/agent_tasks.json",
        )
        assert outcome.status is RunStatus.BLOCKED
        assert outcome.step == "prepare_story_images"
        assert outcome.reason == "manual_image_selection_required"
        assert outcome.items == [{"story_id": "42"}]
        assert outcome.task_file == "data/x/agent_tasks.json"
        assert outcome.steps == ("prepare_story_images",)

    def test_blocked_defaults_to_empty_items(self):
        outcome = RunOutcome.blocked(
            "human_review", "manual_script_review_required", ["human_review"]
        )
        assert outcome.items == []
        assert outcome.task_file is None

    def test_failed_carries_reason(self):
        outcome = RunOutcome.failed("render", ["render"], reason="timeout")
        assert outcome.status is RunStatus.FAILED
        assert outcome.step == "render"
        assert outcome.reason == "timeout"

    def test_accepts_list_steps(self):
        outcome = RunOutcome.completed(["fetch"])
        assert outcome.steps == ("fetch",)


class TestRunOutcomeWire:
    def test_as_wire_dict_completed(self):
        outcome = RunOutcome.completed(["fetch"])
        assert outcome.as_wire_dict() == {
            "status": "completed",
            "step": None,
            "reason": None,
            "items": [],
            "task_file": None,
            "steps": ["fetch"],
            "exit_code": 0,
        }

    def test_as_wire_dict_blocked(self):
        outcome = RunOutcome.blocked(
            "write_script",
            "low_decision_confidence",
            ["write_script"],
            items=[{"x": 1}],
        )
        wire = outcome.as_wire_dict()
        assert wire["status"] == "blocked"
        assert wire["step"] == "write_script"
        assert wire["reason"] == "low_decision_confidence"
        assert wire["items"] == [{"x": 1}]
        assert wire["exit_code"] == 2
        assert wire["steps"] == ["write_script"]
