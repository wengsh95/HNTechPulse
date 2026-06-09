import json
from unittest.mock import MagicMock, patch
from pathlib import Path

from src.core.interfaces import ContentFetcher, LLMProvider, TTSProvider, Renderer
from src.core.models import ContentPackage, Script, ScriptSegment
from src.core.models import ContentComment, ContentItem
from src.pipeline.orchestrator import (
    DEFAULT_STEPS,
    Orchestrator,
    PIPELINE_STEPS,
    STANDALONE_STEPS,
    _resolve_steps,
)


# ── Fixtures ─────────────────────────────────────────────────────────────


def _make_config():
    return {
        "logging": {"level": "WARNING"},
        "pipeline": {"target_story_count": 3},
        "llm": {"model": "test-model", "fast_model": "test-fast"},
    }


def _make_orchestrator(dry_run=True):
    config = _make_config()
    return Orchestrator(
        config=config,
        content_fetcher=MagicMock(spec=ContentFetcher),
        llm_provider=MagicMock(spec=LLMProvider),
        tts_provider=MagicMock(spec=TTSProvider),
        renderer=MagicMock(spec=Renderer),
        debug=True,
        dry_run=dry_run,
    )


def _make_content():
    return ContentPackage(date="2026-04-26", items=[])


def _make_failed_content():
    return ContentPackage(
        date="2026-04-26",
        items=[
            ContentItem(
                source="hackernews",
                source_id="123",
                title="Failed Story",
                url="https://example.com/failed",
                enrichment_source="fetch_failed",
            )
        ],
    )


def _make_failed_content_with_comments():
    content = _make_failed_content()
    content.items[0].comments = [
        ContentComment(author=f"u{i}", content=f"substantial comment {i}")
        for i in range(5)
    ]
    return content


def _make_script():
    return Script(
        title="T",
        description="D",
        tags=[],
        segments=[ScriptSegment(segment_type="opening", audio_text="hi", duration=1.0)],
    )


# ── Step list constants ─────────────────────────────────────────────────


class TestStepList:
    def test_pipeline_steps_in_expected_order(self):
        expected = [
            "fetch",
            "prefilter",
            "fetch_comments",
            "enrich_articles",
            "translate_titles",
            "analyze_comments",
            "judge_comments",
            "write_script",
            "translate_comments",
            "synthesize_audio",
            "title",
            "cover_image",
            "cover_thumbnail",
            "publish_guide",
            "prepare_render",
        ]
        assert PIPELINE_STEPS == expected

    def test_standalone_is_render(self):
        assert STANDALONE_STEPS == {"render", "preview"}

    def test_default_steps_skip_optional_production_assets(self):
        assert "cover_image" not in DEFAULT_STEPS
        assert "cover_thumbnail" not in DEFAULT_STEPS
        assert "publish_guide" not in DEFAULT_STEPS
        assert DEFAULT_STEPS[-1] == "prepare_render"

    def test_optional_cover_thumbnail_expands_to_cover_image_only(self):
        assert _resolve_steps(["cover_thumbnail"]) == [
            "cover_image",
            "cover_thumbnail",
        ]


# ── Per-step behaviour ──────────────────────────────────────────────────


class TestStepFetch:
    def test_dry_run_returns_empty_package(self):
        orch = _make_orchestrator(dry_run=True)
        result = orch._step_fetch("2026-04-26")
        assert isinstance(result, ContentPackage)
        assert result.date == "2026-04-26"
        assert len(result.items) == 0


class TestStepPrefilter:
    def test_dry_run_returns_content_unchanged(self):
        orch = _make_orchestrator(dry_run=True)
        content = _make_content()
        assert orch._step_prefilter(content, "2026-04-26") is content

    def test_prefilter_cache_is_validated_by_prefilter(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "data" / "2026-04-26").mkdir(parents=True)
        (tmp_path / "data" / "2026-04-26" / "content.json").write_text('{"items":[]}')
        (tmp_path / "data" / "2026-04-26" / "prefilter.json").write_text("{}")

        orch = _make_orchestrator(dry_run=False)
        orch.config["prefilter"] = {"comment_preview_enabled": False}
        orch.prefilter = MagicMock()
        content = _make_content()
        orch.prefilter.filter.return_value = content
        result = orch._step_prefilter(content, "2026-04-26")
        assert result is content
        orch.prefilter.filter.assert_called_once_with(content, "2026-04-26")

    def test_fetches_comment_preview_before_prefilter(self):
        orch = _make_orchestrator(dry_run=False)
        orch.config["prefilter"] = {"comment_preview_enabled": True, "comment_preview_count": 3}
        content = _make_failed_content()
        orch.content_fetcher.fetch_comment_preview = MagicMock(return_value=content)
        orch.prefilter = MagicMock()
        orch.prefilter.filter.return_value = content
        orch.content_preparer = MagicMock()

        result = orch._step_prefilter(content, "2026-04-26")

        assert result is content
        orch.content_fetcher.fetch_comment_preview.assert_called_once_with(
            content,
            "2026-04-26",
            top_level_count=3,
        )
        orch.prefilter.filter.assert_called_once_with(content, "2026-04-26")


class TestStepFetchComments:
    def test_dry_run_returns_content_unchanged(self):
        orch = _make_orchestrator(dry_run=True)
        content = _make_content()
        assert orch._step_fetch_comments(content, "2026-04-26") is content

    def test_partial_comments_do_not_skip_full_fetch(self):
        orch = _make_orchestrator(dry_run=False)
        content = _make_failed_content_with_comments()
        content.items[0].comments_partial = True
        orch.content_fetcher.fetch_comments = MagicMock(return_value=content)
        orch.content_preparer = MagicMock()

        result = orch._step_fetch_comments(content, "2026-04-26")

        assert result is content
        orch.content_fetcher.fetch_comments.assert_called_once_with(
            content,
            "2026-04-26",
        )


class TestStepEnrichArticles:
    def test_dry_run_returns_empty_failure_list(self):
        orch = _make_orchestrator(dry_run=True)
        content = _make_content()
        out, failed = orch._step_enrich_articles(content, "2026-04-26")
        assert out is content
        assert failed == []

    def test_no_enricher_returns_empty_failure_list(self):
        orch = _make_orchestrator(dry_run=False)
        orch.article_enricher = None
        content = _make_content()
        out, failed = orch._step_enrich_articles(content, "2026-04-26")
        assert out is content
        assert failed == []


class TestStepTranslateTitles:
    def test_dry_run_returns_content_unchanged(self):
        orch = _make_orchestrator(dry_run=True)
        content = _make_content()
        assert orch._step_translate_titles(content, "2026-04-26") is content


class TestStepAnalyzeComments:
    def test_dry_run_returns_content_unchanged(self):
        orch = _make_orchestrator(dry_run=True)
        content = _make_content()
        assert orch._step_analyze_comments(content, "2026-04-26") is content


class TestStepJudgeComments:
    def test_dry_run_returns_content_unchanged(self):
        orch = _make_orchestrator(dry_run=True)
        content = _make_content()
        assert orch._step_judge_comments(content, "2026-04-26") is content


class TestStepWriteScript:
    def test_dry_run_returns_test_script(self):
        orch = _make_orchestrator(dry_run=True)
        content = _make_content()
        result = orch._step_write_script(content, "2026-04-26")
        assert isinstance(result, Script)
        assert len(result.segments) >= 1
        assert result.segments[0].segment_type == "opening"


class TestStepTranslateComments:
    def test_dry_run_returns_content_unchanged(self):
        orch = _make_orchestrator(dry_run=True)
        content = _make_content()
        script = _make_script()
        out_c, out_s = orch._step_translate_comments(content, script, "2026-04-26")
        assert out_c is content
        assert out_s is script

    def test_no_script_skips(self):
        orch = _make_orchestrator(dry_run=False)
        orch.translation_manager = MagicMock()
        content = _make_content()
        out_c, out_s = orch._step_translate_comments(content, None, "2026-04-26")
        assert out_c is content
        assert out_s is None
        orch.translation_manager.translate.assert_not_called()


class TestStepSynthesizeAudio:
    def test_dry_run_returns_script_with_zero_audio(self):
        orch = _make_orchestrator(dry_run=True)
        script = _make_script()
        result = orch._step_synthesize_audio(_make_content(), script, "2026-04-26")
        assert result is script
        assert all(s.audio_path == "" for s in result.segments)

    def test_no_script_returns_none(self):
        orch = _make_orchestrator(dry_run=False)
        orch.tts_processor = MagicMock()
        result = orch._step_synthesize_audio(_make_content(), None, "2026-04-26")
        assert result is None
        orch.tts_processor.process_audio.assert_not_called()


class TestStepTitle:
    def test_dry_run_returns_script_unchanged(self):
        orch = _make_orchestrator(dry_run=True)
        script = _make_script()
        result = orch._step_title(_make_content(), script, "2026-04-26")
        assert result is script

    def test_no_script_returns_none(self):
        orch = _make_orchestrator(dry_run=False)
        result = orch._step_title(_make_content(), None, "2026-04-26")
        assert result is None


class TestStepCoverImage:
    def test_dry_run_returns_none(self):
        orch = _make_orchestrator(dry_run=True)
        result = orch._step_cover_image(_make_content(), _make_script(), "2026-04-26")
        assert result is None
        orch.image_generator = None


class TestStepCoverThumbnail:
    def test_dry_run_returns_none(self):
        orch = _make_orchestrator(dry_run=True)
        with patch.object(Path, "exists", return_value=True):
            result = orch._step_cover_thumbnail(
                _make_content(), _make_script(), "2026-04-26"
            )
        assert result is None


class TestStepPublishGuide:
    def test_dry_run_returns_none(self):
        orch = _make_orchestrator(dry_run=True)
        result = orch._step_publish_guide(_make_content(), _make_script(), "2026-04-26")
        assert result is None


class TestStepPrepareRender:
    def test_dry_run_does_not_call_renderer(self):
        orch = _make_orchestrator(dry_run=True)
        orch._step_prepare_render(_make_content(), _make_script(), "2026-04-26")
        orch.renderer.write_props.assert_not_called()

    def test_no_script_warns_and_skips(self):
        orch = _make_orchestrator(dry_run=False)
        orch._step_prepare_render(_make_content(), None, "2026-04-26")
        orch.renderer.write_props.assert_not_called()

    def test_invokes_renderer_write_props(self):
        orch = _make_orchestrator(dry_run=False)
        script = _make_script()
        content = _make_content()
        # write_props contract: returns (props_path, props_json, scenes_payload).
        # The mock would otherwise return a bare MagicMock, which can't be
        # unpacked into 3 values.
        orch.renderer.write_props.return_value = (Path("/tmp/props.json"), "{}", {})
        orch._step_prepare_render(content, script, "2026-04-26")
        orch.renderer.write_props.assert_called_once()


class TestStepRender:
    def test_dry_run_returns_none(self):
        orch = _make_orchestrator(dry_run=True)
        result = orch._step_render(_make_script(), "2026-04-26")
        assert result is None
        orch.renderer.render.assert_not_called()


# ── run() dispatch ──────────────────────────────────────────────────────


class TestRunDispatch:
    def test_runs_only_requested_step_chain(self):
        orch = _make_orchestrator(dry_run=True)
        # Patch all _step_* methods to detect which get called
        step_names = [
            "_step_fetch",
            "_step_prefilter",
            "_step_fetch_comments",
            "_step_enrich_articles",
            "_step_translate_titles",
            "_step_analyze_comments",
            "_step_judge_comments",
            "_step_write_script",
            "_step_translate_comments",
            "_step_synthesize_audio",
            "_step_title",
            "_step_cover_image",
            "_step_cover_thumbnail",
            "_step_publish_guide",
            "_step_prepare_render",
        ]
        mocks = {}
        for name in step_names:
            m = MagicMock()
            if name == "_step_enrich_articles":
                m.return_value = (_make_content(), [])
            elif name in ("_step_translate_comments",):
                m.return_value = (_make_content(), _make_script())
            elif name in (
                "_step_synthesize_audio",
                "_step_title",
                "_step_write_script",
            ):
                m.return_value = _make_script()
            elif name == "_step_fetch":
                m.return_value = _make_content()
            else:
                m.return_value = None
            setattr(orch, name, m)
            mocks[name] = m

        # Request only "title" — should expand to all steps up to "title"
        orch.run("2026-04-26", steps=["title"], force=False)

        # Steps before and including "title" should have been called;
        # steps after should not.
        steps_in_order = [
            "_step_fetch",
            "_step_prefilter",
            "_step_fetch_comments",
            "_step_enrich_articles",
            "_step_translate_titles",
            "_step_analyze_comments",
            "_step_judge_comments",
            "_step_write_script",
            "_step_translate_comments",
            "_step_synthesize_audio",
            "_step_title",
        ]
        steps_after = [
            "_step_cover_image",
            "_step_cover_thumbnail",
            "_step_publish_guide",
            "_step_prepare_render",
        ]
        for name in steps_in_order:
            mocks[name].assert_called_once(), f"{name} should have been called"
        for name in steps_after:
            mocks[name].assert_not_called(), f"{name} should NOT have been called"

    def test_agent_mode_writes_state_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        orch = _make_orchestrator(dry_run=True)
        orch.agent_mode = True

        orch.run("2026-04-26", steps=["fetch"], force=False)

        state_path = tmp_path / "data" / "2026-04-26" / "pipeline_state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["status"] == "complete"
        assert state["completed_steps"] == ["fetch"]
        assert state["artifacts"]["content"] is None

    def test_agent_mode_blocks_after_enrichment_failure(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        orch = _make_orchestrator(dry_run=False)
        orch.agent_mode = True
        content = _make_failed_content_with_comments()
        script = _make_script()
        orch._step_fetch = MagicMock(return_value=content)
        orch._step_prefilter = MagicMock(return_value=content)
        orch._step_fetch_comments = MagicMock(return_value=content)
        orch._step_enrich_articles = MagicMock(return_value=(content, content.items))
        orch._step_translate_titles = MagicMock(return_value=content)
        orch._step_analyze_comments = MagicMock(return_value=content)
        orch._step_judge_comments = MagicMock(return_value=content)
        orch._step_write_script = MagicMock(return_value=script)

        orch.run("2026-04-26", steps=["write_script"], force=False)

        orch._step_translate_titles.assert_not_called()
        orch._step_write_script.assert_not_called()
        state_path = tmp_path / "data" / "2026-04-26" / "pipeline_state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["status"] == "blocked"
        assert state["blocked_reason"] == "manual_download_required"
        assert state["missing_manual_files"][0]["story_id"] == "123"
        task_path = tmp_path / "data" / "2026-04-26" / "agent_tasks.json"
        tasks = json.loads(task_path.read_text(encoding="utf-8"))
        assert tasks["schema_version"] == 2
        assert tasks["repair_contract"]["owner"] == "agent"
        assert tasks["repair_contract"]["do_not_continue_without_source_context"]
        assert tasks["tasks"][0]["task_type"] == "fetch_article"
        assert tasks["tasks"][0]["save_as"]["html"].endswith("123.html")
        assert tasks["tasks"][0]["acceptable_outputs"] == ["html", "pdf", "synthesis_html"]
        assert tasks["tasks"][0]["resume_command"].endswith(
            "scripts/agent_run.py --date 2026-04-26 --resume"
        )
        assert "Do not fabricate" in tasks["tasks"][0]["failure_policy"]
        events_path = tmp_path / "data" / "2026-04-26" / "agent_events.jsonl"
        assert "run_blocked" in events_path.read_text(encoding="utf-8")
        assert "downloaded_pages" in state["next_recommended_command"]

    def test_agent_mode_can_allow_degraded_enrichment(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        orch = _make_orchestrator(dry_run=False)
        orch.agent_mode = True
        orch.allow_degraded_enrichment = True
        content = _make_failed_content()
        script = _make_script()
        orch._step_fetch = MagicMock(return_value=content)
        orch._step_prefilter = MagicMock(return_value=content)
        orch._step_fetch_comments = MagicMock(return_value=content)
        orch._step_enrich_articles = MagicMock(return_value=(content, content.items))
        orch._step_translate_titles = MagicMock(return_value=content)
        orch._step_analyze_comments = MagicMock(return_value=content)
        orch._step_judge_comments = MagicMock(return_value=content)
        orch._step_write_script = MagicMock(return_value=script)

        orch.run("2026-04-26", steps=["write_script"], force=False)

        orch._step_translate_titles.assert_called_once()
        orch._step_write_script.assert_called_once()
        state_path = tmp_path / "data" / "2026-04-26" / "pipeline_state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["status"] == "degraded"
        assert state["degraded_items"][0]["story_id"] == "123"
        assert state["degraded_items"][0]["continued"] is True

    def test_refresh_variants_clears_script_outputs_only(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        base = tmp_path / "data" / "2026-04-26"
        segments = base / "segments"
        variants = base / "variants"
        segments.mkdir(parents=True)
        variants.mkdir(parents=True)
        (base / "content.json").write_text("{}", encoding="utf-8")
        (base / "script.json").write_text("{}", encoding="utf-8")
        (base / "selected_variant.json").write_text("{}", encoding="utf-8")
        (variants / "index.json").write_text("{}", encoding="utf-8")
        (segments / "story_scan_item_0.json").write_text("{}", encoding="utf-8")
        (segments / "translation_titles.json").write_text("{}", encoding="utf-8")
        orch = _make_orchestrator(dry_run=False)

        orch._refresh_variant_outputs("2026-04-26")

        assert (base / "content.json").exists()
        assert not (base / "script.json").exists()
        assert not (base / "selected_variant.json").exists()
        assert not variants.exists()
        assert not (segments / "story_scan_item_0.json").exists()
        assert (segments / "translation_titles.json").exists()

    def test_agent_mode_blocks_insufficient_story_context(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        orch = _make_orchestrator(dry_run=False)
        orch.agent_mode = True
        content = _make_failed_content()
        orch._step_fetch = MagicMock(return_value=content)
        orch._step_prefilter = MagicMock(return_value=content)
        orch._step_fetch_comments = MagicMock(return_value=content)
        orch._step_enrich_articles = MagicMock(return_value=(content, content.items))
        orch._step_translate_titles = MagicMock(return_value=content)

        orch.run("2026-04-26", steps=["translate_titles"], force=False)

        orch._step_translate_titles.assert_not_called()
        state_path = tmp_path / "data" / "2026-04-26" / "pipeline_state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["status"] == "blocked"
        assert state["blocked_reason"] == "insufficient_story_context"
        assert state["blocked_items"][0]["comment_count"] == 0
