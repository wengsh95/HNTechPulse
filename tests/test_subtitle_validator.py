"""Tests for the hard subtitle-rule validator in _build_card_narration_validator.

These rules (length, commas, semicolons, repetition, forbidden words) are
enforced in code because the LLM cannot reliably self-check CJK character
counts.  See prompts/story_script.md for the declared rules.
"""

import logging

from src.providers.llm.llm_provider_base import (
    _build_card_narration_validator,
    _check_comment_openers,
    _check_subtitle_texts,
    _subtitle_width,
    _longest_common_substring_len,
)

_LOGGER = logging.getLogger("test")


def _validator():
    return _build_card_narration_validator(["event_card", "atmosphere_card"], _LOGGER)


def _wrap(cards):
    """Build a minimal parsed dict with the given card_narrations."""
    return {"card_narrations": cards}


# ── _subtitle_width ────────────────────────────────────────────


def test_subtitle_width_cjk_and_ascii():
    assert _subtitle_width("中") == 2
    assert _subtitle_width("A") == 1
    assert _subtitle_width("1") == 1
    assert _subtitle_width("，") == 2
    assert _subtitle_width("Claude Code") == 11
    # 吞掉(4) + 33k(3) + space(1) + token(5) = 13
    assert _subtitle_width("吞掉33k token") == 13


# ── _longest_common_substring_len ──────────────────────────────


def test_lcs_basic():
    assert _longest_common_substring_len("", "abc") == 0
    assert _longest_common_substring_len("abc", "") == 0
    assert _longest_common_substring_len("abcdef", "xbcdey") == 4  # "bcde"
    assert _longest_common_substring_len("完全不同", "毫不相干") == 1  # share "不"


# ── _check_subtitle_texts ──────────────────────────────────────


def test_check_clean_texts_pass():
    texts = ["这是一个正常句子。", "第二句也没问题。"]
    assert _check_subtitle_texts(0, texts) == []


def test_check_detects_semicolon():
    viols = _check_subtitle_texts(0, ["第一句；还有分号。"])
    assert len(viols) == 1
    assert "分号" in viols[0]


def test_check_detects_ascii_semicolon():
    viols = _check_subtitle_texts(0, ["first; second."])
    assert len(viols) == 1
    assert "分号" in viols[0]


def test_check_detects_too_long():
    long = "有人在API边界实测发现Claude Code还没读用户提示光系统提示和工具定义就吞掉约33k tokens是OpenCode的近五倍。"
    viols = _check_subtitle_texts(0, [long])
    assert any("超长" in v for v in viols)


def test_check_detects_too_many_commas():
    viols = _check_subtitle_texts(0, ["A，B，C，D。"])
    assert any("逗号" in v for v in viols)


def test_check_detects_multiple_punctuation():
    viols = _check_subtitle_texts(0, ["第一句。第二句。"])
    assert any("多标点" in v for v in viols)


def test_check_ignores_decimal_periods():
    assert _check_subtitle_texts(0, ["GPT-5.6 Sol降价50%。"]) == []


def test_check_detects_forbidden_words():
    for word in ("断网", "高管不在乎", "全落空", "士气崩", "翻脸"):
        viols = _check_subtitle_texts(0, [f"出现了{word}这个词。"])
        assert any(word in v for v in viols), f"failed to detect {word}"


def test_check_detects_adjacent_repetition():
    texts = [
        "Claude Code还没读到用户提示就先吞33k",
        "Claude Code还没读到用户提示就先吞33k tokens。",
    ]
    viols = _check_subtitle_texts(0, texts)
    assert any("复读" in v for v in viols)


def test_check_no_repetition_under_threshold():
    texts = ["短句一。", "完全不同的短句二。"]
    assert _check_subtitle_texts(0, texts) == []


def test_comment_openers_reject_generic_first_sentence():
    violations = _check_comment_openers(
        1,
        ["评论区很快指出标题有误导。", "有人认为这个价格仍然太高。"],
    )
    assert any("首句使用泛化开头" in item for item in violations)
    assert any("泛化主语" in item for item in violations)


def test_comment_openers_accept_concrete_mechanism():
    assert (
        _check_comment_openers(
            1,
            ["GitHub Actions 的空值策略不会主动报错。", "这会掩盖脚本拼接风险。"],
        )
        == []
    )


# ── _build_card_narration_validator ────────────────────────────


def test_validator_accepts_clean_response():
    parsed = _wrap(
        [
            {
                "card_type": "event_card",
                "subtitle_texts": ["正常短句一。", "正常短句二。"],
            },
            {"card_type": "atmosphere_card", "subtitle_texts": ["正常评论句。"]},
        ]
    )
    _validator()(parsed)  # should not raise


def test_validator_accepts_empty_cards():
    _validator()({})  # no card_narrations key
    _validator()({"card_narrations": []})


def test_validator_rejects_too_long():
    long = "这是一个非常非常非常非常非常非常非常非常非常非常非常非常非常长的超过三十八个汉字的句子需要被检测出来。"
    parsed = _wrap(
        [
            {"card_type": "event_card", "subtitle_texts": [long]},
        ]
    )
    try:
        _validator()(parsed)
        assert False, "should have raised"
    except ValueError as e:
        assert "超长" in str(e)


def test_validator_rejects_semicolon():
    parsed = _wrap(
        [
            {"card_type": "event_card", "subtitle_texts": ["正常句。"]},
            {"card_type": "atmosphere_card", "subtitle_texts": ["分号句；不行。"]},
        ]
    )
    try:
        _validator()(parsed)
        assert False, "should have raised"
    except ValueError as e:
        assert "分号" in str(e)


def test_validator_rejects_bad_card_type():
    parsed = _wrap(
        [
            {"card_type": "unknown_card", "subtitle_texts": ["正常句。"]},
        ]
    )
    try:
        _validator()(parsed)
        assert False, "should have raised"
    except ValueError as e:
        assert "card_type" in str(e)


def test_validator_rejects_non_string_subtitle():
    parsed = _wrap(
        [
            {"card_type": "event_card", "subtitle_texts": [123]},
        ]
    )
    try:
        _validator()(parsed)
        assert False, "should have raised"
    except ValueError as e:
        assert "string" in str(e)


def test_validator_aggregates_multiple_violations():
    parsed = _wrap(
        [
            {
                "card_type": "event_card",
                "subtitle_texts": [
                    "超长句子" * 20 + "。",
                    "分号；句。",
                ],
            },
        ]
    )
    try:
        _validator()(parsed)
        assert False, "should have raised"
    except ValueError as e:
        msg = str(e)
        assert "超长" in msg
        assert "分号" in msg
