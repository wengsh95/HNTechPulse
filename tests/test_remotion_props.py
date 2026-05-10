import pytest
from unittest.mock import MagicMock

from src.core.models import (
    ContentItem, ContentComment, ContentPackage,
    Script, ScriptSegment, SceneElement, WordTiming,
)
from src.providers.renderer.remotion_props import (
    _safe_get_item, _safe_get_comment,
    _expand_story_header, _expand_comment_card, _expand_comment_bubble,
    _expand_news_carousel_card, _expand_dashboard_card,
    _expand_perspective_compare,
    _expand_event_card, _expand_atmosphere_card, _expand_quote_card,
    expand_element_props, ELEMENT_EXPANDERS,
    build_cues, _build_cues_from_word_timings, _build_cues_from_sentence_timings,
    _split_into_cues, sanitize_props, script_to_props,
)


def _make_content_package():
    items = []
    for i in range(3):
        comments = [
            ContentComment(author=f"user_{j}", content=f"comment {j}", content_cn=f"评论 {j}" if j == 0 else None)
            for j in range(2)
        ]
        items.append(ContentItem(
            source="hackernews",
            source_id=str(100 + i),
            title=f"Story {i}",
            title_cn=f"故事 {i}" if i == 0 else None,
            url=f"https://example.com/{i}",
            score=100 - i * 10,
            comment_count=2,
            published_at=1700000000 + i * 100,
            comments=comments,
            article_images=["img1.png", "img2.png"] if i == 0 else [],
        ))
    return ContentPackage(
        date="2026-04-26",
        items=items,
        deep_dive_indices=[0],
        brief_indices=[1],
        quick_news_indices=[2],
    )


def _make_script_segment(segment_type="opening", audio_text="Hello world.", duration=10.0, word_timings=None):
    meta = {}
    if word_timings:
        meta["word_timings"] = [
            {"text": wt.text, "start_time": wt.start_time, "end_time": wt.end_time}
            for wt in word_timings
        ]
        meta["timing_level"] = "word"
    return ScriptSegment(
        segment_type=segment_type,
        audio_text=audio_text,
        estimated_duration=duration,
        actual_duration=duration,
        start_time=0.0,
        end_time=duration,
        meta=meta,
    )


# ── _safe_get_item ─────────────────────────────────────────────────────

class TestSafeGetItem:
    def test_valid_index(self):
        content = _make_content_package()
        assert _safe_get_item(content, 0) is content.items[0]

    def test_none_index(self):
        content = _make_content_package()
        assert _safe_get_item(content, None) is None

    def test_non_int_index(self):
        content = _make_content_package()
        assert _safe_get_item(content, "0") is None
        assert _safe_get_item(content, 0.5) is None

    def test_negative_index(self):
        content = _make_content_package()
        assert _safe_get_item(content, -1) is None

    def test_out_of_range(self):
        content = _make_content_package()
        assert _safe_get_item(content, 99) is None

    def test_empty_items(self):
        content = ContentPackage(date="2026-04-26", items=[], deep_dive_indices=[], brief_indices=[], quick_news_indices=[])
        assert _safe_get_item(content, 0) is None


# ── _safe_get_comment ──────────────────────────────────────────────────

class TestSafeGetComment:
    def test_valid_index(self):
        item = _make_content_package().items[0]
        assert _safe_get_comment(item, 0) is item.comments[0]

    def test_none_index(self):
        item = _make_content_package().items[0]
        assert _safe_get_comment(item, None) is None

    def test_non_int_index(self):
        item = _make_content_package().items[0]
        assert _safe_get_comment(item, "0") is None

    def test_out_of_range(self):
        item = _make_content_package().items[0]
        assert _safe_get_comment(item, 99) is None

    def test_empty_comments(self):
        item = ContentItem(source="hn", source_id="1", title="T", url=None, published_at=0, comments=[])
        assert _safe_get_comment(item, 0) is None


# ── _expand_story_header ───────────────────────────────────────────────

class TestExpandStoryHeader:
    def test_valid_story_index(self):
        content = _make_content_package()
        result = _expand_story_header({"story_index": 0}, content)
        assert result == {"story_title": "Story 0", "score": 100, "comments": 2}

    def test_missing_story_index(self):
        content = _make_content_package()
        result = _expand_story_header({}, content)
        assert result is None

    def test_out_of_range_story_index(self):
        content = _make_content_package()
        result = _expand_story_header({"story_index": 99}, content)
        assert result is None

    def test_none_score(self):
        content = _make_content_package()
        content.items[0].score = None
        result = _expand_story_header({"story_index": 0}, content)
        assert result["score"] == 0

    def test_none_comment_count(self):
        content = _make_content_package()
        content.items[0].comment_count = None
        result = _expand_story_header({"story_index": 0}, content)
        assert result["comments"] == 0


# ── _expand_comment_card ───────────────────────────────────────────────

class TestExpandCommentCard:
    def test_valid_indices(self):
        content = _make_content_package()
        result = _expand_comment_card({"story_index": 0, "comment_index": 0}, content)
        assert result["author"] == "user_0"
        assert result["text"] == "comment 0"

    def test_missing_comment_index(self):
        content = _make_content_package()
        result = _expand_comment_card({"story_index": 0}, content)
        assert result is None

    def test_out_of_range_comment(self):
        content = _make_content_package()
        result = _expand_comment_card({"story_index": 0, "comment_index": 99}, content)
        assert result is None


# ── _expand_comment_bubble ─────────────────────────────────────────────

class TestExpandCommentBubble:
    def test_valid_indices(self):
        content = _make_content_package()
        result = _expand_comment_bubble({"story_index": 0, "comment_index": 0}, content)
        assert result["author"] == "user_0"
        assert result["original_text"] == "comment 0"

    def test_missing_item(self):
        content = _make_content_package()
        result = _expand_comment_bubble({"story_index": 99, "comment_index": 0}, content)
        assert result is None


# ── _expand_news_carousel_card ─────────────────────────────────────────

class TestExpandNewsCarouselCard:
    def test_with_comment(self):
        content = _make_content_package()
        result = _expand_news_carousel_card({"story_index": 0, "comment_index": 0}, content)
        assert result["story_title"] == "Story 0"
        assert result["author"] == "user_0"
        assert result["comment_text"] == "comment 0"

    def test_without_comment(self):
        content = _make_content_package()
        result = _expand_news_carousel_card({"story_index": 0}, content)
        assert result["author"] == "?"
        assert result["comment_score"] == 0
        assert result["comment_text"] == ""

    def test_missing_item(self):
        content = _make_content_package()
        result = _expand_news_carousel_card({"story_index": 99}, content)
        assert result is None


# ── _expand_dashboard_card ─────────────────────────────────────────────

class TestExpandDashboardCard:
    def test_expands_entries(self):
        content = _make_content_package()
        props = {"entries": [{"story_index": 0}]}
        result = _expand_dashboard_card(props, content)
        assert result["entries"][0]["original_title"] == "Story 0"
        assert result["entries"][0]["score"] == 100

    def test_empty_entries(self):
        content = _make_content_package()
        result = _expand_dashboard_card({"entries": []}, content)
        assert result == {"entries": []}

    def test_invalid_story_index_in_entry(self):
        content = _make_content_package()
        props = {"entries": [{"story_index": 99, "original_title": "keep"}]}
        result = _expand_dashboard_card(props, content)
        assert result["entries"][0]["original_title"] == "keep"


# ── _expand_event_card ───────────────────────────────────────────────

class TestExpandEventCard:
    def test_overwrites_story_meta(self):
        content = _make_content_package()
        result = _expand_event_card({"story_index": 0}, content)
        assert result["story_title"] == "Story 0"

    def test_image_injection(self):
        content = _make_content_package()
        result = _expand_event_card({"story_index": 0}, content)
        assert result["image_src"] == "images/img1.png"
        assert result["image_type"] == "article"

    def test_no_image(self):
        content = _make_content_package()
        result = _expand_event_card({"story_index": 1}, content)
        assert result["image_src"] == ""

    def test_passes_through_keywords(self):
        content = _make_content_package()
        result = _expand_event_card({"story_index": 0, "keywords": ["AI", "开源"]}, content)
        assert result["keywords"] == ["AI", "开源"]

    def test_default_keywords(self):
        content = _make_content_package()
        result = _expand_event_card({"story_index": 0}, content)
        assert result["keywords"] == []


# ── _expand_atmosphere_card ────────────────────────────────────────────

class TestExpandAtmosphereCard:
    def test_injects_stance_distribution(self):
        content = _make_content_package()
        props = {"story_index": 0, "stance_distribution": {"支持": 0.5, "质疑": 0.5}}
        result = _expand_atmosphere_card(props, content)
        assert result["stance_distribution"] == {"支持": 0.5, "质疑": 0.5}

    def test_default_stance_distribution(self):
        content = _make_content_package()
        result = _expand_atmosphere_card({"story_index": 0}, content)
        assert result["stance_distribution"] == {}

    def test_debate_focus_default_when_not_set(self):
        content = _make_content_package()
        result = _expand_atmosphere_card({"story_index": 0}, content)
        assert result["debate_focus"] == []
        assert result["community_sentiment"] == ""

    def test_includes_controversy_score(self):
        content = _make_content_package()
        result = _expand_atmosphere_card({"story_index": 0}, content)
        assert "controversy_score" in result
        assert isinstance(result["controversy_score"], (int, float))
        assert result["score"] == 100
        assert result["comment_count"] == 2


# ── _expand_quote_card ─────────────────────────────────────────────────

class TestExpandQuoteCard:
    def test_injects_quotes(self):
        content = _make_content_package()
        result = _expand_quote_card({"story_index": 0}, content)
        assert "quotes" in result
        assert isinstance(result["quotes"], list)

    def test_derives_stance_from_sentiment(self):
        content = _make_content_package()
        content.items[0].comments[0].sentiment = 0.8
        content.items[0].comments[0].quality_score = 0.9
        content.items[0].comments[1].sentiment = -0.7
        content.items[0].comments[1].quality_score = 0.8
        result = _expand_quote_card({"story_index": 0}, content)
        assert len(result["quotes"]) == 2
        assert result["quotes"][0]["stance"] == "支持"
        assert result["quotes"][1]["stance"] == "质疑"


# ── expand_element_props ───────────────────────────────────────────────

class TestExpandElementProps:
    def test_known_type_dispatches(self):
        content = _make_content_package()
        logger = MagicMock()
        result = expand_element_props("story_header", {"story_index": 0}, content, logger)
        assert result["story_title"] == "Story 0"

    def test_unknown_type_returns_raw_props(self):
        content = _make_content_package()
        logger = MagicMock()
        props = {"foo": "bar"}
        result = expand_element_props("unknown_type", props, content, logger)
        assert result == props

    def test_none_content_returns_raw_props(self):
        logger = MagicMock()
        props = {"foo": "bar"}
        result = expand_element_props("story_header", props, None, logger)
        assert result == props

    def test_expander_exception_returns_raw_props(self):
        content = _make_content_package()
        logger = MagicMock()
        props = {"story_index": "not_an_int"}
        result = expand_element_props("story_header", props, content, logger)
        assert result == props


# ── build_cues ─────────────────────────────────────────────────────────

class TestBuildCues:
    def test_word_timings_priority(self):
        wt = [WordTiming(text="Hello.", start_time=0.0, end_time=1.0)]
        seg = _make_script_segment(word_timings=wt)
        logger = MagicMock()
        cues = build_cues(seg, 1.0, logger)
        assert len(cues) > 0
        logger.debug.assert_called()

    def test_auto_split_fallback(self):
        seg = _make_script_segment(audio_text="Hello world. Goodbye.", duration=5.0)
        seg.meta = {}
        logger = MagicMock()
        cues = build_cues(seg, 5.0, logger)
        assert len(cues) >= 1


# ── _build_cues_from_word_timings ──────────────────────────────────────

class TestBuildCuesFromWordTimings:
    def test_sentence_break_flushes(self):
        timings = [
            WordTiming(text="Hello", start_time=0.0, end_time=0.5),
            WordTiming(text="world.", start_time=0.5, end_time=1.0),
            WordTiming(text="Next", start_time=1.0, end_time=1.5),
            WordTiming(text="line.", start_time=1.5, end_time=2.0),
        ]
        cues = _build_cues_from_word_timings(timings, 2.0)
        assert len(cues) == 2
        assert cues[0]["text"] == "Helloworld."
        assert cues[1]["text"] == "Nextline."

    def test_clause_break_long_text(self):
        timings = [
            WordTiming(text="This is a really long clause,",
                       start_time=0.0, end_time=1.0),
            WordTiming(text=" and another part.", start_time=1.0, end_time=2.0),
        ]
        cues = _build_cues_from_word_timings(timings, 2.0)
        assert len(cues) == 2

    def test_clause_break_short_text_no_flush(self):
        timings = [
            WordTiming(text="Short,", start_time=0.0, end_time=0.5),
            WordTiming(text=" text.", start_time=0.5, end_time=1.0),
        ]
        cues = _build_cues_from_word_timings(timings, 1.0)
        assert len(cues) == 1

    def test_first_cue_starts_at_zero(self):
        timings = [
            WordTiming(text="Hello.", start_time=0.1, end_time=1.0),
        ]
        cues = _build_cues_from_word_timings(timings, 1.0)
        assert cues[0]["start_time"] == 0.0

    def test_last_cue_ends_at_duration(self):
        timings = [
            WordTiming(text="Hello.", start_time=0.0, end_time=0.9),
        ]
        cues = _build_cues_from_word_timings(timings, 5.0)
        assert cues[-1]["end_time"] == 5.0

    def test_empty_timings(self):
        assert _build_cues_from_word_timings([], 5.0) == []

    def test_chinese_sentence_breaks(self):
        timings = [
            WordTiming(text="你好。", start_time=0.0, end_time=1.0),
            WordTiming(text="世界！", start_time=1.0, end_time=2.0),
        ]
        cues = _build_cues_from_word_timings(timings, 2.0)
        assert len(cues) == 2


# ── _build_cues_from_sentence_timings ──────────────────────────────────

class TestBuildCuesFromSentenceTimings:
    def test_basic_sentence_cues(self):
        timings = [
            WordTiming(text="First sentence.", start_time=0.0, end_time=2.0),
            WordTiming(text="Second sentence.", start_time=2.0, end_time=4.0),
        ]
        cues = _build_cues_from_sentence_timings(timings, 4.0)
        assert len(cues) == 2
        assert cues[0]["text"] == "First sentence."

    def test_first_cue_starts_at_zero(self):
        timings = [
            WordTiming(text="Hi.", start_time=0.1, end_time=1.0),
        ]
        cues = _build_cues_from_sentence_timings(timings, 1.0)
        assert cues[0]["start_time"] == 0.0

    def test_last_cue_ends_at_duration(self):
        timings = [
            WordTiming(text="Hi.", start_time=0.0, end_time=0.9),
        ]
        cues = _build_cues_from_sentence_timings(timings, 5.0)
        assert cues[-1]["end_time"] == 5.0

    def test_empty_timings(self):
        assert _build_cues_from_sentence_timings([], 5.0) == []


# ── _split_into_cues ───────────────────────────────────────────────────

class TestSplitIntoCues:
    def test_empty_text(self):
        assert _split_into_cues("", 5.0) == []

    def test_zero_duration(self):
        assert _split_into_cues("Hello.", 0) == []

    def test_single_sentence(self):
        cues = _split_into_cues("Hello world.", 5.0)
        assert len(cues) == 1
        assert cues[0]["start_time"] == 0.0
        assert cues[0]["end_time"] == 5.0

    def test_multiple_sentences(self):
        cues = _split_into_cues("First sentence. Second sentence.", 6.0)
        assert len(cues) == 2

    def test_short_sentence_merge(self):
        cues = _split_into_cues("Hi. This is a longer sentence here.", 5.0)
        assert len(cues) >= 1

    def test_char_ratio_time_distribution(self):
        text = "Short. This is a much longer sentence with more characters."
        cues = _split_into_cues(text, 10.0)
        if len(cues) >= 2:
            assert cues[1]["start_time"] == pytest.approx(cues[0]["end_time"])

    def test_last_cue_snaps_to_duration(self):
        cues = _split_into_cues("First. Second. Third.", 9.0)
        assert cues[-1]["end_time"] == 9.0

    def test_html_tags_stripped(self):
        cues = _split_into_cues("<b>Hello</b> world.", 5.0)
        assert len(cues) >= 1
        assert "<b>" not in cues[0]["text"]

    def test_chinese_punctuation(self):
        cues = _split_into_cues("第一句。第二句！", 4.0)
        assert len(cues) >= 1


# ── sanitize_props ─────────────────────────────────────────────────────

class TestSanitizeProps:
    def test_primitives_unchanged(self):
        assert sanitize_props({"a": "hi", "b": 1, "c": 2.0, "d": True}) == {"a": "hi", "b": 1, "c": 2.0, "d": True}

    def test_none_preserved(self):
        assert sanitize_props({"a": None}) == {"a": None}

    def test_dict_recursive(self):
        result = sanitize_props({"a": {"b": 1}})
        assert result == {"a": {"b": 1}}

    def test_list_items(self):
        result = sanitize_props({"a": [{"b": 1}, 2, "three"]})
        assert result == {"a": [{"b": 1}, 2, "three"]}

    def test_numpy_type_with_item(self):
        class FakeNumpy:
            def item(self):
                return 42
        result = sanitize_props({"a": FakeNumpy()})
        assert result["a"] == 42

    def test_custom_object_str(self):
        class Custom:
            def __str__(self):
                return "custom"
        result = sanitize_props({"a": Custom()})
        assert result["a"] == "custom"

    def test_mixed_nested(self):
        class FakeNumpy:
            def item(self):
                return 7
        result = sanitize_props({
            "items": [{"val": FakeNumpy()}, "text"],
            "nested": {"x": None},
        })
        assert result["items"][0]["val"] == 7
        assert result["nested"]["x"] is None


# ── script_to_props ────────────────────────────────────────────────────

class TestScriptToProps:
    def test_basic_structure(self):
        script = Script(
            title="Test", description="Desc", tags=["t"],
            segments=[_make_script_segment(duration=10.0)],
            total_duration=10.0,
        )
        logger = MagicMock()
        result = script_to_props(script, "/audio", 1280, 720, 24, "#000", logger=logger)
        assert result["width"] == 1280
        assert result["height"] == 720
        assert result["fps"] == 24
        assert result["bgColor"] == "#000"
        assert result["title"] == "Test"
        assert result["totalDuration"] == 10.0
        assert len(result["segments"]) == 1

    def test_segment_duration_uses_actual(self):
        seg = ScriptSegment(
            segment_type="opening", audio_text="Hi",
            estimated_duration=5.0, actual_duration=10.0,
        )
        script = Script(title="T", description="", tags=[], segments=[seg], total_duration=10.0)
        result = script_to_props(script, "/audio", 1280, 720, 24, "#000")
        assert result["segments"][0]["duration"] == 10.0

    def test_segment_duration_fallback_to_estimated(self):
        seg = ScriptSegment(
            segment_type="opening", audio_text="Hi",
            estimated_duration=5.0, actual_duration=None,
        )
        script = Script(title="T", description="", tags=[], segments=[seg], total_duration=5.0)
        result = script_to_props(script, "/audio", 1280, 720, 24, "#000")
        assert result["segments"][0]["duration"] == 5.0

    def test_scene_element_skipped_when_zero_duration(self):
        seg = _make_script_segment(duration=10.0)
        seg.scene_elements = [
            SceneElement(element_type="subtitle", start_time=0.0, end_time=0.0, props={}),
            SceneElement(element_type="subtitle", start_time=0.0, end_time=5.0, props={}),
        ]
        script = Script(title="T", description="", tags=[], segments=[seg], total_duration=10.0)
        result = script_to_props(script, "/audio", 1280, 720, 24, "#000")
        assert len(result["segments"][0]["scene_elements"]) == 1

    def test_cues_included(self):
        seg = _make_script_segment(audio_text="Hello world.", duration=5.0)
        script = Script(title="T", description="", tags=[], segments=[seg], total_duration=5.0)
        result = script_to_props(script, "/audio", 1280, 720, 24, "#000")
        assert "cues" in result["segments"][0]
        assert len(result["segments"][0]["cues"]) >= 1
