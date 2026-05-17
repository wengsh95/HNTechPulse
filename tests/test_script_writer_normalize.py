from src.core.models import ContentComment, ContentItem, ScriptSegment, SceneElement
from src.pipeline.script_writer import ScriptWriter


def _make_comment(**kwargs):
    defaults = {
        "author": "user",
        "content": "This is a test comment with enough length to score well",
        "source_id": "c1",
        "quality_score": 0.6,
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


class TestNormalizeAtmosphereCard:
    def test_injects_debate_focus(self):
        comments = [
            _make_comment(source_id="c1", quality_score=0.8),
            _make_comment(source_id="c2", quality_score=0.7),
        ]
        item = _make_item(comments=comments)
        segment = ScriptSegment(
            segment_type="story_scan",
            audio_text="test",
            estimated_duration=10.0,
            scene_elements=[
                SceneElement(
                    element_type="atmosphere_card",
                    start_time=0,
                    end_time=0,
                    props={"story_index": 0},
                )
            ],
        )

        judgement = {
            "debate_focus": ["API design", "performance"],
            "stance_distribution": {"支持": 0.6, "质疑": 0.4},
        }

        ScriptWriter._normalize_atmosphere_card(segment, item, judgement)

        props = segment.scene_elements[0].props
        assert props["debate_focus"] == ["API design", "performance"]
        assert props["stance_distribution"] == {"支持": 0.6, "质疑": 0.4}

    def test_no_op_when_empty_judgement(self):
        comments = [_make_comment(source_id="c1")]
        item = _make_item(comments=comments)
        original_props = {"story_index": 0, "existing_key": "value"}
        segment = ScriptSegment(
            segment_type="story_scan",
            audio_text="test",
            estimated_duration=10.0,
            scene_elements=[
                SceneElement(
                    element_type="atmosphere_card",
                    start_time=0,
                    end_time=0,
                    props=dict(original_props),
                )
            ],
        )

        ScriptWriter._normalize_atmosphere_card(segment, item, {})

        # Props should be unchanged (no debate_focus or stance_distribution injected)
        assert "debate_focus" not in segment.scene_elements[0].props
        assert segment.scene_elements[0].props["existing_key"] == "value"

    def test_injects_only_debate_focus(self):
        comments = [_make_comment(source_id="c1")]
        item = _make_item(comments=comments)
        segment = ScriptSegment(
            segment_type="story_scan",
            audio_text="test",
            estimated_duration=10.0,
            scene_elements=[
                SceneElement(
                    element_type="atmosphere_card",
                    start_time=0,
                    end_time=0,
                    props={"story_index": 0},
                )
            ],
        )

        judgement = {"debate_focus": ["security"], "stance_distribution": {}}

        ScriptWriter._normalize_atmosphere_card(segment, item, judgement)

        props = segment.scene_elements[0].props
        assert props["debate_focus"] == ["security"]
        assert "stance_distribution" not in props or props["stance_distribution"] == {}


class TestAudioOnlyScriptHelpers:
    def test_highlight_audio_text_lists_topics_without_visual_navigation(self):
        text = ScriptWriter._highlight_audio_text(
            [
                {"title_translation": "Bambu Lab open source contract"},
                {"title_translation": "TanStack NPM supply chain"},
                {"title_translation": "AI coding shifts language choice"},
            ]
        )

        assert "progress" not in text.lower()
        assert "Bambu Lab" in text
        assert "TanStack" in text

    def test_cache_refreshes_story_scan_with_legacy_audio_markers(self):
        segment = ScriptSegment(
            segment_type="story_scan",
            audio_text="Story one. Body.",
            estimated_duration=8.0,
            scene_elements=[
                SceneElement(
                    element_type="story_audio_marker",
                    start_time=0,
                    end_time=1,
                    props={"story_index": 0, "is_audio_marker": True},
                ),
                SceneElement(
                    element_type="event_card",
                    start_time=1,
                    end_time=8,
                    props={"story_index": 0},
                ),
            ],
        )

        assert ScriptWriter._cache_needs_audio_only_refresh(
            type("ScriptLike", (), {"segments": [segment]})()
        )
