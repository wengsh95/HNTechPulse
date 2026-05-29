from src.core.models import ContentComment, ContentItem, ScriptSegment, SceneElement
from src.pipeline.script import ScriptWriter


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
            duration=10.0,
            start_time=0.0,
            end_time=10.0,
            scene_elements=[
                SceneElement(
                    element_type="atmosphere_card",
                    props={"story_index": 0},
                    start_time=0.0,
                    end_time=10.0,
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
            duration=10.0,
            start_time=0.0,
            end_time=10.0,
            scene_elements=[
                SceneElement(
                    element_type="atmosphere_card",
                    props=dict(original_props),
                    start_time=0.0,
                    end_time=10.0,
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
            duration=10.0,
            start_time=0.0,
            end_time=10.0,
            scene_elements=[
                SceneElement(
                    element_type="atmosphere_card",
                    props={"story_index": 0},
                    start_time=0.0,
                    end_time=10.0,
                )
            ],
        )

        judgement = {"debate_focus": ["security"], "stance_distribution": {}}

        ScriptWriter._normalize_atmosphere_card(segment, item, judgement)

        props = segment.scene_elements[0].props
        assert props["debate_focus"] == ["security"]
        assert "stance_distribution" not in props or props["stance_distribution"] == {}

    def test_selected_comment_ids_honor_judgement_candidates(self):
        comments = [
            _make_comment(
                source_id="fallback",
                content="This ordinary fallback comment has enough length to pass quote quality checks.",
                quality_score=0.8,
            ),
            _make_comment(
                source_id="judged",
                content="This judged comment has a concrete viewpoint and should be preferred by the selector.",
                quality_score=0.4,
            ),
        ]
        item = _make_item(comments=comments)
        segment = ScriptSegment(
            segment_type="story_scan",
            audio_text="test",
            duration=10.0,
            start_time=0.0,
            end_time=10.0,
            scene_elements=[
                SceneElement(
                    element_type="atmosphere_card",
                    props={"story_index": 0},
                    start_time=0.0,
                    end_time=10.0,
                )
            ],
        )
        judgement = {
            "quote_candidates": [
                {
                    "comment_id": "judged",
                    "has_viewpoint": True,
                    "reject_for_quote": False,
                }
            ]
        }

        ScriptWriter._normalize_atmosphere_card(segment, item, judgement)

        selected_ids = segment.scene_elements[0].props["selected_comment_ids"]
        assert selected_ids[0] == "judged"


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
