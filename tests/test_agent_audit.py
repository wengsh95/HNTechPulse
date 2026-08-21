from pathlib import Path
import json

from scripts.internal.agent.agent_audit import (
    _artifact_check,
    _decision_check,
    _format_mmss,
    _issue,
    _manifest_check,
    _next_command,
    _scripts_semantically_equal,
    _state_check,
    _summarize_blocks,
    audit,
)
from src.pipeline.agent_io import file_sha256, write_artifact_manifest
from src.pipeline.paths import (
    agent_path,
    pipeline_path,
    pipeline_variants_root,
    publish_path,
)
from src.pipeline.publish_guide_inputs import publish_guide_manifest_inputs
from src.utils.atomic_io import atomic_write_json
from src.workflow.machine import WorkflowMachine
from src.workflow.video import VIDEO_WORKFLOW_STEPS


def test_audit_helpers_format_and_normalize_issue_payload(tmp_path):
    assert _format_mmss(61.6) == "01:02"
    assert _format_mmss(None) == "00:00"

    issue = _issue(
        "warning",
        "demo",
        "A message",
        path=tmp_path / "artifact.json",
        recommendation="uv run python scripts/internal/agent/agent_run.py",
        why="because",
        fixable_by_agent=True,
    )

    assert issue == {
        "severity": "warning",
        "check": "demo",
        "message": "A message",
        "path": str(tmp_path / "artifact.json").replace("\\", "/"),
        "recommendation": "uv run python scripts/internal/agent/agent_run.py",
        "why": "because",
        "fixable_by_agent": True,
    }


def test_scripts_semantically_equal_handles_missing_and_invalid_inputs(tmp_path):
    variant = tmp_path / "variant.json"
    promoted = tmp_path / "promoted.json"
    variant.write_text("not json", encoding="utf-8")
    promoted.write_text("{}", encoding="utf-8")
    assert _scripts_semantically_equal(variant, promoted) is False
    assert _scripts_semantically_equal(tmp_path / "missing.json", promoted) is False


def test_artifact_check_reports_required_and_publish_tail_gaps(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-04-26"

    issues = _artifact_check(date, tmp_path)

    checks = {issue["check"] for issue in issues}
    assert {"content_exists", "script_exists"} <= checks
    assert {"title_exists", "cover_exists", "publish_guide_exists"} <= checks


def test_manifest_check_reports_missing_and_mismatched_manifests(tmp_path):
    missing = tmp_path / "missing.json"
    missing.write_text("{}", encoding="utf-8")
    mismatch = tmp_path / "mismatch.json"
    mismatch.write_text("{}", encoding="utf-8")
    mismatch.with_suffix(".json.manifest.json").write_text(
        json.dumps({"artifact_hash": "wrong"}), encoding="utf-8"
    )

    issues = _manifest_check([missing, mismatch])

    assert any(issue["check"] == "manifest_exists" for issue in issues)
    assert any(issue["check"] == "manifest_hash_matches" for issue in issues)


def test_state_check_explains_human_review_block(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "scripts.internal.agent.agent_audit.load_workflow_report",
        lambda date: {
            "status": "blocked",
            "current_state": "human_review",
            "states": {"human_review": {"last_error": "human_review_required"}},
        },
    )

    state, issues = _state_check("2026-04-26")

    assert state["status"] == "blocked"
    assert issues[0]["fixable_by_agent"] is False
    assert "Do not auto-resume" in issues[0]["why"]


def test_decision_check_reports_missing_and_invalid_decisions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-04-26"

    decision, issues = _decision_check(date)
    assert decision is None
    assert issues[0]["check"] == "agent_decision_exists"

    decision_path = agent_path(date, "agent_decision.json")
    decision_path.parent.mkdir(parents=True)
    decision_path.write_text(json.dumps({"status": "blocked"}), encoding="utf-8")
    decision, issues = _decision_check(date)
    assert decision["status"] == "blocked"
    assert issues[0]["check"] == "agent_decision_status"


def test_next_command_prioritizes_explicit_recommendation_and_publish_tail():
    issues = [
        {"severity": "error", "check": "workflow_state_status"},
        {
            "severity": "warning",
            "check": "title_exists",
            "recommendation": "uv run python scripts/internal/agent/agent_run.py --date 2026-04-26 --resume",
        },
    ]
    next_command = _next_command("2026-04-26", issues)
    assert next_command["command"].endswith("--resume")

    publish_command = _next_command(
        "2026-04-26", [{"severity": "warning", "check": "publish_guide_exists"}]
    )
    assert publish_command["command"].endswith("--steps prepare_render")


def test_summarize_blocks_separates_agent_human_and_unknown_issues():
    summary = _summarize_blocks(
        [
            {"check": "agent", "message": "repair", "fixable_by_agent": True},
            {"check": "human", "message": "approve", "fixable_by_agent": False},
            {"check": "unknown", "message": "inspect", "severity": "warning"},
            {"check": "info", "message": "ignore", "severity": "info"},
        ]
    )

    assert summary["agent_fixable_count"] == 1
    assert summary["needs_human_count"] == 1
    assert summary["unknown_count"] == 1


def _write_manifest(path: Path) -> None:
    atomic_write_json(
        path.with_suffix(path.suffix + ".manifest.json"),
        {
            "schema_version": 1,
            "artifact": str(path).replace("\\", "/"),
            "artifact_hash": file_sha256(path),
        },
    )


def _write_minimal_storyboard(date: str) -> None:
    """A lint-clean storyboard so audit() sees no storyboard errors."""
    atomic_write_json(
        pipeline_path(date, "storyboard.json"),
        {
            "schema_version": 1,
            "shots": [
                {
                    "shot_id": "shot_01",
                    "template_id": "cover_v1",
                    "props": {"headline": "测试标题"},
                }
            ],
        },
    )


def _write_complete_workflow(
    date: str, requested_steps: list[str] | None = None
) -> None:
    machine = WorkflowMachine(date, VIDEO_WORKFLOW_STEPS)
    machine.ensure(metadata={"requested_steps": requested_steps or ["write_script"]})
    for state in ("ingest", "research", "editorial", "human_review", "produce"):
        machine.mark_running(state)
        machine.mark_done(state)


def test_agent_audit_passes_complete_selected_variant(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-04-26"
    selected_dir = pipeline_variants_root(date) / "v01_balanced"
    selected_dir.mkdir(parents=True)

    _write_complete_workflow(date)
    atomic_write_json(
        agent_path(date, "agent_decision.json"),
        {"schema_version": 1, "date": date, "status": "continue"},
    )
    atomic_write_json(
        agent_path(date, "agent_variant_decision.json"),
        {
            "schema_version": 1,
            "date": date,
            "status": "continue",
            "selected_variant": "v01_balanced",
        },
    )
    atomic_write_json(pipeline_path(date, "content.json"), {"items": []})
    script_payload = {"title": "Script", "segments": []}
    atomic_write_json(pipeline_path(date, "script.json"), script_payload)
    atomic_write_json(selected_dir / "script.json", script_payload)
    _write_minimal_storyboard(date)

    for path in [
        pipeline_path(date, "content.json"),
        pipeline_path(date, "script.json"),
    ]:
        _write_manifest(path)

    result = audit(date)

    assert result["publishable"] is True
    assert result["status"] == "ok"
    assert result["error_count"] == 0


def test_agent_audit_blocks_when_selected_variant_not_promoted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-04-26"
    selected_dir = pipeline_variants_root(date) / "v01_balanced"
    selected_dir.mkdir(parents=True)

    _write_complete_workflow(date)
    atomic_write_json(
        agent_path(date, "agent_decision.json"),
        {"schema_version": 1, "date": date, "status": "continue"},
    )
    atomic_write_json(
        agent_path(date, "agent_variant_decision.json"),
        {
            "schema_version": 1,
            "date": date,
            "status": "continue",
            "selected_variant": "v01_balanced",
        },
    )
    atomic_write_json(pipeline_path(date, "content.json"), {"items": []})
    # The variant snapshot is the writer's content. The promoted (root) script
    # is what later steps will post-process; here it has *different* segments,
    # so the semantic comparison should fail and the run should be blocked.
    atomic_write_json(
        pipeline_path(date, "script.json"),
        {
            "title": "Promoted",
            "segments": [{"segment_type": "story_scan", "audio_text": "WRONG"}],
        },
    )
    atomic_write_json(
        selected_dir / "script.json",
        {
            "title": "Variant",
            "segments": [{"segment_type": "story_scan", "audio_text": "ORIGINAL"}],
        },
    )

    result = audit(date)

    assert result["publishable"] is False
    assert result["status"] == "blocked"
    assert any(i.get("check") == "selected_variant_promoted" for i in result["issues"])


def test_agent_audit_skips_variant_promotion_for_downstream_video_run(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    date = "2026-04-26"
    selected_dir = pipeline_variants_root(date) / "v01_balanced"
    selected_dir.mkdir(parents=True)

    _write_complete_workflow(
        date,
        [
            "human_review",
            "prepare_subtitles",
            "synthesize_audio",
            "prepare_render",
            "render",
        ],
    )
    atomic_write_json(
        agent_path(date, "agent_decision.json"),
        {"schema_version": 1, "date": date, "status": "continue"},
    )
    atomic_write_json(
        agent_path(date, "agent_variant_decision.json"),
        {
            "schema_version": 1,
            "date": date,
            "status": "continue",
            "selected_variant": "v01_balanced",
        },
    )
    atomic_write_json(pipeline_path(date, "content.json"), {"items": []})
    atomic_write_json(
        pipeline_path(date, "script.json"),
        {
            "title": "Manual script",
            "segments": [{"segment_type": "story_scan", "audio_text": "MANUAL"}],
        },
    )
    atomic_write_json(
        selected_dir / "script.json",
        {
            "title": "Generated variant",
            "segments": [{"segment_type": "story_scan", "audio_text": "VARIANT"}],
        },
    )
    _write_manifest(pipeline_path(date, "content.json"))
    _write_manifest(pipeline_path(date, "script.json"))

    result = audit(date)

    assert not any(
        issue.get("check") == "selected_variant_promoted" for issue in result["issues"]
    )


def test_agent_audit_warns_when_publish_guide_is_stale(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-04-26"
    base = tmp_path / "data" / date[:7] / date
    base.mkdir(parents=True)

    _write_complete_workflow(date)
    atomic_write_json(
        agent_path(date, "agent_decision.json"),
        {"schema_version": 1, "date": date, "status": "continue"},
    )
    atomic_write_json(pipeline_path(date, "content.json"), {"items": []})
    atomic_write_json(
        pipeline_path(date, "script.json"), {"title": "Script", "segments": []}
    )
    _write_minimal_storyboard(date)
    guide = publish_path(date, "publish_guide.md")
    guide.parent.mkdir(parents=True, exist_ok=True)
    guide.write_text("old guide", encoding="utf-8")

    result = audit(date)

    assert result["publishable"] is True
    assert any(i.get("check") == "publish_guide_fresh" for i in result["issues"])


def test_agent_audit_accepts_publish_guide_manifest_with_runtime(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-04-26"
    base = tmp_path / "data" / date[:7] / date
    base.mkdir(parents=True)

    _write_complete_workflow(date)
    atomic_write_json(
        agent_path(date, "agent_decision.json"),
        {"schema_version": 1, "date": date, "status": "continue"},
    )
    atomic_write_json(pipeline_path(date, "content.json"), {"items": []})
    atomic_write_json(
        pipeline_path(date, "script.json"),
        {
            "title": "Script default",
            "description": "Default desc",
            "total_duration": 12,
            "segments": [
                {
                    "segment_type": "opening",
                    "audio_text": "开场。",
                    "start_time": 0,
                    "end_time": 12,
                }
            ],
        },
    )
    atomic_write_json(
        publish_path(date, "title.json"),
        {
            "title": "Published title",
            "description": "Published desc",
        },
    )
    guide = publish_path(date, "publish_guide.md")
    guide.parent.mkdir(parents=True, exist_ok=True)
    guide.write_text("fresh guide", encoding="utf-8")
    context = publish_guide_manifest_inputs(date)
    assert context is not None
    assert context["script_title"] == "Published title"
    assert context["script_description"] == "Published desc"
    write_artifact_manifest(guide, step="publish_guide", date=date, inputs=context)
    _write_minimal_storyboard(date)

    result = audit(date)

    assert result["publishable"] is True
    assert not any(i.get("check") == "publish_guide_fresh" for i in result["issues"])


def test_agent_audit_tolerates_subtitle_rechunking(tmp_path, monkeypatch):
    """synthesize_audio re-splits subtitle_texts into finer display cues; the
    audit must compare joined content, not the raw chunk lists, or every
    post-audio run would falsely report variant drift."""
    monkeypatch.chdir(tmp_path)
    date = "2026-04-26"
    selected_dir = pipeline_variants_root(date) / "v01_balanced"
    selected_dir.mkdir(parents=True)

    _write_complete_workflow(date)
    atomic_write_json(
        agent_path(date, "agent_decision.json"),
        {"schema_version": 1, "date": date, "status": "continue"},
    )
    atomic_write_json(
        agent_path(date, "agent_variant_decision.json"),
        {
            "schema_version": 1,
            "date": date,
            "status": "continue",
            "selected_variant": "v01_balanced",
        },
    )
    atomic_write_json(pipeline_path(date, "content.json"), {"items": []})

    # Same content, different chunking. The variant snapshot is frozen at
    # write_script time (single line); the promoted script holds the
    # post-synthesize_audio re-split cues. Joining must make them equal.
    seg_variant = {
        "segment_type": "story_scan",
        "audio_text": "相同的解说文本",
        "scene_elements": [{"props": {"subtitle_texts": ["你好世界今天天气不错"]}}],
    }
    seg_promoted = {
        "segment_type": "story_scan",
        "audio_text": "相同的解说文本",
        "scene_elements": [{"props": {"subtitle_texts": ["你好世界", "今天天气不错"]}}],
    }
    atomic_write_json(
        pipeline_path(date, "script.json"),
        {"title": "Promoted", "segments": [seg_promoted]},
    )
    atomic_write_json(
        selected_dir / "script.json",
        {"title": "Variant", "segments": [seg_variant]},
    )
    _write_minimal_storyboard(date)

    for path in [
        pipeline_path(date, "content.json"),
        pipeline_path(date, "script.json"),
    ]:
        _write_manifest(path)

    result = audit(date)

    assert result["publishable"] is True
    assert result["status"] == "ok"
    assert result["error_count"] == 0


def test_agent_audit_tolerates_subtitle_rechunking_english(tmp_path, monkeypatch):
    """English/mixed subtitle cues get re-split at sentence-break + space
    boundaries by synthesize_audio; the splitter keeps the period on the left
    chunk and drops the inter-chunk space, so the audit must compare
    whitespace-stripped content (not folded whitespace) or English narration
    would falsely report variant drift."""
    monkeypatch.chdir(tmp_path)
    date = "2026-04-26"
    selected_dir = pipeline_variants_root(date) / "v01_balanced"
    selected_dir.mkdir(parents=True)

    _write_complete_workflow(date)
    atomic_write_json(
        agent_path(date, "agent_decision.json"),
        {"schema_version": 1, "date": date, "status": "continue"},
    )
    atomic_write_json(
        agent_path(date, "agent_variant_decision.json"),
        {
            "schema_version": 1,
            "date": date,
            "status": "continue",
            "selected_variant": "v01_balanced",
        },
    )
    atomic_write_json(pipeline_path(date, "content.json"), {"items": []})

    # Author froze a single English cue at write_script time. synthesize_audio
    # re-splits it into two cues at the sentence break; the splitter keeps the
    # period on the left chunk and drops the inter-chunk space. Joining must
    # treat these as content-equal.
    seg_variant = {
        "segment_type": "story_scan",
        "audio_text": "Same narration text.",
        "scene_elements": [
            {"props": {"subtitle_texts": ["First sentence. Second sentence."]}}
        ],
    }
    seg_promoted = {
        "segment_type": "story_scan",
        "audio_text": "Same narration text.",
        "scene_elements": [
            {"props": {"subtitle_texts": ["First sentence.", "Second sentence."]}}
        ],
    }
    atomic_write_json(
        pipeline_path(date, "script.json"),
        {"title": "Promoted", "segments": [seg_promoted]},
    )
    atomic_write_json(
        selected_dir / "script.json",
        {"title": "Variant", "segments": [seg_variant]},
    )
    _write_minimal_storyboard(date)

    for path in [
        pipeline_path(date, "content.json"),
        pipeline_path(date, "script.json"),
    ]:
        _write_manifest(path)

    result = audit(date)

    assert result["publishable"] is True
    assert result["status"] == "ok"
    assert result["error_count"] == 0


def test_agent_audit_blocks_on_real_subtitle_drift(tmp_path, monkeypatch):
    """Re-chunking tolerance must not mask genuine textual drift: when the
    promoted subtitle content differs from the variant by real characters
    (not just split points), the audit must still block."""
    monkeypatch.chdir(tmp_path)
    date = "2026-04-26"
    selected_dir = pipeline_variants_root(date) / "v01_balanced"
    selected_dir.mkdir(parents=True)

    _write_complete_workflow(date)
    atomic_write_json(
        agent_path(date, "agent_decision.json"),
        {"schema_version": 1, "date": date, "status": "continue"},
    )
    atomic_write_json(
        agent_path(date, "agent_variant_decision.json"),
        {
            "schema_version": 1,
            "date": date,
            "status": "continue",
            "selected_variant": "v01_balanced",
        },
    )
    atomic_write_json(pipeline_path(date, "content.json"), {"items": []})

    # Same split point, but the words differ - this is real drift that
    # re-chunking tolerance must not hide.
    seg_variant = {
        "segment_type": "story_scan",
        "audio_text": "Same narration text.",
        "scene_elements": [{"props": {"subtitle_texts": ["你好世界今天天气不错"]}}],
    }
    seg_promoted = {
        "segment_type": "story_scan",
        "audio_text": "Same narration text.",
        "scene_elements": [{"props": {"subtitle_texts": ["你好世界", "今天天气真好"]}}],
    }
    atomic_write_json(
        pipeline_path(date, "script.json"),
        {"title": "Promoted", "segments": [seg_promoted]},
    )
    atomic_write_json(
        selected_dir / "script.json",
        {"title": "Variant", "segments": [seg_variant]},
    )

    result = audit(date)

    assert result["publishable"] is False
    assert result["status"] == "blocked"
    assert any(i.get("check") == "selected_variant_promoted" for i in result["issues"])
