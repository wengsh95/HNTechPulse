"""Import human-edited or LLM-generated Markdown video scripts into the structured pipeline."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.core.models import ContentPackage, SceneElement, Script, ScriptSegment
from src.pipeline.agent_io import write_artifact_manifest
from src.pipeline.paths import date_root, pipeline_path
from src.pipeline.script.cards import _clean_subtitle_text, split_long_subtitle
from src.pipeline.script.io import (
    save_script,
    save_script_lock,
    script_audio_input_hash,
)
from src.pipeline.storyboard_draft import build_storyboard
from src.utils.atomic_io import atomic_write_json


_SECTION_HEADING_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_SUBSECTION_HEADING_RE = re.compile(r"^###\s+(.+)$", re.MULTILINE)
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\)]+)\)")
_BOLD_TEXT_RE = re.compile(r"\*\*([^\*]+)\*\*")


def _clean_text(text: str) -> str:
    """Strip markdown formatting (bold, links, extra spaces) to produce clean spoken/display text."""
    text = _MARKDOWN_LINK_RE.sub(r"\1", text)
    text = text.replace("**", "").replace("*", "").replace("`", "")
    return text.strip()


def _extract_links(text: str) -> list[tuple[str, str]]:
    """Extract list of (label, url) tuples."""
    return _MARKDOWN_LINK_RE.findall(text)


def _split_into_sentences(text: str) -> list[str]:
    """Split text into spoken clauses / sentences for subtitle cues."""
    cleaned = _clean_text(text)
    raw_sentences = re.split(r"(?<=[。！？!?])\s*", cleaned)
    cues: list[str] = []
    for sent in raw_sentences:
        sent = sent.strip()
        if not sent:
            continue
        splits = split_long_subtitle(sent)
        cues.extend(
            [_clean_subtitle_text(s) for s in splits if _clean_subtitle_text(s)]
        )
    return cues


def parse_markdown_script(
    markdown_text: str,
    date: str,
    content: ContentPackage | None = None,
) -> Script:
    """Parse an editorial markdown video script into a structured Script model."""
    lines = markdown_text.splitlines()

    url_to_item = {}
    if content:
        for idx, item in enumerate(content.items):
            if item.url:
                url_to_item[item.url.strip()] = (idx, item)

    sections: list[tuple[str, list[str]]] = []
    current_sec_title: str | None = None
    current_sec_lines: list[str] = []

    for line in lines:
        match = re.match(r"^##\s+(.+)$", line)
        if match:
            if current_sec_title is not None and current_sec_lines:
                sections.append((current_sec_title, current_sec_lines))
            current_sec_title = match.group(1).strip()
            current_sec_lines = []
        else:
            if current_sec_title is not None:
                current_sec_lines.append(line)
    if current_sec_title is not None and current_sec_lines:
        sections.append((current_sec_title, current_sec_lines))

    cover_headline = "每日HN日报"
    cover_subtitle = ""
    cover_date = date

    opening_text_lines: list[str] = []
    story_sections: list[dict[str, Any]] = []
    quick_news_items: list[dict[str, Any]] = []
    closing_text_lines: list[str] = []

    for title, sec_lines in sections:
        norm_title = title.lower()
        sec_text = "\n".join(sec_lines).strip()

        if "封面" in norm_title or "cover" in norm_title:
            bolds = _BOLD_TEXT_RE.findall(sec_text)
            if len(bolds) >= 1:
                cover_headline = bolds[0].strip()
            if len(bolds) >= 2:
                cover_subtitle = bolds[1].strip()
            if len(bolds) >= 3:
                cover_date = bolds[2].strip()
            continue

        if "开场" in norm_title or "opening" in norm_title or "hook" in norm_title:
            for p in sec_text.split("\n\n"):
                p_clean = _clean_text(p)
                if p_clean and not p_clean.startswith("#"):
                    opening_text_lines.append(p_clean)
            continue

        if "快讯" in norm_title or "速览" in norm_title or "quick" in norm_title:
            current_quick_title = ""
            current_quick_lines: list[str] = []
            for sline in sec_lines:
                sub_m = re.match(r"^###\s+(.+)$", sline)
                if sub_m:
                    if current_quick_title and current_quick_lines:
                        q_text = "\n".join(current_quick_lines).strip()
                        links = _extract_links(q_text)
                        quick_news_items.append(
                            {
                                "title": current_quick_title,
                                "text": _clean_text(q_text),
                                "url": links[0][1] if links else "",
                            }
                        )
                    current_quick_title = sub_m.group(1).strip()
                    current_quick_lines = []
                else:
                    current_quick_lines.append(sline)
            if current_quick_title and current_quick_lines:
                q_text = "\n".join(current_quick_lines).strip()
                links = _extract_links(q_text)
                quick_news_items.append(
                    {
                        "title": current_quick_title,
                        "text": _clean_text(q_text),
                        "url": links[0][1] if links else "",
                    }
                )
            continue

        if "结尾" in norm_title or "closing" in norm_title or "总结" in norm_title:
            for p in sec_text.split("\n\n"):
                p_clean = _clean_text(p)
                if p_clean and not p_clean.startswith("#"):
                    closing_text_lines.append(p_clean)
            continue

        is_headline = "头条" in norm_title or "headline" in norm_title
        clean_story_title = re.sub(
            r"^(头条|重点[一二三四0-9]*|故事[0-9]*)[:：\s]*", "", title
        ).strip()
        story_links = _extract_links(sec_text)
        story_url = story_links[0][1] if story_links else ""

        matched_idx = None
        matched_item = None
        if story_url and story_url in url_to_item:
            matched_idx, matched_item = url_to_item[story_url]

        story_body_paras: list[str] = []
        comment_paras: list[str] = []
        in_comment = False

        for p in sec_text.split("\n\n"):
            p_str = p.strip()
            if not p_str or p_str.startswith("#"):
                continue
            if "评论区" in p_str or "HN 评论" in p_str or "社区讨论" in p_str:
                in_comment = True
            if in_comment:
                comment_paras.append(_clean_text(p_str))
            else:
                story_body_paras.append(_clean_text(p_str))

        if not story_body_paras and comment_paras:
            story_body_paras = comment_paras[:1]
            comment_paras = comment_paras[1:]

        story_sections.append(
            {
                "section_label": "头条"
                if is_headline
                else f"重点 {len(story_sections):02d}",
                "is_headline": is_headline,
                "title": clean_story_title
                or (matched_item.editor_angle if matched_item else "焦点观察"),
                "url": story_url,
                "matched_index": matched_idx,
                "matched_item": matched_item,
                "body_paragraphs": story_body_paras,
                "comment_paragraphs": comment_paras,
            }
        )

    # 1. Construct Opening Segment
    opening_audio_text = (
        " ".join(opening_text_lines)
        if opening_text_lines
        else f"欢迎收看HN每日观察，今天是{date}。"
    )
    opening_subtitles = []
    for p in opening_text_lines:
        opening_subtitles.extend(_split_into_sentences(p))
    if not opening_subtitles:
        opening_subtitles = [opening_audio_text]

    opening_duration = max(6, int(len(opening_audio_text) / 4.5))

    cover_props: dict[str, Any] = {
        "headline": cover_headline,
        "date_label": cover_date,
        "date": date,
        "template_id": "cover_v1",
        "shot_id": "S01-01",
        "subtitle_texts": opening_subtitles[:2],
    }
    if cover_subtitle:
        cover_props["subtitle"] = cover_subtitle

    opening_segment = ScriptSegment(
        segment_type="opening",
        audio_text=opening_audio_text,
        duration=opening_duration,
        emotion="warm",
        scene_elements=[
            SceneElement(
                element_type="cover_card",
                start_time=0.0,
                end_time=float(opening_duration),
                props=cover_props,
            )
        ],
        meta={"highlights": {"entries": []}},
    )

    # 2. Construct Story Scan Segment
    story_scene_elements: list[SceneElement] = []
    all_story_audio_parts: list[str] = []
    sub_segment_subtitle_texts: list[list[str]] = []
    sub_segment_durations: list[float] = []

    for s_idx, s_info in enumerate(story_sections):
        item = s_info["matched_item"]
        story_index = (
            s_info["matched_index"] if s_info["matched_index"] is not None else s_idx
        )

        body_text = " ".join(s_info["body_paragraphs"])
        body_subs = []
        for p in s_info["body_paragraphs"]:
            body_subs.extend(_split_into_sentences(p))
        if not body_subs and body_text:
            body_subs = [body_text]

        body_dur = max(10.0, len(body_text) / 4.5)
        all_story_audio_parts.append(body_text)
        sub_segment_subtitle_texts.append(body_subs)
        sub_segment_durations.append(body_dur)

        evidence_template = (
            "headline_v1" if s_info["is_headline"] else "source_evidence_v1"
        )
        evidence_elem_type = (
            "headline_card" if s_info["is_headline"] else "source_evidence_card"
        )

        evidence_props: dict[str, Any] = {
            "story_index": story_index,
            "title": s_info["title"],
            "section_label": s_info["section_label"],
            "eyebrow": s_info["section_label"],
            "subtitle_texts": body_subs,
            "source_url": s_info["url"],
            "template_id": evidence_template,
            "shot_id": f"S02-{len(story_scene_elements) + 1:02d}",
            "story_role": "evidence",
        }
        if item:
            evidence_props["source_title"] = item.title
            evidence_props["title_cn"] = item.title_cn or item.title
            evidence_props["category"] = item.category or "技术观察"
            evidence_props["score"] = item.score or 0
            evidence_props["comment_count"] = item.comment_count or 0
            evidence_props["why_it_matters"] = item.why_it_matters or s_info["title"]
            if item.key_points:
                evidence_props["key_points"] = item.key_points
            if item.image_src:
                evidence_props["image_src"] = item.image_src
                evidence_props["story_image"] = item.image_src
                evidence_props["image_url"] = item.image_src

        story_scene_elements.append(
            SceneElement(
                element_type=evidence_elem_type,
                start_time=0.0,
                end_time=body_dur,
                props=evidence_props,
                sub_segment_index=len(story_scene_elements),
            )
        )

        comment_text = (
            " ".join(s_info["comment_paragraphs"])
            if s_info["comment_paragraphs"]
            else f"{s_info['title']}引发社区深入讨论。"
        )
        comment_subs = []
        for p in s_info["comment_paragraphs"]:
            comment_subs.extend(_split_into_sentences(p))
        if not comment_subs:
            comment_subs = [comment_text]

        comm_dur = max(8.0, len(comment_text) / 4.5)
        all_story_audio_parts.append(comment_text)
        sub_segment_subtitle_texts.append(comment_subs)
        sub_segment_durations.append(comm_dur)

        quote_text = (
            s_info["comment_paragraphs"][0]
            if s_info["comment_paragraphs"]
            else s_info["title"]
        )
        if len(quote_text) > 80:
            quote_text = quote_text[:76] + "..."

        comment_props: dict[str, Any] = {
            "story_index": story_index,
            "section_label": s_info["section_label"],
            "eyebrow": f"HN 评论 · {s_info['section_label']}",
            "quote": quote_text,
            "author": "HN community",
            "stance": "观点",
            "subtitle_texts": comment_subs,
            "template_id": "comment_single_v1",
            "shot_id": f"S02-{len(story_scene_elements) + 1:02d}",
            "story_role": "comment",
            "quotes": [
                {
                    "author": "HN community",
                    "text": quote_text,
                    "stance": "观点",
                }
            ],
        }
        if len(s_info["comment_paragraphs"]) >= 2:
            comment_props["left_summary"] = s_info["comment_paragraphs"][0]
            comment_props["right_summary"] = s_info["comment_paragraphs"][1]
            comment_props["left_stance"] = "观点一"
            comment_props["right_stance"] = "观点二"

        story_scene_elements.append(
            SceneElement(
                element_type="comment_card",
                start_time=0.0,
                end_time=comm_dur,
                props=comment_props,
                sub_segment_index=len(story_scene_elements),
            )
        )

    story_audio_text = " ".join(all_story_audio_parts)
    story_duration = sum(sub_segment_durations)

    story_segment = ScriptSegment(
        segment_type="story_scan",
        audio_text=story_audio_text,
        duration=story_duration,
        emotion="warm",
        scene_elements=story_scene_elements,
        meta={
            "sub_segment_subtitle_texts": sub_segment_subtitle_texts,
            "sub_segment_estimated_durations": sub_segment_durations,
            "story_indices": [
                s.get("matched_index") or i for i, s in enumerate(story_sections)
            ],
        },
    )

    # 3. Construct Quick News Segment
    quick_elements: list[SceneElement] = []
    quick_audio_parts: list[str] = ["接下来是快讯。"]
    quick_sub_subs: list[list[str]] = []
    quick_durations: list[float] = []

    for q_idx, q_item in enumerate(quick_news_items):
        q_title = q_item["title"]
        q_fact = q_item["text"]
        q_audio = f"{q_title}。{q_fact}"
        quick_audio_parts.append(q_audio)
        subs = _split_into_sentences(q_audio)
        dur = max(6.0, len(q_audio) / 4.5)
        quick_sub_subs.append(subs)
        quick_durations.append(dur)

        q_props: dict[str, Any] = {
            "index": f"{q_idx + 1:02d}",
            "title": q_title,
            "fact": q_fact,
            "source_url": q_item["url"],
            "subtitle_texts": subs,
            "section_label": "速览",
            "eyebrow": "速览",
            "template_id": "quick_news_v1",
            "shot_id": f"S03-{q_idx + 1:02d}",
            "story_role": "quick",
        }
        quick_elements.append(
            SceneElement(
                element_type="quick_card",
                start_time=0.0,
                end_time=dur,
                props=q_props,
                sub_segment_index=q_idx,
            )
        )

    quick_audio_text = " ".join(quick_audio_parts)
    quick_duration = sum(quick_durations) if quick_durations else 10.0

    quick_segment = ScriptSegment(
        segment_type="quick_news",
        audio_text=quick_audio_text,
        duration=quick_duration,
        emotion="neutral",
        scene_elements=quick_elements,
        meta={
            "sub_segment_subtitle_texts": quick_sub_subs,
            "sub_segment_estimated_durations": quick_durations,
        },
    )

    # 4. Construct Closing Segment
    closing_audio_text = (
        " ".join(closing_text_lines)
        if closing_text_lines
        else "今天的HN速览就到这里，祝你今天顺利，我们下期继续。"
    )
    closing_subs = []
    for p in closing_text_lines:
        closing_subs.extend(_split_into_sentences(p))
    if not closing_subs:
        closing_subs = [closing_audio_text]

    closing_duration = max(8, int(len(closing_audio_text) / 4.5))

    summary_items = [
        {
            "category": s["section_label"],
            "title": s["title"],
            "signal": s["title"],
        }
        for s in story_sections[:3]
    ]

    closing_props: dict[str, Any] = {
        "keywords_label": "今日关键词",
        "keywords": [s["title"][:8] for s in story_sections[:3]]
        or ["AI", "Infra", "Developer"],
        "summary_label": "今日脉络",
        "summary_items": summary_items,
        "takeaways": [s["title"] for s in story_sections[:3]],
        "template_id": "closing_v1",
        "shot_id": "S04-01",
        "subtitle_texts": closing_subs[:3],
    }

    closing_segment = ScriptSegment(
        segment_type="closing",
        audio_text=closing_audio_text,
        duration=closing_duration,
        emotion="warm",
        scene_elements=[
            SceneElement(
                element_type="closing_card",
                start_time=0.0,
                end_time=float(closing_duration),
                props=closing_props,
            )
        ],
        meta={},
    )

    return Script(
        title=f"HN每日观察 | {date}",
        description=f"每日快讯 - {date}",
        tags=[],
        segments=[opening_segment, story_segment, quick_segment, closing_segment],
        total_duration=opening_duration
        + story_duration
        + quick_duration
        + closing_duration,
    )


def import_markdown_script(
    date: str,
    file_path: Path | None = None,
    content: ContentPackage | None = None,
) -> tuple[Script, Path]:
    """Load markdown, parse into Script, save script.json, script_lock.json, and storyboard.json."""
    if file_path is None:
        root = date_root(date)
        file_path = root / "video_script.md"

    if not file_path.exists():
        raise FileNotFoundError(f"Markdown script not found: {file_path}")

    markdown_text = file_path.read_text(encoding="utf-8")
    script = parse_markdown_script(markdown_text, date=date, content=content)

    saved_path = pipeline_path(date, "script.json")
    save_script(script, date=date)
    save_script_lock(script, date=date, source="markdown_import")

    storyboard = build_storyboard(script, date=date)
    sb_path = pipeline_path(date, "storyboard.json")
    atomic_write_json(sb_path, storyboard)
    write_artifact_manifest(
        sb_path,
        step="draft_storyboard",
        date=date,
        inputs={"script_hash": script_audio_input_hash(script)},
    )

    return script, saved_path
