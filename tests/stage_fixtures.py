"""Small object builders shared by stage-boundary tests."""

from unittest.mock import MagicMock

from src.core.interfaces import ContentFetcher, LLMProvider, Renderer, TTSProvider
from src.core.models import (
    ContentComment,
    ContentItem,
    ContentPackage,
    Script,
    ScriptSegment,
)
from src.pipeline.orchestrator import Orchestrator


def make_config() -> dict:
    return {
        "logging": {"level": "WARNING"},
        "pipeline": {"target_story_count": 3},
        "llm": {"model": "test-model", "fast_model": "test-fast"},
    }


def make_orchestrator(dry_run: bool = True) -> Orchestrator:
    orchestrator = Orchestrator(
        config=make_config(),
        content_fetcher=MagicMock(spec=ContentFetcher),
        llm_provider=MagicMock(spec=LLMProvider),
        tts_provider=MagicMock(spec=TTSProvider),
        renderer=MagicMock(spec=Renderer),
        debug=True,
        dry_run=dry_run,
    )
    orchestrator.llm_provider.fast_model = "test-fast"
    orchestrator.llm_provider.fast_temperature = 0.1
    return orchestrator


def make_content() -> ContentPackage:
    return ContentPackage(date="2026-04-26", items=[])


def make_failed_content() -> ContentPackage:
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


def make_failed_content_with_comments() -> ContentPackage:
    content = make_failed_content()
    content.items[0].comments = [
        ContentComment(author=f"u{i}", content=f"substantial comment {i}")
        for i in range(5)
    ]
    return content


def make_script() -> Script:
    return Script(
        title="T",
        description="D",
        tags=[],
        segments=[ScriptSegment(segment_type="opening", audio_text="hi", duration=1.0)],
    )
