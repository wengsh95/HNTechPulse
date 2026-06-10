import json
import pytest
from unittest.mock import patch

from src.providers.llm.llm_client import (
    _strip_json_fence,
    _clamp_index_in_place,
    _floor_index_in_place,
)
from src.providers.llm.openai import OpenAILLMProvider
from src.core.models import ContentItem, ContentComment


def _make_config():
    return {
        "logging": {"level": "WARNING"},
        "llm": {"model": "test-model", "max_tokens": 1024},
        "pipeline": {"max_comments_for_r1_analyze": 80},
    }


def _make_content_item(index=0):
    comments = [
        ContentComment(author=f"user_{j}", content=f"comment {j}") for j in range(3)
    ]
    return ContentItem(
        source="hackernews",
        source_id=str(100 + index),
        title=f"Story {index}",
        url=f"https://example.com/{index}",
        score=100,
        comment_count=3,
        published_at=1700000000,
        comments=comments,
    )


def _make_provider():
    with patch.dict("os.environ", {"OPENAI_API_KEY": "fake-key"}):
        with patch("src.providers.llm.backend.OpenAI"):
            return OpenAILLMProvider(_make_config())


# ── _strip_json_fence ───────────────────────────────────────────────────


class TestStripJsonFence:
    def test_no_fence(self):
        assert _strip_json_fence('{"key": "val"}') == '{"key": "val"}'

    def test_json_fence(self):
        text = '```json\n{"key": "val"}\n```'
        assert _strip_json_fence(text) == '{"key": "val"}'

    def test_bare_fence(self):
        text = '```\n{"key": "val"}\n```'
        assert _strip_json_fence(text) == '{"key": "val"}'


# ── _clamp_index_in_place ───────────────────────────────────────────────


class TestClampIndexInPlace:
    def test_in_range_no_change(self):
        d = {"idx": 2}
        _clamp_index_in_place(d, "idx", 5, "test")
        assert d["idx"] == 2

    def test_negative_clamped_to_zero(self):
        d = {"idx": -1}
        _clamp_index_in_place(d, "idx", 5, "test")
        assert d["idx"] == 0

    def test_at_max_clamped(self):
        d = {"idx": 5}
        _clamp_index_in_place(d, "idx", 5, "test")
        assert d["idx"] == 4

    def test_non_int_no_op(self):
        d = {"idx": "two"}
        _clamp_index_in_place(d, "idx", 5, "test")
        assert d["idx"] == "two"

    def test_missing_key_no_op(self):
        d = {}
        _clamp_index_in_place(d, "idx", 5, "test")
        assert "idx" not in d


# ── _floor_index_in_place ──────────────────────────────────────────────


class TestFloorIndexInPlace:
    def test_negative_floored_to_zero(self):
        d = {"idx": -1}
        _floor_index_in_place(d, "idx")
        assert d["idx"] == 0

    def test_non_negative_unchanged(self):
        d = {"idx": 5}
        _floor_index_in_place(d, "idx")
        assert d["idx"] == 5

    def test_non_int_no_op(self):
        d = {"idx": "two"}
        _floor_index_in_place(d, "idx")
        assert d["idx"] == "two"

    def test_missing_key_no_op(self):
        d = {}
        _floor_index_in_place(d, "idx")
        assert "idx" not in d


# ── _extract_json ──────────────────────────────────────────────────────


class TestExtractJson:
    def test_direct_json_object(self):
        provider = _make_provider()
        result = provider._extract_json('{"key": "val"}')
        assert result == {"key": "val"}

    def test_fenced_json(self):
        provider = _make_provider()
        result = provider._extract_json('```json\n{"key": "val"}\n```')
        assert result == {"key": "val"}

    def test_json_embedded_in_text(self):
        provider = _make_provider()
        result = provider._extract_json('Here is the result: {"key": "val"} end')
        assert result == {"key": "val"}

    def test_malformed_json_triggers_repair(self):
        provider = _make_provider()
        result = provider._extract_json('{"key": "val",}')
        assert result == {"key": "val"}

    def test_no_json_raises_value_error(self):
        provider = _make_provider()
        with pytest.raises(ValueError, match="No valid JSON"):
            provider._extract_json("just plain text no json here")

    def test_empty_string_raises(self):
        provider = _make_provider()
        with pytest.raises(ValueError):
            provider._extract_json("")


# ── _repair_json ───────────────────────────────────────────────────────


class TestRepairJson:
    def test_trailing_comma_before_brace(self):
        provider = _make_provider()
        result = provider._client._repair_json('{"a": 1,}')
        assert result == {"a": 1}

    def test_trailing_comma_before_bracket(self):
        provider = _make_provider()
        result = provider._client._repair_json('{"a": [1,]}')
        assert result == {"a": [1]}

    def test_unquoted_keys(self):
        provider = _make_provider()
        result = provider._client._repair_json("{a: 1}")
        assert result == {"a": 1}

    def test_double_quoted_keys(self):
        provider = _make_provider()
        result = provider._client._repair_json('{"a": 1}')
        assert result == {"a": 1}

    def test_early_closing_brace(self):
        provider = _make_provider()
        result = provider._client._repair_json('{"a": 1} extra stuff')
        assert result == {"a": 1}

    def test_unrepairable_raises(self):
        provider = _make_provider()
        with pytest.raises(json.JSONDecodeError):
            provider._client._repair_json("not json at all")


# ── _split_prompt ──────────────────────────────────────────────────────


class TestSplitPrompt:
    def test_with_system_cut(self):
        prompt = "System instructions<!-- SYSTEM_CUT -->User content"
        result = OpenAILLMProvider._split_prompt(prompt)
        assert len(result) == 2
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "System instructions"
        assert result[1]["role"] == "user"
        assert result[1]["content"] == "User content"

    def test_without_system_cut(self):
        prompt = "Just user content"
        result = OpenAILLMProvider._split_prompt(prompt)
        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_empty_system_part(self):
        prompt = "   <!-- SYSTEM_CUT -->User content"
        result = OpenAILLMProvider._split_prompt(prompt)
        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_marker_at_start(self):
        prompt = "<!-- SYSTEM_CUT -->User content"
        result = OpenAILLMProvider._split_prompt(prompt)
        assert len(result) == 1
        assert result[0]["content"] == "User content"


# ── _single_story_to_json ──────────────────────────────────────────────


class TestSingleStoryToJson:
    def test_basic_serialization(self):
        provider = _make_provider()
        item = _make_content_item(0)
        result = provider._single_story_to_json(item, 0)
        parsed = json.loads(result)
        assert parsed["index"] == 0
        assert parsed["title"] == "Story 0"
        assert parsed["score"] == 100
        assert len(parsed["comments"]) == 3

    def test_comment_truncation(self):
        config = _make_config()
        config["pipeline"]["max_comments_for_r1_analyze"] = 2
        with patch.dict("os.environ", {"OPENAI_API_KEY": "fake-key"}):
            with patch("src.providers.llm.backend.OpenAI"):
                provider = OpenAILLMProvider(config)
        item = _make_content_item(0)
        result = provider._single_story_to_json(item, 0)
        parsed = json.loads(result)
        assert len(parsed["comments"]) == 2
        assert parsed["truncated_to"] == 2

    def test_article_summary_included(self):
        provider = _make_provider()
        item = _make_content_item(0)
        item.article_summary = "A summary"
        result = provider._single_story_to_json(item, 0)
        parsed = json.loads(result)
        assert parsed["article_summary"] == "A summary"

    def test_article_text_excerpt(self):
        provider = _make_provider()
        item = _make_content_item(0)
        item.article_text = "x" * 600
        result = provider._single_story_to_json(item, 0)
        parsed = json.loads(result)
        assert len(parsed["article_excerpt"]) == 500

    def test_eventcard_fields_included(self):
        provider = _make_provider()
        item = _make_content_item(0)
        item.editor_angle = "Google发布新模型"
        item.dek = "Google在IO大会上发布了Gemini 2.5 Pro，推理能力大幅提升"
        item.key_points = [
            {"label": "背景", "text": "Google IO 2026大会"},
            {"label": "影响", "text": "影响所有使用LLM的开发者"},
        ]
        item.keywords = ["Gemini", "LLM", "推理"]
        item.category = "AI工具"
        result = provider._single_story_to_json(item, 0)
        parsed = json.loads(result)
        assert parsed["editor_angle"] == "Google发布新模型"
        assert parsed["dek"] == "Google在IO大会上发布了Gemini 2.5 Pro，推理能力大幅提升"
        assert len(parsed["key_points"]) == 2
        assert parsed["keywords"] == ["Gemini", "LLM", "推理"]
        assert parsed["category"] == "AI工具"

    def test_eventcard_fields_omitted_when_none(self):
        provider = _make_provider()
        item = _make_content_item(0)
        result = provider._single_story_to_json(item, 0)
        parsed = json.loads(result)
        assert "editor_angle" not in parsed
        assert "dek" not in parsed
        assert "key_points" not in parsed
        assert "keywords" not in parsed
        assert "category" not in parsed
