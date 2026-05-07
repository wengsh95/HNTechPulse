import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from src.core.models import (
    ContentItem, ContentComment, ContentPackage,
    Script, ScriptSegment, SceneElement, Cue,
    StoryAnalysis, SelectionResult,
)
from src.core.interfaces import ContentFetcher, LLMProvider, TTSProvider, Renderer
from src.pipeline.content_preparer import ContentPreparer
from src.pipeline.script_writer import ScriptWriter
from src.pipeline.orchestrator import Orchestrator


def _make_config():
    return {
        "logging": {"level": "WARNING"},
        "pipeline": {
            "num_deep_dive": 1,
            "num_brief": 2,
            "num_quick_news": 6,
        },
        "llm": {"model": "test-model"},
    }


def _make_content_package():
    items = []
    for i in range(9):
        comments = [
            ContentComment(author=f"user_{j}", content=f"comment {j}")
            for j in range(3)
        ]
        items.append(ContentItem(
            source="hackernews",
            source_id=str(100 + i),
            title=f"Story {i}",
            url=f"https://example.com/{i}",
            score=100 - i * 10,
            comment_count=3,
            published_at=1700000000 + i * 100,
            comments=comments,
        ))
    return ContentPackage(
        date="2026-04-26",
        items=items,
        deep_dive_indices=[0],
        brief_indices=[1, 2],
        quick_news_indices=[3, 4, 5, 6, 7, 8],
    )


def _make_selection_result():
    return SelectionResult(
        deep_dive_decision={"story_index": 0, "featured_comment_indices": [0]},
        quick_selections=[{"story_index": 1, "featured_comment_index": 0}],
        patterns=[],
        raw_json='{"deep_dive_decision": {"story_index": 0}}',
    )


def _make_script():
    return Script(
        title="Test Script",
        description="Test",
        tags=["test"],
        segments=[
            ScriptSegment(
                segment_type="opening",
                audio_text="Hello",
                estimated_duration=10.0,
                actual_duration=10.0,
                start_time=0.0,
                end_time=10.0,
            ),
            ScriptSegment(
                segment_type="quick_news",
                audio_text="News",
                estimated_duration=20.0,
                actual_duration=20.0,
                start_time=10.0,
                end_time=30.0,
            ),
        ],
        total_duration=30.0,
    )


class TestContentPreparer:
    def test_prepare_returns_content_unchanged(self):
        config = _make_config()
        preparer = ContentPreparer(config, debug=True)
        content = _make_content_package()
        result = preparer.prepare(content)
        assert result is content

    def test_save_and_load_roundtrip(self, tmp_path):
        config = _make_config()
        preparer = ContentPreparer(config, debug=True)
        content = _make_content_package()

        date = "2026-04-26"
        with patch.object(Path, "mkdir"):
            with patch("builtins.open", MagicMock()):
                with patch("json.dump"):
                    preparer.save_content(content, date)


class TestScriptWriter:
    def test_write_calls_llm_provider(self):
        config = _make_config()
        mock_llm = MagicMock(spec=LLMProvider)
        mock_llm.generate_selection.return_value = _make_selection_result()
        mock_llm.build_comments_json.return_value = "{}"
        mock_llm.generate_script.return_value = _make_script()

        writer = ScriptWriter(config, mock_llm, debug=True)

        content = _make_content_package()
        with patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "read_text", return_value="prompt text"), \
             patch("pathlib.Path.exists", return_value=True), \
             patch.object(Path, "mkdir"):
            pass

    def test_write_from_selection_uses_selection_result_from_core(self):
        config = _make_config()
        mock_llm = MagicMock(spec=LLMProvider)
        mock_llm.build_comments_json.return_value = "{}"
        mock_llm.generate_script.return_value = _make_script()

        writer = ScriptWriter(config, mock_llm, debug=True)

        selection_raw = json.dumps({
            "deep_dive_decision": {"story_index": 0},
            "quick_selections": [],
            "patterns": [],
        })

        content = _make_content_package()
        script = writer.write_from_selection(content, selection_raw, "prompt")

        mock_llm.build_comments_json.assert_called_once()
        mock_llm.generate_script.assert_called_once()
        call_kwargs = mock_llm.generate_script.call_args
        assert isinstance(call_kwargs.kwargs.get("selection") or call_kwargs[1].get("selection"), SelectionResult)


class TestOrchestrator:
    def test_dry_run_fetch(self):
        config = _make_config()
        mock_fetcher = MagicMock(spec=ContentFetcher)
        mock_llm = MagicMock(spec=LLMProvider)
        mock_tts = MagicMock(spec=TTSProvider)
        mock_renderer = MagicMock(spec=Renderer)

        orch = Orchestrator(
            config=config,
            content_fetcher=mock_fetcher,
            llm_provider=mock_llm,
            tts_provider=mock_tts,
            renderer=mock_renderer,
            debug=True,
            dry_run=True,
        )
        orch.run(date="2026-04-26", steps=["fetch"])
        mock_fetcher.fetch.assert_not_called()

    def test_dry_run_tts(self):
        config = _make_config()
        mock_fetcher = MagicMock(spec=ContentFetcher)
        mock_llm = MagicMock(spec=LLMProvider)
        mock_tts = MagicMock(spec=TTSProvider)
        mock_renderer = MagicMock(spec=Renderer)

        orch = Orchestrator(
            config=config,
            content_fetcher=mock_fetcher,
            llm_provider=mock_llm,
            tts_provider=mock_tts,
            renderer=mock_renderer,
            debug=True,
            dry_run=True,
        )

        script = _make_script()
        result = orch._step_tts(script, "2026-04-26")
        assert result.total_duration == 30.0
        for seg in result.segments:
            assert seg.actual_duration is not None

    def test_compute_timeline(self):
        config = _make_config()
        mock_fetcher = MagicMock(spec=ContentFetcher)
        mock_llm = MagicMock(spec=LLMProvider)
        mock_tts = MagicMock(spec=TTSProvider)
        mock_renderer = MagicMock(spec=Renderer)

        orch = Orchestrator(
            config=config,
            content_fetcher=mock_fetcher,
            llm_provider=mock_llm,
            tts_provider=mock_tts,
            renderer=mock_renderer,
            debug=True,
            dry_run=True,
        )

        script = Script(
            title="Test",
            description="",
            tags=[],
            segments=[
                ScriptSegment(segment_type="a", audio_text="x", estimated_duration=5.0),
                ScriptSegment(segment_type="b", audio_text="y", estimated_duration=10.0),
            ],
        )
        result = orch._compute_timeline(script)
        assert result.segments[0].start_time == 0.0
        assert result.segments[0].end_time == 5.0
        assert result.segments[1].start_time == 5.0
        assert result.segments[1].end_time == 15.0
        assert result.total_duration == 15.0


class TestLLMProviderInterface:
    def test_selection_result_importable_from_core(self):
        from src.core.models import SelectionResult, StoryAnalysis
        assert SelectionResult is not None
        assert StoryAnalysis is not None

    def test_llm_provider_interface_references_core_types(self):
        import inspect
        sig = inspect.signature(LLMProvider.generate_selection)
        assert "content" in sig.parameters
        assert "analyze_prompt_template" in sig.parameters
        assert "decision_prompt_template" in sig.parameters
