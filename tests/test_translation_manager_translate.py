import json
from pathlib import Path
from unittest.mock import MagicMock, patch


from src.core.interfaces import LLMProvider
from src.core.models import (
    ContentComment,
    ContentItem,
    ContentPackage,
    Script,
    ScriptSegment,
)
from src.pipeline.content_io import ContentPreparer
from src.pipeline.translation_manager import TranslationManager


def _make_config():
    return {
        "logging": {"level": "WARNING"},
        "pipeline": {"target_story_count": 3},
        "llm": {"model": "test-model"},
    }


def _make_comment(content="Test comment with enough length", **kwargs):
    defaults = {
        "author": "user",
        "content": content,
        "source_id": "c1",
        "quality_score": 0.5,
    }
    defaults.update(kwargs)
    return ContentComment(**defaults)


def _make_item(comments=None, **kwargs):
    defaults = {
        "source": "hackernews",
        "source_id": "100",
        "title": "Test Story",
        "url": "https://example.com",
        "score": 50,
        "comment_count": len(comments or []),
        "published_at": 1700000000,
        "comments": comments or [],
    }
    defaults.update(kwargs)
    return ContentItem(**defaults)


def _make_content_package(items=None):
    if items is None:
        items = [_make_item()]
    return ContentPackage(date="2026-04-26", items=items)


def _make_script():
    return Script(
        title="Test",
        description="",
        tags=[],
        segments=[
            ScriptSegment(
                segment_type="opening",
                audio_text="Hello",
                duration=10.0,
            ),
        ],
    )


def _make_manager():
    mock_llm = MagicMock(spec=LLMProvider)
    config = _make_config()
    with patch("src.pipeline.translation_manager.setup_logger"):
        preparer = ContentPreparer(config, debug=True)
        manager = TranslationManager(mock_llm, preparer, config, debug=True)
    return manager, mock_llm


class TestTranslate:
    def test_loads_cached_translations_into_script(self, tmp_path, monkeypatch):
        """Cached title translations should flow through to the script's
        opening/cover card via apply_translations_to_script. Title_cn on
        ContentItem is owned by the enrich step, not translate()."""
        monkeypatch.chdir(tmp_path)
        manager, mock_llm = _make_manager()
        content = _make_content_package()
        script = _make_script()

        # Cached translations keyed by source_id (the unified scheme).
        trans_path = Path("data/2026-04-26/translations.json")
        trans_path.parent.mkdir(parents=True, exist_ok=True)
        trans_path.write_text(json.dumps({"title_100": "测试标题"}), encoding="utf-8")

        manager.content_preparer.save_content(content, "2026-04-26")

        with patch.object(manager, "collect_comment_refs", return_value={}):
            manager.translate(content, script, "2026-04-26")

        # Manager no longer mutates title_cn — that's enrich's job.
        assert content.items[0].title_cn is None
        # translate_titles is no longer called from the produce step.
        mock_llm.translate_titles.assert_not_called()
        # The cached translation will still flow into the script's
        # cover/highlight cards via apply_translations_to_script (called
        # inside manager.translate).

    def test_does_not_call_translate_titles(self, tmp_path, monkeypatch):
        """After the M3 refactor, title translation is owned by the enrich
        step. TranslationManager.translate must not invoke the LLM provider's
        translate_titles even when items lack title_cn."""
        monkeypatch.chdir(tmp_path)
        manager, mock_llm = _make_manager()
        item_with_cn = _make_item(source_id="100", title_cn="翻译标题")
        item_without_cn = _make_item(source_id="101", title="Another Story")
        content = _make_content_package(items=[item_with_cn, item_without_cn])
        script = _make_script()

        with patch.object(manager, "collect_comment_refs", return_value={}):
            with patch.object(manager, "_apply_comment_translations"):
                manager.translate(content, script, "2026-04-26")

        mock_llm.translate_titles.assert_not_called()
