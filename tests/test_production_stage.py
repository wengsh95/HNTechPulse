from unittest.mock import MagicMock

import pytest

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


class TestRenderStage:
    def test_dry_run_returns_none(self):
        orch = make_orchestrator(dry_run=True)

        assert orch._step_render(make_script(), "2026-04-26") is None
        orch.renderer.render.assert_not_called()
