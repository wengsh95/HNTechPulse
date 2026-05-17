from pathlib import Path
from unittest.mock import patch


from src.core.models import (
    ContentItem,
    ContentPackage,
    SceneElement,
    Script,
    ScriptSegment,
)
from src.pipeline.report_generator import ReportGenerator


def _make_item(**kwargs):
    defaults = {
        "source": "hackernews",
        "source_id": "100",
        "title": "Test Story",
        "url": "https://example.com",
        "score": 50,
        "comment_count": 10,
        "published_at": 1700000000,
    }
    defaults.update(kwargs)
    return ContentItem(**defaults)


def _make_content_package(items=None):
    if items is None:
        items = [_make_item()]
    return ContentPackage(date="2026-04-26", items=items)


def _make_script(segments=None):
    if segments is None:
        segments = [
            ScriptSegment(
                segment_type="opening",
                audio_text="Hello",
                estimated_duration=10.0,
                actual_duration=9.0,
            ),
            ScriptSegment(
                segment_type="closing",
                audio_text="Bye",
                estimated_duration=8.0,
                actual_duration=7.0,
            ),
        ]
    return Script(title="Test", description="", tags=[], segments=segments)


class TestGenerate:
    def test_creates_report_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("src.pipeline.report_generator.setup_logger"):
            gen = ReportGenerator()
        content = _make_content_package()
        script = _make_script()

        gen.generate("2026-04-26", ["fetch", "script"], 30.0, content, script)

        report_path = Path("data/2026-04-26/report.md")
        assert report_path.exists()

    def test_includes_basic_info(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("src.pipeline.report_generator.setup_logger"):
            gen = ReportGenerator()
        content = _make_content_package()
        script = _make_script()

        gen.generate("2026-04-26", ["fetch", "script"], 30.0, content, script)

        text = Path("data/2026-04-26/report.md").read_text(encoding="utf-8")
        assert "2026-04-26" in text
        assert "30.0s" in text
        assert "fetch" in text

    def test_with_no_content(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("src.pipeline.report_generator.setup_logger"):
            gen = ReportGenerator()

        gen.generate("2026-04-26", ["fetch"], 10.0, None, None)

        text = Path("data/2026-04-26/report.md").read_text(encoding="utf-8")
        assert "N/A" in text

    def test_flags_short_segments(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("src.pipeline.report_generator.setup_logger"):
            gen = ReportGenerator()

        # Segment with actual/estimated ratio < 0.6
        segments = [
            ScriptSegment(
                segment_type="story_scan",
                audio_text="test",
                estimated_duration=10.0,
                actual_duration=3.0,
            ),
        ]
        script = _make_script(segments=segments)
        content = _make_content_package()

        gen.generate("2026-04-26", ["script"], 10.0, content, script)

        text = Path("data/2026-04-26/report.md").read_text(encoding="utf-8")
        assert "时长偏短" in text

    def test_flags_missing_images(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("src.pipeline.report_generator.setup_logger"):
            gen = ReportGenerator()

        item = _make_item(enrichment_source="aiohttp", article_images=[])
        content = _make_content_package(items=[item])
        script = _make_script()

        gen.generate("2026-04-26", ["enrich"], 10.0, content, script)

        text = Path("data/2026-04-26/report.md").read_text(encoding="utf-8")
        assert "缺少图片" in text

    def test_counts_story_coverage_from_script_elements(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("src.pipeline.report_generator.setup_logger"):
            gen = ReportGenerator()

        content = _make_content_package(items=[_make_item(source_id=str(i)) for i in range(10)])
        script = _make_script(
            segments=[
                ScriptSegment(
                    segment_type="story_scan",
                    audio_text="scan",
                    estimated_duration=100.0,
                    actual_duration=90.0,
                    scene_elements=[
                        SceneElement(
                            element_type="event_card",
                            start_time=0,
                            end_time=10,
                            props={"story_index": i, "coverage_tier": "focus"},
                        )
                        for i in range(3)
                    ]
                    + [
                        SceneElement(
                            element_type="story_compact_card",
                            start_time=30 + i * 10,
                            end_time=40 + i * 10,
                            props={"story_index": 3 + i, "coverage_tier": "standard"},
                        )
                        for i in range(3)
                    ]
                    + [
                        SceneElement(
                            element_type="quick_roundup_card",
                            start_time=60,
                            end_time=80,
                            props={
                                "items": [
                                    {"story_index": i, "coverage_tier": "quick"}
                                    for i in range(6, 10)
                                ]
                            },
                        )
                    ],
                )
            ]
        )

        gen.generate("2026-04-26", ["script"], 10.0, content, script)

        text = Path("data/2026-04-26/report.md").read_text(encoding="utf-8")
        assert "| 深度报道 | 3 |" in text
        assert "| 简要速览 | 3 |" in text
        assert "| 快讯 | 4 |" in text
