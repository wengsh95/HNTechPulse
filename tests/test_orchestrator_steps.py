from unittest.mock import MagicMock, patch
from pathlib import Path

from src.core.interfaces import ContentFetcher, LLMProvider, TTSProvider, Renderer
from src.core.models import ContentPackage, Script, ScriptSegment
from src.pipeline.orchestrator import Orchestrator, PIPELINE_STEPS, STANDALONE_STEPS


# ── Fixtures ─────────────────────────────────────────────────────────────


def _make_config():
    return {
        "logging": {"level": "WARNING"},
        "pipeline": {"num_deep_dive": 1, "num_brief": 2, "target_story_count": 3},
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

    def test_short_circuits_when_cache_exists(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "data" / "2026-04-26").mkdir(parents=True)
        (tmp_path / "data" / "2026-04-26" / "content.json").write_text('{"items":[]}')
        (tmp_path / "data" / "2026-04-26" / "prefilter.json").write_text("{}")

        orch = _make_orchestrator(dry_run=False)
        orch.prefilter = MagicMock()
        content = _make_content()
        result = orch._step_prefilter(content, "2026-04-26")
        assert result is content
        orch.prefilter.filter.assert_not_called()


class TestStepFetchComments:
    def test_dry_run_returns_content_unchanged(self):
        orch = _make_orchestrator(dry_run=True)
        content = _make_content()
        assert orch._step_fetch_comments(content, "2026-04-26") is content


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
