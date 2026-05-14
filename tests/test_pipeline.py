import pytest
from unittest.mock import MagicMock

from src.core.models import (
    ContentItem,
    ContentComment,
    ContentPackage,
    Script,
    ScriptSegment,
    SceneElement,
    SelectionResult,
)
from src.core.interfaces import ContentFetcher, LLMProvider, TTSProvider, Renderer
from src.pipeline.content_preparer import ContentPreparer
from src.pipeline.script_writer import ScriptWriter
from src.pipeline.orchestrator import Orchestrator
from src.pipeline.comment_judgement import save_comment_judgements


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
            ContentComment(author=f"user_{j}", content=f"comment {j}") for j in range(3)
        ]
        items.append(
            ContentItem(
                source="hackernews",
                source_id=str(100 + i),
                title=f"Story {i}",
                url=f"https://example.com/{i}",
                score=100 - i * 10,
                comment_count=3,
                published_at=1700000000 + i * 100,
                comments=comments,
            )
        )
    return ContentPackage(
        date="2026-04-26",
        items=items,
        deep_dive_indices=[0],
        brief_indices=[1, 2],
        quick_news_indices=[3, 4, 5, 6, 7, 8],
    )


def _make_selection_result():
    return SelectionResult(
        brief_items=[{"story_index": 0}],
        raw_json='{"brief_items": [{"story_index": 0}]}',
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
    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        """Save a ContentPackage, load it back, verify all fields match."""
        monkeypatch.chdir(tmp_path)
        config = _make_config()
        preparer = ContentPreparer(config, debug=True)
        content = _make_content_package()
        date = "2026-04-26"

        preparer.save_content(content, date)
        loaded = preparer.load_content(date)

        assert loaded.date == content.date
        assert loaded.deep_dive_indices == content.deep_dive_indices
        assert loaded.brief_indices == content.brief_indices
        assert loaded.quick_news_indices == content.quick_news_indices
        assert len(loaded.items) == len(content.items)
        for original, loaded_item in zip(content.items, loaded.items):
            assert loaded_item.source == original.source
            assert loaded_item.source_id == original.source_id
            assert loaded_item.title == original.title
            assert loaded_item.url == original.url
            assert loaded_item.score == original.score
            assert loaded_item.comment_count == original.comment_count
            assert len(loaded_item.comments) == len(original.comments)
            for orig_c, load_c in zip(original.comments, loaded_item.comments):
                assert load_c.author == orig_c.author
                assert load_c.content == orig_c.content


class TestScriptWriter:
    def test_write_calls_llm_provider(self, tmp_path):
        config = _make_config()
        mock_llm = MagicMock()
        mock_llm.generate_single_story_segment.return_value = ScriptSegment(
            segment_type="story_scan_item",
            audio_text="test",
            estimated_duration=10.0,
            emotion="upbeat",
        )

        writer = ScriptWriter(config, mock_llm, debug=True)

        content = _make_content_package()

        script = writer.write(content)

        assert (
            mock_llm.generate_single_story_segment.call_count == 6
        )  # num_brief_items default
        assert len(script.segments) >= 2  # at least opening + closing

    def test_write_passes_comment_judgement_to_story_generation(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        config = _make_config()
        mock_llm = MagicMock()
        mock_llm.generate_single_story_segment.return_value = ScriptSegment(
            segment_type="story_scan_item",
            audio_text="test",
            estimated_duration=10.0,
            emotion="upbeat",
            scene_elements=[
                SceneElement(
                    element_type="quote_card",
                    start_time=0,
                    end_time=0,
                    props={"story_index": 0, "selected_comment_ids": []},
                )
            ],
        )
        content = _make_content_package()
        content.items[0].comments = [
            ContentComment(
                author="u",
                content="I am skeptical because this creates a real operational tradeoff.",
                source_id="c1",
                quality_score=0.8,
            )
        ]
        save_comment_judgements(
            content.date,
            {
                content.items[0].source_id: {
                    "story_id": content.items[0].source_id,
                    "quote_candidates": [
                        {"comment_id": "c1", "quote_score": 0.9, "has_viewpoint": True}
                    ],
                }
            },
        )

        writer = ScriptWriter(config, mock_llm, debug=True)
        writer.write(content)

        first_call = mock_llm.generate_single_story_segment.call_args_list[0]
        assert (
            first_call.kwargs["comments_data"]["quote_candidates"][0]["comment_id"]
            == "c1"
        )


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
                ScriptSegment(
                    segment_type="b", audio_text="y", estimated_duration=10.0
                ),
            ],
        )
        result = orch._timing.compute_timeline(script)
        assert result.segments[0].start_time == 0.0
        assert result.segments[0].end_time == 5.0
        assert result.segments[1].start_time == 5.0
        assert result.segments[1].end_time == 15.0
        assert result.total_duration == 15.0


class TestLLMProviderInterface:
    def test_selection_result_importable_from_core(self):
        from src.core.models import SelectionResult

        assert SelectionResult is not None

    def test_llm_provider_interface_references_core_types(self):
        import inspect

        sig = inspect.signature(LLMProvider.generate_single_story_segment)
        assert "content" in sig.parameters
        assert "story_index" in sig.parameters


class TestSubtitleVisualAlignment:
    """Verify scene_element and cue times are consistent after TTS."""

    def _make_orchestrator(self):
        config = _make_config()
        mock_fetcher = MagicMock(spec=ContentFetcher)
        mock_llm = MagicMock(spec=LLMProvider)
        mock_tts = MagicMock(spec=TTSProvider)
        mock_renderer = MagicMock(spec=Renderer)
        return Orchestrator(
            config=config,
            content_fetcher=mock_fetcher,
            llm_provider=mock_llm,
            tts_provider=mock_tts,
            renderer=mock_renderer,
            debug=True,
            dry_run=True,
        )

    def test_scene_elements_span_full_segment(self):
        """After _set_scene_element_times, each scene_element spans [0, duration]."""
        orch = self._make_orchestrator()
        script = Script(
            title="Test",
            description="",
            tags=[],
            segments=[
                ScriptSegment(
                    segment_type="opening",
                    audio_text="Hello",
                    estimated_duration=7.0,
                    actual_duration=6.5,
                    scene_elements=[
                        SceneElement(
                            element_type="cover_card",
                            start_time=0,
                            end_time=0,
                            props={},
                        )
                    ],
                ),
                ScriptSegment(
                    segment_type="closing",
                    audio_text="Bye",
                    estimated_duration=8.0,
                    actual_duration=7.2,
                    scene_elements=[
                        SceneElement(
                            element_type="closing_card",
                            start_time=0,
                            end_time=0,
                            props={},
                        )
                    ],
                ),
            ],
        )
        orch._timing.set_scene_element_times(script)
        for seg in script.segments:
            duration = seg.actual_duration
            for elem in seg.scene_elements:
                assert elem.start_time == 0.0
                assert elem.end_time == duration

    def test_combined_segment_proportional_layout(self):
        """story_scan with sub_segment_estimated_durations lays out elements proportionally."""
        orch = self._make_orchestrator()
        script = Script(
            title="Test",
            description="",
            tags=[],
            segments=[
                ScriptSegment(
                    segment_type="story_scan",
                    audio_text="A B C",
                    estimated_duration=40.0,
                    actual_duration=50.0,
                    scene_elements=[
                        SceneElement(
                            element_type="story_scan_card",
                            start_time=0,
                            end_time=0,
                            props={"story_index": i},
                        )
                        for i in range(3)
                    ],
                    meta={"sub_segment_estimated_durations": [10.0, 20.0, 10.0]},
                ),
            ],
        )
        orch._timing.set_scene_element_times(script)
        seg = script.segments[0]
        assert seg.scene_elements[0].start_time == 0.0
        assert seg.scene_elements[0].end_time == pytest.approx(12.5)
        assert seg.scene_elements[1].start_time == pytest.approx(12.5)
        assert seg.scene_elements[1].end_time == pytest.approx(37.5)
        assert seg.scene_elements[2].start_time == pytest.approx(37.5)
        assert seg.scene_elements[2].end_time == pytest.approx(50.0)

    def test_no_time_out_of_bounds(self):
        """No scene_element time exceeds segment duration."""
        orch = self._make_orchestrator()
        script = Script(
            title="Test",
            description="",
            tags=[],
            segments=[
                ScriptSegment(
                    segment_type="story_scan",
                    audio_text="A B",
                    estimated_duration=20.0,
                    actual_duration=18.0,
                    scene_elements=[
                        SceneElement(
                            element_type="story_scan_card",
                            start_time=0,
                            end_time=0,
                            props={},
                        ),
                        SceneElement(
                            element_type="story_scan_card",
                            start_time=0,
                            end_time=0,
                            props={},
                        ),
                    ],
                    meta={"sub_segment_estimated_durations": [10.0, 10.0]},
                ),
            ],
        )
        orch._timing.set_scene_element_times(script)
        seg = script.segments[0]
        for elem in seg.scene_elements:
            assert 0.0 <= elem.start_time <= seg.actual_duration
            assert 0.0 <= elem.end_time <= seg.actual_duration
            assert elem.end_time > elem.start_time

    def test_time_monotonicity(self):
        """scene_element end_time > start_time, and elements don't overlap backwards."""
        orch = self._make_orchestrator()
        script = Script(
            title="Test",
            description="",
            tags=[],
            segments=[
                ScriptSegment(
                    segment_type="story_scan",
                    audio_text="A B C",
                    estimated_duration=30.0,
                    actual_duration=28.0,
                    scene_elements=[
                        SceneElement(
                            element_type="story_scan_card",
                            start_time=0,
                            end_time=0,
                            props={},
                        )
                        for _ in range(3)
                    ],
                    meta={"sub_segment_estimated_durations": [8.0, 15.0, 7.0]},
                ),
            ],
        )
        orch._timing.set_scene_element_times(script)
        seg = script.segments[0]
        prev_end = 0.0
        for elem in seg.scene_elements:
            assert elem.end_time > elem.start_time
            assert elem.start_time >= prev_end
            prev_end = elem.end_time
