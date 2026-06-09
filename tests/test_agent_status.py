import json
from pathlib import Path

from scripts.agent_status import build_status


def _write_manifest(base: Path, renderer: str) -> None:
    (base / "cli_props.json.manifest.json").write_text(
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
        (base / "cli_props.json").write_text("{}", encoding="utf-8")
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
        (base / "cli_props.json").write_text("{}", encoding="utf-8")
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
        (base / "cli_props.json").write_text("{}", encoding="utf-8")
        _write_manifest(base, "RemotionRenderer")

        status = build_status("2026-06-09")

        assert any(
            item["reason"] == "public Remotion props mirror is missing"
            for item in status["stale_artifacts"]
        )
