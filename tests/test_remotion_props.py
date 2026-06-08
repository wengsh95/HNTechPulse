import pytest
from unittest.mock import MagicMock

from src.core.models import (
    ContentItem,
    ContentComment,
    ContentPackage,
    Cue,
    Script,
    ScriptSegment,
    SceneElement,
)
from src.providers.renderer.remotion_props import (
    _safe_get_item,
    _safe_get_comment,
    _expand_highlight_entries,
    _expand_event_card,
    _expand_atmosphere_card,
    expand_element_props,
    sanitize_props,
    script_to_props,
)
from src.providers.renderer.cue_builder import (
    build_cues,
    _split_into_cues,
)
from src.pipeline.comment import (
    compute_comment_quality,
    is_resource_pointer_comment,
    select_representative_comments,
    select_quote_comments,
)


def _make_content_package():
    items = []
    for i in range(3):
        comments = [
            ContentComment(
                author=f"user_{j}",
                content=f"comment {j}",
                content_cn=f"评论 {j}" if j == 0 else None,
            )
            for j in range(2)
        ]
        items.append(
            ContentItem(
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
            )
        )
    return ContentPackage(
        date="2026-04-26",
        items=items,
        deep_dive_indices=[0],
        brief_indices=[1],
    )


def _make_script_segment(
    segment_type="opening", audio_text="Hello world.", duration=10.0
):
    return ScriptSegment(
        segment_type=segment_type,
        audio_text=audio_text,
        duration=duration,
        start_time=0.0,
        end_time=duration,
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
        content = ContentPackage(
            date="2026-04-26",
            items=[],
            deep_dive_indices=[],
            brief_indices=[],
        )
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
        item = ContentItem(
            source="hn", source_id="1", title="T", url=None, published_at=0, comments=[]
        )
        assert _safe_get_comment(item, 0) is None


# ── _expand_highlight_entries ──────────────────────────────────────────


class TestExpandHighlightEntries:
    def test_expands_entries(self):
        content = _make_content_package()
        result = _expand_highlight_entries([{"story_index": 0}], content)
        assert result[0]["original_title"] == "Story 0"
        assert result[0]["score"] == 100

    def test_empty_entries(self):
        content = _make_content_package()
        result = _expand_highlight_entries([], content)
        assert result == []

    def test_invalid_story_index_in_entry(self):
        content = _make_content_package()
        result = _expand_highlight_entries(
            [{"story_index": 99, "original_title": "keep"}], content
        )
        assert result[0]["original_title"] == "keep"


# ── _expand_event_card ───────────────────────────────────────────────


class TestExpandEventCard:
    def test_overwrites_story_meta(self):
        content = _make_content_package()
        result = _expand_event_card({"story_index": 0}, content)
        assert result["story_title"] == "Story 0"
        assert result["score"] == 100
        assert result["comment_count"] == 2

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
        result = _expand_event_card(
            {"story_index": 0, "keywords": ["AI", "开源"]}, content
        )
        assert result["keywords"] == ["AI", "开源"]

    def test_default_keywords(self):
        content = _make_content_package()
        result = _expand_event_card({"story_index": 0}, content)
        assert result["keywords"] == []

    def test_event_fields_fallback_to_content_item(self):
        content = _make_content_package()
        content.items[0].why_it_matters = "改变开发工作流"

        result = _expand_event_card({"story_index": 0}, content)

        assert result["why_it_matters"] == "改变开发工作流"


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

    def test_includes_controversy_score(self):
        content = _make_content_package()
        result = _expand_atmosphere_card({"story_index": 0}, content)
        assert "controversy_score" in result
        assert isinstance(result["controversy_score"], (int, float))
        assert result["score"] == 100
        assert result["comment_count"] == 2

    def test_preserves_existing_quote_translation_and_uses_claim(self, monkeypatch):
        content = _make_content_package()
        content.date = "2026-04-26"
        content.items[0].source_id = "story0"
        content.items[0].comments[0].source_id = "c0"
        content.items[0].comments[
            0
        ].content = "This selected comment has enough detail to pass the quote filter."
        content.items[0].comments[0].content_cn = "评论零"
        content.items[0].comments[0].quality_score = 0.6

        monkeypatch.setattr(
            "src.providers.renderer.remotion_props.load_comment_judgements",
            lambda _date: {
                "story0": {
                    "comment_lanes": {
                        "representative": [
                            {
                                "comment_id": "c0",
                                "claim": "翻译不等于展示文案",
                                "quote_score": 0.9,
                            }
                        ]
                    },
                    "quote_candidates": [
                        {
                            "comment_id": "c0",
                            "quote_score": 0.9,
                            "has_viewpoint": True,
                        }
                    ],
                }
            },
        )

        result = _expand_atmosphere_card(
            {
                "story_index": 0,
                "selected_comment_ids": ["c0"],
                "quotes": [
                    {
                        "source_id": "c0",
                        "text": "comment 0",
                        "text_cn": "评论零",
                    }
                ],
            },
            content,
        )
        assert result["quotes"][0]["source_id"] == "c0"
        assert result["quotes"][0]["text_cn"] == "评论零"
        assert result["quotes"][0]["display_text"] == "翻译不等于展示文案"

    def test_quote_display_text_uses_judgement_claim(self, monkeypatch):
        content = _make_content_package()
        content.date = "2026-04-26"
        content.items[0].source_id = "story0"
        content.items[0].comments[0].source_id = "c0"
        content.items[0].comments[
            0
        ].content = "This selected comment is intentionally much longer than a card quote should be."
        content.items[0].comments[0].quality_score = 0.8

        monkeypatch.setattr(
            "src.providers.renderer.remotion_props.load_comment_judgements",
            lambda _date: {
                "story0": {
                    "comment_lanes": {
                        "representative": [
                            {
                                "comment_id": "c0",
                                "claim": "边界才是真问题",
                                "quote_score": 0.9,
                            }
                        ]
                    },
                    "quote_candidates": [
                        {
                            "comment_id": "c0",
                            "quote_score": 0.9,
                            "has_viewpoint": True,
                        }
                    ],
                }
            },
        )

        result = _expand_atmosphere_card(
            {"story_index": 0, "selected_comment_ids": ["c0"]},
            content,
        )

        assert result["quotes"][0]["display_text"] == "边界才是真问题"

    def test_quote_display_text_requires_judgement_claim(self, monkeypatch):
        content = _make_content_package()
        content.date = "2026-04-26"
        content.items[0].source_id = "story0"
        content.items[0].comments[0].source_id = "c0"
        content.items[0].comments[
            0
        ].content = "This selected comment is intentionally much longer than a card quote should be."
        content.items[0].comments[0].quality_score = 0.8

        monkeypatch.setattr(
            "src.providers.renderer.remotion_props.load_comment_judgements",
            lambda _date: {
                "story0": {
                    "comment_lanes": {},
                    "quote_candidates": [
                        {
                            "comment_id": "c0",
                            "quote_score": 0.9,
                            "has_viewpoint": True,
                        }
                    ],
                }
            },
        )

        with pytest.raises(ValueError, match="requires comment_lanes claim"):
            _expand_atmosphere_card(
                {"story_index": 0, "selected_comment_ids": ["c0"]},
                content,
            )


# ── expand_element_props ───────────────────────────────────────────────


def test_quote_selection_filters_resource_pointer_comments():
    text = "Here is an article about writing portable ARM64 assembly: https://ariadne.space/2023/04/12/writing-portable-arm-assembly/"
    comment = ContentComment(
        author="linker", content=text, source_id="link", quality_score=0.95
    )
    assert is_resource_pointer_comment(text)
    assert select_representative_comments([comment]) == []


def test_select_quote_comments_honors_ids_then_fills_to_three():
    comments = [
        ContentComment(
            author="linker",
            content="Here is an article about writing portable ARM64 assembly: https://ariadne.space/2023/04/12/writing-portable-arm-assembly/",
            source_id="link",
            quality_score=0.95,
        ),
        ContentComment(
            author="skeptic",
            content="The hard part is not the syntax, it is keeping ABI assumptions and toolchain behavior consistent across platforms.",
            source_id="view",
            quality_score=0.7,
            sentiment=-0.4,
        ),
        ContentComment(
            author="operator",
            content="In production this usually fails at the boundary where deployment scripts assume one platform and users bring another.",
            source_id="ops",
            quality_score=0.65,
            sentiment=-0.2,
        ),
        ContentComment(
            author="supporter",
            content="I like the goal, but it should document the unsupported cases clearly instead of pretending portability is automatic.",
            source_id="support",
            quality_score=0.6,
            sentiment=0.5,
        ),
    ]
    selected = select_quote_comments(comments, selected_ids=["view"])
    assert [c.source_id for c in selected] == ["view", "support", "ops"]


def test_resource_pointer_quality_is_penalized():
    item = ContentItem(
        source="hn",
        source_id="1",
        title="Writing portable ARM64 assembly",
        url=None,
        published_at=0,
    )
    comment = ContentComment(
        author="linker",
        content="Here is an article about writing portable ARM64 assembly: https://ariadne.space/2023/04/12/writing-portable-arm-assembly/",
        source_id="link",
        depth=0,
    )
    assert compute_comment_quality(comment, item) < 0.22


class TestExpandElementProps:
    def test_known_type_dispatches(self):
        content = _make_content_package()
        logger = MagicMock()
        result = expand_element_props("event_card", {"story_index": 0}, content, logger)
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
        result = expand_element_props("event_card", props, None, logger)
        assert result == props

    def test_expander_exception_returns_raw_props(self):
        content = _make_content_package()
        logger = MagicMock()
        props = {"story_index": "not_an_int"}
        result = expand_element_props("event_card", props, content, logger)
        assert result == props


# ── build_cues ─────────────────────────────────────────────────────────


class TestBuildCues:
    def test_auto_split_fallback(self):
        seg = _make_script_segment(audio_text="Hello world. Goodbye.", duration=5.0)
        logger = MagicMock()
        cues = build_cues(seg, 5.0, logger)
        assert len(cues) >= 1

    def test_existing_long_cue_is_split_for_display(self):
        seg = _make_script_segment(audio_text="", duration=12.0)
        seg.cues = [
            Cue(
                text="早上好，这里是HN每日观察。今天的主线是开发者工具正在变快，但维护成本和信任边界也被重新摊开。你最担心哪一个变化？",
                start_time=0.0,
                end_time=12.0,
            )
        ]
        logger = MagicMock()

        cues = build_cues(seg, 12.0, logger)

        assert len(cues) > 1
        assert cues[0]["start_time"] == 0.0
        assert cues[-1]["end_time"] == 12.0
        for left, right in zip(cues, cues[1:]):
            assert right["start_time"] == pytest.approx(left["end_time"])


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
        assert sanitize_props({"a": "hi", "b": 1, "c": 2.0, "d": True}) == {
            "a": "hi",
            "b": 1,
            "c": 2.0,
            "d": True,
        }

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

        result = sanitize_props(
            {
                "items": [{"val": FakeNumpy()}, "text"],
                "nested": {"x": None},
            }
        )
        assert result["items"][0]["val"] == 7
        assert result["nested"]["x"] is None


# ── script_to_props ────────────────────────────────────────────────────


class TestScriptToProps:
    def test_basic_structure(self):
        script = Script(
            title="Test",
            description="Desc",
            tags=["t"],
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
            segment_type="opening",
            audio_text="Hi",
            duration=10.0,
            start_time=0.0,
            end_time=10.0,
        )
        script = Script(
            title="T", description="", tags=[], segments=[seg], total_duration=10.0
        )
        result = script_to_props(script, "/audio", 1280, 720, 24, "#000")
        assert result["segments"][0]["duration"] == 10.0

    def test_segment_duration_fallback_to_estimated(self):
        seg = ScriptSegment(
            segment_type="opening",
            audio_text="Hi",
            duration=5.0,
            start_time=0.0,
            end_time=5.0,
        )
        script = Script(
            title="T", description="", tags=[], segments=[seg], total_duration=5.0
        )
        result = script_to_props(script, "/audio", 1280, 720, 24, "#000")
        assert result["segments"][0]["duration"] == 5.0

    def test_scene_element_skipped_when_zero_duration(self):
        seg = _make_script_segment(duration=10.0)
        seg.scene_elements = [
            SceneElement(
                element_type="subtitle", start_time=0.0, end_time=0.0, props={}
            ),
            SceneElement(
                element_type="subtitle", start_time=0.0, end_time=5.0, props={}
            ),
        ]
        script = Script(
            title="T", description="", tags=[], segments=[seg], total_duration=10.0
        )
        result = script_to_props(script, "/audio", 1280, 720, 24, "#000")
        assert len(result["segments"][0]["scene_elements"]) == 1

    def test_cues_included(self):
        seg = _make_script_segment(audio_text="Hello world.", duration=5.0)
        script = Script(
            title="T", description="", tags=[], segments=[seg], total_duration=5.0
        )
        result = script_to_props(script, "/audio", 1280, 720, 24, "#000")
        assert "cues" in result["segments"][0]
        assert len(result["segments"][0]["cues"]) >= 1
