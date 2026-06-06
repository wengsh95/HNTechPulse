from pathlib import Path

from scripts.agent_audit import audit
from src.pipeline.agent_io import file_sha256
from src.utils.atomic_io import atomic_write_json


def _write_manifest(path: Path) -> None:
    atomic_write_json(
        path.with_suffix(path.suffix + ".manifest.json"),
        {
            "schema_version": 1,
            "artifact": str(path).replace("\\", "/"),
            "artifact_hash": file_sha256(path),
        },
    )


def test_agent_audit_passes_complete_selected_variant(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-04-26"
    base = tmp_path / "data" / date
    selected_dir = base / "variants" / "v01_balanced"
    selected_dir.mkdir(parents=True)

    atomic_write_json(
        base / "pipeline_state.json",
        {
            "schema_version": 1,
            "date": date,
            "status": "complete",
            "next_recommended_command": None,
        },
    )
    atomic_write_json(
        base / "agent_decision.json",
        {"schema_version": 1, "date": date, "status": "continue"},
    )
    atomic_write_json(
        base / "agent_variant_decision.json",
        {
            "schema_version": 1,
            "date": date,
            "status": "continue",
            "selected_variant": "v01_balanced",
        },
    )
    atomic_write_json(base / "content.json", {"items": []})
    script_payload = {"title": "Script", "segments": []}
    atomic_write_json(base / "script.json", script_payload)
    atomic_write_json(selected_dir / "script.json", script_payload)

    for path in [base / "content.json", base / "script.json"]:
        _write_manifest(path)

    result = audit(date)

    assert result["publishable"] is True
    assert result["status"] == "ok"
    assert result["error_count"] == 0


def test_agent_audit_blocks_when_selected_variant_not_promoted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    date = "2026-04-26"
    base = tmp_path / "data" / date
    selected_dir = base / "variants" / "v01_balanced"
    selected_dir.mkdir(parents=True)

    atomic_write_json(
        base / "pipeline_state.json",
        {"schema_version": 1, "date": date, "status": "complete"},
    )
    atomic_write_json(
        base / "agent_decision.json",
        {"schema_version": 1, "date": date, "status": "continue"},
    )
    atomic_write_json(
        base / "agent_variant_decision.json",
        {
            "schema_version": 1,
            "date": date,
            "status": "continue",
            "selected_variant": "v01_balanced",
        },
    )
    atomic_write_json(base / "content.json", {"items": []})
    atomic_write_json(base / "script.json", {"title": "A", "segments": []})
    atomic_write_json(selected_dir / "script.json", {"title": "B", "segments": []})

    result = audit(date)

    assert result["publishable"] is False
    assert result["status"] == "blocked"
    assert any(i["check"] == "selected_variant_promoted" for i in result["issues"])
