import json
from pathlib import Path

from scripts.agent_status import _stale_command, build_status
from src.pipeline.paths import render_path


def _write_manifest(base: Path, renderer: str) -> None:
    props = render_path("2026-06-09", "cli_props.json")
    props.parent.mkdir(parents=True, exist_ok=True)
    props.write_text("{}", encoding="utf-8")
    (props.with_suffix(props.suffix + ".manifest.json")).write_text(
        json.dumps({"inputs": {"renderer": renderer}}, ensure_ascii=False),
        encoding="utf-8",
    )


class TestRendererSpecificStaleness:
    def test_hyperframes_does_not_require_remotion_public_props(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        base = tmp_path / "data" / "2026-06-09"
        (base / "hyperframes_project").mkdir(parents=True)
        _cli = render_path("2026-06-09", "cli_props.json")
        _cli.parent.mkdir(parents=True, exist_ok=True)
        _cli.write_text("{}", encoding="utf-8")
        (base / "hyperframes_project" / "index.html").write_text(
            "<!doctype html>", encoding="utf-8"
        )
        _write_manifest(base, "HyperFramesRenderer")

        status = build_status("2026-06-09")

        reasons = {item["reason"] for item in status["stale_artifacts"]}
        assert "public Remotion props mirror is missing" not in reasons
        assert "HyperFrames project index is missing" not in reasons
        assert status["artifacts"]["hyperframes_index"]["exists"] is True

    def test_hyperframes_missing_index_is_stale(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        base = tmp_path / "data" / "2026-06-09"
        base.mkdir(parents=True)
        _cli = render_path("2026-06-09", "cli_props.json")
        _cli.parent.mkdir(parents=True, exist_ok=True)
        _cli.write_text("{}", encoding="utf-8")
        _write_manifest(base, "HyperFramesRenderer")

        status = build_status("2026-06-09")

        assert {
            "artifact": "data/2026-06-09/hyperframes_project/index.html",
            "reason": "HyperFrames project index is missing",
        } in status["stale_artifacts"]

    def test_remotion_still_requires_public_props(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        base = tmp_path / "data" / "2026-06-09"
        base.mkdir(parents=True)
        _cli = render_path("2026-06-09", "cli_props.json")
        _cli.parent.mkdir(parents=True, exist_ok=True)
        _cli.write_text("{}", encoding="utf-8")
        _write_manifest(base, "RemotionRenderer")

        status = build_status("2026-06-09")

        assert any(
            item["reason"] == "public Remotion props mirror is missing"
            for item in status["stale_artifacts"]
        )


class TestStaleCommand:
    def test_script_stale_recovery_matches_pipeline_order(self):
        command = _stale_command(
            "2026-06-09",
            [
                {
                    "artifact": "data/2026-06-09/script.json",
                    "reason": "content.json is newer than script.json",
                }
            ],
        )["command"]

        expected = (
            "uv run python scripts/agent_run.py --date 2026-06-09 "
            "--steps write_script,translate_comments,synthesize_audio,title,"
            "cover_image,cover_thumbnail,publish_guide,prepare_render,render"
        )
        assert command == expected
