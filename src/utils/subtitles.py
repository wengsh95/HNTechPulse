"""Subtitle text shaping shared by TTS alignment and rendering prep."""

from __future__ import annotations

import re
from math import ceil


DEFAULT_MAX_CJK_WEIGHT = 24.0
DEFAULT_MAX_CHARS = 52
MIN_FRAGMENT_WEIGHT = 8.0

_SENTENCE_BREAKERS = set("\u3002\uff01\uff1f.!?")
_SOFT_BREAKERS = set("\uff0c\u3001\uff1b\uff1a,;:")
_CLOSING_QUOTES = set("\u201d\u2019\u300b\u3009\u300f\u300d)")


def split_subtitle_texts(
    texts: list[str],
    *,
    max_cjk_weight: float = DEFAULT_MAX_CJK_WEIGHT,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[str]:
    """Split subtitles into one-line display cues while preserving word order."""
    result: list[str] = []
    for text in texts:
        for part in split_subtitle_text(
            text, max_cjk_weight=max_cjk_weight, max_chars=max_chars
        ):
            if part:
                result.append(part)
    return result


def split_subtitle_text(
    text: str,
    *,
    max_cjk_weight: float = DEFAULT_MAX_CJK_WEIGHT,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[str]:
    text = _normalize_spaces(text)
    if not text:
        return []

    parts = _split_by_sentence_breaks(text)
    if len(parts) == 1 and _fits_one_line(
        text, max_cjk_weight=max_cjk_weight, max_chars=max_chars
    ):
        return [text]

    out: list[str] = []
    for part in parts:
        out.extend(
            _split_long_fragment(
                part,
                max_cjk_weight=max_cjk_weight,
                max_chars=max_chars,
            )
        )
    return [p for p in out if p]


def subtitle_display_weight(text: str) -> float:
    """Approximate one-line visual width in CJK character units."""
    weight = 0.0
    for ch in text:
        if ch.isspace():
            weight += 0.25
        elif _is_cjk(ch):
            weight += 1.0
        elif ch.isascii():
            weight += 0.5
        else:
            weight += 0.8
    return weight


def _split_long_fragment(
    text: str,
    *,
    max_cjk_weight: float,
    max_chars: int,
) -> list[str]:
    text = _normalize_spaces(text)
    if not text:
        return []

    parts: list[str] = []
    current = text
    while current and not _fits_one_line(
        current, max_cjk_weight=max_cjk_weight, max_chars=max_chars
    ):
        split_idx = _best_split_index(current, max_cjk_weight, max_chars)
        if split_idx <= 0:
            break
        left = current[:split_idx].strip()
        right = current[split_idx:].strip()
        if not left or not right:
            break
        parts.append(left)
        current = right
    if current:
        parts.append(current)
    return parts


def _best_split_index(text: str, max_cjk_weight: float, max_chars: int) -> int:
    limit_idx = _index_at_limit(text, max_cjk_weight, max_chars)
    if limit_idx <= 0:
        return -1

    min_idx = _index_at_weight(text, MIN_FRAGMENT_WEIGHT)
    search_start = max(1, min_idx)
    search_end = min(len(text) - 1, max(limit_idx + 1, search_start))

    for breaker_set in (_SOFT_BREAKERS, _SENTENCE_BREAKERS):
        best = -1
        best_score = float("inf")
        for i in range(search_start, search_end):
            ch = text[i]
            if ch not in breaker_set:
                continue
            split_idx = _consume_closing_quotes(text, i + 1)
            if split_idx >= len(text):
                continue
            if _splits_ascii_token(text, split_idx):
                continue
            left = text[:split_idx].strip()
            right = text[split_idx:].strip()
            if not left or not right:
                continue
            if not _fits_one_line(
                left, max_cjk_weight=max_cjk_weight, max_chars=max_chars
            ):
                continue
            score = abs(subtitle_display_weight(left) - subtitle_display_weight(right))
            if score < best_score:
                best = split_idx
                best_score = score
        if best > 0:
            return best

    space_idx = text.rfind(" ", search_start, search_end)
    if space_idx > search_start and _valid_hard_split(
        text, space_idx, max_cjk_weight=max_cjk_weight
    ):
        return space_idx

    total_weight = subtitle_display_weight(text)
    part_count = max(2, ceil(total_weight / max_cjk_weight))
    target_weight = min(
        max_cjk_weight, max(MIN_FRAGMENT_WEIGHT, total_weight / part_count)
    )
    target_idx = min(_index_at_weight(text, target_weight), len(text) - 1)

    candidates = sorted(range(1, len(text)), key=lambda i: abs(i - target_idx))
    for hard_idx in candidates:
        if _valid_hard_split(text, hard_idx, max_cjk_weight=max_cjk_weight):
            return hard_idx
    return -1


def _split_by_sentence_breaks(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in _SENTENCE_BREAKERS and not _is_decimal_or_ascii_dot(text, i):
            end = _consume_closing_quotes(text, i + 1)
            part = text[start:end].strip()
            if part:
                parts.append(part)
            start = end
            i = end
            continue
        i += 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts or [text]


def _fits_one_line(text: str, *, max_cjk_weight: float, max_chars: int) -> bool:
    return len(text) <= max_chars and subtitle_display_weight(text) <= max_cjk_weight


def _index_at_limit(text: str, max_cjk_weight: float, max_chars: int) -> int:
    weight = 0.0
    for i, ch in enumerate(text):
        weight += subtitle_display_weight(ch)
        if weight > max_cjk_weight or i + 1 > max_chars:
            return i
    return len(text)


def _index_at_weight(text: str, min_weight: float) -> int:
    weight = 0.0
    for i, ch in enumerate(text):
        weight += subtitle_display_weight(ch)
        if weight >= min_weight:
            return i + 1
    return 0


def _consume_closing_quotes(text: str, idx: int) -> int:
    while idx < len(text) and text[idx] in _CLOSING_QUOTES:
        idx += 1
    return idx


def _normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _is_cjk(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"


def _is_decimal_or_ascii_dot(text: str, idx: int) -> bool:
    if text[idx] != ".":
        return False
    prev_ch = text[idx - 1] if idx > 0 else ""
    next_ch = text[idx + 1] if idx + 1 < len(text) else ""
    return (
        prev_ch.isascii()
        and prev_ch.isalnum()
        and next_ch.isascii()
        and next_ch.isalnum()
    )


def _valid_hard_split(text: str, split_idx: int, *, max_cjk_weight: float) -> bool:
    if split_idx <= 0 or split_idx >= len(text):
        return False
    left = text[:split_idx].strip()
    right = text[split_idx:].strip()
    if not left or not right:
        return False
    if subtitle_display_weight(left) > max_cjk_weight:
        return False
    if subtitle_display_weight(left) < MIN_FRAGMENT_WEIGHT:
        return False
    if subtitle_display_weight(right) < MIN_FRAGMENT_WEIGHT:
        return False
    if _splits_ascii_token(text, split_idx):
        return False
    if right[0] in _SENTENCE_BREAKERS or right[0] in _SOFT_BREAKERS:
        return False
    return True


def _splits_ascii_token(text: str, split_idx: int) -> bool:
    left = text[:split_idx].rstrip()
    right = text[split_idx:].lstrip()
    if not left or not right:
        return False
    left_ch = left[-1]
    right_ch = right[0]
    if not left_ch.isascii() or not right_ch.isascii():
        return False
    token_chars = set("._+-/#")
    return (left_ch.isalnum() or left_ch in token_chars) and (
        right_ch.isalnum() or right_ch in token_chars
    )
