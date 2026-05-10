"""Streamlit editor for HN TechPulse video scripts.

Usage:
    uv run streamlit run src/editor/app.py --server.port 8501
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path (streamlit run doesn't add it automatically)
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

from src.editor.state import EditorState
from src.editor.components.story_editor import render_story_editor

st.set_page_config(page_title="HN TechPulse Editor", layout="wide")


# ── session init ───────────────────────────────────────────────

def init_state(date: str):
    if "editor" not in st.session_state or st.session_state.get("date") != date:
        s = EditorState(date)
        if s.load():
            st.session_state.editor = s
            st.session_state.date = date
            st.session_state.dirty = False
        else:
            st.session_state.editor = None
            st.session_state.date = date


# ── sidebar ────────────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.title("HN TechPulse Editor")

        # Date picker
        data_dir = Path("data")
        dates = sorted(
            [d.name for d in data_dir.iterdir() if d.is_dir() and (d / "script.json").exists()],
            reverse=True,
        )
        if not dates:
            st.warning("未找到已生成的脚本 (script.json)")
            st.stop()

        date = st.selectbox("日期", dates, key="date_select")
        init_state(date)

        state: EditorState = st.session_state.editor
        if state is None:
            st.error(f"加载失败: data/{date}/script.json")
            st.stop()

        st.divider()

        # Segment navigation
        segments = state.script.get("segments", [])
        seg_labels = {
            "opening": "开场",
            "dashboard": "热度榜",
            "story_scan": "新闻速览",
            "closing": "结尾",
        }
        seg_options = [s["segment_type"] for s in segments]
        selected = st.radio(
            "段落导航",
            seg_options,
            format_func=lambda x: seg_labels.get(x, x),
            key="seg_nav",
        )
        st.session_state.active_segment = selected

        st.divider()

        # Save
        c1, c2 = st.columns(2)
        if c1.button("💾 保存", use_container_width=True):
            state.save()
            state.save_enrichment()
            st.session_state.dirty = False
            st.toast("已保存 script.json")
        if c2.button("🔄 重新加载", use_container_width=True):
            state.load()
            st.session_state.dirty = False
            st.rerun()

        st.caption(f"数据目录: data/{date}/")
        st.caption(f"段落数: {len(segments)}")


# ── segment editors ────────────────────────────────────────────

def render_opening_editor(state: EditorState):
    seg = state.get_segment("opening")
    if not seg:
        st.info("无开场段落")
        return

    st.header("开场")
    new_text = st.text_area("旁白文字", value=seg.get("audio_text", ""), height=120, key="opening_text")
    if new_text != seg.get("audio_text", ""):
        seg["audio_text"] = new_text
        st.session_state.dirty = True

    emotion = st.selectbox(
        "情绪", ["warm", "energetic", "neutral", "calm"],
        index=["warm", "energetic", "neutral", "calm"].index(seg.get("emotion", "warm"))
        if seg.get("emotion") in ["warm", "energetic", "neutral", "calm"] else 0,
        key="opening_emotion"
    )
    if emotion != seg.get("emotion"):
        seg["emotion"] = emotion
        st.session_state.dirty = True

    # Title card props
    for elem in seg.get("scene_elements", []):
        if elem.get("element_type") == "title_card":
            props = elem.get("props", {})
            new_title = st.text_input("标题", value=props.get("title", ""), key="tc_title")
            if new_title != props.get("title"):
                props["title"] = new_title
                st.session_state.dirty = True
            new_sub = st.text_input("副标题", value=props.get("subtitle", ""), key="tc_sub")
            if new_sub != props.get("subtitle"):
                props["subtitle"] = new_sub
                st.session_state.dirty = True


def render_dashboard_editor(state: EditorState):
    seg = state.get_segment("dashboard")
    if not seg:
        st.info("无热度榜段落")
        return

    st.header("热度榜")
    new_text = st.text_area("旁白文字", value=seg.get("audio_text", ""), height=68, key="dash_text")
    if new_text != seg.get("audio_text", ""):
        seg["audio_text"] = new_text
        st.session_state.dirty = True

    # Dashboard entries
    for elem in seg.get("scene_elements", []):
        if elem.get("element_type") == "dashboard_card":
            entries = elem.get("props", {}).get("entries", [])
            if not entries:
                continue
            st.subheader("榜单条目")
            for entry in entries:
                rank = entry.get("rank", "?")
                orig = entry.get("original_title", "")
                with st.expander(f"#{rank} {orig[:60]}", expanded=False):
                    new_t = st.text_input(
                        "翻译标题", value=entry.get("title_translation", ""),
                        key=f"dash_t_{rank}"
                    )
                    if new_t != entry.get("title_translation"):
                        entry["title_translation"] = new_t
                        st.session_state.dirty = True


def render_story_scan_editor(state: EditorState):
    seg = state.get_segment("story_scan")
    if not seg:
        st.info("无新闻速览段落")
        return

    st.header("新闻速览")

    # Full audio text (one string for all stories)
    st.subheader("旁白文字（全文）")
    new_text = st.text_area(
        "audio_text", value=seg.get("audio_text", ""),
        height=200, key="scan_audio_text",
        label_visibility="collapsed"
    )
    if new_text != seg.get("audio_text", ""):
        seg["audio_text"] = new_text
        st.session_state.dirty = True

    st.divider()

    # Per-story editors
    stories = state.get_stories()
    if not stories:
        st.info("未找到 story 数据")
        return

    st.subheader(f"逐条编辑（共 {len(stories)} 条）")
    story_idx = st.selectbox(
        "选择新闻", range(len(stories)),
        format_func=lambda i: f"#{i + 1} {state.get_story_title(stories[i].get('source_id', ''))}",
        key="story_select"
    )

    if story_idx < len(stories):
        render_story_editor(state, stories[story_idx])


def render_closing_editor(state: EditorState):
    seg = state.get_segment("closing")
    if not seg:
        st.info("无结尾段落")
        return

    st.header("结尾")
    new_text = st.text_area("旁白文字", value=seg.get("audio_text", ""), height=120, key="closing_text")
    if new_text != seg.get("audio_text", ""):
        seg["audio_text"] = new_text
        st.session_state.dirty = True

    emotion = st.selectbox(
        "情绪", ["warm", "calm", "neutral", "upbeat"],
        index=["warm", "calm", "neutral", "upbeat"].index(seg.get("emotion", "warm"))
        if seg.get("emotion") in ["warm", "calm", "neutral", "upbeat"] else 0,
        key="closing_emotion"
    )
    if emotion != seg.get("emotion"):
        seg["emotion"] = emotion
        st.session_state.dirty = True


# ── main ───────────────────────────────────────────────────────

EDITORS = {
    "opening": render_opening_editor,
    "dashboard": render_dashboard_editor,
    "story_scan": render_story_scan_editor,
    "closing": render_closing_editor,
}

render_sidebar()

active = st.session_state.get("active_segment", "opening")
editor_fn = EDITORS.get(active)
if editor_fn:
    editor_fn(st.session_state.editor)
