"""Generate a self-contained HTML for reviewing stories and selecting images for video."""

from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from typing import Any

IMAGE_CARD_TYPES = {"event_card"}
STORY_CARD_TYPES = IMAGE_CARD_TYPES | {"atmosphere_card"}


def _path_to_data_url(path: str, data_dir: Path) -> str:
    if path.startswith(("http://", "https://")):
        return ""
    fp = Path(path)
    if not fp.is_absolute():
        fp = data_dir / fp
    fp = fp.resolve()
    if not fp.is_file():
        return ""
    mime = mimetypes.guess_type(fp.name)[0] or "image/jpeg"
    with open(fp, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


def _collect_images(enrichment_item: dict, data_dir: Path) -> list[dict]:
    images: list[dict] = []
    seen: set[str] = set()

    for c in enrichment_item.get("image_candidates") or []:
        p = c["path"] if isinstance(c, dict) else c
        src = c.get("source", "") if isinstance(c, dict) else ""
        if p in seen:
            continue
        seen.add(p)
        data_url = (
            p
            if p.startswith(("http://", "https://"))
            else _path_to_data_url(p, data_dir)
        )
        if data_url:
            images.append({"path": p, "source": src, "data_url": data_url})

    for p in enrichment_item.get("article_images") or []:
        if p in seen:
            continue
        seen.add(p)
        data_url = (
            p
            if p.startswith(("http://", "https://"))
            else _path_to_data_url(p, data_dir)
        )
        if data_url:
            images.append({"path": p, "source": "article", "data_url": data_url})

    sp = enrichment_item.get("screenshot_image")
    if sp and sp not in seen:
        data_url = _path_to_data_url(sp, data_dir)
        if data_url:
            images.append({"path": sp, "source": "screenshot", "data_url": data_url})

    return images


def _extract_stories(script: dict) -> dict[int, dict]:
    stories: dict[int, dict] = {}
    for seg in script.get("segments", []):
        for elem in seg.get("scene_elements", []):
            et = elem.get("element_type", "")
            if et not in STORY_CARD_TYPES:
                continue
            props = elem.get("props", {})

            si = props.get("story_index")
            if si is None:
                continue

            info = stories.setdefault(si, {"story_index": si, "card_type": et})

            for key in (
                "source_title",
                "title_cn",
                "editor_angle",
                "key_points",
                "why_it_matters",
                "score",
                "comment_count",
                "keywords",
                "category",
                "heat_level",
                "discussion_mode",
                "discussion_summary",
                "display_title",
                "reader_hook",
                "micro_takeaway",
            ):
                v = props.get(key)
                if v is not None:
                    info[key] = v

            st = props.get("subtitle_texts")
            if st:
                info["subtitle_texts"] = st

            for key in ("debate_focus", "stance_distribution", "quotes"):
                v = props.get(key)
                if v:
                    info[key] = v

    return stories


def _build_page_data(
    script: dict, content_items: list[dict], enrichment: dict, data_dir: Path
) -> list[dict]:
    stories = _extract_stories(script)
    eitems = enrichment.get("items", {})
    pages: list[dict] = []

    for idx, item in enumerate(content_items):
        sid = str(item.get("source_id", ""))
        if idx not in stories:
            continue
        s = stories[idx]
        ei = eitems.get(sid, {})
        images = _collect_images(ei, data_dir)
        sel = s.get("image_index", 0)
        if images and sel >= len(images):
            sel = 0
        pages.append(
            {
                **s,
                "source_id": sid,
                "url": item.get("url", ""),
                "images": images,
                "selected_image_index": sel,
            }
        )

    return pages


_CSS = """\
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Georgia","Songti SC","SimSun",serif;background:#f8f5f0;color:#2c2416;line-height:1.7;padding:0 0 90px}
.header{background:linear-gradient(135deg,#1a1a2e 0%,#2d1b3d 100%);color:#f8f5f0;padding:3rem 2rem 2rem;text-align:center;border-bottom:4px solid #c9a961}
.header h1{font-family:"Georgia",serif;font-size:2.2rem;font-weight:400;letter-spacing:.02em;margin-bottom:.5rem;font-style:italic}
.header .date{color:#c9a961;font-family:"Courier New",monospace;font-size:.9rem;letter-spacing:.1em;text-transform:uppercase}
.container{max-width:980px;margin:2rem auto;padding:0 1.5rem}
.story-card{background:#fffbf5;border-radius:2px;margin-bottom:2rem;overflow:hidden;box-shadow:0 2px 12px rgba(44,36,22,.08);border:1px solid #e8dcc4}
.story-header{padding:1.5rem 2rem;border-bottom:2px solid #e8dcc4;background:#fdf8f0}
.story-num{display:inline-block;background:#2c2416;color:#f8f5f0;font-family:"Courier New",monospace;font-size:.75rem;font-weight:700;padding:4px 12px;border-radius:2px;margin-bottom:.75rem;letter-spacing:.05em}
.story-title{font-family:"Georgia","Songti SC",serif;font-size:1.5rem;font-weight:700;line-height:1.35;margin-bottom:.35rem;color:#1a1410}
.story-title-en{font-family:"Georgia",serif;font-size:.9rem;color:#8b7355;font-style:italic;margin-bottom:.4rem}
.story-meta{display:flex;gap:1.2rem;font-family:"Courier New",monospace;font-size:.8rem;color:#8b7355;margin-top:.75rem;flex-wrap:wrap;align-items:center}
.story-body{padding:1.75rem 2rem}
.section-label{font-family:"Courier New",monospace;font-size:.7rem;text-transform:uppercase;letter-spacing:.12em;color:#8b7355;font-weight:700;margin-bottom:.5rem}
.info-block{margin-bottom:1.25rem}
.kp{margin-bottom:.6rem;padding-left:1rem;border-left:3px solid #c9a961}
.kp-label{font-family:"Courier New",monospace;font-size:.7rem;color:#c9a961;font-weight:700;text-transform:uppercase;letter-spacing:.08em}
.kp-text{font-size:.95rem;line-height:1.65;color:#3d3426}
.subs{font-size:.95rem;color:#2c2416;background:#f5ede0;padding:1rem 1.25rem;border-radius:2px;line-height:1.85;border-left:3px solid #c9a961}
.tag{display:inline-block;font-family:"Courier New",monospace;font-size:.7rem;padding:3px 10px;border-radius:2px;margin:3px 5px 3px 0;background:#e8dcc4;color:#5c4a32;letter-spacing:.03em}
.tag-heat{background:#d4a574;color:#fff}
.tag-cat{background:#a8c5d6;color:#2c3e50}
.debate{background:#faf6ef;padding:1.25rem;border-radius:2px;border:2px solid #e8dcc4;margin-top:1rem}
.stance-bars{display:flex;height:8px;border-radius:1px;overflow:hidden;margin:.75rem 0;box-shadow:inset 0 1px 2px rgba(0,0,0,.1)}
.stance-bar{height:100%}
.stance-pos{background:#6b8e4e}.stance-neu{background:#d4a574}.stance-neg{background:#b85c3c}
.stance-labels{display:flex;gap:1rem;font-family:"Courier New",monospace;font-size:.75rem;color:#5c4a32;margin-bottom:.6rem;font-weight:600}
.quote{padding:.75rem 0;border-bottom:1px solid #e8dcc4;font-size:.9rem;line-height:1.6;color:#3d3426}
.quote:last-child{border-bottom:none}
.quote-author{font-family:"Courier New",monospace;font-size:.7rem;color:#8b7355;margin-top:.3rem;display:block}
.image-section{padding:1.25rem 2rem;border-top:3px solid #c9a961;background:#fdf8f0}
.image-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:.75rem;margin-top:.5rem}
.image-thumb{aspect-ratio:4/3;border-radius:2px;overflow:hidden;cursor:pointer;border:3px solid transparent;transition:all .2s;background:#e8dcc4;position:relative}
.image-thumb:hover{border-color:#c9a961;transform:translateY(-2px);box-shadow:0 4px 8px rgba(44,36,22,.15)}
.image-thumb.selected{border-color:#2c2416;box-shadow:0 2px 8px rgba(44,36,22,.2)}
.image-thumb img{width:100%;height:100%;object-fit:cover;display:block}
.image-thumb .src{position:absolute;bottom:0;left:0;right:0;background:rgba(44,36,22,.85);color:#f8f5f0;font-family:"Courier New",monospace;font-size:.65rem;padding:4px 6px;text-align:center;letter-spacing:.05em}
.upload-btn{display:inline-flex;align-items:center;gap:.4rem;padding:.6rem 1rem;font-family:"Courier New",monospace;font-size:.8rem;background:#fdf8f0;border:2px dashed #c9a961;border-radius:2px;cursor:pointer;color:#8b7355;transition:all .2s;font-weight:600;letter-spacing:.05em}
.upload-btn:hover{background:#f5ede0;border-color:#8b7355;color:#5c4a32}
.no-image{display:flex;align-items:center;justify-content:center;aspect-ratio:4/3;border-radius:2px;background:#f5ede0;color:#8b7355;font-family:"Courier New",monospace;font-size:.75rem}
.export-bar{position:fixed;bottom:0;left:0;right:0;background:#2c2416;color:#f8f5f0;padding:1rem 2rem;display:flex;justify-content:space-between;align-items:center;z-index:100;box-shadow:0 -2px 12px rgba(44,36,22,.2);border-top:2px solid #c9a961}
.export-btn{background:#c9a961;color:#2c2416;border:none;padding:.65rem 1.75rem;border-radius:2px;font-family:"Courier New",monospace;font-size:.85rem;cursor:pointer;font-weight:700;letter-spacing:.08em;text-transform:uppercase;transition:all .2s}
.export-btn:hover{background:#d4b876;transform:translateY(-1px);box-shadow:0 3px 8px rgba(44,36,22,.3)}
.export-info{font-family:"Courier New",monospace;font-size:.85rem;color:#c9a961;letter-spacing:.05em}
"""

_JS = """\
let PD=window.__PAGE_DATA__;
let uploads={};

function selImg(si,idx){
  PD.forEach(s=>{if(s.story_index===si)s.selected_image_index=idx});
  document.querySelectorAll('.image-thumb[data-story="'+si+'"]').forEach(el=>{
    el.classList.toggle('selected',parseInt(el.dataset.index)===idx);
  });
  updBar();
}

function updBar(){
  let t=0,s=0;
  PD.forEach(st=>{if(st.images.length>0){t++;if(st.selected_image_index>=0)s++}});
  Object.keys(uploads).forEach(k=>{t++;s++});
  let el=document.getElementById('export-info');
  if(el)el.textContent='\\u5df2\\u9009\\u56fe: '+s+'/'+t;
}

function uploadImg(si,ev){
  let file=ev.target.files[0];if(!file)return;
  let r=new FileReader();
  r.onload=function(e){
    if(!uploads[si])uploads[si]=[];
    let idx=uploads[si].length;
    uploads[si].push({data:e.target.result,filename:file.name});
    let g=document.getElementById('img-grid-'+si);if(!g)return;
    let t=document.createElement('div');
    t.className='image-thumb';
    t.dataset.story=si;t.dataset.index='u'+idx;
    t.onclick=function(){selImg(si,'u'+idx)};
    t.innerHTML='<img src="'+e.target.result+'"><div class="src">upload</div>';
    g.insertBefore(t,g.lastElementChild);
    selImg(si,'u'+idx);
  };
  r.readAsDataURL(file);
  ev.target.value='';
}

function doExport(){
  let sel={},ni={};
  PD.forEach(s=>{
    if(typeof s.selected_image_index==='number')sel[s.story_index]=s.selected_image_index;
  });
  Object.keys(uploads).forEach(k=>{ni[k]=uploads[k]});
  let blob=new Blob([JSON.stringify({date:PD.length?PD[0].date:'',selections:sel,new_images:ni},null,2)],{type:'application/json'});
  let a=document.createElement('a');
  a.href=URL.createObjectURL(blob);
  a.download='image_selections.json';
  a.click();URL.revokeObjectURL(a.href);
}
"""


def _img_html(img: dict) -> str:
    src = img["data_url"]
    if src:
        return f'<img src="{src}" alt="">'
    if img["path"].startswith(("http://", "https://")):
        return f'<img src="{img["path"]}" alt="" onerror="this.parentElement.style.display=\'none\'">'
    return '<div class="no-image">N/A</div>'


def _story_html(story: dict) -> str:
    si = story["story_index"]
    ct = story.get("card_type", "")
    has_img = ct in IMAGE_CARD_TYPES

    parts = ['<div class="story-card"><div class="story-header">']
    parts.append(f'<div class="story-num">#{si + 1}</div>')
    title = (
        story.get("title_cn")
        or story.get("display_title")
        or story.get("source_title", "")
    )
    parts.append(f'<div class="story-title">{title}</div>')
    st = story.get("source_title", "")
    if st and st != title:
        parts.append(f'<div class="story-title-en">{st}</div>')

    meta = []
    score = story.get("score")
    if score:
        meta.append(f"{score} pts")
    cc = story.get("comment_count")
    if cc:
        meta.append(f"{cc} comments")
    hl = story.get("heat_level")
    if hl:
        meta.append(f'<span class="tag tag-heat">{hl}</span>')
    cat = story.get("category")
    if cat:
        meta.append(f'<span class="tag tag-cat">{cat}</span>')
    dm = story.get("discussion_mode")
    if dm:
        meta.append(dm)
    if meta:
        parts.append(
            f'<div class="story-meta">{" · ".join(str(m) for m in meta)}</div>'
        )
    parts.append("</div>")

    parts.append('<div class="story-body">')

    ea = story.get("editor_angle")
    if ea:
        parts.append(
            f'<div class="info-block"><div class="section-label">编辑角度</div><div>{ea}</div></div>'
        )

    rh = story.get("reader_hook")
    if rh:
        parts.append(
            f'<div class="info-block"><div class="section-label">阅读钩子</div><div>{rh}</div></div>'
        )

    mt = story.get("micro_takeaway")
    if mt:
        parts.append(
            f'<div class="info-block"><div class="section-label">核心要点</div><div>{mt}</div></div>'
        )

    kps = story.get("key_points")
    if kps:
        parts.append('<div class="info-block"><div class="section-label">关键点</div>')
        for kp in kps:
            label = kp.get("label", "")
            text = kp.get("text", "")
            parts.append(
                f'<div class="kp"><div class="kp-label">{label}</div><div class="kp-text">{text}</div></div>'
            )
        parts.append("</div>")

    wim = story.get("why_it_matters")
    if wim:
        parts.append(
            f'<div class="info-block"><div class="section-label">为什么重要</div><div>{wim}</div></div>'
        )

    ds = story.get("discussion_summary")
    if ds:
        parts.append(
            f'<div class="info-block"><div class="section-label">讨论概要</div><div>{ds}</div></div>'
        )

    subs = story.get("subtitle_texts")
    if subs:
        parts.append(
            f'<div class="info-block"><div class="section-label">旁白文字</div>'
            f'<div class="subs">{" ".join(subs)}</div></div>'
        )

    kws = story.get("keywords")
    if kws:
        kw_tags = "".join(f'<span class="tag">{k}</span>' for k in kws)
        parts.append(
            f'<div class="info-block"><div class="section-label">关键词</div>'
            f"<div>{kw_tags}</div></div>"
        )

    df = story.get("debate_focus")
    sd = story.get("stance_distribution")
    quotes = story.get("quotes")
    if df or sd or quotes:
        parts.append('<div class="debate">')
        parts.append('<div class="section-label">评论区</div>')
        if sd:
            pos = int(sd.get("支持", 0) * 100)
            neu = int(sd.get("中立", 0) * 100)
            neg = max(0, 100 - pos - neu)
            parts.append(
                f'<div class="stance-bars">'
                f'<div class="stance-bar stance-pos" style="width:{pos}%"></div>'
                f'<div class="stance-bar stance-neu" style="width:{neu}%"></div>'
                f'<div class="stance-bar stance-neg" style="width:{neg}%"></div>'
                f"</div>"
            )
            parts.append(
                f'<div class="stance-labels">'
                f"<span>支持 {pos}%</span><span>中立 {neu}%</span><span>质疑 {neg}%</span>"
                f"</div>"
            )
        if df:
            parts.append(
                f'<div style="margin-bottom:.5rem"><strong>争议焦点: </strong>'
                f"{', '.join(df)}</div>"
            )
        if quotes:
            for q in quotes:
                author = q.get("author", "?")
                text = q.get("display_text") or q.get("text", "")
                upvotes = q.get("upvotes") or 0
                parts.append(
                    f'<div class="quote">{text}<br>'
                    f'<span class="quote-author">{author} · {upvotes} upvotes</span></div>'
                )
        parts.append("</div>")

    parts.append("</div>")

    if has_img:
        sel = story.get("selected_image_index", 0)
        imgs = story.get("images", [])
        parts.append('<div class="image-section">')
        parts.append('<div class="section-label">配图选择</div>')
        parts.append(f'<div class="image-grid" id="img-grid-{si}">')
        for i, img in enumerate(imgs):
            cls = "image-thumb selected" if i == sel else "image-thumb"
            src = img.get("source", "")
            parts.append(
                f'<div class="{cls}" data-story="{si}" data-index="{i}" '
                f'onclick="selImg({si},{i})">'
                f"{_img_html(img)}"
                f'<div class="src">{src}</div></div>'
            )
        parts.append(
            f'<label class="upload-btn">+ 上传'
            f'<input type="file" accept="image/*" style="display:none" '
            f'onchange="uploadImg({si},event)"></label>'
        )
        parts.append("</div></div>")

    parts.append("</div>")
    return "".join(parts)


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>配图选择 — {date}</title>
<style>{css}</style>
</head>
<body>
<div class="header">
<h1>{title}</h1>
<div class="date">{date} · {story_count} stories</div>
</div>
<div class="container">
{story_cards}
</div>
<div class="export-bar">
<span class="export-info" id="export-info">已选图: 0/0</span>
<button class="export-btn" onclick="doExport()">导出选择 (JSON)</button>
</div>
<script>
window.__PAGE_DATA__={page_data_json};
{js}
updBar();
</script>
</body>
</html>"""


def generate_html(date: str) -> str:
    data_dir = Path(f"data/{date}")
    script_path = data_dir / "script.json"
    content_path = data_dir / "content.json"
    enrichment_path = data_dir / "enrichment.json"

    script = json.loads(script_path.read_text(encoding="utf-8"))
    content = json.loads(content_path.read_text(encoding="utf-8"))
    enrichment = (
        json.loads(enrichment_path.read_text(encoding="utf-8"))
        if enrichment_path.exists()
        else {}
    )

    content_items = content.get("items", [])
    page_data = _build_page_data(script, content_items, enrichment, data_dir)

    story_cards = []

    for story in page_data:
        story_cards.append(_story_html(story))

    page_json = json.dumps(page_data, ensure_ascii=False)
    title = script.get("title", "HN TechPulse")

    return _HTML_TEMPLATE.format(
        date=date,
        title=title,
        story_count=len(page_data),
        css=_CSS,
        story_cards="".join(story_cards),
        page_data_json=page_json,
        js=_JS,
    )


def generate(date: str) -> Path:
    data_dir = Path(f"data/{date}")
    html = generate_html(date)
    output = data_dir / "preview.html"
    output.write_text(html, encoding="utf-8")
    return output


def import_selections(date: str) -> dict[str, Any]:
    """Read image_selections.json and apply to script.json and enrichment.json."""
    data_dir = Path(f"data/{date}")
    sel_path = data_dir / "image_selections.json"
    if not sel_path.exists():
        return {"applied": 0}

    data = json.loads(sel_path.read_text(encoding="utf-8"))
    selections = data.get("selections", {})
    new_images = data.get("new_images", {})

    script_path = data_dir / "script.json"
    script = json.loads(script_path.read_text(encoding="utf-8"))
    applied = 0

    for seg in script.get("segments", []):
        for elem in seg.get("scene_elements", []):
            if elem.get("element_type") not in IMAGE_CARD_TYPES:
                continue
            props = elem.get("props", {})
            si = props.get("story_index")
            if si is not None and str(si) in selections:
                props["image_index"] = selections[str(si)]
                applied += 1

    if applied:
        script_path.write_text(
            json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if new_images:
        enrichment_path = data_dir / "enrichment.json"
        if enrichment_path.exists():
            enrichment = json.loads(enrichment_path.read_text(encoding="utf-8"))
        else:
            enrichment = {"items": {}}

        content = json.loads((data_dir / "content.json").read_text(encoding="utf-8"))
        items = content.get("items", [])
        img_dir = data_dir / "images"
        img_dir.mkdir(exist_ok=True)

        for si_str, imgs in new_images.items():
            si = int(si_str)
            if si >= len(items):
                continue
            sid = str(items[si].get("source_id", ""))
            ei = enrichment.setdefault("items", {}).setdefault(sid, {})
            candidates = ei.setdefault("image_candidates", [])

            for img_info in imgs:
                img_data = img_info.get("data", "")
                filename = img_info.get("filename", "upload.jpg")
                if "," in img_data:
                    img_data = img_data.split(",", 1)[1]
                raw = base64.b64decode(img_data)
                save_name = f"{sid}_upload_{len(candidates)}.jpg"
                (img_dir / save_name).write_bytes(raw)
                rel_path = f"images/{save_name}"
                candidates.append(
                    {"path": rel_path, "source": "upload", "label": filename}
                )

        enrichment_path.write_text(
            json.dumps(enrichment, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return {"applied": applied, "new_images": sum(len(v) for v in new_images.values())}
