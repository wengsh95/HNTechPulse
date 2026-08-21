import json
from unittest.mock import MagicMock, patch

import pytest
from pathlib import Path

from src.pipeline.paths import render_path, render_root
from tests.stage_fixtures import make_content, make_orchestrator, make_script


class TestCoverThumbnailStage:
    def test_dry_run_returns_none(self):
        orch = make_orchestrator(dry_run=True)

        with patch.object(Path, "exists", return_value=True):
            assert (
                orch._step_cover_thumbnail(make_content(), make_script(), "2026-04-26")
                is None
            )

    def test_missing_background_or_text_props_fails_with_recovery_hint(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        orch = make_orchestrator(dry_run=False)

        with pytest.raises(FileNotFoundError, match="run --steps cover_image first"):
            orch._step_cover_thumbnail(make_content(), make_script(), "2026-04-26")

    def test_missing_npx_is_reported_after_cover_inputs_exist(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        date = "2026-04-26"
        render_root(date).mkdir(parents=True)
        (render_root(date) / "cover_bg.png").write_bytes(b"png")
        props_path = render_path(date, "cover_props_v1.json")
        props_path.write_text(json.dumps({"title": "Test"}), encoding="utf-8")
        orch = make_orchestrator(dry_run=False)

        with patch("src.pipeline.stages.packaging.find_npx", return_value=None):
            with pytest.raises(FileNotFoundError, match="npx not found"):
                orch._step_cover_thumbnail(make_content(), make_script(), date)


class TestPublishGuideStage:
    def test_dry_run_returns_none(self):
        orch = make_orchestrator(dry_run=True)

        assert (
            orch._write_publish_guide(make_content(), make_script(), "2026-04-26")
            is None
        )

    def test_regenerates_when_manifest_input_hash_is_missing(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        date = "2026-04-26"
        guide_path = (
            tmp_path / "data" / date[:7] / date / "publish" / "publish_guide.md"
        )
        guide_path.parent.mkdir(parents=True)
        guide_path.write_text("old", encoding="utf-8")

        orch = make_orchestrator(dry_run=False)
        orch.llm_provider.complete_prompt = MagicMock(return_value="new guide")

        orch._write_publish_guide(make_content(), make_script(), date)

        assert guide_path.read_text(encoding="utf-8") == "new guide"
        orch.llm_provider.complete_prompt.assert_called_once()

    def test_uses_title_json_for_publish_metadata_context(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        date = "2026-04-26"
        base = tmp_path / "data" / date[:7] / date / "publish"
        base.mkdir(parents=True)
        (base / "title.json").write_text(
            json.dumps(
                {"title": "Published Title", "description": "Published description"},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        orch = make_orchestrator(dry_run=False)
        orch.llm_provider.complete_prompt = MagicMock(return_value="guide")

        orch._write_publish_guide(make_content(), make_script(), date)

        context = orch.llm_provider.complete_prompt.call_args.args[1]
        assert context["script_title"] == "Published Title"
        assert context["script_description"] == "Published description"
        assert "prompt_hash" not in context
