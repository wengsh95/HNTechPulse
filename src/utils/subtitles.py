"""Subtitle text shaping shared by TTS alignment and rendering prep."""

from __future__ import annotations

import re
from math import ceil


DEFAULT_MAX_CJK_WEIGHT = 24.0
DEFAULT_MAX_CHARS = 52
MIN_FRAGMENT_WEIGHT = 8.0
MIN_SOFT_BREAK_WEIGHT = 12.0

# Bump this when the local subtitle selection policy changes.  It is included
# in the audio input hash so a policy fix cannot accidentally reuse old TTS
# alignment artifacts.
SUBTITLE_POLICY_VERSION = "local-agent-v2"

_SENTENCE_BREAKERS = set("\u3002\uff01\uff1f.!?")
_SOFT_BREAKERS = set("\uff0c\u3001\uff1b\uff1a,;:")
_CLOSING_QUOTES = set("\u201d\u2019\u300b\u3009\u300f\u300d)")
_JOIN_TRAILING_CONNECTORS = set("的在为以和与及将把对从向于由按跟")
_NUMERIC_TOKEN_RE = re.compile(
    r"(?:\d+(?:\.\d+)?|[零〇一二三四五六七八九十百千万亿兆两]+)"
    r"(?:[万亿兆千百十点]*)"
    r"(?:美元|人民币|港币|欧元|元|亿元|亿美元|万亿|倍|个|名|项|条|次|家|岁|年|月|日|轮|期|级|层)?"
)


def split_subtitle_texts(
    texts: list[str],
    *,
    max_cjk_weight: float = DEFAULT_MAX_CJK_WEIGHT,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[str]:
    """Split subtitles into one-line display cues while preserving word order."""
    result: list[str] = []
    # The script writer may have split a semantic token across two subtitle
    # entries (for example ``七十`` / ``亿美元``).  Merge only those unsafe
    # boundaries first; ordinary editorial boundaries remain independent.
    for text in _merge_unsafe_boundaries(texts):
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


def _merge_unsafe_boundaries(texts: list[str]) -> list[str]:
    merged: list[str] = []
    for raw in texts:
        text = _normalize_spaces(raw)
        if not text:
            continue
        if merged and _needs_boundary_merge(merged[-1], text):
            merged[-1] = merged[-1].rstrip() + text.lstrip()
        else:
            merged.append(text)
    return merged


def _needs_boundary_merge(left: str, right: str) -> bool:
    left = left.rstrip()
    right = right.lstrip()
    if not left or not right:
        return False
    if left[-1] in _SENTENCE_BREAKERS or left[-1] in _SOFT_BREAKERS:
        return False
    combined = left + right
    boundary = len(left)
    if _is_protected_token_boundary(combined, boundary):
        return True
    return left[-1] in _JOIN_TRAILING_CONNECTORS


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

    # Do not choose a short leading clause such as ``据 Bloomberg 报道，`` as
    # the first cue when a fuller phrase can fit before the display limit.
    min_idx = _index_at_weight(text, MIN_SOFT_BREAK_WEIGHT)
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

    candidates = sorted(
        range(1, len(text)),
        key=lambda i: _hard_split_score(text, i, target_idx),
    )
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
    if _is_protected_token_boundary(text, split_idx):
        return False
    if right[0] in _SENTENCE_BREAKERS or right[0] in _SOFT_BREAKERS:
        return False
    return True


def _is_protected_token_boundary(text: str, split_idx: int) -> bool:
    """Return whether a cut would break an English or numeric token."""
    if _splits_ascii_token(text, split_idx):
        return True
    for match in _NUMERIC_TOKEN_RE.finditer(text):
        if match.start() < split_idx < match.end():
            return True
    return False


def subtitle_boundary_is_safe(left: str, right: str) -> bool:
    """Check that two adjacent cues do not break a word or numeric token."""
    left = str(left or "").rstrip()
    right = str(right or "").lstrip()
    if not left or not right:
        return True
    if right[0] in _SENTENCE_BREAKERS or right[0] in _SOFT_BREAKERS:
        return False
    return not _is_protected_token_boundary(left + right, len(left))


def _hard_split_score(text: str, split_idx: int, target_idx: int) -> float:
    """Prefer cuts after a complete numeric token over cuts before one."""
    score = abs(split_idx - target_idx)
    for match in _NUMERIC_TOKEN_RE.finditer(text):
        if match.start() == split_idx:
            score += 5
        if match.end() == split_idx:
            score -= 3
    return score


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
