"""Tests for src/pipeline/agent_state.py

The AgentState class is the *contract* between the pipeline and any external
agent that drives it. The state file (``pipeline_state.json``), the event
log (``agent_events.jsonl``), and the task file (``agent_tasks.json``) are
the only way an agent learns what to do next. Any silent regression here
breaks the agent contract — these tests pin down the full state machine.
"""

import json
from pathlib import Path

import pytest

from src.core.models import ContentItem
from src.pipeline.agent_io import load_pipeline_state
from src.pipeline.agent_state import (
    BLOCK_INSUFFICIENT_CONTEXT,
    BLOCK_MANUAL_DOWNLOAD,
    AgentState,
)


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def state(tmp_path, monkeypatch) -> AgentState:
    """Fresh AgentState rooted in tmp_path/data/{date}/."""
    monkeypatch.chdir(tmp_path)
    return AgentState(
        date="2026-06-08",
        steps=["fetch", "prefilter", "write_script"],
        config={
            "llm": {"model": "main-model", "fast_model": "fast-model"},
            "pipeline": {"target_story_count": 3},
        },
    )


def _read_events(tmp_path: Path, date: str = "2026-06-08") -> list[dict]:
    p = tmp_path / "data" / date / "agent_events.jsonl"
    if not p.exists():
        return []
    return [
        json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line
    ]


def _make_item(
    source_id: str = "100", title: str = "Story", url: str = "https://example.com"
):
    return ContentItem(
        source="hackernews",
        source_id=source_id,
        title=title,
        url=url,
        score=10,
        comment_count=0,
        published_at=0,
        comments=[],
    )


# ── start_run ────────────────────────────────────────────────────────


class TestStartRun:
    def test_sets_status_running_and_persists(self, state, tmp_path):
        state.start_run()

        assert state.status == "running"
        assert state.completed_steps == []
        snapshot = load_pipeline_state("2026-06-08")
        assert snapshot is not None
        assert snapshot["status"] == "running"
        assert snapshot["date"] == "2026-06-08"
        assert snapshot["steps"] == ["fetch", "prefilter", "write_script"]

    def test_emits_run_started_event(self, state, tmp_path):
        state.start_run()

        events = _read_events(tmp_path)
        assert len(events) == 1
        assert events[0]["event"] == "run_started"
        assert events[0]["steps"] == ["fetch", "prefilter", "write_script"]


# ── start_step / complete_step / fail_step transitions ──────────────


class TestStepLifecycle:
    def test_start_step_sets_current_and_clears_prior_failure(self, state, tmp_path):
        state.failed_step = "prefilter"
        state.last_error = {"type": "X", "message": "y"}
        state.start_step("write_script")

        assert state.current_step == "write_script"
        assert state.failed_step is None
        assert state.last_error is None
        events = _read_events(tmp_path)
        assert events[-1]["event"] == "step_started"
        assert events[-1]["step"] == "write_script"

    def test_complete_step_appends_only_once(self, state, tmp_path):
        state.start_step("fetch")
        state.complete_step("fetch")
        state.complete_step("fetch")  # idempotent

        assert state.completed_steps == ["fetch"]
        assert state.current_step is None
        # NOTE: complete_step currently appends an event on every call (not
        # idempotent in the event log). Pin that down so we notice if the
        # dedup logic gets added/changed.
        completed = [
            e for e in _read_events(tmp_path) if e["event"] == "step_completed"
        ]
        assert len(completed) == 2  # one per call (current behavior)

    def test_complete_step_preserves_other_current(self, state, tmp_path):
        """complete_step(name) clears current only if it matches `name`."""
        state.current_step = "other"
        state.completed_steps = ["fetch"]
        state.complete_step("fetch")

        assert state.completed_steps == ["fetch"]
        assert state.current_step == "other"  # untouched

    def test_fail_step_records_status_and_error(self, state, tmp_path):
        state.start_step("prefilter")
        err = ValueError("upstream 502")
        state.fail_step("prefilter", err)

        assert state.status == "failed"
        assert state.failed_step == "prefilter"
        assert state.current_step is None
        assert state.last_error == {"type": "ValueError", "message": "upstream 502"}

        events = _read_events(tmp_path)
        last = events[-1]
        assert last["event"] == "step_failed"
        assert last["error_type"] == "ValueError"
        assert last["message"] == "upstream 502"

    def test_full_happy_path_lifecycle(self, state, tmp_path):
        """A complete run records a deterministic event log + state transitions."""
        state.start_run()
        state.start_step("fetch")
        state.complete_step("fetch")
        state.start_step("prefilter")
        state.complete_step("prefilter")
        state.start_step("write_script")
        state.complete_step("write_script")
        state.finish_run()

        assert state.status == "complete"
        assert state.completed_steps == ["fetch", "prefilter", "write_script"]
        assert state.failed_step is None

        events = [e["event"] for e in _read_events(tmp_path)]
        assert events == [
            "run_started",
            "step_started",
            "step_completed",
            "step_started",
            "step_completed",
            "step_started",
            "step_completed",
            "run_finished",
        ]


# ── block ────────────────────────────────────────────────────────────


class TestBlock:
    def test_block_sets_status_and_reason(self, state, tmp_path):
        state.block("write_script", BLOCK_INSUFFICIENT_CONTEXT)

        assert state.status == "blocked"
        assert state.blocked_reason == BLOCK_INSUFFICIENT_CONTEXT
        assert state.failed_step == "write_script"
        assert state.current_step is None
        assert state.blocked_items == []

    def test_block_records_items(self, state, tmp_path):
        items = [{"story_id": "1", "title": "T", "url": "u"}]
        state.block("write_script", "low_decision_confidence", items=items)

        assert state.blocked_items == items
        events = _read_events(tmp_path)
        last = events[-1]
        assert last["event"] == "run_blocked"
        assert last["reason"] == "low_decision_confidence"
        assert last["item_count"] == 1

    def test_block_emits_run_blocked_event(self, state, tmp_path):
        state.block("enrich_articles", BLOCK_INSUFFICIENT_CONTEXT)

        events = _read_events(tmp_path)
        last = events[-1]
        assert last["event"] == "run_blocked"
        assert last["step"] == "enrich_articles"
        assert last["reason"] == BLOCK_INSUFFICIENT_CONTEXT
        assert last["item_count"] == 0
        # No task file written → agent_task_file in event is None
        assert last["task_file"] is None


# ── block_for_manual_files ───────────────────────────────────────────


class TestBlockForManualFiles:
    def test_writes_task_file_with_expected_paths(self, state, tmp_path):
        items = [
            _make_item(source_id="42", title="Foo", url="https://foo.com"),
            _make_item(source_id="43", title="Bar", url="https://bar.com"),
        ]
        state.block_for_manual_files("enrich_articles", items, synthesis_from="any")

        task_path = tmp_path / "data" / "2026-06-08" / "agent_tasks.json"
        assert task_path.exists()
        payload = json.loads(task_path.read_text(encoding="utf-8"))

        assert payload["schema_version"] == 2
        assert payload["blocked_reason"] == BLOCK_MANUAL_DOWNLOAD
        assert len(payload["tasks"]) == 2
        for task, item in zip(payload["tasks"], items):
            assert task["task_type"] == "fetch_article"
            assert task["status"] == "pending"
            assert task["story_id"] == item.source_id
            assert task["url"] == item.url
            assert "synthesis_html" in task["acceptable_outputs"]
            # Path separators must be portable (forward slashes on Windows too)
            assert "\\" not in task["save_as"]["html"]

    def test_synthesis_from_original_disallows_synthesis(self, state, tmp_path):
        items = [_make_item(source_id="99")]
        state.block_for_manual_files(
            "enrich_articles", items, synthesis_from="original"
        )

        payload = json.loads(
            (tmp_path / "data" / "2026-06-08" / "agent_tasks.json").read_text(
                encoding="utf-8"
            )
        )
        # Per-task list excludes synthesis_html
        assert "synthesis_html" not in payload["tasks"][0]["acceptable_outputs"]
        # Aggregate contract: ALL tasks are "original" → contract = "original"
        assert payload["repair_contract"]["synthesis_policy"] == "original"
        assert (
            "synthesis_html is NOT acceptable"
            in payload["repair_contract"]["minimum_success_condition"]
        )

    def test_mixed_synthesis_yields_per_task_policy(self, tmp_path, monkeypatch):
        """Mixed synthesis_from values (no 'any', no all-'original') → per_task."""
        monkeypatch.chdir(tmp_path)
        state2 = AgentState(date="2026-06-09", steps=["enrich_articles"], config={})
        # Inject missing_manual_files manually to simulate mixed non-"any" input
        state2.missing_manual_files = [
            {
                "story_id": "1",
                "title": "T1",
                "url": "u1",
                "synthesis_from": "original",
                "expected_html": "x",
                "expected_pdf": "y",
            },
            {
                "story_id": "2",
                "title": "T2",
                "url": "u2",
                "synthesis_from": "news_aggregation",
                "expected_html": "x",
                "expected_pdf": "y",
            },
        ]
        state2.blocked_reason = BLOCK_MANUAL_DOWNLOAD
        state2._write_task_list()

        payload = json.loads(
            Path("data/2026-06-09/agent_tasks.json").read_text(encoding="utf-8")
        )
        # Aggregate: not all "original" (so not "original"), and no "any"
        # in the set, so falls through to "per_task".
        assert payload["repair_contract"]["synthesis_policy"] == "per_task"
        # Task 0 (original) excludes synthesis_html; task 1 (mirror) includes it
        assert "synthesis_html" not in payload["tasks"][0]["acceptable_outputs"]
        assert "synthesis_html" in payload["tasks"][1]["acceptable_outputs"]

    def test_mixed_with_any_yields_any_policy(self, tmp_path, monkeypatch):
        """If any task uses synthesis_from='any', the aggregate is 'any'."""
        monkeypatch.chdir(tmp_path)
        state2 = AgentState(date="2026-06-10", steps=["enrich_articles"], config={})
        state2.missing_manual_files = [
            {
                "story_id": "1",
                "title": "T1",
                "url": "u1",
                "synthesis_from": "original",
                "expected_html": "x",
                "expected_pdf": "y",
            },
            {
                "story_id": "2",
                "title": "T2",
                "url": "u2",
                "synthesis_from": "any",
                "expected_html": "x",
                "expected_pdf": "y",
            },
        ]
        state2.blocked_reason = BLOCK_MANUAL_DOWNLOAD
        state2._write_task_list()

        payload = json.loads(
            Path("data/2026-06-10/agent_tasks.json").read_text(encoding="utf-8")
        )
        assert payload["repair_contract"]["synthesis_policy"] == "any"

    def test_state_transitions_to_blocked(self, state, tmp_path):
        items = [_make_item(source_id="1")]
        state.block_for_manual_files("enrich_articles", items)

        assert state.status == "blocked"
        assert state.blocked_reason == BLOCK_MANUAL_DOWNLOAD
        assert state.missing_manual_files[0]["expected_html"].endswith("1.html")


# ── add_degraded_items ───────────────────────────────────────────────


class TestAddDegradedItems:
    def test_records_items_and_switches_status(self, state, tmp_path):
        items = [
            _make_item(source_id="5", title="X"),
            _make_item(source_id="6", title="Y"),
        ]
        state.add_degraded_items("enrich_articles", items, reason="fetch_failed")

        assert state.status == "degraded"
        assert len(state.degraded_items) == 2
        for entry, item in zip(state.degraded_items, items):
            assert entry["step"] == "enrich_articles"
            assert entry["story_id"] == str(item.source_id)
            assert entry["title"] == item.title
            assert entry["continued"] is True

    def test_does_not_downgrade_failed_status(self, state, tmp_path):
        """If a step failed earlier, calling add_degraded_items must not
        overwrite the status to 'degraded'."""
        state.fail_step("prefilter", RuntimeError("x"))
        state.add_degraded_items("write_script", [_make_item()], reason="low_quality")

        assert state.status == "failed"

    def test_emits_degraded_event(self, state, tmp_path):
        state.add_degraded_items(
            "enrich_articles", [_make_item()], reason="fetch_failed"
        )

        events = _read_events(tmp_path)
        last = events[-1]
        assert last["event"] == "degraded_items_recorded"
        assert last["count"] == 1


# ── finish_run ───────────────────────────────────────────────────────


class TestFinishRun:
    def test_running_becomes_complete(self, state, tmp_path):
        state.start_run()
        state.finish_run()

        assert state.status == "complete"
        assert state.current_step is None
        assert state.failed_step is None
        events = _read_events(tmp_path)
        last = events[-1]
        assert last["event"] == "run_finished"
        assert last["status"] == "complete"

    def test_failed_stays_failed(self, state, tmp_path):
        state.fail_step("write_script", RuntimeError("x"))
        state.finish_run()

        # finish_run only promotes running → complete
        assert state.status == "failed"

    def test_degraded_stays_degraded(self, state, tmp_path):
        state.add_degraded_items(
            "enrich_articles", [_make_item()], reason="fetch_failed"
        )
        state.finish_run()

        assert state.status == "degraded"


# ── next_recommended_command ─────────────────────────────────────────


class TestNextRecommendedCommand:
    def test_complete_returns_none(self, state, tmp_path):
        state.start_run()
        state.finish_run()
        snapshot = load_pipeline_state("2026-06-08")
        assert snapshot["next_recommended_command"] is None

    def test_blocked_manual_download_recommends_resume(self, state, tmp_path):
        state.block_for_manual_files("enrich_articles", [_make_item(source_id="7")])
        snapshot = load_pipeline_state("2026-06-08")
        cmd = snapshot["next_recommended_command"]
        assert "scripts/agent_run.py" in cmd
        assert "--resume" in cmd
        assert "--agent" not in cmd
        assert "2026-06-08" in cmd
        assert "downloaded_pages" in cmd

    def test_blocked_insufficient_context_recommends_resume(self, state, tmp_path):
        state.block("write_script", BLOCK_INSUFFICIENT_CONTEXT)
        snapshot = load_pipeline_state("2026-06-08")
        assert "scripts/agent_run.py" in snapshot["next_recommended_command"]
        assert "--resume" in snapshot["next_recommended_command"]
        assert "--agent" not in snapshot["next_recommended_command"]
        assert "Gather more source context" in snapshot["next_recommended_command"]

    def test_failed_step_recommends_just_that_step(self, state, tmp_path):
        state.start_run()
        state.start_step("write_script")
        state.fail_step("write_script", RuntimeError("boom"))
        snapshot = load_pipeline_state("2026-06-08")
        cmd = snapshot["next_recommended_command"]
        assert cmd is not None
        assert "scripts/agent_run.py" in cmd
        assert "--steps write_script" in cmd
        assert "--agent" not in cmd
        assert "--resume" not in cmd  # not blocked, just failed

    def test_running_recommends_next_incomplete_step(self, state, tmp_path):
        state.start_run()
        state.start_step("fetch")
        state.complete_step("fetch")
        # Did not start prefilter → next step is prefilter
        snapshot = load_pipeline_state("2026-06-08")
        assert "scripts/agent_run.py" in snapshot["next_recommended_command"]
        assert "--steps prefilter" in snapshot["next_recommended_command"]
        assert "--agent" not in snapshot["next_recommended_command"]


# ── state file schema stability ──────────────────────────────────────


class TestStateSchema:
    def test_pipeline_state_includes_artifacts(self, state, tmp_path):
        state.start_run()
        snapshot = load_pipeline_state("2026-06-08")
        # All artifact keys present, even if the file is None
        for key in (
            "content",
            "script",
            "audio_dir",
            "title",
            "cover",
            "publish_guide",
            "render_props",
            "output",
        ):
            assert key in snapshot["artifacts"]

    def test_pipeline_state_includes_config_summary(self, state, tmp_path):
        state.start_run()
        snapshot = load_pipeline_state("2026-06-08")
        cfg = snapshot["config"]
        assert cfg["model"] == "main-model"
        assert cfg["fast_model"] == "fast-model"
        assert cfg["target_story_count"] == 3

    def test_pipeline_state_includes_schema_version(self, state, tmp_path):
        state.start_run()
        snapshot = load_pipeline_state("2026-06-08")
        assert snapshot["schema_version"] == 1

    def test_event_log_is_append_only(self, state, tmp_path):
        """A second AgentState on the same date appends to the same log."""
        state.start_run()
        state.start_step("fetch")
        state.complete_step("fetch")

        # New instance, same date, different step
        state2 = AgentState(date="2026-06-08", steps=["prefilter"], config=state.config)
        state2.start_run()
        state2.start_step("prefilter")

        events = _read_events(tmp_path)
        # 3 from state1 + 2 from state2 (run_started, step_started)
        assert len(events) == 5
        assert events[0]["event"] == "run_started"
        assert events[-1]["event"] == "step_started"
