from unittest.mock import MagicMock

import pytest

from src.pipeline.paths import publish_path, render_path
from tests.stage_fixtures import make_content, make_orchestrator, make_script


class TestPrepareRenderStage:
    def test_dry_run_does_not_call_renderer(self):
        orch = make_orchestrator(dry_run=True)

        orch._step_prepare_render(make_content(), make_script(), "2026-04-26")

        orch.renderer.write_props.assert_not_called()

    def test_no_script_raises(self):
        orch = make_orchestrator(dry_run=False)

        with pytest.raises(ValueError, match="Script not loaded"):
            orch._step_prepare_render(make_content(), None, "2026-04-26")

        orch.renderer.write_props.assert_not_called()

    def test_invokes_renderer_write_props(self, tmp_path):
        orch = make_orchestrator(dry_run=False)
        props_path = tmp_path / "props.json"
        props_path.write_text("{}", encoding="utf-8")
        orch._write_publish_guide = MagicMock()
        orch.renderer.write_props.return_value = (props_path, "{}", {})

        orch._step_prepare_render(make_content(), make_script(), "2026-04-26")

        orch.renderer.write_props.assert_called_once()
        orch._write_publish_guide.assert_called_once()

    def test_missing_story_image_stops_before_publish_packaging(self, monkeypatch):
        orch = make_orchestrator(dry_run=False)
        orch._write_publish_guide = MagicMock()

        with monkeypatch.context() as patcher:
            patcher.setattr(
                "src.pipeline.stages.production.require_story_images",
                MagicMock(side_effect=FileNotFoundError("story image missing")),
            )
            with pytest.raises(FileNotFoundError, match="story image missing"):
                orch._step_prepare_render(make_content(), make_script(), "2026-04-26")

        orch._write_publish_guide.assert_not_called()
        orch.renderer.write_props.assert_not_called()


class TestRenderStage:
    def test_dry_run_returns_none(self):
        orch = make_orchestrator(dry_run=True)

        assert orch._step_render(make_script(), "2026-04-26") is None
        orch.renderer.render.assert_not_called()

    def test_fresh_output_skips_renderer(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        date = "2026-04-26"
        render_path(date, "cli_props.json").parent.mkdir(parents=True)
        render_path(date, "cli_props.json").write_text("{}", encoding="utf-8")
        publish_path(date, "output.mp4").parent.mkdir(parents=True)
        publish_path(date, "output.mp4").write_bytes(b"video")
        orch = make_orchestrator(dry_run=False)

        with monkeypatch.context() as patcher:
            patcher.setattr(
                "src.pipeline.stages.production.is_artifact_fresh", lambda *args: True
            )
            orch._step_render(make_script(), date, content=make_content())

        orch.renderer.render.assert_not_called()

    def test_renderer_without_output_fails_closed(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        date = "2026-04-26"
        render_path(date, "cli_props.json").parent.mkdir(parents=True)
        render_path(date, "cli_props.json").write_text("{}", encoding="utf-8")
        orch = make_orchestrator(dry_run=False)

        with monkeypatch.context() as patcher:
            patcher.setattr(
                "src.pipeline.stages.production.is_artifact_fresh", lambda *args: False
            )
            with pytest.raises(RuntimeError, match="did not produce a valid output"):
                orch._step_render(make_script(), date, content=make_content())

    def test_preview_dry_run_skips_renderer(self):
        orch = make_orchestrator(dry_run=True)

        orch._step_preview(make_script(), "2026-04-26", content=make_content())

        orch.renderer.preview.assert_not_called()

    def test_clear_render_cache_removes_renderer_cache_and_output(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        date = "2026-04-26"
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        publish_path(date, "output.mp4").parent.mkdir(parents=True)
        publish_path(date, "output.mp4").write_bytes(b"video")
        orch = make_orchestrator(dry_run=False)
        orch.renderer.cache_paths.return_value = [cache_dir]

        orch._clear_render_cache(date)

        assert not cache_dir.exists()
        assert not publish_path(date, "output.mp4").exists()
