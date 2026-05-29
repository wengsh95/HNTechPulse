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
        "pipeline": {"num_deep_dive": 1, "num_brief": 2},
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
    def test_loads_cached_translations(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        manager, mock_llm = _make_manager()
        content = _make_content_package()
        script = _make_script()

        # Create cached translations
        trans_path = Path("data/2026-04-26/translations.json")
        trans_path.parent.mkdir(parents=True, exist_ok=True)
        trans_path.write_text(json.dumps({"title_100": "测试标题"}), encoding="utf-8")

        # Also need content saved for content_preparer
        manager.content_preparer.save_content(content, "2026-04-26")

        with patch.object(manager, "collect_comment_refs", return_value={}):
            result_content, result_script = manager.translate(
                content, script, "2026-04-26"
            )

        assert result_content.items[0].title_cn == "测试标题"
        mock_llm.translate_titles.assert_not_called()

    def test_calls_llm_for_missing_titles(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        manager, mock_llm = _make_manager()
        content = _make_content_package()
        script = _make_script()

        mock_llm.translate_titles.return_value = content
        content.items[0].title_cn = "翻译标题"

        # Ensure no cache exists
        with patch.object(manager, "collect_comment_refs", return_value={}):
            with patch.object(manager, "_apply_comment_translations"):
                result_content, _ = manager.translate(content, script, "2026-04-26")

        mock_llm.translate_titles.assert_called_once()
