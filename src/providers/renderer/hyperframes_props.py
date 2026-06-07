"""
HyperFrames props bridge: convert Script → per-scene host element data
and render the root `index.html` consumed by `npx hyperframes render`.

The element_type names (`cover_card` / `event_card` / `atmosphere_card` /
`closing_card`) are deliberately identical to the Remotion renderer so the
upstream `cli_props.json` schema stays single-source-of-truth.
"""

import html as html_lib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.models import Script
from src.providers.renderer.remotion_props import script_to_props
from src.utils.logger import setup_logger


# Map script element_type → sub-composition src + variable ids
_ELEMENT_TO_SUB_COMP = {
    "cover_card": ("cover.html", "cover-card"),
    "event_card": ("event.html", "event-card"),
    "atmosphere_card": ("atmosphere.html", "atmosphere-card"),
    "closing_card": ("closing.html", "closing-card"),
}


def _date_label(value: str) -> str:
    """Format YYYY-MM-DD as a compact Chinese card date label."""
    if not value:
        return ""
    parts = value.split("-")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        return f"{int(parts[0])}年{int(parts[1])}月{int(parts[2])}日"
    return value


def _controversy_label(score: float) -> str:
    if score >= 7:
        return "高度分歧"
    if score >= 3:
        return "存在分歧"
    if score > 0:
        return "分歧较低"
    return "讨论平稳"


def _json_attr(value: Any) -> str:
    """Encode a Python value as a JSON string safe for an HTML attribute.

    The attribute is wrapped in single quotes (`'...'`), so we MUST NOT
    escape the double quote characters inside the JSON. We DO escape the
    single quote (in case a value contains one), plus `&`, `<`, `>`.
    """
    s = json.dumps(value, ensure_ascii=False)
    s = s.replace("&", "&amp;")
    s = s.replace("<", "&lt;")
    s = s.replace(">", "&gt;")
    s = s.replace("'", "&#39;")
    return s


def _audio_url(seg: Dict[str, Any]) -> Optional[str]:
    """Extract the audio_path (relative URL) for a segment, if any."""
    return seg.get("audio_path")


def _collect_subtitle_cues(full_props: Dict[str, Any]) -> List[Dict[str, Any]]:
    cues: List[Dict[str, Any]] = []
    for seg in full_props.get("segments", []):
        seg_start = float(seg.get("start_time") or 0)
        for cue in seg.get("cues") or []:
            text = str(cue.get("text") or "").strip()
            if not text:
                continue
            start = seg_start + float(cue.get("start_time") or 0)
            end = seg_start + float(cue.get("end_time") or 0)
            if end <= start:
                continue
            cues.append({
                "text": text,
                "start": round(start, 3),
                "end": round(end, 3),
            })
    return cues


def _collect_story_markers(full_props: Dict[str, Any]) -> List[Dict[str, Any]]:
    markers: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for seg in full_props.get("segments", []):
        seg_start = float(seg.get("start_time") or 0)
        for elem in seg.get("scene_elements") or []:
            if elem.get("element_type") != "event_card":
                continue
            props = elem.get("props") or {}
            story_index = props.get("story_index", props.get("display_index", len(markers)))
            key = str(story_index)
            if key in seen:
                continue
            seen.add(key)
            title = (
                props.get("editor_angle")
                or props.get("title_cn")
                or props.get("story_title")
                or props.get("source_title")
                or ""
            )
            markers.append({
                "start": round(seg_start + float(elem.get("start_time") or 0), 3),
                "title": str(title),
                "category": str(props.get("category") or ""),
            })
    return sorted(markers, key=lambda item: float(item.get("start") or 0))


def _build_decorative_waveform(total_duration: float, sample_rate: int = 12) -> Dict[str, Any]:
    """Create deterministic pseudo-amplitude data for the root waveform layer."""
    import math

    count = max(1, int(max(0.0, total_duration) * sample_rate))
    values: List[float] = []
    for i in range(count):
        t = i / sample_rate
        amp = (
            0.34
            + 0.28 * abs(math.sin(t * 2.7))
            + 0.18 * abs(math.sin(t * 7.1 + 0.8))
            + 0.10 * abs(math.sin(t * 13.0 + 1.7))
        )
        values.append(round(max(0.08, min(1.0, amp)), 3))
    return {"sample_rate": sample_rate, "values": values}


def build_waveform_from_pcm(samples: List[float], sample_rate_hz: int, buckets_per_sec: int = 12) -> Dict[str, Any]:
    """Convert normalized PCM samples into RMS buckets for future real waveforms.

    This helper is intentionally dependency-free. The renderer currently uses
    `_build_decorative_waveform`; future audio analysis code can decode MP3/WAV
    into normalized samples and call this function.
    """
    if sample_rate_hz <= 0 or buckets_per_sec <= 0 or not samples:
        return {"sample_rate": buckets_per_sec, "values": []}
    bucket_size = max(1, int(sample_rate_hz / buckets_per_sec))
    values: List[float] = []
    for start in range(0, len(samples), bucket_size):
        bucket = samples[start:start + bucket_size]
        if not bucket:
            continue
        rms = (sum(float(x) * float(x) for x in bucket) / len(bucket)) ** 0.5
        values.append(round(max(0.0, min(1.0, rms)), 3))
    return {"sample_rate": buckets_per_sec, "values": values}


def script_to_hyperframes_scenes(
    script: Script,
    audio_dir: str,
    width: int,
    height: int,
    fps: int,
    bg_color: str,
    content=None,
    date: str = "",
    logger=None,
) -> Dict[str, Any]:
    """Convert Script dataclass into a normalized scene list for HyperFrames.

    Returns a dict with: `width`, `height`, `fps`, `bgColor`, `title`,
    `totalDuration`, and `scenes` (list of host-element specs).

    Each scene spec has:
      - comp_id        : "cover-card" | "event-card" | "atmosphere-card" | "closing-card"
      - comp_src       : "compositions/<file>.html"
      - start          : seconds (float)
      - duration       : seconds (float)
      - track_index    : int (all cards share 0; audio tracks start at 1)
      - variables      : dict of per-instance variable values
      - audio          : {src, start, duration, track_index} or None
    """
    if logger is None:
        logger = setup_logger("hyperframes_props")

    # Reuse the shared Remotion serializer to get fully expanded scene_elements.
    full = script_to_props(
        script, audio_dir, width, height, fps, bg_color,
        content=content, logger=logger,
    )

    scenes: List[Dict[str, Any]] = []
    audio_tracks: List[Dict[str, Any]] = []
    # Each visual card gets its own track_index so cards on the same canvas
    # don't overlap on the same track. Audio tracks start at track 1000 to
    # stay well above any visual card count.
    next_visual_track = 0
    next_audio_track = 1000
    default_date_label = _date_label(
        getattr(content, "date", "")
        or date
        or ""
    )

    for seg in full.get("segments", []):
        seg_start = float(seg.get("start_time") or 0)
        seg_duration = float(seg.get("duration") or 0)
        subtitle_audios = seg.get("subtitle_audios") or []

        # Per-segment audio track (narration). In story_scan mode
        # tts_processor builds both the concatenated segment audio and
        # per-subtitle slices (see tts_processor._finalize_story_scan);
        # HNTechPulseComposition only plays the slices there, so we mirror
        # that here — emitting both would play them on top of each other.
        if seg.get("audio_path") and not subtitle_audios:
            audio_tracks.append(
                {
                    "src": seg["audio_path"],
                    "start": round(seg_start, 3),
                    "duration": round(seg_duration, 3),
                    "track_index": next_audio_track,
                }
            )
            next_audio_track += 1

        # Per-subtitle audio (story_scan mode)
        for sa in subtitle_audios:
            audio_tracks.append(
                {
                    "src": sa["audio_path"],
                    "start": round(seg_start + float(sa.get("start_time") or 0), 3),
                    "duration": round(
                        float(sa.get("end_time") or 0) - float(sa.get("start_time") or 0),
                        3,
                    ),
                    "track_index": next_audio_track,
                }
            )
            next_audio_track += 1

        for elem in seg.get("scene_elements", []):
            etype = elem.get("element_type")
            if etype not in _ELEMENT_TO_SUB_COMP:
                logger.info(f"Skipping unknown element_type: {etype}")
                continue
            comp_src, comp_id = _ELEMENT_TO_SUB_COMP[etype]
            # IMPORTANT: scene_element start_time/end_time are relative to the
            # segment, not absolute. Add seg_start so filter_scenes_to_chunk
            # can correctly clip the scene to its chunk's time window.
            # Without this, opening/closing segments (which sit at non-zero
            # absolute times) collapse to start=0 and overlap with the cover
            # chunk, causing the cover chunk to render every scene at 0s.
            start = seg_start + float(elem.get("start_time") or 0)
            end = seg_start + float(elem.get("end_time") or 0)
            if end <= start:
                continue
            duration = end - start
            scenes.append(
                {
                    "comp_id": comp_id,
                    "comp_src": f"compositions/{comp_src}",
                    "start": round(start, 3),
                    "duration": round(duration, 3),
                    "track_index": next_visual_track,
                    "element_type": etype,
                    "variables": _extract_variables(
                        etype,
                        elem.get("props") or {},
                        date_label=default_date_label,
                    ),
                    "raw_props": elem.get("props") or {},
                }
            )
            next_visual_track += 1

    total_duration = float(full.get("totalDuration") or 0.0)
    return {
        "width": width,
        "height": height,
        "fps": fps,
        "bgColor": bg_color,
        "title": full.get("title", ""),
        "totalDuration": total_duration,
        "scenes": scenes,
        "audio_tracks": audio_tracks,
        "subtitle_cues": _collect_subtitle_cues(full),
        "story_markers": _collect_story_markers(full),
        "waveform": _build_decorative_waveform(total_duration),
        # Keep the full props too so we can dump cli_props.json for inspection.
        "cli_props": full,
    }


def _extract_variables(
    element_type: str,
    props: Dict[str, Any],
    date_label: str = "",
) -> Dict[str, Any]:
    """Map an expanded scene_element props dict → per-composition variables."""
    if element_type == "cover_card":
        lineup = props.get("lineup_entries") or props.get("highlight_entries") or []
        return {
            "headline": "HN 每日观察",
            "date_label": props.get("date_label") or date_label,
            "subtitle": "快讯 / 洞察 / 趋势",
            "lineup_json": json.dumps(lineup[:3], ensure_ascii=False),
        }
    if element_type == "event_card":
        # Title priority mirrors Remotion's extractEventProps:
        # editor_angle (Chinese editorial framing) → title_cn → story_title (English).
        story_title = props.get("story_title", "")
        title_zh = (
            props.get("editor_angle")
            or props.get("title_cn")
            or story_title
        )
        # sub_title is the English source title shown small under the
        # Chinese headline. Skip it when it would duplicate the headline.
        source_title = props.get("source_title") or story_title
        sub_title = source_title if source_title and source_title != title_zh else ""

        # "影响" section text lives in key_points (a list of {label, text}
        # produced by the script writer). Find the entry whose label is
        # "影响" / "影响分析"; fall back to empty so the section auto-hides.
        impact_text = ""
        for kp in props.get("key_points") or []:
            if not isinstance(kp, dict):
                continue
            if kp.get("label") in ("影响", "影响分析"):
                impact_text = kp.get("text", "") or ""
                break

        return {
            "title": title_zh,
            "sub_title": sub_title,
            "source_domain": props.get("source_domain", ""),
            "date_label": props.get("date_label") or date_label,
            "score": int(props.get("score") or 0),
            "comment_count": int(props.get("comment_count") or 0),
            "why_it_matters": props.get("why_it_matters", ""),
            "impact": impact_text,
            "tags_json": json.dumps(props.get("keywords") or [], ensure_ascii=False),
            "image_src": props.get("image_src", ""),
        }
    if element_type == "atmosphere_card":
        score = float(props.get("controversy_score") or 0)
        return {
            "title": props.get("title") or f"争议指数 {score:.1f} {_controversy_label(score)}",
            "subtitle": props.get("subtitle", ""),
            "date_label": props.get("date_label") or date_label,
            "stance_json": json.dumps(
                props.get("stance_distribution") or {"support": 0, "neutral": 0, "skeptical": 0},
                ensure_ascii=False,
            ),
            "debate_focus_json": json.dumps(props.get("debate_focus") or [], ensure_ascii=False),
            "quotes_json": json.dumps(props.get("quotes") or [], ensure_ascii=False),
        }
    if element_type == "closing_card":
        # summary_items: [{category, title, signal}, ...] → reshape for closing.html template
        raw_items = props.get("summary_items") or props.get("stories") or []
        stories = []
        for idx, item in enumerate(raw_items):
            if isinstance(item, str):
                stories.append({"title": item, "rank": idx + 1})
            elif isinstance(item, dict):
                stories.append({
                    "title": item.get("title") or item.get("text") or "",
                    "signal": item.get("signal") or item.get("category") or "",
                    "rank": item.get("rank") or idx + 1,
                })
        return {
            "title": "今日 HN 观察 / 回顾",
            "subtitle": props.get("subtitle", ""),
            "date_label": props.get("date_label") or date_label,
            "stories_json": json.dumps(stories, ensure_ascii=False),
        }
    return {}


def render_index_html(scenes_payload: Dict[str, Any], title: str) -> str:
    """Build the root composition HTML for HyperFrames.

    The composition is `hn-techpulse-root`, holding all card hosts on track 0
    and audio tracks at track 1..N.
    """
    width = scenes_payload["width"]
    height = scenes_payload["height"]
    bg = scenes_payload.get("bgColor", "#fefaf2")
    scenes = scenes_payload["scenes"]
    audio_tracks = scenes_payload["audio_tracks"]
    total_duration = float(scenes_payload.get("totalDuration") or 0)
    subtitle_cues = scenes_payload.get("subtitle_cues") or []
    story_markers = scenes_payload.get("story_markers") or []
    waveform = scenes_payload.get("waveform") or {"sample_rate": 12, "values": []}

    host_lines: List[str] = []
    for i, s in enumerate(scenes):
        host_lines.append(
            f'  <div\n'
            f'    id="host-{i}"\n'
            f'    data-composition-id="{html_lib.escape(s["comp_id"])}"\n'
            f'    data-composition-src="{html_lib.escape(s["comp_src"])}"\n'
            f'    data-start="{s["start"]}"\n'
            f'    data-duration="{s["duration"]}"\n'
            f'    data-track-index="{s["track_index"]}"\n'
            f"    data-variable-values='{_json_attr(s['variables'])}'\n"
            f'  ></div>'
        )

    audio_lines: List[str] = []
    for i, a in enumerate(audio_tracks):
        audio_lines.append(
            f'  <audio\n'
            f'    id="audio-{i}"\n'
            f'    data-start="{a["start"]}"\n'
            f'    data-duration="{a["duration"]}"\n'
            f'    data-track-index="{a["track_index"]}"\n'
            f'    src="{html_lib.escape(a["src"])}"\n'
            f'    data-volume="1"\n'
            f'  ></audio>'
        )

    title_safe = html_lib.escape(title or "HN TechPulse")
    subtitle_json = json.dumps(subtitle_cues, ensure_ascii=False)
    story_markers_json = json.dumps(story_markers, ensure_ascii=False)
    waveform_json = json.dumps(waveform, ensure_ascii=False)
    scene_runtime_json = json.dumps(
        [
            {
                "host_id": f"host-{i}",
                "comp_id": s.get("comp_id", ""),
                "variables": s.get("variables") or {},
            }
            for i, s in enumerate(scenes)
        ],
        ensure_ascii=False,
    )

    body = (
        "<!doctype html>\n"
        '<html lang="zh-CN">\n'
        "  <head>\n"
        '    <meta charset="UTF-8" />\n'
        f"    <title>{title_safe}</title>\n"
        "    <style>\n"
        "      html, body { margin: 0; padding: 0; background: "
        f"{bg};"
        " }\n"
        "      .hf-global-layer { position: absolute; inset: 0; pointer-events: none; z-index: 9999; font-family: 'Source Han Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif; }\n"
        "      .hf-subtitle { position: absolute; left: 50%; bottom: 54px; width: min(1320px, calc(100% - 180px)); transform: translateX(-50%); box-sizing: border-box; padding: 14px 28px 16px; border: 1px solid rgba(32,25,20,.10); border-radius: 12px; background: linear-gradient(90deg, rgba(255,250,242,.10), rgba(255,250,242,.92) 16%, rgba(255,250,242,.92) 84%, rgba(255,250,242,.10)); color: #201914; font-size: 36px; line-height: 1.28; text-align: center; opacity: 0; transition: opacity .16s ease, transform .16s ease; text-wrap: balance; }\n"
        "      .hf-subtitle.is-visible { opacity: 1; transform: translateX(-50%) translateY(-2px); }\n"
        "      .hf-progress { position: absolute; left: 69px; right: 69px; bottom: 28px; height: 6px; border-radius: 999px; background: rgba(32,25,20,.08); overflow: hidden; }\n"
        "      .hf-progress__bar { width: 0%; height: 100%; border-radius: inherit; background: linear-gradient(90deg, #ff6600, rgba(255,102,0,.34)); }\n"
        "      .hf-progress__marker { position: absolute; top: 50%; width: 9px; height: 9px; border-radius: 50%; background: #b64a12; transform: translate(-50%, -50%); opacity: .75; }\n"
        "      .hf-waveform { position: absolute; right: 76px; bottom: 102px; display: flex; align-items: center; gap: 5px; height: 34px; opacity: .58; }\n"
        "      .hf-waveform span { width: 4px; height: 12px; border-radius: 999px; background: #b64a12; transform-origin: center bottom; }\n"
        "    </style>\n"
        "  </head>\n"
        "  <body>\n"
        f'    <div data-composition-id="hn-techpulse-root" data-width="{width}" data-height="{height}" data-start="0" data-duration="{total_duration}">\n'
        + "\n".join(host_lines) + "\n"
        + "\n".join(audio_lines) + "\n"
        '      <div class="hf-global-layer">\n'
        '        <div class="hf-waveform" aria-hidden="true"></div>\n'
        '        <div class="hf-subtitle"></div>\n'
        '        <div class="hf-progress"><div class="hf-progress__bar"></div></div>\n'
        '      </div>\n'
        "    </div>\n"
        '    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>\n'
        "    <script>\n"
        "      window.__timelines = window.__timelines || {};\n"
        f"      const __hfSubtitleCues = {subtitle_json};\n"
        f"      const __hfStoryMarkers = {story_markers_json};\n"
        f"      const __hfWaveform = {waveform_json};\n"
        f"      const __hfSceneRuntime = {scene_runtime_json};\n"
        f"      const __hfTotalDuration = {total_duration};\n"
        "      const rootEl = document.querySelector('[data-composition-id=\"hn-techpulse-root\"]');\n"
        "      const subtitleEl = rootEl.querySelector('.hf-subtitle');\n"
        "      const progressBar = rootEl.querySelector('.hf-progress__bar');\n"
        "      const progressTrack = rootEl.querySelector('.hf-progress');\n"
        "      const waveEl = rootEl.querySelector('.hf-waveform');\n"
        "      const waveBars = Array.from({ length: 28 }, () => { const s = document.createElement('span'); waveEl.appendChild(s); return s; });\n"
        "      const parseJson = (value, fallback) => { try { return JSON.parse(value || ''); } catch (e) { return fallback; } };\n"
        "      const setText = (root, selector, value) => { const el = root.querySelector(selector); if (el) el.textContent = value || ''; };\n"
        "      const setHidden = (el, hidden) => { if (el) el.style.display = hidden ? 'none' : ''; };\n"
        "      const fillList = (root, selector, items, render) => { const el = root.querySelector(selector); if (!el) return; el.innerHTML = ''; (items || []).filter(Boolean).forEach((item, index) => { const child = render(item, index); if (child) el.appendChild(child); }); };\n"
        "      const div = (className, text) => { const el = document.createElement('div'); if (className) el.className = className; if (text !== undefined) el.textContent = text || ''; return el; };\n"
        "      function hydrateCover(host, vars) {\n"
        "        const root = host.querySelector('.hf-comp-cover'); if (!root) return false;\n"
        "        setText(root, '.brand-strip__date', vars.date_label || '');\n"
        "        setText(root, '.card-title', vars.headline || 'HN 每日观察');\n"
        "        setText(root, '.card-deck', vars.subtitle || '快讯 / 洞察 / 趋势');\n"
        "        const lineup = parseJson(vars.lineup_json, []);\n"
        "        fillList(root, '.opening__list', lineup, (item, index) => { const row = div('opening__item'); row.appendChild(div('opening__index', String(index + 1).padStart(2, '0'))); row.appendChild(div('opening__text', typeof item === 'string' ? item : (item.title || item.text || item.headline || ''))); return row; });\n"
        "        return true;\n"
        "      }\n"
        "      function hydrateEvent(host, vars) {\n"
        "        const root = host.querySelector('.hf-comp-event'); if (!root) return false;\n"
        "        setText(root, '.brand-strip__date', vars.date_label || '');\n"
        "        setText(root, '.card-title', vars.title || '');\n"
        "        setText(root, '.event-source-title', vars.sub_title || '');\n"
        "        setText(root, '.lead__src', vars.source_domain || '');\n"
        "        setText(root, '.metrics', `${Number(vars.score || 0)} points / ${Number(vars.comment_count || 0)} comments`);\n"
        "        const why = root.querySelector('.why-section'); const impact = root.querySelector('.impact-section');\n"
        "        setText(root, '.why-section .section-content', vars.why_it_matters || '');\n"
        "        setText(root, '.impact-section .section-content', vars.impact || '');\n"
        "        setHidden(why, !vars.why_it_matters); setHidden(impact, !vars.impact);\n"
        "        const tags = parseJson(vars.tags_json, []);\n"
        "        fillList(root, '.tags', tags, (tag) => { const el = document.createElement('span'); el.textContent = typeof tag === 'string' ? tag : String(tag || ''); return el; });\n"
        "        const imageBox = root.querySelector('.event-image');\n"
        "        if (imageBox && vars.image_src) { let img = imageBox.querySelector('img'); if (!img) { img = document.createElement('img'); imageBox.appendChild(img); } img.src = vars.image_src; img.alt = vars.title || ''; setHidden(imageBox, false); } else { setHidden(imageBox, true); }\n"
        "        return true;\n"
        "      }\n"
        "      function hydrateAtmosphere(host, vars) {\n"
        "        const root = host.querySelector('.hf-comp-atmosphere'); if (!root) return false;\n"
        "        setText(root, '.brand-strip__date', vars.date_label || '');\n"
        "        setText(root, '.card-title', vars.title || '');\n"
        "        setText(root, '.card-deck', vars.subtitle || '');\n"
        "        const stance = parseJson(vars.stance_json, {});\n"
        "        fillList(root, '.stance', Object.entries(stance), ([label, value]) => { const row = div('stance__row'); row.appendChild(div('stance__label', label)); row.appendChild(div('stance__value', String(value ?? 0))); return row; });\n"
        "        const focus = parseJson(vars.debate_focus_json, []);\n"
        "        fillList(root, '.debate-list', focus, (item) => div('debate-list__item', typeof item === 'string' ? item : (item.text || item.title || '')));\n"
        "        const quotes = parseJson(vars.quotes_json, []);\n"
        "        fillList(root, '.quote-list', quotes, (item) => div('quote-list__item', typeof item === 'string' ? item : (item.text || item.quote || '')));\n"
        "        return true;\n"
        "      }\n"
        "      function hydrateClosing(host, vars) {\n"
        "        const root = host.querySelector('.hf-comp-closing'); if (!root) return false;\n"
        "        setText(root, '.brand-strip__date', vars.date_label || '');\n"
        "        setText(root, '.card-title', vars.title || '今日 HN 观察 / 回顾');\n"
        "        setText(root, '.card-deck', vars.subtitle || '');\n"
        "        const stories = parseJson(vars.stories_json, []);\n"
        "        fillList(root, '.story-list', stories, (item, index) => {\n"
        "          if (typeof item === 'string') return div('story', item);\n"
        "          const row = div('story');\n"
        "          const numDiv = div('num-disc', String(item.rank || index + 1));\n"
        "          const textDiv = div('story__text');\n"
        "          const zhDiv = div('story__zh', item.title || '');\n"
        "          const enDiv = div('story__en', item.signal || '');\n"
        "          textDiv.appendChild(zhDiv); textDiv.appendChild(enDiv);\n"
        "          row.appendChild(numDiv); row.appendChild(textDiv);\n"
        "          return row;\n"
        "        });\n"
        "        return true;\n"
        "      }\n"
        "      function hydrateScenes(attempt = 0) {\n"
        "        let pending = 0;\n"
        "        __hfSceneRuntime.forEach((scene) => {\n"
        "          const host = document.getElementById(scene.host_id); if (!host) { pending += 1; return; }\n"
        "          const vars = scene.variables || {}; let ok = false;\n"
        "          if (scene.comp_id === 'cover-card') ok = hydrateCover(host, vars);\n"
        "          if (scene.comp_id === 'event-card') ok = hydrateEvent(host, vars);\n"
        "          if (scene.comp_id === 'atmosphere-card') ok = hydrateAtmosphere(host, vars);\n"
        "          if (scene.comp_id === 'closing-card') ok = hydrateClosing(host, vars);\n"
        "          if (!ok) pending += 1;\n"
        "        });\n"
        "        if (pending && attempt < 120) requestAnimationFrame(() => hydrateScenes(attempt + 1));\n"
        "      }\n"
        "      hydrateScenes();\n"
        "      __hfStoryMarkers.forEach((marker) => { if (!__hfTotalDuration) return; const m = document.createElement('span'); m.className = 'hf-progress__marker'; m.style.left = Math.max(0, Math.min(100, (Number(marker.start || 0) / __hfTotalDuration) * 100)) + '%'; progressTrack.appendChild(m); });\n"
        "      const rootTl = gsap.timeline({ paused: true });\n"
        "      const cueAt = (time) => __hfSubtitleCues.find((cue) => time >= Number(cue.start || 0) && time < Number(cue.end || 0));\n"
        "      rootTl.eventCallback('onUpdate', () => {\n"
        "        const time = rootTl.time();\n"
        "        const cue = cueAt(time);\n"
        "        if (cue) { subtitleEl.textContent = cue.text || ''; subtitleEl.classList.add('is-visible'); } else { subtitleEl.classList.remove('is-visible'); }\n"
        "        if (__hfTotalDuration > 0) progressBar.style.width = Math.max(0, Math.min(100, (time / __hfTotalDuration) * 100)) + '%';\n"
        "        const rate = Number(__hfWaveform.sample_rate || 12);\n"
        "        const values = __hfWaveform.values || [];\n"
        "        const base = Math.max(0, Math.floor(time * rate));\n"
        "        waveBars.forEach((bar, i) => { const amp = Number(values[(base + i) % Math.max(1, values.length)] || 0.2); bar.style.transform = 'scaleY(' + (0.35 + amp * 1.55).toFixed(3) + ')'; bar.style.opacity = String(0.34 + amp * 0.56); });\n"
        "      });\n"
        "      rootTl.to({}, { duration: __hfTotalDuration || 0.001 });\n"
        '      window.__timelines["hn-techpulse-root"] = rootTl;\n'
        "    </script>\n"
        "  </body>\n"
        "</html>\n"
    )
    return body


def write_scene_spec(scenes_payload: Dict[str, Any], output_path: Path) -> Path:
    """Dump the scene spec to disk for debugging/inspection."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(scenes_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def filter_scenes_to_chunk(
    scenes_payload: Dict[str, Any],
    chunk_start_sec: float,
    chunk_end_sec: float,
) -> Dict[str, Any]:
    """Filter a scene spec down to a single time-range chunk.

    Visual scenes and audio tracks whose ``[start, start+duration]`` does NOT
    overlap ``[chunk_start_sec, chunk_end_sec]`` are dropped. Surviving items
    are clamped so they start at 0 (relative to the chunk) and never extend
    past ``chunk_end_sec``. The output ``totalDuration`` is set to
    ``chunk_end_sec - chunk_start_sec`` so the rendered chunk is exactly the
    length of its time range. Wrapper metadata (``width``/``height``/``fps``/
    ``bgColor``/``title``) is preserved verbatim.

    The filtered payload is the cache key for the chunk — the same input
    always produces the same output dict, so a hash of its JSON is stable.
    """
    chunk_dur = max(0.0, chunk_end_sec - chunk_start_sec)

    new_scenes: List[Dict[str, Any]] = []
    for s in scenes_payload.get("scenes", []):
        s_start = float(s.get("start") or 0)
        s_dur = float(s.get("duration") or 0)
        s_end = s_start + s_dur
        if s_end <= chunk_start_sec or s_start >= chunk_end_sec:
            continue
        new_start = max(0.0, s_start - chunk_start_sec)
        new_end = min(s_end, chunk_end_sec) - chunk_start_sec
        new_dur = new_end - new_start
        if new_dur <= 0:
            continue
        new_scenes.append({**s, "start": round(new_start, 3), "duration": round(new_dur, 3)})

    new_audio: List[Dict[str, Any]] = []
    for a in scenes_payload.get("audio_tracks", []):
        a_start = float(a.get("start") or 0)
        a_dur = float(a.get("duration") or 0)
        a_end = a_start + a_dur
        if a_end <= chunk_start_sec or a_start >= chunk_end_sec:
            continue
        new_start = max(0.0, a_start - chunk_start_sec)
        new_end = min(a_end, chunk_end_sec) - chunk_start_sec
        new_dur = new_end - new_start
        if new_dur <= 0:
            continue
        new_audio.append({**a, "start": round(new_start, 3), "duration": round(new_dur, 3)})

    new_cues: List[Dict[str, Any]] = []
    for cue in scenes_payload.get("subtitle_cues", []):
        cue_start = float(cue.get("start") or 0)
        cue_end = float(cue.get("end") or 0)
        if cue_end <= chunk_start_sec or cue_start >= chunk_end_sec:
            continue
        new_start = max(0.0, cue_start - chunk_start_sec)
        new_end = min(cue_end, chunk_end_sec) - chunk_start_sec
        if new_end <= new_start:
            continue
        new_cues.append({
            **cue,
            "start": round(new_start, 3),
            "end": round(new_end, 3),
        })

    total_duration = float(scenes_payload.get("totalDuration") or 0)
    markers = scenes_payload.get("story_markers", [])
    new_markers: List[Dict[str, Any]] = []
    for marker in markers:
        marker_start = float(marker.get("start") or 0)
        if marker_start < chunk_start_sec or marker_start >= chunk_end_sec:
            continue
        new_markers.append({
            **marker,
            "start": round(marker_start - chunk_start_sec, 3),
        })

    waveform = scenes_payload.get("waveform") or {}
    sample_rate = int(waveform.get("sample_rate") or 12)
    values = waveform.get("values") or []
    if values and total_duration > 0:
        start_idx = max(0, int(chunk_start_sec * sample_rate))
        end_idx = min(len(values), max(start_idx + 1, int(chunk_end_sec * sample_rate)))
        new_waveform = {"sample_rate": sample_rate, "values": values[start_idx:end_idx]}
    else:
        new_waveform = waveform

    return {
        **{k: v for k, v in scenes_payload.items() if k not in (
            "scenes",
            "audio_tracks",
            "subtitle_cues",
            "story_markers",
            "waveform",
            "totalDuration",
        )},
        "scenes": new_scenes,
        "audio_tracks": new_audio,
        "subtitle_cues": new_cues,
        "story_markers": new_markers,
        "waveform": new_waveform,
        "totalDuration": round(chunk_dur, 3),
    }
