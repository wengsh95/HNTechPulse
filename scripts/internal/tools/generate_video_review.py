#!/usr/bin/env python3
"""Generate a tiny, self-contained HTML review for a video script.

The page intentionally renders each script segment as:

    narration -> matching scene elements -> per-shot narration

It is an editorial review aid, not another renderer.  It works before a full
video render and can also read a storyboard that has not been applied yet.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline.paths import date_root, pipeline_path  # noqa: E402


ELEMENT_LABELS = {
    "cover_card": "封面",
    "headline_card": "头条钩子",
    "event_card": "事件卡",
    "source_evidence_card": "来源证据",
    "atmosphere_card": "讨论气氛",
    "comment_card": "单条评论",
    "comment_dual_card": "评论对照",
    "data_number_card": "数据冲击",
    "quick_card": "快讯",
    "closing_card": "结尾",
    "signals_card": "三条信号",
}


def _esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _join_texts(value: Any, separator: str = " ") -> str:
    if isinstance(value, list):
        return separator.join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


def _storyboard_for_element(
    storyboard_shots: list[dict[str, Any]],
    *,
    segment_index: int,
    element_index: int,
    element: dict[str, Any],
    all_elements: list[dict[str, Any]],
) -> dict[str, Any] | None:
    props = element.get("props") or {}
    shot_id = props.get("shot_id")
    if shot_id:
        return next(
            (shot for shot in storyboard_shots if shot.get("shot_id") == shot_id),
            None,
        )

    for shot in storyboard_shots:
        if (
            shot.get("segment_index") == segment_index
            and shot.get("element_index") == element_index
        ):
            return shot

    story_index = props.get("story_index")
    if story_index is None:
        return None
    for shot in storyboard_shots:
        if shot.get("story_index") != story_index:
            continue
        source_type = shot.get("source_element_type")
        candidates = [
            candidate
            for candidate in all_elements
            if (candidate.get("props") or {}).get("story_index") == story_index
            and (not source_type or candidate.get("element_type") == source_type)
        ]
        source_index = shot.get("source_element_index")
        if source_index is None and len(candidates) == 1:
            return shot
        if isinstance(source_index, int) and 0 <= source_index < len(candidates):
            if candidates[source_index] is element:
                return shot
    return None


def _shot_copy(
    element: dict[str, Any], storyboard_shot: dict[str, Any] | None
) -> tuple[str, dict[str, Any]]:
    element_type = str(element.get("element_type") or "scene_element")
    props = dict(element.get("props") or {})
    if storyboard_shot:
        template_id = str(
            storyboard_shot.get("template_id")
            or storyboard_shot.get("element_type")
            or ""
        )
        props.update(storyboard_shot.get("props") or {})
        return template_id, props
    return str(
        props.get("template_id") or ELEMENT_LABELS.get(element_type, element_type)
    ), props


def _shot_content(props: dict[str, Any]) -> str:
    rows: list[str] = []
    for label, keys in (
        ("标题", ("title", "headline", "source_title", "title_cn", "editor_angle")),
        ("事实", ("fact", "event_summary", "dek", "caption", "context")),
        ("评论", ("quote", "discussion_summary")),
    ):
        value = next((props.get(key) for key in keys if props.get(key)), "")
        if value:
            rows.append(f"<div><b>{_esc(label)}</b> {_esc(value)}</div>")

    for label, side in (("支持", "left_summary"), ("质疑", "right_summary")):
        if props.get(side):
            rows.append(f"<div><b>{_esc(label)}</b> {_esc(props[side])}</div>")

    if props.get("value") is not None:
        value = f"{props.get('value')} {props.get('label') or ''}".strip()
        rows.append(f"<div><b>数字</b> {_esc(value)}</div>")
    if props.get("items"):
        rows.append(
            f"<div><b>信号</b> {_esc(_join_texts(props['items'], ' / '))}</div>"
        )
    return "".join(rows) or '<div class="muted">暂无画面文字</div>'


def _first_prop(props: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = props.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _source_host(value: str) -> str:
    if not value:
        return ""
    try:
        from urllib.parse import urlparse

        return urlparse(value).netloc.replace("www.", "") or value
    except ValueError:
        return value


def _image_preview(props: dict[str, Any]) -> str:
    """Show the selected local story image in the editorial review page."""

    raw = _first_prop(props, "image_src", "story_image")
    if not raw or raw.startswith(("http://", "https://")):
        return ""
    image_path = Path(raw)
    if image_path.parts and image_path.parts[0].lower() == "images":
        href = "../media/" + "/".join(image_path.parts)
    else:
        href = "../media/images/" + image_path.name
    return f'''<div class="story-image">
      <span class="preview-kicker">STORY IMAGE · {_esc(image_path.name)}</span>
      <img src="{_esc(href)}" alt="story image" loading="lazy">
    </div>'''


def _template_visual(template_id: str, props: dict[str, Any]) -> str:
    """Render a semantic visual mock, so the HTML review is not a generic text dump."""

    title = _first_prop(props, "title", "headline", "editor_angle", "source_title")
    fact = _first_prop(props, "fact", "event_summary", "key_fact", "dek", "context")
    subtitle = _first_prop(props, "subtitle", "why_it_matters", "summary")
    source = _source_host(_first_prop(props, "source_url", "image_url"))
    eyebrow = _first_prop(props, "eyebrow", "category")

    if template_id == "cover_v1":
        return f"""<div class="template-preview preview-cover">
          <span class="preview-kicker">HN DAILY / {_esc(props.get("date") or "TODAY")}</span>
          <strong>{_esc(title or props.get("headline") or "每日技术观察")}</strong>
          <span class="preview-cover-rule"></span>
          <small>头条 · 重点 · 速览</small>
        </div>"""
    if template_id == "headline_v1":
        stat = _first_prop(props, "stat", "stat_label")
        return f"""<div class="template-preview preview-headline">
          <span class="preview-kicker">{_esc(eyebrow or "HEADLINE")}</span>
          <strong>{_esc(title or "今日头条")}</strong>
          {f"<p>{_esc(subtitle)}</p>" if subtitle else ""}
          {f'<span class="preview-pill">{_esc(stat)}</span>' if stat else ""}
        </div>"""
    if template_id == "event_v1":
        category = _first_prop(props, "category", "eyebrow")
        return f"""<div class="template-preview preview-event">
          <span class="preview-index">EVENT</span>
          <div><strong>{_esc(title or "事件")}</strong><p>{_esc(fact or subtitle)}</p></div>
          {f'<span class="preview-tag">{_esc(category)}</span>' if category else ""}
        </div>"""
    if template_id == "source_evidence_v1":
        return f"""<div class="template-preview preview-evidence">
          <div class="evidence-frame"><span>SOURCE</span><b>{_esc(source or "原文截图")}</b></div>
          <div><span class="preview-kicker">EVIDENCE</span><strong>{_esc(title or "来源证据")}</strong><p>{_esc(fact or subtitle)}</p></div>
        </div>"""
    if template_id in {"discussion_v1", "comment_single_v1"}:
        quote = _first_prop(
            props, "quote", "comment_summary", "discussion_summary", "summary"
        )
        author = _first_prop(props, "author", "stance")
        return f"""<div class="template-preview preview-discussion">
          <span class="preview-kicker">HN COMMENT / COMMUNITY</span>
          <blockquote>“{_esc(quote or "评论区讨论")}"</blockquote>
          {f"<small>{_esc(author)}</small>" if author else ""}
        </div>"""
    if template_id == "comment_dual_v1":
        left = _first_prop(props, "left_summary", "left_text")
        right = _first_prop(props, "right_summary", "right_text")
        return f"""<div class="template-preview preview-dual">
          <div><span>观点 A</span><p>{_esc(left or "支持方观点")}</p></div>
          <div><span>观点 B</span><p>{_esc(right or "质疑方观点")}</p></div>
        </div>"""
    if template_id == "data_number_v1":
        value = _first_prop(props, "value")
        label = _first_prop(props, "label")
        context = _first_prop(props, "context", "comparisons")
        return f"""<div class="template-preview preview-number">
          <strong>{_esc(value or "—")}</strong><span>{_esc(label or title or "关键数字")}</span>
          {f"<p>{_esc(context)}</p>" if context else ""}
        </div>"""
    if template_id == "quick_news_v1":
        index = _first_prop(props, "index")
        return f"""<div class="template-preview preview-quick">
          <span class="quick-index">{_esc(index or "01")}</span>
          <div><strong>{_esc(title or "快讯")}</strong><p>{_esc(fact or subtitle)}</p></div>
          {f"<small>{_esc(source)}</small>" if source else ""}
        </div>"""
    if template_id == "closing_signals_v1":
        items = props.get("items") or []
        if not isinstance(items, list):
            items = [items]
        chips = "".join(f"<li>{_esc(item)}</li>" for item in items[:3])
        return f"""<div class="template-preview preview-signals">
          <span class="preview-kicker">TAKEAWAYS</span><strong>{_esc(title or "今天留下三条信号")}</strong>
          <ul>{chips}</ul>
        </div>"""
    if template_id == "closing_v1":
        return f"""<div class="template-preview preview-closing"><span>END OF BRIEF</span><strong>{_esc(title or "明日继续")}</strong></div>"""
    return (
        f'<div class="template-preview preview-fallback">{_shot_content(props)}</div>'
    )


def _shot_html(
    *,
    segment_index: int,
    element_index: int,
    element: dict[str, Any],
    storyboard_shot: dict[str, Any] | None,
) -> str:
    element_type = str(element.get("element_type") or "scene_element")
    template_id, props = _shot_copy(element, storyboard_shot)
    shot_id = str(props.get("shot_id") or (storyboard_shot or {}).get("shot_id") or "")
    subtitle = _join_texts(props.get("subtitle_texts"), " ")
    start = element.get("start_time")
    end = element.get("end_time")
    timing = (
        f"{start:.1f}s – {end:.1f}s"
        if isinstance(start, (int, float)) and isinstance(end, (int, float))
        else f"镜头 {element_index + 1}"
    )
    visual = _template_visual(template_id, props)
    image_preview = _image_preview(props)
    if image_preview:
        visual += image_preview
    return f"""
      <article class="shot">
        <div class="shot-head">
          <span class="shot-no">{_esc(shot_id or f"S{segment_index + 1:02d}-{element_index + 1:02d}")}</span>
          <span class="time">{_esc(timing)}</span>
          <span class="template">{_esc(template_id)}</span>
          <span class="type">{_esc(ELEMENT_LABELS.get(element_type, element_type))}</span>
        </div>
        <div class="visual">{visual}</div>
        <div class="voice"><b>对应台词</b> {_esc(subtitle or "该镜头使用段落旁白")}</div>
      </article>
    """


def generate_html(date: str) -> Path:
    script_path = pipeline_path(date, "script.json")
    storyboard_path = pipeline_path(date, "storyboard.json")
    if not script_path.exists():
        raise FileNotFoundError(f"script.json not found: {script_path}")

    script = json.loads(script_path.read_text(encoding="utf-8"))
    storyboard = {}
    if storyboard_path.exists():
        storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
    storyboard_shots = storyboard.get("shots") or []

    segments = script.get("segments") or []
    all_elements = [
        element
        for segment in segments
        for element in segment.get("scene_elements") or []
    ]
    segment_html: list[str] = []
    for segment_index, segment in enumerate(segments):
        elements = segment.get("scene_elements") or []
        shots = []
        for element_index, element in enumerate(elements):
            shot = _storyboard_for_element(
                storyboard_shots,
                segment_index=segment_index,
                element_index=element_index,
                element=element,
                all_elements=all_elements,
            )
            shots.append(
                _shot_html(
                    segment_index=segment_index,
                    element_index=element_index,
                    element=element,
                    storyboard_shot=shot,
                )
            )
        segment_type = str(segment.get("segment_type") or "segment")
        segment_html.append(
            f"""
      <section class="segment">
        <h2>{segment_index + 1:02d} · {_esc(segment_type)}</h2>
        <div class="narration"><b>台本段落</b><p>{_esc(segment.get("audio_text"))}</p></div>
        <div class="shots">{"".join(shots) or '<div class="muted">暂无镜头</div>'}</div>
      </section>
    """
        )

    mode = (
        "已读取 storyboard.json"
        if storyboard_shots
        else "未提供 storyboard.json，显示 script.json 中的原始镜头"
    )
    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>视频台本与分镜 · {_esc(date)}</title>
  <style>
    :root {{ color-scheme: light; --ink:#17202a; --muted:#68727d; --line:#dfe4e8; --blue:#2563eb; --paper:#f6f7f9; }}
    * {{ box-sizing:border-box; }} body {{ margin:0; background:var(--paper); color:var(--ink); font:15px/1.65 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif; }}
    main {{ width:min(1000px, calc(100% - 32px)); margin:32px auto 64px; }}
    header {{ background:#111827; color:white; padding:28px 32px; border-radius:16px; margin-bottom:20px; }}
    h1 {{ margin:0 0 8px; font-size:25px; }} h2 {{ margin:0 0 14px; font-size:18px; }} p {{ margin:6px 0; }}
    .meta {{ color:#cbd5e1; font-size:13px; }} .segment {{ background:white; border:1px solid var(--line); border-radius:14px; padding:22px; margin:16px 0; }}
    .narration {{ background:#f8fafc; border-left:4px solid var(--blue); padding:12px 16px; margin-bottom:16px; }}
    .shots {{ display:grid; gap:10px; }} .shot {{ border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
    .shot-head {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; padding:9px 12px; background:#f1f5f9; font-size:12px; }}
    .shot-no {{ font-weight:700; color:var(--blue); }} .time,.template,.type {{ color:var(--muted); }} .template {{ margin-left:auto; font-family:ui-monospace,monospace; }}
    .visual,.voice {{ padding:10px 14px; }} .visual {{ border-bottom:1px solid var(--line); }} .voice {{ color:#4b5563; font-size:14px; }}
    .story-image {{ margin-top:10px; padding:8px; border:1px solid #cbd5e1; border-radius:8px; background:#f8fafc; }} .story-image img {{ display:block; width:100%; max-height:220px; object-fit:contain; margin-top:6px; background:#e2e8f0; }}
    .voice b,.visual b,.narration b {{ color:var(--ink); margin-right:6px; }} .muted {{ color:var(--muted); }}
    .template-preview {{ min-height:180px; padding:22px; border-radius:8px; display:flex; flex-direction:column; justify-content:space-between; gap:14px; overflow:hidden; }}
    .template-preview strong {{ display:block; font-size:25px; line-height:1.22; letter-spacing:-.02em; }}
    .template-preview p {{ margin:0; color:#475569; line-height:1.55; }} .template-preview small {{ color:#64748b; }}
    .preview-kicker {{ color:#2563eb; font:700 11px/1.2 ui-monospace,SFMono-Regular,monospace; letter-spacing:.12em; text-transform:uppercase; }}
    .preview-cover {{ min-height:210px; color:#f8fafc; background:linear-gradient(135deg,#111827,#1e3a5f 60%,#0f766e); }}
    .preview-cover strong {{ font-size:34px; max-width:75%; }} .preview-cover small {{ color:#bfdbfe; }} .preview-cover-rule {{ width:72px; height:4px; background:#5eead4; }}
    .preview-headline {{ background:#eff6ff; border-left:7px solid #2563eb; }} .preview-headline strong {{ font-size:32px; max-width:82%; }}
    .preview-pill,.preview-tag {{ align-self:flex-start; border-radius:999px; padding:5px 10px; background:#dbeafe; color:#1d4ed8; font-size:12px; font-weight:700; }}
    .preview-event {{ display:grid; grid-template-columns:auto 1fr auto; align-items:center; gap:18px; background:#f8fafc; }} .preview-index {{ color:#0f766e; font:800 12px ui-monospace,monospace; letter-spacing:.12em; }}
    .preview-evidence {{ display:grid; grid-template-columns:1fr 1.2fr; gap:18px; background:#fff7ed; }} .evidence-frame {{ min-height:135px; border:1px solid #fdba74; background:#ffedd5; display:flex; flex-direction:column; justify-content:center; align-items:center; gap:8px; color:#9a3412; font:12px ui-monospace,monospace; }}
    .preview-discussion {{ background:#f5f3ff; border-left:7px solid #7c3aed; }} .preview-discussion blockquote {{ margin:0; font-size:24px; line-height:1.4; color:#312e81; }}
    .preview-dual {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; background:#f8fafc; }} .preview-dual > div {{ padding:16px; border-top:5px solid #2563eb; background:#eff6ff; }} .preview-dual > div+div {{ border-top-color:#0f766e; background:#ecfdf5; }} .preview-dual span {{ font:700 11px ui-monospace,monospace; color:#475569; }}
    .preview-number {{ align-items:flex-start; background:#111827; color:#f8fafc; }} .preview-number strong {{ color:#5eead4; font:800 58px/1 ui-monospace,monospace; }} .preview-number span {{ font-size:17px; }} .preview-number p {{ color:#cbd5e1; }}
    .preview-quick {{ display:grid; grid-template-columns:auto 1fr auto; align-items:center; gap:16px; background:#ecfeff; border-left:7px solid #0891b2; }} .quick-index {{ color:#0e7490; font:800 28px ui-monospace,monospace; }} .preview-quick strong {{ font-size:22px; }} .preview-quick small {{ color:#0e7490; font:12px ui-monospace,monospace; }}
    .preview-signals {{ background:#f0fdf4; border-top:6px solid #16a34a; }} .preview-signals ul {{ display:grid; grid-template-columns:repeat(3,1fr); gap:8px; padding:0; margin:0; list-style:none; }} .preview-signals li {{ padding:10px; background:#dcfce7; color:#166534; font-size:13px; }}
    .preview-closing {{ align-items:center; justify-content:center; min-height:150px; background:#0f172a; color:#e2e8f0; }} .preview-closing strong {{ color:#5eead4; }} .preview-fallback {{ background:#f8fafc; }}
    @media (max-width:700px) {{ .preview-evidence,.preview-dual {{ grid-template-columns:1fr; }} .preview-event,.preview-quick {{ grid-template-columns:auto 1fr; }} .preview-event .preview-tag,.preview-quick small {{ grid-column:2; }} .preview-signals ul {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body><main>
  <header><h1>{_esc(script.get("title") or "视频台本与分镜")}</h1><div class="meta">{_esc(date)} · {_esc(mode)}</div><p>{_esc(script.get("description"))}</p></header>
  {"".join(segment_html)}
</main></body></html>"""
    output = date_root(date) / "review" / "video_review.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_text, encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate an HTML video script/storyboard review"
    )
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    output = generate_html(args.date)
    print(output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
