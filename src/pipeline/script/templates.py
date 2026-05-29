"""Script templates: opening, closing, and highlight entry generation."""

from datetime import datetime
from typing import Optional

from src.core.models import (
    ContentPackage,
    ScriptSegment,
    SceneElement,
    SelectionResult,
)


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
        title = (
            entry.get("title_translation")
            or entry.get("editor_angle")
            or entry.get("original_title")
            or ""
        )
        title = str(title).strip()
        if len(title) > 18:
            title = title[:18].rstrip("，。！？；：,.!?;:") + "…"
        ordinal = CHINESE_ORDINALS[idx] if idx < len(CHINESE_ORDINALS) else str(idx + 1)
        labels.append(f"第{ordinal}，{title}" if title else f"第{ordinal}条")
    if not labels:
        return "来看今天的三个技术信号，我们一条条听。"
    return f"今天看{len(labels)}条：" + "；".join(labels) + "。我们一条条听。"


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
    standard_count = len([e for e in entries if e.get("coverage_tier") == "standard"])
    quick_count = len([e for e in entries if e.get("coverage_tier") == "quick"])
    if len(entries) > 3:
        audio_text = (
            f"早上好，这里是 HN每日观察。今天选了{len(entries)}条讨论，"
            f"{focus_count}条重点，{standard_count}条速读，{quick_count}条快扫。"
        )
        duration = 8
    else:
        audio_text = "早上好，这里是 HN每日观察，带你看昨天HN发生了什么。"
        duration = 5

    top3_titles: list[str] = []
    if story_scan_segs:
        for seg in story_scan_segs[:3]:
            for elem in seg.scene_elements:
                if elem.element_type == "event_card":
                    title = (
                        elem.props.get("editor_angle")
                        or elem.props.get("title_cn")
                        or ""
                    )
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
                    "headline": "每日技术速览",
                    "subtitle": date_display,
                    "keywords": keywords[:3],
                    "lineup_entries": entries,
                    "section_counts": {
                        "focus": focus_count,
                        "standard": standard_count,
                        "quick": quick_count,
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
        title = (
            entry.get("editor_angle")
            or entry.get("title_translation")
            or entry.get("original_title")
            or ""
        )
        note = entry.get("why_it_matters") or ""
        category = entry.get("category") or "观察"
        if not title and not note:
            continue
        items.append(
            {
                "category": str(category),
                "title": str(title),
                "note": str(note),
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
        text = (
            entry.get("why_it_matters")
            or entry.get("editor_angle")
            or entry.get("title_translation")
            or ""
        )
        text = str(text).strip()
        if not text:
            continue
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

    if weekday in {4, 5}:
        audio_text = "今天的 HN 速览就到这里，周末继续留意那些真正值得追的问题。"
    else:
        audio_text = "今天的 HN 速览就到这里，我们明天继续看哪些讨论值得停一下。"
    duration = 8
    takeaways = closing_takeaways(highlight_entries)
    signal = (
        "今天值得带走的，是这些讨论各自提出的具体问题。"
        if highlight_entries and len(highlight_entries) > 3
        else (takeaways[0] if takeaways else "今天的技术讨论，先记住问题，再看答案。")
    )
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

    for i, bi in enumerate(selection.brief_items):
        story_idx = bi.get("story_index")
        if story_idx is not None and story_idx < len(content.items):
            item = content.items[story_idx]
            angle = angle_by_story.get(story_idx, {})
            entries.append(
                {
                    "rank": i + 1,
                    "story_index": story_idx,
                    "original_title": item.title,
                    "title_translation": item.title_cn,
                    "editor_angle": angle.get("editor_angle")
                    or angle.get("dek")
                    or angle.get("event_summary")
                    or item.title_cn
                    or item.title,
                    "why_it_matters": angle.get("why_it_matters") or "",
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
