"""Script templates: opening, closing, and highlight entry generation."""

from datetime import datetime
from typing import Optional

from src.core.models import (
    ContentPackage,
    ScriptSegment,
    SceneElement,
    SelectionResult,
)
from src.utils.text import normalize_cjk_mixed_spacing


CHINESE_ORDINALS = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]


def story_angle_from_segment(segment: ScriptSegment, item=None) -> dict:
    """Extract the product-facing angle fields from an LLM story segment."""
    event_elem = next(
        (elem for elem in segment.scene_elements if elem.element_type == "event_card"),
        None,
    )
    props = event_elem.props if event_elem else {}
    return {
        "editor_angle": props.get("editor_angle")
        or (item.editor_angle if item else None)
        or "",
        "dek": props.get("dek") or (item.dek if item else None) or "",
        "key_points": props.get("key_points")
        or (item.key_points if item else None)
        or [],
        "event_summary": props.get("event_summary")
        or (item.dek if item else None)
        or "",
        "why_it_matters": props.get("why_it_matters")
        or (item.why_it_matters if item else None)
        or "",
        "category": props.get("category") or (item.category if item else None) or "",
        "keywords": props.get("keywords") or (item.keywords if item else None) or [],
    }


def highlight_audio_text(entries: list[dict]) -> str:
    """Summarize the lineup for listeners who are not watching the screen."""
    labels = []
    for idx, entry in enumerate(entries[:3]):
        title = entry.get("title_translation")
        assert title, f"Story {idx} missing title_translation"
        title = str(title).strip()
        if len(title) > 18:
            title = title[:18].rstrip("，。！？；：,.!?;:") + "…"
        ordinal = CHINESE_ORDINALS[idx] if idx < len(CHINESE_ORDINALS) else str(idx + 1)
        labels.append(f"第{ordinal}，{title}")
    if not labels:
        return "来看今天的三个技术信号，我们一条条听。"
    return f"今天看{len(labels)}条：" + "；".join(labels) + "。我们一条条听。"


# 默认截断长度：cover 副标题每个钩子的目标字符数 (≤14 让 3 个钩子 + 2 个 " · " 落在 40 字以内)
DEFAULT_HOOK_MAX_LEN = 14

# 开场钩子的目标字符数 (≤10 让 3 个钩子 + 2 个 "、" 在 35 字以内, 配音 ~5s)
OPENING_HOOK_MAX_LEN = 10

# 收尾/开场 thesis 规则 (顺序敏感, 命中第一个匹配)
# - keywords: 命中 category 或 editor_angle 任一即可
# - prefix: 开场前缀 ("今天的主线是" / "今天的主线不是")
# - body: 接 prefix 后构成完整开场金句
# - closing: 收尾独立句 (不再带 "今天的主线是" 这种开场框架词)
THESIS_RULES: list[dict] = [
    {
        "keywords": ("安全", "隐私", "漏洞", "攻击面", "权限"),
        "prefix": "今天的主线不是",
        "body": "AI又变强了，而是AI进入真实系统后，风险开始外溢。",
        "closing": "重点不是AI又变强了，而是AI进入真实系统后，风险开始外溢。",
    },
    {
        "keywords": ("硬件", "芯片", "CPU", "GPU", "Windows PC", "Nvidia"),
        "prefix": "今天的主线是",
        "body": "本地AI正在从软件话题，变成硬件和平台控制权之争。",
        "closing": "本地AI正在从软件话题，变成硬件和平台控制权之争。",
    },
    {
        "keywords": ("开源", "开发", "工具", "Python", "CPython"),
        "prefix": "今天的主线是",
        "body": "开发者工具正在变快，但维护成本和信任边界也被重新摊开。",
        "closing": "开发者工具正在变快，但维护成本和信任边界也被重新摊开。",
    },
    {
        "keywords": ("资本", "融资", "IPO", "估值", "上市", "递表"),
        "prefix": "今天的主线是",
        "body": "AI热潮开始接受资本规则的反向拷问。",
        "closing": "AI热潮开始接受资本规则的反向拷问。",
    },
]

DEFAULT_THESIS = {
    "prefix": "今天的三条HN讨论",
    "body": "都在指向同一个问题：技术热度落到现实里，代价由谁承担。",
    "closing": "今天的三条HN讨论，都在指向同一个问题：技术热度落到现实里，代价由谁承担。",
}

_NOISE_TOKENS = (
    "真正的",
    "今天的",
    "评论区",
    "开始",
    "正在",
    "变成",
    "进入",
    "要求",
    "需要",
)

_CLAUSE_SEPARATORS = ("：", ":", "，", ",", "。", "？", "!", "！")


def _normalize(text: str) -> str:
    return normalize_cjk_mixed_spacing(str(text or "").strip())


def _strip_noise(text: str) -> str:
    """Remove boilerplate openers and connectors from a hook candidate.

    Returns the stripped string, or ``""`` if stripping would leave
    nothing meaningful (e.g. the source was only noise words)."""
    for token in _NOISE_TOKENS:
        text = text.replace(token, "")
    return text.strip()


def _compact_copy(text: str, max_len: int = DEFAULT_HOOK_MAX_LEN) -> str:
    text = _normalize(text)
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip("，。！？；：,.!?;: ") + "…"


def _entry_hook(entry: dict, max_len: int = DEFAULT_HOOK_MAX_LEN) -> str:
    def _shorten_clause(text: str) -> str:
        text = _normalize(text)
        for sep in _CLAUSE_SEPARATORS:
            if sep in text:
                text = text.split(sep, 1)[0].strip()
                break
        return _strip_noise(text)

    for key in ("signal", "editor_angle", "title_translation", "original_title"):
        value = entry.get(key)
        if not value:
            continue
        raw = str(value)
        shortened = _shorten_clause(raw)
        return _compact_copy(shortened or raw, max_len)
    return "技术信号"


def _match_thesis(entries: list[dict]) -> dict:
    """Return the first THESIS_RULES entry whose keywords appear in the
    first 3 stories' category or editor_angle. Falls back to DEFAULT_THESIS."""
    haystack = " ".join(
        [str(e.get("category") or "") for e in entries[:3]]
        + [str(e.get("editor_angle") or "") for e in entries[:3]]
    )
    for rule in THESIS_RULES:
        if any(kw in haystack for kw in rule["keywords"]):
            return rule
    return DEFAULT_THESIS


def _daily_thesis(entries: list[dict]) -> dict:
    """Return a structured thesis for the day's opening/closing.

    Shape: ``{"prefix": str, "body": str, "closing": str}``

    - ``prefix + body`` is the full opening line (e.g. "今天的主线是…")
    - ``closing`` is the closing-friendly rewrite as a self-contained
      sentence (no opening framing like "今天的主线是…")
    """
    return _match_thesis(entries)


def _opening_audio(entries: list[dict]) -> str:
    if not entries:
        return "早上好，这里是HN每日观察。今天看三个值得停一下的技术信号。"
    rule = _daily_thesis(entries)
    thesis = f"{rule['prefix']}{rule['body']}"
    hooks = "、".join(
        _entry_hook(e, OPENING_HOOK_MAX_LEN) for e in entries[:3]
    )
    return f"早上好，这里是HN每日观察。{thesis}今天看{hooks}。"


def _closing_audio(entries: list[dict], weekday: int | None) -> str:
    if not entries:
        return "今天的HN速览就到这里。想每天跟上HN技术风向，可以点个关注，我们下期继续。"
    rule = _daily_thesis(entries)
    question = "你最担心哪一个变化？评论区聊聊。"
    if weekday in {4, 5}:
        tail = "周末也会继续留意那些真正值得追的问题。"
    else:
        tail = "想每天用几分钟跟上HN技术风向，可以点个关注。"
    return f"放在一起看，{rule['closing']}{question}{tail}"


def generate_fixed_opening(
    date: str,
    selection: Optional[SelectionResult] = None,
    content: Optional[ContentPackage] = None,
    story_scan_segs: Optional[list[ScriptSegment]] = None,
    highlight_entries: Optional[list[dict]] = None,
) -> ScriptSegment:
    """Generate a short positioning line before the first story."""
    try:
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        date_display = date_obj.strftime("%Y年%m月%d日")
    except (ValueError, TypeError):
        date_display = date

    entries = highlight_entries or []
    focus_count = len([e for e in entries if e.get("coverage_tier") == "focus"])
    audio_text = _opening_audio(entries)
    duration = 8 if len(audio_text) > 45 else 6

    top3_titles: list[str] = []
    if story_scan_segs:
        for seg in story_scan_segs[:3]:
            for elem in seg.scene_elements:
                if elem.element_type == "event_card":
                    title = elem.props.get("editor_angle")
                    if title:
                        top3_titles.append(str(title))
                    break

    keyword_counts: dict[str, int] = {}
    for entry in entries:
        for kw in entry.get("keywords") or []:
            token = str(kw).strip()
            if not token:
                continue
            if any(token in t or t in token for t in top3_titles):
                continue
            keyword_counts[token] = keyword_counts.get(token, 0) + 1
    keywords: list[str] = [
        kw for kw, _ in sorted(keyword_counts.items(), key=lambda x: (-x[1], x[0]))
    ][:3]
    if len(keywords) < 3:
        seen = set(keywords)
        for entry in entries[3:]:
            cat = str(entry.get("category") or "").strip()
            if cat and cat not in seen:
                keywords.append(cat)
                seen.add(cat)
                if len(keywords) >= 3:
                    break

    # ── Cover subtitle: 今日 3 件事钩子 (rule-based, 不调 LLM) ──
    # 优先用 highlight_entries[:3] 的 editor_angle 拼接, 替换原纯日期显示.
    hook_parts: list[str] = []
    for entry in (highlight_entries or [])[:3]:
        angle = str(entry.get("editor_angle") or "").strip()
        if angle:
            hook_parts.append(angle)
    if not hook_parts and top3_titles:
        hook_parts = top3_titles[:3]
    if hook_parts:
        # Compact each hook once; reuse the compacted form when we have to
        # drop tail items so a single un-compacted editor_angle never leaks
        # past the joiner. Threshold ≈ 3 × 14 + 2 separators of " · " (6 chars)
        # so all three compacted hooks fit comfortably on a 1920-wide badge
        # without entering the fallback path.
        compacted = [_compact_copy(part, 14) for part in hook_parts]
        subtitle = " · ".join(compacted)
        if len(subtitle) > 50:
            # 截断最后一个 hook, 保持 ≤50 字
            while len(subtitle) > 50 and len(compacted) > 1:
                compacted.pop()
                subtitle = " · ".join(compacted) + " · …"
            if len(subtitle) > 50:
                subtitle = subtitle[:49].rstrip(" ，,;；:：") + "…"
    else:
        subtitle = date_display  # fallback 到日期

    return ScriptSegment(
        segment_type="opening",
        audio_text=audio_text,
        duration=duration,
        scene_elements=[
            SceneElement(
                element_type="cover_card",
                start_time=0.0,
                end_time=duration,
                props={
                    "headline": "每日HN观察",
                    "subtitle": subtitle,
                    "date_label": date_display,  # 保留日期用于 chrome 显示
                    "keywords": keywords[:3],
                    "lineup_entries": entries,
                    "section_counts": {
                        "focus": focus_count,
                    },
                }
                | (
                    {
                        "highlight_entries": highlight_entries[:3],
                        "focus_count": focus_count or min(3, len(highlight_entries)),
                    }
                    if highlight_entries
                    else {}
                ),
            )
        ],
        meta={"highlights": {"entries": entries}} if highlight_entries else {},
    )


def closing_keywords(highlight_entries: Optional[list[dict]] = None) -> list[str]:
    keywords: list[str] = []
    seen: set[str] = set()

    def add_keyword(value) -> None:
        if not value:
            return
        text = str(value).strip()
        if not text or text in seen:
            return
        seen.add(text)
        keywords.append(text)

    for entry in highlight_entries or []:
        add_keyword(entry.get("category"))
        for keyword in entry.get("keywords") or []:
            add_keyword(keyword)
        if len(keywords) >= 3:
            break

    return (keywords or ["Agents", "Infra", "Developer Tools"])[:3]


def closing_summary_items(
    highlight_entries: Optional[list[dict]] = None,
) -> list[dict]:
    items: list[dict] = []
    for entry in (highlight_entries or [])[:3]:
        title = entry.get("title_translation")
        assert title, "Story missing title_translation"
        signal = entry.get("signal") or entry.get("editor_angle") or ""
        category = entry.get("category") or "观察"
        items.append(
            {
                "category": str(category),
                "title": str(title),
                "signal": str(signal),
            }
        )

    if items:
        return items

    return [
        {
            "category": "AI",
            "title": "AI 正从产品功能，变成开发工作流的底层能力。",
            "note": "继续关注工具链、成本结构与真实生产力提升。",
        },
        {
            "category": "Infra",
            "title": "底层基础设施仍是社区判断技术价值的核心坐标。",
            "note": "性能、可控性和维护成本比发布声量更重要。",
        },
    ]


def closing_totals(highlight_entries: Optional[list[dict]] = None) -> dict:
    entries = highlight_entries or []
    story_count = len(entries)
    score_total = sum(
        int(entry.get("score") or 0)
        for entry in entries
        if str(entry.get("score") or "").isdigit()
    )
    comment_total = sum(
        int(entry.get("comment_count") or 0)
        for entry in entries
        if str(entry.get("comment_count") or "").isdigit()
    )
    return {
        "story_count": story_count,
        "score_total": score_total,
        "comment_total": comment_total,
    }


def closing_takeaways(highlight_entries: Optional[list[dict]] = None) -> list[str]:
    takeaways: list[str] = []
    for entry in (highlight_entries or [])[:3]:
        text = entry.get("why_it_matters")
        assert text, "Story missing why_it_matters"
        text = str(text).strip()
        if len(text) > 34:
            text = text[:34].rstrip("，。！？；：,.!?;:") + "…"
        takeaways.append(text)
    return takeaways[:3]


def generate_fixed_closing(
    date: str, highlight_entries: Optional[list[dict]] = None
) -> ScriptSegment:
    """生成每日快讯结尾"""
    try:
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        weekday = date_obj.weekday()
    except (ValueError, TypeError):
        weekday = None

    audio_text = _closing_audio(highlight_entries or [], weekday)
    duration = 12 if len(audio_text) > 55 else 9
    takeaways = closing_takeaways(highlight_entries)
    signal = "今日信号"
    kw = closing_keywords(highlight_entries)
    summary_items = closing_summary_items(highlight_entries)
    totals = closing_totals(highlight_entries)

    return ScriptSegment(
        segment_type="closing",
        audio_text=audio_text,
        duration=duration,
        scene_elements=[
            SceneElement(
                element_type="closing_card",
                start_time=0.0,
                end_time=duration,
                props={
                    "signal_label": "今日信号",
                    "signal": signal,
                    "keywords_label": "今日关键词",
                    "keywords": kw,
                    "summary_label": "今日脉络",
                    "summary_items": summary_items,
                    "takeaways": takeaways,
                    "closing_mode": "takeaways",
                    "totals": totals,
                },
            )
        ],
        meta={},
    )


def build_highlight_entries(
    selection: SelectionResult,
    content: ContentPackage,
    story_scan_segs: Optional[list[ScriptSegment]] = None,
) -> list[dict]:
    """Build the opening highlight list from selected stories."""
    entries = []
    angle_by_story = {}
    signal_by_story: dict[int, str] = {}
    for idx, seg in enumerate(story_scan_segs or []):
        story_index = None
        for elem in seg.scene_elements:
            if elem.props and "story_index" in elem.props:
                story_index = elem.props.get("story_index")
                break
        if story_index is None and idx < len(selection.brief_items):
            story_index = selection.brief_items[idx].get("story_index")
        item = (
            content.items[story_index]
            if story_index is not None and story_index < len(content.items)
            else None
        )
        angle = story_angle_from_segment(seg, item=item)
        if story_index is not None:
            angle_by_story[int(story_index)] = angle
            # Extract LLM-generated signal from segment meta
            sig = seg.meta.get("signal")
            if sig:
                signal_by_story[int(story_index)] = str(sig)

    for i, bi in enumerate(selection.brief_items):
        story_idx = bi.get("story_index")
        if story_idx is not None and story_idx < len(content.items):
            item = content.items[story_idx]
            angle = angle_by_story.get(story_idx, {})
            editor_angle = (
                angle.get("editor_angle")
                or angle.get("dek")
                or angle.get("event_summary")
            )
            assert editor_angle, (
                f"Story {story_idx} missing editor_angle, dek, and event_summary"
            )
            entries.append(
                {
                    "rank": i + 1,
                    "story_index": story_idx,
                    "original_title": item.title,
                    "title_translation": item.title_cn,
                    "editor_angle": editor_angle,
                    "why_it_matters": angle.get("why_it_matters") or "",
                    "signal": signal_by_story.get(story_idx, ""),
                    "category": angle.get("category") or "",
                    "keywords": angle.get("keywords") or [],
                    "score": item.score,
                    "comment_count": item.comment_count,
                    "coverage_tier": bi.get("coverage_tier", "focus"),
                    "presentation_mode": bi.get("presentation_mode", "deep"),
                    "section": bi.get("section", ""),
                }
            )

    return entries
