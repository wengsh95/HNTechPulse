"""Human approval gate for the editorial video script."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from src.core.models import Script
from src.pipeline.agent_io import (
    file_sha256,
    is_artifact_fresh,
    utc_now,
    write_artifact_manifest,
)
from src.pipeline.paths import agent_path, date_root, pipeline_path
from src.pipeline.script.io import load_script, script_editorial_hash
from src.utils.atomic_io import atomic_write_json, atomic_write_text


def script_review_page_path(date: str) -> Path:
    return date_root(date) / "review" / "script_review.html"


def _review_page_inputs(date: str, script: Script) -> dict[str, Any]:
    return {
        "script_hash": script_editorial_hash(script),
        "automatic_review_hash": file_sha256(pipeline_path(date, "script_review.json")),
    }


def _esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _subtitle_rows(texts: list[Any]) -> str:
    rows = "".join(
        f"<li><span>{index + 1:02d}</span><p>{_esc(text)}</p></li>"
        for index, text in enumerate(texts)
        if str(text).strip()
    )
    return rows or '<li class="empty">没有逐句字幕</li>'


def _segment_sections(script: Script) -> str:
    sections: list[str] = []
    for segment_index, segment in enumerate(script.segments):
        subsegments = segment.meta.get("sub_segment_subtitle_texts") or []
        cards: list[str] = []

        if subsegments:
            for sub_index, texts in enumerate(subsegments):
                element = (
                    segment.scene_elements[sub_index]
                    if sub_index < len(segment.scene_elements)
                    else None
                )
                props = element.props if element else {}
                title = (
                    props.get("title_cn")
                    or props.get("editor_angle")
                    or props.get("source_title")
                    or f"子段 {sub_index + 1}"
                )
                role = (
                    "评论" if element and "comment" in element.element_type else "事实"
                )
                cards.append(
                    f"""
                    <article class="copy-card">
                      <div class="copy-head"><span>{_esc(role)}</span><b>{_esc(title)}</b></div>
                      <ol>{_subtitle_rows(list(texts or []))}</ol>
                    </article>
                    """
                )
        else:
            subtitle_texts = [
                text
                for element in segment.scene_elements
                for text in (element.props.get("subtitle_texts") or [])
            ]
            cards.append(
                f"""
                <article class="copy-card">
                  <div class="copy-head"><span>段落</span><b>{_esc(segment.segment_type)}</b></div>
                  <ol>{_subtitle_rows(subtitle_texts or [segment.audio_text])}</ol>
                </article>
                """
            )

        sections.append(
            f"""
            <section>
              <div class="section-head">
                <h2>{segment_index + 1:02d} · {_esc(segment.segment_type)}</h2>
                <small>{len(segment.audio_text)} 字</small>
              </div>
              <details><summary>查看连续口播</summary><p class="narration">{_esc(segment.audio_text)}</p></details>
              <div class="copy-grid">{"".join(cards)}</div>
            </section>
            """
        )
    return "".join(sections)


def generate_script_review_page(
    script: Script,
    date: str,
    *,
    config: dict[str, Any] | None = None,
) -> Path:
    """Write a read-only local page for the human script checkpoint."""

    automatic_review_path = pipeline_path(date, "script_review.json")
    automatic_review: dict[str, Any] = {}
    if automatic_review_path.exists():
        try:
            loaded = json.loads(automatic_review_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                automatic_review = loaded
        except (OSError, json.JSONDecodeError):
            pass

    assessment = (
        automatic_review.get("overall_assessment") or "自动审校未提供整体评价。"
    )
    revision_count = len(automatic_review.get("revisions") or [])
    script_hash = script_editorial_hash(script)
    approve_command = f"uv run python scripts/internal/agent/agent_run.py --date {date} --approve-script"
    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>文案人工审查 · {_esc(date)}</title>
  <style>
    :root {{ --ink:#172033; --muted:#667085; --line:#d9dee8; --blue:#2356d8; --paper:#f4f6f9; --green:#087a55; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; color:var(--ink); background:var(--paper); font:15px/1.65 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif; }}
    main {{ width:min(1040px,calc(100% - 32px)); margin:28px auto 64px; }}
    header,section {{ background:#fff; border:1px solid var(--line); border-radius:14px; }}
    header {{ padding:26px 30px; border-top:6px solid var(--blue); }}
    h1,h2,p {{ margin-top:0; }} h1 {{ margin-bottom:6px; font-size:27px; }} h2 {{ margin:0; font-size:19px; }}
    .meta {{ color:var(--muted); font:12px ui-monospace,SFMono-Regular,monospace; word-break:break-all; }}
    .assessment {{ margin:18px 0; padding:13px 16px; background:#eef4ff; border-left:4px solid var(--blue); }}
    .command {{ padding:12px 14px; color:#e8efff; background:#111827; border-radius:8px; font:13px/1.55 ui-monospace,SFMono-Regular,monospace; overflow-wrap:anywhere; }}
    section {{ margin-top:16px; padding:20px; }} .section-head,.copy-head {{ display:flex; align-items:center; gap:10px; justify-content:space-between; }}
    .section-head small {{ color:var(--muted); }} details {{ margin:12px 0; }} summary {{ color:var(--blue); cursor:pointer; }}
    .narration {{ margin:9px 0; padding:12px 14px; background:#f7f8fa; border-radius:8px; }}
    .copy-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }}
    .copy-card {{ border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
    .copy-head {{ justify-content:flex-start; padding:10px 13px; background:#f7f8fa; }} .copy-head span {{ color:var(--green); font-size:12px; font-weight:700; }}
    .copy-head b {{ overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
    ol {{ list-style:none; margin:0; padding:7px 13px 10px; }} li {{ display:grid; grid-template-columns:28px 1fr; gap:8px; border-bottom:1px solid #edf0f4; }}
    li:last-child {{ border-bottom:0; }} li span {{ color:#98a2b3; font:11px/1.9 ui-monospace,monospace; }} li p {{ margin:4px 0; }} .empty {{ color:var(--muted); padding:8px 0; }}
    @media (max-width:720px) {{ .copy-grid {{ grid-template-columns:1fr; }} header {{ padding:22px; }} }}
  </style>
</head>
<body><main>
  <header>
    <h1>文案人工审查</h1>
    <div class="meta">{_esc(date)} · script {_esc(script_hash[:12])} · 自动改写 {revision_count} 段</div>
    <div class="assessment"><b>自动审校：</b>{_esc(assessment)}</div>
    <p>请重点检查：信息是否讲透、HN 评论是否具体、头条与重点是否有层级、速览是否过密。任何文案修改都会使当前批准失效。</p>
    <p><b>确认当前版本后执行：</b></p>
    <div class="command">{_esc(approve_command)}</div>
  </header>
  {_segment_sections(script)}
</main></body></html>"""

    output = script_review_page_path(date)
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(output, page)
    write_artifact_manifest(
        output,
        step="human_review",
        date=date,
        inputs=_review_page_inputs(date, script),
        config=config,
    )
    return output


def load_script_approval(date: str) -> dict[str, Any] | None:
    path = agent_path(date, "script_approval.json")
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def script_approval_is_current(date: str, script: Script | None = None) -> bool:
    script = script or load_script(date)
    approval = load_script_approval(date)
    return bool(
        approval
        and approval.get("status") == "approved"
        and approval.get("date") == date
        and approval.get("script_hash") == script_editorial_hash(script)
    )


def approve_current_script(
    date: str,
    *,
    reviewer: str = "human",
    note: str = "",
) -> Path:
    """Approve exactly the script version represented by the current review page."""

    script = load_script(date)
    page = script_review_page_path(date)
    inputs = _review_page_inputs(date, script)
    if not is_artifact_fresh(page, inputs):
        raise ValueError(
            "Script review page is missing or stale; run the human_review step first"
        )

    output = agent_path(date, "script_approval.json")
    atomic_write_json(
        output,
        {
            "schema_version": 1,
            "status": "approved",
            "date": date,
            "approved_at": utc_now(),
            "reviewer": reviewer.strip() or "human",
            "note": note.strip(),
            "script_hash": script_editorial_hash(script),
            "review_page": str(page).replace("\\", "/"),
            "review_page_hash": file_sha256(page),
            "automatic_review_hash": inputs["automatic_review_hash"],
        },
    )
    return output
