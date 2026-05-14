import json
from dataclasses import asdict
from src.core.models import (
    ContentComment,
    ContentItem,
    ContentPackage,
    SceneElement,
    Cue,
    ScriptSegment,
    Script,
    SelectionResult,
)


class TestSelectionResult:
    def test_creation(self):
        sr = SelectionResult(
            brief_items=[{"story_index": 0}],
            raw_json='{"brief_items": [{"story_index": 0}]}',
        )
        assert sr.brief_items[0]["story_index"] == 0

    def test_defaults(self):
        sr = SelectionResult()
        assert sr.brief_items == []
        assert sr.raw_json == ""


class TestContentModels:
    def test_content_comment(self):
        cc = ContentComment(author="test", content="hello")
        assert cc.author == "test"
        assert cc.content_cn is None

    def test_content_item(self):
        ci = ContentItem(
            source="hackernews",
            source_id="123",
            title="Test",
            url="https://example.com",
        )
        assert ci.comments == []
        assert ci.score is None

    def test_content_package(self):
        cp = ContentPackage(date="2026-04-26", items=[])
        assert cp.deep_dive_indices == []
        assert cp.brief_indices == []
        assert cp.quick_news_indices == []


class TestScriptModels:
    def test_scene_element(self):
        se = SceneElement(
            element_type="subtitle",
            start_time=0.0,
            end_time=5.0,
            props={"text": "Hello"},
        )
        assert se.element_type == "subtitle"

    def test_cue(self):
        cue = Cue(text="Hello", start_time=0.0, end_time=2.0)
        assert cue.text == "Hello"

    def test_script_segment(self):
        seg = ScriptSegment(
            segment_type="opening",
            audio_text="Welcome",
            estimated_duration=10.0,
        )
        assert seg.emotion == "neutral"
        assert seg.scene_elements == []
        assert seg.actual_duration is None

    def test_script(self):
        script = Script(
            title="Test",
            description="Desc",
            tags=["tech"],
            segments=[],
        )
        assert script.total_duration is None

    def test_script_serialization_roundtrip(self):
        seg = ScriptSegment(
            segment_type="opening",
            audio_text="Hello world",
            estimated_duration=15.0,
            emotion="energetic",
            scene_elements=[
                SceneElement(
                    element_type="subtitle",
                    start_time=0.0,
                    end_time=5.0,
                    props={"text": "Hi"},
                )
            ],
            cues=[Cue(text="Hello", start_time=0.0, end_time=5.0)],
            meta={"key": "value"},
        )
        script = Script(
            title="Test Script",
            description="A test",
            tags=["test"],
            segments=[seg],
        )
        d = asdict(script)
        json_str = json.dumps(d, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert parsed["title"] == "Test Script"
        assert len(parsed["segments"]) == 1
        assert parsed["segments"][0]["emotion"] == "energetic"
