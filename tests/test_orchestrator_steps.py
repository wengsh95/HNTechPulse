from unittest.mock import MagicMock

from src.core.interfaces import ContentFetcher, LLMProvider, TTSProvider, Renderer
from src.core.models import ContentPackage, Script
from src.pipeline.orchestrator import Orchestrator


def _make_config():
    return {
        "logging": {"level": "WARNING"},
        "pipeline": {"num_deep_dive": 1, "num_brief": 2, "num_quick_news": 6},
        "llm": {"model": "test-model"},
    }


def _make_orchestrator(dry_run=True):
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
        dry_run=dry_run,
    )


class TestStepFetch:
    def test_dry_run_returns_empty_package(self):
        orch = _make_orchestrator(dry_run=True)
        result = orch._step_fetch("2026-04-26")
        assert isinstance(result, ContentPackage)
        assert result.date == "2026-04-26"
        assert len(result.items) == 0


class TestStepEnrich:
    def test_dry_run_returns_content_unchanged(self):
        orch = _make_orchestrator(dry_run=True)
        content = ContentPackage(date="2026-04-26", items=[])
        result = orch._step_enrich(content, "2026-04-26")
        assert result is content

    def test_skips_when_enricher_none(self):
        orch = _make_orchestrator(dry_run=False)
        orch.article_enricher = None
        content = ContentPackage(date="2026-04-26", items=[])
        orch.content_fetcher.fetch_comments.return_value = content
        result = orch._step_enrich(content, "2026-04-26")
        assert result is content


class TestStepScript:
    def test_dry_run_returns_test_script(self):
        orch = _make_orchestrator(dry_run=True)
        content = ContentPackage(date="2026-04-26", items=[])
        result = orch._step_script(content, "2026-04-26")
        assert isinstance(result, Script)
        assert len(result.segments) >= 1
        assert result.segments[0].segment_type == "opening"
