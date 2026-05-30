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
from src.pipeline.content_io import ContentPreparer
from src.pipeline.script import ScriptWriter
from src.pipeline.orchestrator import Orchestrator
from src.pipeline.comment import save_comment_judgements


def _make_config():
    return {
        "logging": {"level": "WARNING"},
        "pipeline": {
            "target_story_count": 3,
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
                duration=10.0,
            ),
            ScriptSegment(
                segment_type="quick_news",
                audio_text="News",
                duration=10.0,
            ),
        ],
    )


class TestContentPreparer:
    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        """Save a ContentPackage, load it back, verify all fields match."""
        monkeypatch.chdir(tmp_path)
        config = _make_config()
        preparer = ContentPreparer(config, debug=True)
        content = _make_content_package()
        content.items[0].why_it_matters = "影响开发工作流"
        date = "2026-04-26"

        preparer.save_content(content, date)
        loaded = preparer.load_content(date)

        assert loaded.date == content.date
        assert loaded.deep_dive_indices == content.deep_dive_indices
        assert loaded.brief_indices == content.brief_indices
        assert len(loaded.items) == len(content.items)
        for original, loaded_item in zip(content.items, loaded.items):
            assert loaded_item.source == original.source
            assert loaded_item.source_id == original.source_id
            assert loaded_item.title == original.title
            assert loaded_item.url == original.url
            assert loaded_item.score == original.score
            assert loaded_item.comment_count == original.comment_count
            assert loaded_item.why_it_matters == original.why_it_matters
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
            duration=10.0,
        )

        writer = ScriptWriter(config, mock_llm, debug=True)

        content = _make_content_package()

        script = writer.write(content)

        assert (
            mock_llm.generate_single_story_segment.call_count
            == config["pipeline"]["target_story_count"]
        )
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
            duration=10.0,
            scene_elements=[
                SceneElement(
                    element_type="quote_card",
                    start_time=0.0,
                    end_time=5.0,
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

    def test_closing_card_includes_daily_signal(self):
        writer = ScriptWriter(_make_config(), MagicMock(), debug=True)
        segment = writer._generate_fixed_closing(
            "2026-04-26",
            [
                {
                    "category": "AI",
                    "keywords": ["Agents", "Infra", "Agents"],
                },
                {
                    "category": "Developer Tools",
                    "keywords": ["Open Source"],
                },
            ],
        )

        props = segment.scene_elements[0].props
        assert props["signal_label"] == "今日信号"
        assert props["signal"] == "今天的技术讨论，先记住问题，再看答案。"
        assert props["keywords_label"] == "今日关键词"
        assert props["keywords"] == ["AI", "Agents", "Infra"]
        assert props["summary_label"] == "今日脉络"
        assert props["summary_items"][0]["category"] == "AI"
        assert (
            props["summary_items"][0]["title"]
            == "AI 正从产品功能，变成开发工作流的底层能力。"
        )
        assert props["totals"]["story_count"] == 2


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


class TestLLMProviderInterface:
    def test_selection_result_importable_from_core(self):
        from src.core.models import SelectionResult

        assert SelectionResult is not None

    def test_llm_provider_interface_references_core_types(self):
        import inspect

        sig = inspect.signature(LLMProvider.generate_single_story_segment)
        assert "content" in sig.parameters
        assert "story_index" in sig.parameters
