from pathlib import Path
from typing import Optional

from src.core.models import Script, ContentPackage, ContentItem


def generate_brief_transcript(
    script: Script,
    date: str,
    content: Optional[ContentPackage] = None,
) -> str:
    """Generate newsletter-style markdown for daily brief product (4-segment structure)."""
    lines = [f"# HN每日观察 | {date}", ""]
    if script.description:
        lines.append(f"> {script.description}")
    if script.total_duration:
        mins = int(script.total_duration) // 60
        secs = int(script.total_duration) % 60
        lines.append(f"> 视频时长 {mins}:{secs:02d}")
    lines.append("")

    opening_segment = None
    scan_segment = None
    closing_segment = None

    for seg in script.segments:
        if seg.segment_type == "opening":
            opening_segment = seg
        elif seg.segment_type == "story_scan":
            scan_segment = seg
        elif seg.segment_type == "closing":
            closing_segment = seg

    # Opening
    if opening_segment:
        lines.append("---")
        lines.append("")
        lines.append("## 开场")
        lines.append("")
        lines.append(opening_segment.audio_text)
        lines.append("")

    highlight_entries = []
    if opening_segment:
        for elem in opening_segment.scene_elements:
            if elem.element_type == "cover_card":
                highlight_entries = elem.props.get("highlight_entries", [])
                break

    if highlight_entries or content:
        lines.append("---")
        lines.append("")
        lines.append("## 今日亮点")
        lines.append("")

        if highlight_entries:
            for entry in highlight_entries:
                rank = entry.get("rank", "")
                title = entry.get("original_title", "") or entry.get("title", "")
                title_cn = entry.get("title_translation", "") or entry.get(
                    "title_cn", ""
                )
                score = entry.get("score", "")
                comments = entry.get("comment_count", "")
                score_str = f" ▲ {score}" if score else ""
                comments_str = f" · 💬 {comments}" if comments else ""
                if title_cn:
                    lines.append(
                        f"{rank}. **{title_cn}** / {title}{score_str}{comments_str}"
                    )
                else:
                    lines.append(f"{rank}. **{title}**{score_str}{comments_str}")
        elif content:
            for i, item in enumerate(content.items[:3], 1):
                score_str = f" ▲ {item.score}" if item.score else ""
                comments_str = (
                    f" · 💬 {item.comment_count}" if item.comment_count else ""
                )
                title_cn = item.title_cn
                if title_cn:
                    lines.append(
                        f"{i}. **{title_cn}** / {item.title}{score_str}{comments_str}"
                    )
                else:
                    lines.append(f"{i}. **{item.title}**{score_str}{comments_str}")
        lines.append("")

    # Story scan (逐条速览)
    if scan_segment:
        # Group scene_elements by story_index
        story_elems: dict = {}
        for elem in scan_segment.scene_elements:
            si = elem.props.get("story_index") if elem.props else None
            if si is not None:
                story_elems.setdefault(si, []).append(elem)

        # Split audio_text per card using sub_segment_subtitle_texts
        subtitle_texts_list = (
            scan_segment.meta.get("sub_segment_subtitle_texts", [])
            if scan_segment.meta
            else []
        )
        card_texts = []
        for texts in subtitle_texts_list:
            card_texts.append(" ".join(t for t in texts if t))

        lines.append("---")
        lines.append("")
        lines.append("## 逐条速览")
        lines.append("")

        card_idx = 0
        for i in sorted(story_elems.keys()):
            elems = story_elems[i]
            story_item: ContentItem | None = (
                content.items[i] if content and i < len(content.items) else None
            )

            event_elem = next(
                (e for e in elems if e.element_type == "event_card"), None
            )
            atmosphere_elem = next(
                (e for e in elems if e.element_type == "atmosphere_card"), None
            )

            event_summary = (
                event_elem.props.get("dek", "")
                or event_elem.props.get("event_summary", "")
                if event_elem
                else ""
            )
            display_idx = event_elem.props.get("display_index", i) if event_elem else i

            lines.append(
                f"### {display_idx + 1}. {event_summary or (story_item.title if story_item else '')}"
            )
            lines.append("")

            # Card-by-card narration
            for _ in range(
                len(
                    [
                        e
                        for e in elems
                        if e.element_type in ("event_card", "atmosphere_card")
                    ]
                )
            ):
                if card_idx < len(card_texts):
                    lines.append(card_texts[card_idx])
                    lines.append("")
                card_idx += 1

            # Meta info
            meta_parts = []
            image_parts = []
            if story_item:
                if story_item.score:
                    meta_parts.append(f"▲ {story_item.score}")
                if story_item.comment_count:
                    meta_parts.append(f"💬 {story_item.comment_count}")
                if story_item.url:
                    meta_parts.append(f"[原文]({story_item.url})")
                if story_item.article_images:
                    for img in story_item.article_images:
                        image_parts.append(f"🖼 {img}")
                if story_item.screenshot_image:
                    image_parts.append(f"📸 {story_item.screenshot_image}")
                if story_item.logo_image:
                    image_parts.append(f"🏷 {story_item.logo_image}")
            if meta_parts:
                lines.append(" · ".join(meta_parts))
                lines.append("")
            if image_parts:
                lines.append(" · ".join(image_parts))
                lines.append("")

            # Stance distribution from atmosphere_card
            if atmosphere_elem and atmosphere_elem.props:
                dist = atmosphere_elem.props.get("stance_distribution", {})
                if dist:
                    sorted_dist = sorted(dist.items(), key=lambda x: x[1], reverse=True)
                    dist_str = " · ".join(
                        f"{k} {int(v * 100)}%" for k, v in sorted_dist if v > 0
                    )
                    if dist_str:
                        lines.append(f"**社区观点**  {dist_str}")
                        lines.append("")

            # Debate focus from atmosphere_card
            if atmosphere_elem and atmosphere_elem.props:
                debate_focus = atmosphere_elem.props.get("debate_focus", [])
                if debate_focus:
                    lines.append(f"**争议焦点**  {' · '.join(debate_focus)}")
                    lines.append("")

            # Quotes from atmosphere_card
            if atmosphere_elem and atmosphere_elem.props:
                quotes = atmosphere_elem.props.get("quotes", [])
                if quotes:
                    for q in quotes:
                        stance = q.get("stance", "")
                        author = q.get("author", "")
                        text = q.get("text", "")
                        stance_str = f"**[{stance}]** " if stance else ""
                        lines.append(f'- {stance_str}{author}: "{text[:120]}"')
                    lines.append("")
        else:
            if not story_elems and scan_segment.audio_text:
                lines.append(scan_segment.audio_text)
                lines.append("")

    # Closing
    if closing_segment:
        lines.append("---")
        lines.append("")
        lines.append("## 结尾")
        lines.append("")
        lines.append(closing_segment.audio_text)
        lines.append("")

    return "\n".join(lines)


def save_transcript(
    script: Script,
    date: str,
    content: Optional[ContentPackage] = None,
    logger=None,
) -> Path:
    path = Path(f"data/{date}/transcript.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    md_content = generate_brief_transcript(script, date, content)
    path.write_text(md_content, encoding="utf-8")
    if logger:
        logger.info(f"Saved transcript to {path}")
    return path
