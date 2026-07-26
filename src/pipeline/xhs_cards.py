"""Plan and render the Xiaohongshu 3:4 card package."""

from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path
from typing import Any

from PIL import Image

from src.core.models import ContentItem, ContentPackage
from src.pipeline.agent_io import (
    file_sha256,
    is_artifact_fresh,
    write_artifact_manifest,
)
from src.pipeline.paths import (
    media_images_dir,
    pipeline_path,
    publish_path,
    publish_xhs_cards_dir,
)
from src.utils.atomic_io import atomic_write_json, atomic_write_text

ROOT = Path(__file__).resolve().parents[2]
PROMPT_PATH = ROOT / "prompts" / "xhs_cards.md"
TEMPLATE_PATH = (
    ROOT / "src" / "providers" / "renderer" / "xhs_cards" / "template-swiss-card.html"
)
CARD_WIDTH = 1080
CARD_HEIGHT = 1440
CARD_ROLES = ("cover", "evidence", "breakdown", "debate", "quotes", "closing")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _clean(value: Any, limit: int = 0) -> str:
    text = re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()
    if limit and len(text) > limit:
        return text[:limit].rstrip("，。；;、 ")
    return text


def _string_list(value: Any, *, count: int, limit: int) -> list[str]:
    values = value if isinstance(value, list) else []
    result = [_clean(item, limit) for item in values]
    result = [item for item in result if item]
    return result[:count]


def _flatten_key_points(item: ContentItem) -> list[str]:
    result: list[str] = []
    for point in item.key_points or []:
        if isinstance(point, dict):
            text = (
                point.get("detail")
                or point.get("point")
                or point.get("text")
                or point.get("title")
            )
        else:
            text = point
        cleaned = _clean(text, 34)
        if cleaned:
            result.append(cleaned)
    return result


def _fill(values: list[str], fallbacks: list[str], count: int) -> list[str]:
    result: list[str] = []
    for value in [*values, *fallbacks]:
        cleaned = _clean(value, 34)
        if cleaned and cleaned not in result:
            result.append(cleaned)
        if len(result) == count:
            break
    while len(result) < count:
        result.append("更多细节仍需结合原始报道与社区讨论判断")
    return result


def _image_selection(date: str) -> dict[str, Any]:
    return _read_json(pipeline_path(date, "image_selection.json")).get("items") or {}


def _selected_image(date: str, item: ContentItem) -> dict[str, str]:
    selection = _image_selection(date).get(str(item.source_id)) or {}
    selected = selection.get("selected_image")
    candidate: dict[str, Any] = {}
    for entry in selection.get("candidates") or []:
        if isinstance(entry, dict) and entry.get("path") == selected:
            candidate = entry
            break
    raw_path = selected or item.screenshot_image or (item.article_images or [None])[0]
    if not raw_path:
        return {"path": "", "origin_url": ""}
    filename = Path(str(raw_path).replace("\\", "/")).name
    source = media_images_dir(date) / filename
    if not source.exists():
        return {"path": "", "origin_url": ""}
    return {
        "path": str(source).replace("\\", "/"),
        "origin_url": _clean(candidate.get("origin_url")),
    }


def _story_payload(date: str, item: ContentItem) -> dict[str, Any]:
    image = _selected_image(date, item)
    return {
        "source_id": str(item.source_id),
        "title": item.title,
        "title_cn": item.title_cn or item.title,
        "score": item.score,
        "comment_count": item.comment_count,
        "editorial_score": item.editorial_score,
        "category": item.category or "科技",
        "editor_angle": item.editor_angle or item.dek or "",
        "article_summary": _clean(item.article_summary, 500),
        "key_points": item.key_points or [],
        "why_it_matters": item.why_it_matters or "",
        "image_path": image["path"],
        "image_origin_url": image["origin_url"],
    }


def xhs_cards_plan_inputs(date: str) -> dict[str, Any]:
    """Semantic inputs used to determine whether the card plan is fresh."""
    return {
        "content_hash": file_sha256(pipeline_path(date, "content.json")),
        "judgement_hash": file_sha256(pipeline_path(date, "comment_judgement.json")),
        "image_selection_hash": file_sha256(
            pipeline_path(date, "image_selection.json")
        ),
        "prompt_hash": file_sha256(PROMPT_PATH),
        "date": date,
    }


def xhs_cards_render_inputs(date: str) -> dict[str, Any]:
    deck = _read_json(publish_path(date, "xhs_cards.json"))
    image_hashes: dict[str, str | None] = {}
    focus = deck.get("focus_story") or {}
    image_path = focus.get("image_path")
    if image_path:
        image_hashes[str(image_path)] = file_sha256(Path(str(image_path)))
    return {
        "deck_hash": file_sha256(publish_path(date, "xhs_cards.json")),
        "template_hash": file_sha256(TEMPLATE_PATH),
        "image_hashes": image_hashes,
        "date": date,
    }


def _fallback_focus(content: ContentPackage) -> ContentItem:
    if not content.items:
        raise ValueError("No content items available for Xiaohongshu cards")
    return max(
        content.items,
        key=lambda item: (
            float(item.editorial_score or 0),
            int(item.comment_count or 0),
            int(item.score or 0),
        ),
    )


def _normalize_deck(
    result: dict[str, Any],
    content: ContentPackage,
    judgement: dict[str, Any],
    date: str,
) -> dict[str, Any]:
    by_id = {str(item.source_id): item for item in content.items}
    focus = by_id.get(str(result.get("focus_story_id"))) or _fallback_focus(content)
    story_id = str(focus.source_id)
    story_judgement = (judgement.get("stories") or {}).get(story_id) or {}
    image = _selected_image(date, focus)
    key_points = _flatten_key_points(focus)
    base_fallbacks = [
        focus.editor_angle or focus.dek or "",
        focus.article_summary or "",
        focus.why_it_matters or "",
        *key_points,
    ]

    evidence = _fill(
        _string_list(result.get("evidence_points"), count=3, limit=34),
        base_fallbacks,
        3,
    )
    breakdown = _fill(
        _string_list(result.get("breakdown_points"), count=4, limit=34),
        [*key_points, *base_fallbacks],
        4,
    )
    takeaways = _fill(
        _string_list(result.get("takeaways"), count=4, limit=30),
        [focus.why_it_matters or "", *key_points, focus.editor_angle or ""],
        4,
    )

    candidates = [
        candidate
        for candidate in story_judgement.get("quote_candidates") or []
        if isinstance(candidate, dict) and candidate.get("claim")
    ]
    by_comment = {str(item.get("comment_id")): item for item in candidates}
    requested_ids = [str(value) for value in result.get("quote_comment_ids") or []]
    selected_quotes = [
        by_comment[value] for value in requested_ids if value in by_comment
    ]
    for candidate in sorted(
        candidates, key=lambda item: float(item.get("quote_score") or 0), reverse=True
    ):
        if candidate not in selected_quotes:
            selected_quotes.append(candidate)
        if len(selected_quotes) == 3:
            break

    distribution = story_judgement.get("stance_distribution") or {}
    debate_focus = _string_list(story_judgement.get("debate_focus"), count=3, limit=28)
    if not debate_focus:
        debate_focus = ["事实边界", "影响范围", "社区分歧"]

    hook_title = _clean(result.get("hook_title"), 14) or _clean(
        focus.title_cn or focus.title, 14
    )
    question = _clean(result.get("question"), 28) or "这件事会改变你的选择吗？"
    if not question.endswith(("？", "?")):
        question += "？"

    focus_payload = _story_payload(date, focus)
    cards = [
        {
            "id": "xhs-01",
            "role": "cover",
            "title": hook_title,
            "lead": _clean(result.get("hook_lead"), 40)
            or _clean(focus.editor_angle or focus.article_summary, 40),
        },
        {
            "id": "xhs-02",
            "role": "evidence",
            "title": _clean(result.get("evidence_title"), 18) or "先看现有证据",
            "points": evidence,
            "image_path": image["path"],
        },
        {
            "id": "xhs-03",
            "role": "breakdown",
            "title": _clean(result.get("breakdown_title"), 18) or "事情是怎么发生的",
            "points": breakdown,
        },
        {
            "id": "xhs-04",
            "role": "debate",
            "title": _clean(result.get("debate_title"), 18) or "HN 社区在争什么",
            "distribution": {
                str(key): float(value)
                for key, value in distribution.items()
                if isinstance(value, (int, float))
            },
            "points": debate_focus,
        },
        {
            "id": "xhs-05",
            "role": "quotes",
            "title": _clean(result.get("quotes_title"), 18) or "三条高赞观点",
            "quotes": [
                {
                    "comment_id": str(item.get("comment_id") or ""),
                    "stance": _clean(item.get("stance"), 8) or "观点",
                    "claim": _clean(item.get("claim"), 64),
                }
                for item in selected_quotes[:3]
            ],
        },
        {
            "id": "xhs-06",
            "role": "closing",
            "title": _clean(result.get("closing_title"), 18) or "最后记住这四点",
            "points": takeaways,
            "question": question,
        },
    ]
    return {
        "schema_version": 1,
        "date": date,
        "style": "swiss",
        "accent": "ikb",
        "focus_story_id": story_id,
        "focus_story": focus_payload,
        "cards": cards,
    }


def plan_xhs_cards(
    content: ContentPackage, date: str, llm_provider: Any, config: dict[str, Any]
) -> dict[str, Any]:
    """Choose one story and create the normalized six-page card contract."""
    output = publish_path(date, "xhs_cards.json")
    inputs = xhs_cards_plan_inputs(date)
    if is_artifact_fresh(output, inputs):
        return _read_json(output)

    judgement = _read_json(pipeline_path(date, "comment_judgement.json"))
    stories = [_story_payload(date, item) for item in content.items]
    result = llm_provider.complete_prompt(
        str(PROMPT_PATH),
        {
            "date": date,
            "stories_json": json.dumps(stories, ensure_ascii=False, indent=2),
            "quotes_json": json.dumps(judgement, ensure_ascii=False, indent=2),
        },
        label="xhs_cards",
        expect_json=True,
        max_tokens=8192,
        model=llm_provider.fast_model,
        temperature=llm_provider.fast_temperature,
    )
    if not isinstance(result, dict):
        raise ValueError("Xiaohongshu card planner returned a non-object payload")
    deck = _normalize_deck(result, content, judgement, date)
    atomic_write_json(output, deck)
    write_artifact_manifest(
        output,
        step="plan_xhs_cards",
        date=date,
        inputs=inputs,
        config=config,
        extra={
            "card_count": len(deck["cards"]),
            "focus_story_id": deck["focus_story_id"],
        },
    )
    return deck


def _escape(value: Any) -> str:
    return html.escape(_clean(value), quote=True)


def _title_html(value: Any, max_chars: int = 8) -> str:
    text = _clean(value)
    if len(text) <= max_chars:
        return _escape(text)
    cut = min(max_chars, len(text) - 1)
    punctuation = max(text.rfind(mark, 0, max_chars + 2) for mark in "，：、")
    if punctuation >= 3:
        cut = punctuation + 1
    return f"{_escape(text[:cut])}<br>{_escape(text[cut:])}"


def _rows(points: list[str], *, sub: str = "") -> str:
    return "".join(
        (
            '<div class="ledger-row">'
            f'<span class="ledger-num">{index:02d}</span>'
            '<div class="ledger-copy">'
            f'<p class="ledger-title">{_escape(point)}</p>'
            + (f'<p class="ledger-sub">{_escape(sub)}</p>' if sub else "")
            + "</div></div>"
        )
        for index, point in enumerate(points, 1)
    )


def _render_sections(deck: dict[str, Any], image_href: str) -> str:
    cards = {card["role"]: card for card in deck["cards"]}
    focus = deck["focus_story"]
    date = _escape(deck["date"])
    category = _escape(focus.get("category") or "科技")

    cover = cards["cover"]
    evidence = cards["evidence"]
    breakdown = cards["breakdown"]
    debate = cards["debate"]
    quotes = cards["quotes"]
    closing = cards["closing"]

    if image_href:
        evidence_visual = (
            '<figure class="evidence-image">'
            f'<img src="{_escape(image_href)}" alt="{_escape(focus.get("title_cn"))}" '
            'style="object-position:center 35%">'
            "</figure>"
        )
    else:
        evidence_visual = (
            '<div class="evidence-fallback">'
            f'<p class="h-md">{_escape(focus.get("title_cn"))}</p>'
            f'<p class="lead">{_escape(focus.get("editor_angle"))}</p>'
            "</div>"
        )

    distribution = debate.get("distribution") or {}
    stance_order = [key for key in ("支持", "质疑", "中立") if key in distribution]
    stance_order.extend(key for key in distribution if key not in stance_order)
    stats = "".join(
        (
            '<div class="stance-stat">'
            f'<p class="num-xl">{round(float(distribution[key]) * 100):d}%</p>'
            f'<p class="t-cat">{_escape(key)}</p>'
            "</div>"
        )
        for key in stance_order[:3]
    )
    if not stats:
        stats = '<p class="lead">社区观点存在明显分歧，具体立场见下方争议焦点。</p>'

    quote_blocks = "".join(
        (
            '<blockquote class="quote-row">'
            f'<p class="t-cat">{_escape(quote.get("stance"))} · HN COMMENT</p>'
            f'<p class="quote-text">“{_escape(quote.get("claim"))}”</p>'
            "</blockquote>"
        )
        for quote in quotes.get("quotes") or []
    )
    if not quote_blocks:
        quote_blocks = '<p class="lead">本期没有足够可靠的可引用评论。</p>'

    return f"""
    <section class="poster xhs cover-page" id="xhs-01">
      <div class="content stack">
        <div class="chrome-min"><span>HN TechPulse · {category}</span><span>{date}</span></div>
        <p class="t-cat">深度卡片 · 01 / 06</p>
        <h1 class="h-statement">{_title_html(cover.get("title"), 7)}</h1>
        <div class="cover-signal"><span>{_escape(focus.get("score") or 0)} POINTS</span><span>{_escape(focus.get("comment_count") or 0)} COMMENTS</span></div>
        <hr class="hr-accent">
        <p class="lead cover-lead">{_escape(cover.get("lead"))}</p>
        <div class="foot"><span>SWIPE TO READ</span><span>01 / 06</span></div>
      </div>
    </section>

    <section class="poster xhs" id="xhs-02">
      <div class="content stack">
        <div class="chrome-min"><span>Evidence · 证据</span><span>02 / 06</span></div>
        <h2 class="h-xl">{_title_html(evidence.get("title"), 9)}</h2>
        {evidence_visual}
        <div class="compact-list">{_rows(evidence.get("points") or [])}</div>
        <div class="foot"><span>{_escape(focus.get("source_id"))}</span><span>HN TechPulse</span></div>
      </div>
    </section>

    <section class="poster xhs" id="xhs-03">
      <div class="content stack">
        <div class="chrome-min"><span>Breakdown · 拆解</span><span>03 / 06</span></div>
        <h2 class="h-xl">{_title_html(breakdown.get("title"), 9)}</h2>
        <div class="tall-ledger">{_rows(breakdown.get("points") or [], sub="WHY IT MATTERS")}</div>
        <div class="foot"><span>ONE STORY · FOUR SIGNALS</span><span>03 / 06</span></div>
      </div>
    </section>

    <section class="poster xhs debate-page" id="xhs-04">
      <div class="content stack">
        <div class="chrome-min"><span>Debate · 社区</span><span>04 / 06</span></div>
        <h2 class="h-xl">{_title_html(debate.get("title"), 9)}</h2>
        <div class="stance-grid">{stats}</div>
        <div class="debate-focus">{_rows(debate.get("points") or [])}</div>
        <div class="foot"><span>STANCE DISTRIBUTION</span><span>04 / 06</span></div>
      </div>
    </section>

    <section class="poster xhs quotes-page" id="xhs-05">
      <div class="content stack">
        <div class="chrome-min"><span>Voices · 金句</span><span>05 / 06</span></div>
        <h2 class="h-xl">{_title_html(quotes.get("title"), 9)}</h2>
        <div class="quote-stack">{quote_blocks}</div>
        <div class="foot"><span>QUOTED FROM HN DISCUSSION</span><span>05 / 06</span></div>
      </div>
    </section>

    <section class="poster xhs closing-page" id="xhs-06">
      <div class="content stack">
        <div class="chrome-min"><span>Takeaway · 落点</span><span>06 / 06</span></div>
        <h2 class="h-xl">{_title_html(closing.get("title"), 9)}</h2>
        <div class="tall-ledger closing-ledger">{_rows(closing.get("points") or [])}</div>
        <div class="question-block"><p class="t-cat">THE QUESTION</p><p class="h-md">{_escape(closing.get("question"))}</p></div>
        <div class="foot"><span>HN TechPulse</span><span>END</span></div>
      </div>
    </section>
    """


def _copy_focus_asset(deck: dict[str, Any], output_dir: Path) -> tuple[str, list[str]]:
    source_value = (deck.get("focus_story") or {}).get("image_path")
    if not source_value:
        return "", []
    source = Path(str(source_value))
    if not source.exists() or not source.is_file():
        return "", []
    assets = output_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    target = assets / source.name
    shutil.copy2(source, target)
    origin = _clean((deck.get("focus_story") or {}).get("image_origin_url"))
    source_lines = [f"{target.name} ← {origin or str(source).replace(chr(92), '/')}"]
    atomic_write_text(assets / "SOURCES.md", "\n".join(source_lines) + "\n")
    return f"assets/{target.name}", source_lines


def _launch_chromium(playwright: Any) -> Any:
    errors: list[str] = []
    for kwargs in ({"channel": "chrome"}, {"channel": "msedge"}, {}):
        try:
            return playwright.chromium.launch(headless=True, **kwargs)
        except Exception as exc:  # pragma: no cover - depends on local browser install
            errors.append(str(exc).splitlines()[0])
    raise RuntimeError("No Chromium browser available: " + " | ".join(errors))


def _contact_sheet(card_paths: list[Path], target: Path) -> None:
    pad = 24
    cols = 3
    rows = 2
    sheet = Image.new(
        "RGB",
        (cols * CARD_WIDTH + (cols + 1) * pad, rows * CARD_HEIGHT + (rows + 1) * pad),
        "#1a1a1a",
    )
    for index, path in enumerate(card_paths):
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            row, col = divmod(index, cols)
            sheet.paste(
                rgb, (pad + col * (CARD_WIDTH + pad), pad + row * (CARD_HEIGHT + pad))
            )
    sheet.save(target)


def xhs_card_output_paths(date: str) -> list[Path]:
    output_dir = publish_xhs_cards_dir(date)
    return [
        output_dir / f"xhs-{index:02d}-{role}.png"
        for index, role in enumerate(CARD_ROLES, 1)
    ]


def xhs_card_set_is_fresh(date: str) -> bool:
    output_dir = publish_xhs_cards_dir(date)
    index = output_dir / "index.html"
    if not is_artifact_fresh(index, xhs_cards_render_inputs(date)):
        return False
    for path in xhs_card_output_paths(date):
        if not path.exists():
            return False
        try:
            with Image.open(path) as image:
                if image.size != (CARD_WIDTH, CARD_HEIGHT):
                    return False
        except OSError:
            return False
    return (output_dir / "_contact-sheet.png").exists()


def render_xhs_cards(date: str, config: dict[str, Any]) -> list[Path]:
    """Build index.html from the Swiss seed and export all six PNG cards."""
    deck_path = publish_path(date, "xhs_cards.json")
    deck = _read_json(deck_path)
    if not deck:
        raise FileNotFoundError(f"Xiaohongshu card plan not found: {deck_path}")
    if len(deck.get("cards") or []) != len(CARD_ROLES):
        raise ValueError("Xiaohongshu card plan must contain exactly six cards")
    if xhs_card_set_is_fresh(date):
        return xhs_card_output_paths(date)

    output_dir = publish_xhs_cards_dir(date)
    output_dir.mkdir(parents=True, exist_ok=True)
    image_href, _sources = _copy_focus_asset(deck, output_dir)
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    sections = _render_sections(deck, image_href)
    if "<!-- POSTERS_HERE -->" not in template:
        raise ValueError(
            f"Card template is missing POSTERS_HERE marker: {TEMPLATE_PATH}"
        )
    rendered_html = template.replace("<!-- POSTERS_HERE -->", sections)
    index_path = output_dir / "index.html"
    atomic_write_text(index_path, rendered_html)

    from playwright.sync_api import sync_playwright

    output_paths = xhs_card_output_paths(date)
    with sync_playwright() as playwright:
        browser = _launch_chromium(playwright)
        try:
            page = browser.new_page(viewport={"width": 1200, "height": 1600})
            page.goto(index_path.resolve().as_uri(), wait_until="load")
            page.evaluate("document.fonts.ready")
            for index, target in enumerate(output_paths, 1):
                locator = page.locator(f"#xhs-{index:02d}")
                if locator.count() != 1:
                    raise RuntimeError(f"Missing card node #xhs-{index:02d}")
                locator.screenshot(path=str(target), animations="disabled")
        finally:
            browser.close()

    for path in output_paths:
        with Image.open(path) as image:
            if image.size != (CARD_WIDTH, CARD_HEIGHT):
                raise RuntimeError(
                    f"Unexpected card dimensions for {path}: {image.size}"
                )
    _contact_sheet(output_paths, output_dir / "_contact-sheet.png")
    write_artifact_manifest(
        index_path,
        step="render_xhs_cards",
        date=date,
        inputs=xhs_cards_render_inputs(date),
        config=config,
        extra={
            "card_count": len(output_paths),
            "width": CARD_WIDTH,
            "height": CARD_HEIGHT,
        },
    )
    return output_paths
