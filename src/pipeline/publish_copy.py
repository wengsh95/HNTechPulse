"""Publishing-copy policy for the video pipeline.

Pure functions that shape and police the metadata published alongside the
video: title, description, tags, and cover-copy variants.  They were lifted
out of ``src.pipeline.stages.title_cover.py`` unchanged so the stage module
keeps only orchestration (LLM call, caching, image + props rendering) and the
copy policy can be reviewed, tested, and reused on its own.

Behavior is byte-for-byte the original; do not "improve" the copy rules in a
refactor, they are pinned by ``tests/test_publish_copy.py`` and the sampler
tests in ``tests/test_title_cover_stage.py``.
"""

from __future__ import annotations

import re
from typing import Any

from src.pipeline.agent_io import stable_hash
from src.utils.text import normalize_cjk_mixed_spacing

_PUBLISH_DISCUSSION_CLICHES = (
    "你怎么看，欢迎在评论区聊聊。",
    "欢迎在评论区聊聊。",
    "欢迎评论区聊聊。",
    "你怎么看？",
    "你怎么看。",
)
TITLE_NORMALIZATION_VERSION = 9

# Number of cover-copy variants required per date; lives here because the
# publish-copy contract (validate_title_payload) enforces it.
COVER_VARIANT_COUNT = 3


def _clean_publish_description(text: str, max_len: int = 130) -> str:
    """Keep generated publishing copy dense enough for Bilibili metadata."""
    text = normalize_cjk_mixed_spacing(str(text or "")).strip()
    for phrase in _PUBLISH_DISCUSSION_CLICHES:
        text = text.replace(phrase, "")
    text = text.replace("；", "。").replace(";", "。")
    text = re.sub(r"\s+", " ", text).strip()
    # LLM output and the later "ensure every story is mentioned" pass can
    # occasionally repeat the exact same sentence.  Publishing metadata
    # should never preserve that mechanical duplication.
    parts = re.findall(r"[^。！？!?]+[。！？!?]?", text)
    deduped: list[str] = []
    seen: set[str] = set()
    for part in parts:
        part = part.strip()
        key = part.rstrip("。！？!?").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(part)
    text = "".join(deduped)
    if len(text) <= max_len:
        return text

    parts = re.findall(r"[^。！？!?]+[。！？!?]?", text)
    kept: list[str] = []
    total = 0
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if kept and total + len(part) > max_len:
            break
        kept.append(part)
        total += len(part)
    compacted = "".join(kept).strip()
    if compacted:
        return compacted
    return text[:max_len].rstrip("，。！？；：,.!?;: ")


def _downgrade_unsupported_publish_claims(text: str) -> str:
    """Tone down recurring high-conflict copy that overstates source facts."""
    text = normalize_cjk_mixed_spacing(str(text or ""))
    replacements = {
        # Replace whole recurring headline clauses before replacing their
        # individual words.  Word-by-word substitutions used to turn
        # "能不能被暗中削弱" into the visibly broken
        # "能不能疑似收到低档输出".
        "能不能被暗中削弱": "是否收到低档输出",
        "不能被暗中削弱": "质疑低档输出",
        "能不能被疑似削弱": "是否收到低档输出",
        "不能被疑似削弱": "质疑低档输出",
        "被疑似A/B": "疑似被纳入A/B",
        "降档高价计费引发争议": "降档计费争议",
        "付费用户疑似被纳入测试": "用户疑似入组",
        "先掉链子": "先多等100毫秒",
        "先掉线": "延迟先升高",
        "掉线": "延迟升高",
        "断网": "延迟升高",
        "砍掉P2P": "改了P2P路径",
        "砍掉 P2P": "改了 P2P 路径",
        "一刀砍": "改动",
        "20225个Instagram账号": "超2万个Instagram账号",
        "20225个账号": "超2万个账号",
        "20225 个账号": "超2万个账号",
        "20225个": "超2万个",
        "先遭殃": "延迟升高",
        "偷偷": "疑似",
        "暗中": "疑似",
        "暗降": "疑似降",
        "暗改": "疑似调整",
        "悄悄": "疑似",
        "缩水算力": "低档输出",
        "被偷走推理": "推理档位引争议",
        "被疑似削弱": "疑似收到低档输出",
        "削弱": "低档输出",
        "被实验": "被纳入测试",
        "实验品": "测试对象",
        "信任崩塌": "信任风险",
        "信任危机": "信任风险",
        "知情权失守": "知情权争议",
        "疑似\n付费信任失守": "被指\n计费引发质疑",
        "信任失守": "信任风险",
        "伤了付费信任": "引发付费信任风险",
        "中招": "受影响",
        "偷工减料": "档位调整",
        "用作成本实验": "成本影响待验证",
        "砍到": "调到",
        "照收高价": "高价计费引发争议",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    # Keep one uncertainty marker even when separate substitutions put two
    # copies on adjacent cover lines or combine "被指" with "疑似".
    text = re.sub(r"疑似(\s*)疑似", r"\1疑似", text)
    text = re.sub(r"(被曝|被指)([^：\n]{0,14})疑似", r"\1\2", text)
    return text


def _publish_title_width(text: str) -> int:
    """Measure title width with the same compact rule promised in the prompt."""

    body = str(text or "").removeprefix("【HN日报】")
    return sum(1 if ord(char) < 128 else 2 for char in body)


def _validate_cover_title_shape(title: str, *, label: str) -> None:
    """Keep generated cover copy inside the two-line Remotion safe area."""

    lines = str(title or "").splitlines() or [""]
    if len(lines) > 2:
        raise ValueError(f"{label} must use at most two lines")
    widths = [_publish_title_width(line) for line in lines]
    too_wide = [
        f"line {index} width={width}: {line}"
        for index, (line, width) in enumerate(zip(lines, widths), start=1)
        if width > 16
    ]
    if too_wide:
        raise ValueError(
            f"{label} line visual width must be <= 16. " + "; ".join(too_wide)
        )
    if sum(widths) > 32:
        raise ValueError(f"{label} total visual width must be <= 32")


def _normalize_cover_variants(raw: Any) -> list[dict[str, Any]]:
    """Normalize cover copy emitted by the title/editorial LLM call."""
    if not isinstance(raw, list):
        return []

    variants: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        # Raw LLM output uses cover_* names.  title.json stores the canonical
        # names below and is read again by the cover stage, so both schemas
        # must round-trip without losing every field.
        title = _downgrade_unsupported_publish_claims(
            str(entry.get("cover_title") or entry.get("title") or "")
        ).strip()
        if not title:
            continue
        subtitle = normalize_cjk_mixed_spacing(
            _downgrade_unsupported_publish_claims(
                str(entry.get("cover_subtitle") or entry.get("subtitle") or "")
            )
        ).strip()
        tags = [
            normalize_cjk_mixed_spacing(
                _downgrade_unsupported_publish_claims(str(tag))
            ).strip()
            for tag in (entry.get("cover_tags") or entry.get("tags") or [])
            if str(tag).strip()
        ][:2]
        highlights = [
            normalize_cjk_mixed_spacing(
                _downgrade_unsupported_publish_claims(str(word))
            ).strip()
            for word in (entry.get("cover_highlights") or entry.get("highlights") or [])
            if str(word).strip()
        ][:4]
        variants.append(
            {
                "title": title,
                "subtitle": subtitle,
                "tags": tags,
                "highlights": highlights,
            }
        )
    return variants[:COVER_VARIANT_COUNT]


def _validate_title_payload(payload: dict) -> None:
    """Reject incomplete or duplicate publish packages while LLM retry is available."""

    if len(str(payload.get("title") or "").strip()) < 8:
        raise ValueError("Publish title must contain at least 8 characters")
    if not str(payload.get("description") or "").strip():
        raise ValueError("Publish description is required")
    variants = _normalize_cover_variants(payload.get("cover_variants"))
    signatures = {stable_hash(variant) for variant in variants}
    if len(variants) != COVER_VARIANT_COUNT or len(signatures) != COVER_VARIANT_COUNT:
        raise ValueError("Exactly three distinct cover_variants are required")
    _validate_cover_title_shape(
        _downgrade_unsupported_publish_claims(payload.get("cover_title") or ""),
        label="cover_title",
    )
    for index, variant in enumerate(variants, start=1):
        _validate_cover_title_shape(
            variant["title"], label=f"cover_variant[{index}].cover_title"
        )
    candidates = [
        str(candidate).strip()
        for candidate in payload.get("title_candidates") or []
        if isinstance(candidate, str) and candidate.strip()
    ]
    if (
        len(candidates) != 3
        or len(set(candidates)) != 3
        or str(payload.get("title") or "").strip() not in candidates
    ):
        raise ValueError(
            "Exactly three distinct title_candidates including title are required"
        )
    too_wide = [
        (candidate, _publish_title_width(candidate))
        for candidate in candidates
        if _publish_title_width(candidate) > 48
    ]
    if too_wide:
        details = "; ".join(
            f"width={width}: {candidate}" for candidate, width in too_wide
        )
        raise ValueError(
            "Publish title visual width must be <= 48. "
            f"Shorten only these offending titles: {details}"
        )

    # When the main cover names a recognizable company or product, every
    # angle must retain one of those tokens.  Otherwise support/risk variants
    # can degrade into generic copy that is meaningless as a thumbnail.
    main_cover = str(payload.get("cover_title") or "")
    subject_tokens = {
        token.lower()
        for token in re.findall(r"[A-Z][A-Za-z0-9.+-]{2,}", main_cover)
        if token.lower() not in {"the", "and", "for", "with"}
    }
    if subject_tokens:
        for variant in variants:
            variant_title = variant["title"].lower()
            if not any(token in variant_title for token in subject_tokens):
                raise ValueError(
                    "Every cover variant must retain the main company or product"
                )


def _validate_title_grounding(payload: dict, focus_story: dict) -> None:
    """Preserve uncertainty from a source across every outward headline."""

    if not _source_requires_uncertainty(focus_story):
        return

    uncertainty_markers = (
        "疑似",
        "被曝",
        "被指",
        "可能",
        "争议",
        "待确认",
        "待验证",
    )
    outward_titles: list[tuple[str, str]] = [
        ("title", str(payload.get("title") or "").strip()),
        ("cover_title", str(payload.get("cover_title") or "").strip()),
    ]
    outward_titles.extend(
        ("title_candidate", str(candidate).strip())
        for candidate in payload.get("title_candidates") or []
        if isinstance(candidate, str)
    )
    outward_titles.extend(
        (
            "cover_variant",
            str(variant.get("cover_title") or variant.get("title") or "").strip(),
        )
        for variant in payload.get("cover_variants") or []
        if isinstance(variant, dict)
    )
    for kind, text in outward_titles:
        if text and not any(marker in text for marker in uncertainty_markers):
            raise ValueError(
                f"Source is uncertain; this {kind} is missing one marker "
                f"(疑似/被曝/被指/可能/争议/待确认/待验证): {text}"
            )


def _source_requires_uncertainty(focus_story: dict) -> bool:
    source_text = " ".join(
        str(focus_story.get(key) or "")
        for key in ("title", "title_cn", "article_summary", "editor_angle")
    ).lower()
    return any(
        marker in source_text
        for marker in (
            " appears ",
            " reportedly ",
            " allegedly ",
            " suspected ",
            "疑似",
            "可能",
            "被指",
            "a/b测试",
        )
    )


def _preserve_source_uncertainty(text: str, focus_story: dict) -> str:
    """Mechanically qualify secondary title candidates when the source is tentative."""

    if not _source_requires_uncertainty(focus_story) or any(
        marker in text for marker in ("疑似", "被曝", "被指", "可能")
    ):
        return text
    prefix = "【HN日报】"
    if text.startswith(prefix):
        return f"{prefix}被曝{text[len(prefix) :]}"
    return f"疑似{text}"


def _ensure_all_stories_in_description(
    description: str,
    focus_story: dict,
    other_stories: list[dict],
) -> str:
    """Append any story not already mentioned in the description."""

    def _story_keywords(story: dict) -> set[str]:
        src = normalize_cjk_mixed_spacing(
            (story.get("title_cn") or "") + " " + (story.get("editor_angle") or "")
        )
        tokens = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", src))
        generic = {"苹果", "macbook", "ipad", "mac", "iphone"}
        return {token for token in tokens if token not in generic}

    def _story_mentioned(desc: str, story: dict) -> bool:
        source = " ".join(
            str(story.get(key) or "") for key in ("title", "title_cn", "editor_angle")
        )
        ascii_tokens = {
            token.lower()
            for token in re.findall(r"[A-Za-z][A-Za-z0-9.+-]{1,}", source)
            if token.lower() not in {"the", "and", "for", "with", "from"}
        }
        desc_lower = normalize_cjk_mixed_spacing(desc).lower()
        if ascii_tokens and any(token in desc_lower for token in ascii_tokens):
            return True
        keywords = _story_keywords(story)
        if not keywords:
            return True
        return any(keyword.lower() in desc_lower for keyword in keywords)

    def _compact_line(story: dict) -> str:
        editor = story.get("editor_angle") or ""
        summary = (story.get("article_summary") or "")[:120]
        return normalize_cjk_mixed_spacing(editor or summary)

    extra_lines = []
    for story in other_stories:
        if not _story_mentioned(description, story):
            line = _compact_line(story)
            if line:
                extra_lines.append(line)

    if not extra_lines:
        return description
    return description.rstrip("。；; ") + "。" + "。".join(extra_lines) + "。"
