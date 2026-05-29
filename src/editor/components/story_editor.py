"""Per-story editor: event and atmosphere cards."""

from pathlib import Path

import streamlit as st
from src.editor.state import EditorState


def render_story_editor(state: EditorState, story: dict):
    """Render editor for a single story (event + atmosphere cards)."""
    source_id = story.get("source_id", "")
    story_index = story.get("story_index", 0)
    event_card = story.get("event_card") or {}
    atmosphere_card = story.get("atmosphere_card") or {}

    title = state.get_story_title(source_id)
    st.subheader(
        f"#{story_index + 1} {title}" if title else f"Story #{story_index + 1}"
    )

    tab_event, tab_atmo = st.tabs(["事件", "氛围"])

    with tab_event:
        _render_event_tab(state, source_id, event_card, story_index)

    with tab_atmo:
        _render_atmosphere_tab(atmosphere_card, story_index)


STANCE_LABELS = ["支持", "质疑", "中立", "调侃", "担忧"]


def _render_event_tab(
    state: EditorState, source_id: str, event_card: dict, story_index: int
):
    """Edit event summary, keywords, and image."""
    props = event_card.get("props", {}) if event_card else {}

    # ── Image picker ──────────────────────────────────────────
    _render_image_picker(state, source_id, props, story_index)
    st.divider()

    # ── Event summary ─────────────────────────────────────────
    event_summary = st.text_area(
        "事件摘要",
        value=props.get("event_summary", ""),
        height=120,
        key=f"summary_{story_index}",
        help="LLM 生成的摘要，可修改",
    )
    if event_summary != props.get("event_summary", ""):
        props["event_summary"] = event_summary

    # ── Keywords ──────────────────────────────────────────────
    st.divider()
    st.caption("关键词标签（逗号分隔）")
    keywords = props.get("keywords", [])
    kw_text = st.text_input(
        "关键词",
        value=", ".join(keywords) if keywords else "",
        key=f"keywords_{story_index}",
        label_visibility="collapsed",
    )
    new_keywords = [k.strip() for k in kw_text.split(",") if k.strip()]
    if new_keywords != keywords:
        props["keywords"] = new_keywords


def _render_image_picker(
    state: EditorState, source_id: str, props: dict, story_index: int
):
    """Image grid + upload for event_card."""
    candidates = state.get_image_candidates(source_id)
    current_index = props.get("image_index", 0)

    st.caption("封面图片")

    if not candidates:
        st.info("暂无候选图片，请上传或运行 enrich 步骤")
    else:
        paths = [c["path"] for c in candidates]
        if current_index >= len(paths):
            current_index = 0

        # Thumbnail grid
        cols_per_row = 4
        for row_start in range(0, len(candidates), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, col in enumerate(cols):
                idx = row_start + j
                if idx >= len(candidates):
                    break
                c = candidates[idx]
                img_path = state.data_dir / state.date / c["path"]
                with col:
                    if img_path.exists():
                        st.image(str(img_path), use_container_width=True)
                    else:
                        st.caption("[缺失]")
                    st.caption(f"{c.get('source', '')} · #{idx}")
                    if idx == current_index:
                        st.success("✓ 当前")
                    elif st.button("选中", key=f"selimg_{story_index}_{idx}"):
                        props["image_index"] = idx
                        st.rerun()

    # Upload
    st.divider()
    upload_key = f"upload_{story_index}"
    uploaded = st.file_uploader(
        "上传新图片", type=["png", "jpg", "jpeg", "webp"], key=upload_key
    )
    if uploaded is not None:
        process_key = f"_processed_{upload_key}"
        if st.session_state.get(process_key) != uploaded.name:
            st.session_state[process_key] = uploaded.name
            ext = (
                uploaded.name.split(".")[-1].lower() if "." in uploaded.name else "jpg"
            )
            if ext not in {"png", "jpg", "jpeg", "webp"}:
                ext = "jpg"
            import tempfile

            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
                    tmp.write(uploaded.read())
                    tmp_path = tmp.name
                state.add_image(source_id, tmp_path)
                state.save_enrichment()
                # Auto-select the new image
                new_index = len(state.get_image_candidates(source_id)) - 1
                props["image_index"] = new_index
                st.rerun()
            finally:
                if tmp_path:
                    Path(tmp_path).unlink(missing_ok=True)


def _render_atmosphere_tab(atmosphere_card: dict, story_index: int):
    """Edit stance distribution and view quotes."""
    props = atmosphere_card.get("props", {}) if atmosphere_card else {}
    stance_dist: dict = props.get("stance_distribution", {})

    if not stance_dist:
        st.info("该 story 没有立场分布数据")
    else:
        new_stance = {}
        for label in STANCE_LABELS:
            val = stance_dist.get(label, 0.0)
            new_val = st.slider(
                label,
                min_value=0.0,
                max_value=1.0,
                value=float(val),
                step=0.05,
                key=f"stance_{story_index}_{label}",
            )
            new_stance[label] = round(new_val, 2)

        if new_stance != stance_dist:
            props["stance_distribution"] = new_stance

    # Quotes preview
    quotes: list = props.get("quotes", [])
    if quotes:
        st.divider()
        st.caption("精选观点（渲染时自动注入）")
        for qi, q in enumerate(quotes):
            with st.expander(
                f"{q.get('stance', '?')} — {q.get('text', '')[:60]}", expanded=(qi == 0)
            ):
                st.caption(f"立场: {q.get('stance', '?')}")
                st.caption(f"质量分: {q.get('quality_score', '?')}")
                st.text_area(
                    "原文",
                    value=q.get("text", ""),
                    height=68,
                    key=f"qtext_{story_index}_{qi}",
                    disabled=True,
                )
                st.text_area(
                    "中文翻译",
                    value=q.get("text_cn", ""),
                    height=68,
                    key=f"qtextcn_{story_index}_{qi}",
                    disabled=True,
                )
