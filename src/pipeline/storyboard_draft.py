"""Create an agent-authored first-pass storyboard from a generated Script."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.models import SceneElement, Script
from src.pipeline.agent_io import file_sha256, write_artifact_manifest
from src.pipeline.script.io import script_editorial_hash
from src.pipeline.storyboard import (
    PROTECTED_PROPS,
    STORYBOARD_SCHEMA_VERSION,
    TEMPLATE_ID_TO_ELEMENT_TYPE,
    TEMPLATE_REQUIRED_PROPS,
    VALID_ELEMENT_TYPES,
    _validate_required_props,
    _validate_storyboard,
    load_storyboard,
    storyboard_path,
)
from src.utils.atomic_io import atomic_write_json


STORYBOARD_DRAFT_VERSION = 2
STORYBOARD_PROMPT_PATH = Path("prompts/storyboard_draft.md")
ELEMENT_TYPE_TO_TEMPLATE_ID = {
    element_type: template_id
    for template_id, element_type in TEMPLATE_ID_TO_ELEMENT_TYPE.items()
}
VALID_TEMPLATE_IDS = frozenset(TEMPLATE_ID_TO_ELEMENT_TYPE.keys())


@dataclass(frozen=True)
class StoryboardDraft:
    path: Path
    created: bool
    shot_count: int


def draft_storyboard(
    script: Script,
    date: str,
    *,
    llm_provider=None,
    overwrite: bool = False,
    config: dict[str, Any] | None = None,
    logger=None,
) -> StoryboardDraft:
    """Create a storyboard once; never overwrite an existing editorial file by default."""

    path = storyboard_path(date)
    if path.exists() and not overwrite:
        existing = load_storyboard(date)
        manifest_path = path.with_suffix(path.suffix + ".manifest.json")
        manifest = None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = None
        recorded_hash = (
            ((manifest or {}).get("inputs") or {}).get("script_editorial_hash")
            if isinstance(manifest, dict)
            else None
        )
        recorded_prompt_hash = (
            ((manifest or {}).get("inputs") or {}).get("prompt_hash")
            if isinstance(manifest, dict)
            else None
        )
        current_prompt_hash = file_sha256(STORYBOARD_PROMPT_PATH)
        prompt_changed = (
            isinstance(manifest, dict)
            and manifest.get("inputs", {}).get("mode") == "agent"
            and recorded_prompt_hash
            and recorded_prompt_hash != current_prompt_hash
        )
        if (
            recorded_hash and recorded_hash != script_editorial_hash(script)
        ) or prompt_changed:
            if logger:
                logger.info(
                    "  storyboard.json is stale for the current script or prompt; regenerating"
                )
        else:
            shot_count = len(existing.get("shots", [])) if existing else 0
            if logger:
                logger.info(
                    "  storyboard.json already exists; preserving editorial choices (%d shots)",
                    shot_count,
                )
            return StoryboardDraft(path=path, created=False, shot_count=shot_count)

    if llm_provider is not None:
        payload = _build_agent_storyboard(llm_provider, script, date)
    else:
        # Kept as a local, deterministic fallback for unit tests and offline
        # tooling.  The managed video pipeline always passes its LLM provider.
        payload = build_storyboard(script, date)
    atomic_write_json(path, payload)
    write_artifact_manifest(
        path,
        step="draft_storyboard",
        date=date,
        inputs={
            "script_editorial_hash": script_editorial_hash(script),
            "generator_version": STORYBOARD_DRAFT_VERSION,
            "prompt_hash": file_sha256(STORYBOARD_PROMPT_PATH)
            if llm_provider is not None
            else "",
            "mode": "agent" if llm_provider is not None else "heuristic",
        },
        config=config,
    )
    result = StoryboardDraft(path=path, created=True, shot_count=len(payload["shots"]))
    if logger:
        action = "regenerated" if overwrite else "generated"
        logger.info("  Storyboard %s: %d shots → %s", action, result.shot_count, path)
    return result


def _build_agent_storyboard(llm_provider, script: Script, date: str) -> dict[str, Any]:
    context = {
        "script_json": json.dumps(
            _script_context(script), ensure_ascii=False, indent=2
        ),
        "template_catalog_json": json.dumps(
            _template_catalog(), ensure_ascii=False, indent=2
        ),
        "date": date,
    }
    result = llm_provider.complete_prompt(
        STORYBOARD_PROMPT_PATH.as_posix(),
        context,
        label="draft_storyboard",
        expect_json=True,
        max_tokens=12000,
        model=llm_provider.fast_model,
        temperature=llm_provider.fast_temperature,
    )
    if isinstance(result, dict) and isinstance(result.get("storyboard"), dict):
        result = result["storyboard"]
    return _normalize_agent_storyboard(result, script, date)


def _script_context(script: Script) -> dict[str, Any]:
    segments = []
    renderable_targets = []
    for segment_index, segment in enumerate(script.segments):
        elements = []
        for element_index, element in enumerate(segment.scene_elements):
            props = element.props or {}
            elements.append(
                {
                    "element_index": element_index,
                    "element_type": element.element_type,
                    "props": {
                        key: props[key]
                        for key in (
                            "story_index",
                            "display_index",
                            "story_count",
                            "headline",
                            "title",
                            "title_cn",
                            "source_title",
                            "editor_angle",
                            "category",
                            "why_it_matters",
                            "dek",
                            "key_points",
                            "discussion_summary",
                            "debate_focus",
                            "stance_distribution",
                            "quotes",
                            "image_src",
                            "story_image",
                            "section_label",
                            "story_role",
                            "image_target",
                            "quick_story_id",
                            "is_audio_marker",
                            "subtitle_texts",
                        )
                        if key in props
                    },
                }
            )
            if not props.get("is_audio_marker"):
                renderable_targets.append(
                    {"segment_index": segment_index, "element_index": element_index}
                )
        segments.append(
            {
                "segment_index": segment_index,
                "segment_type": segment.segment_type,
                "audio_text": segment.audio_text,
                "scene_elements": elements,
            }
        )
    return {
        "title": script.title,
        "description": script.description,
        "segments": segments,
        "renderable_targets": renderable_targets,
    }


def _template_catalog() -> list[dict[str, Any]]:
    return [
        {
            "template_id": template_id,
            "element_type": element_type,
            "required_props": list(TEMPLATE_REQUIRED_PROPS.get(element_type, ())),
        }
        for template_id, element_type in TEMPLATE_ID_TO_ELEMENT_TYPE.items()
    ]


def _normalize_agent_storyboard(
    result: Any, script: Script, date: str
) -> dict[str, Any]:
    if not isinstance(result, dict) or not isinstance(result.get("shots"), list):
        raise ValueError("Storyboard agent output must contain a shots list")

    eligible: dict[tuple[int, int], SceneElement] = {}
    for segment_index, segment in enumerate(script.segments):
        for element_index, element in enumerate(segment.scene_elements):
            if not (element.props or {}).get("is_audio_marker"):
                eligible[(segment_index, element_index)] = element

    normalized: list[dict[str, Any]] = []
    seen_targets: set[tuple[int, int]] = set()
    seen_shot_ids: set[str] = set()
    for index, raw_shot in enumerate(result["shots"], start=1):
        if not isinstance(raw_shot, dict):
            raise ValueError(f"Storyboard agent shot #{index} must be an object")
        raw_segment_index = raw_shot.get("segment_index")
        raw_element_index = raw_shot.get("element_index")
        if not (
            isinstance(raw_segment_index, int)
            and not isinstance(raw_segment_index, bool)
            and isinstance(raw_element_index, int)
            and not isinstance(raw_element_index, bool)
        ):
            raise ValueError(
                f"Storyboard agent shot #{index} requires integer segment_index "
                "and element_index"
            )
        segment_index = raw_segment_index
        element_index = raw_element_index
        target = (segment_index, element_index)
        if target not in eligible:
            raise ValueError(
                f"Storyboard agent shot #{index} targets a missing or non-renderable "
                f"element: {target}"
            )
        if target in seen_targets:
            raise ValueError(f"Storyboard agent duplicated target: {target}")
        seen_targets.add(target)

        shot_id = str(
            raw_shot.get("shot_id")
            or f"S{segment_index + 1:02d}-{element_index + 1:02d}"
        )
        if shot_id in seen_shot_ids:
            raise ValueError(f"Storyboard agent duplicated shot_id: {shot_id}")
        seen_shot_ids.add(shot_id)

        template_id = _normalize_template_id(raw_shot)
        template_id = _preferred_template_id(eligible[target], template_id)
        raw_props = raw_shot.get("props") or {}
        if not isinstance(raw_props, dict):
            raise ValueError(f"Storyboard agent shot {shot_id}.props must be an object")
        props = {**_preferred_visual_props(eligible[target], template_id), **raw_props}
        protected = sorted(PROTECTED_PROPS.intersection(props))
        if protected:
            raise ValueError(
                f"Storyboard agent shot {shot_id} attempted to edit derived props: "
                f"{protected}"
            )
        element_type = TEMPLATE_ID_TO_ELEMENT_TYPE[template_id]
        merged_props = dict(eligible[target].props or {})
        merged_props.update(props)
        _validate_required_props(element_type, merged_props, shot_id)
        normalized.append(
            {
                "shot_id": shot_id,
                "segment_index": segment_index,
                "element_index": element_index,
                "template_id": template_id,
                "props": props,
            }
        )

    missing = sorted(set(eligible) - seen_targets)
    if missing:
        raise ValueError(f"Storyboard agent omitted scene elements: {missing}")

    payload = {
        "schema_version": STORYBOARD_SCHEMA_VERSION,
        "date": date,
        "generated_by": {
            "kind": "agent",
            "version": STORYBOARD_DRAFT_VERSION,
        },
        "shots": normalized,
    }
    _validate_storyboard(payload, storyboard_path(date))
    return payload


def _normalize_template_id(raw_shot: dict[str, Any]) -> str:
    template_id = raw_shot.get("template_id") or raw_shot.get("element_type")
    if template_id in TEMPLATE_ID_TO_ELEMENT_TYPE:
        return template_id
    if template_id in VALID_ELEMENT_TYPES:
        return ELEMENT_TYPE_TO_TEMPLATE_ID[template_id]
    raise ValueError(f"Storyboard agent used unknown template_id: {template_id!r}")


def _preferred_template_id(element: SceneElement, fallback: str) -> str:
    """Keep the agent's copy choices while enforcing the editorial grammar."""

    props = element.props or {}
    template_id = props.get("template_id")
    if template_id and template_id in VALID_TEMPLATE_IDS:
        return template_id
    role = props.get("story_role")
    if (
        role == "quick"
        or props.get("quick_story_id")
        or element.element_type == "quick_card"
    ):
        return "quick_news_v1"
    if role == "evidence":
        return (
            "headline_v1"
            if props.get("section_label") == "头条"
            else "source_evidence_v1"
        )
    if role == "comment":
        quotes = [
            item
            for item in (props.get("quotes") or props.get("quote_candidates") or [])
            if isinstance(item, dict)
        ]
        return "comment_dual_v1" if len(quotes) >= 2 else "comment_single_v1"
    if element.element_type == "cover_card":
        return "cover_v1"
    if element.element_type == "closing_card":
        return "closing_v1"
    return fallback


def _preferred_visual_props(element: SceneElement, template_id: str) -> dict[str, Any]:
    props = element.props or {}
    label = str(props.get("section_label") or "").strip()
    title = _first_text(props, "editor_angle", "title_cn", "source_title", "title")
    image = _first_text(props, "image_src", "story_image")
    source_url = _first_text(props, "source_url")
    result: dict[str, Any]
    if template_id == "headline_v1":
        result = {"title": title or "今日头条", "eyebrow": label or "头条"}
        subtitle = _first_text(props, "why_it_matters", "dek")
        if subtitle:
            result["subtitle"] = subtitle
        source_label = _first_text(props, "category")
        if source_label:
            result["source_label"] = source_label
        if image:
            result["image_src"] = image
        return result
    if template_id == "source_evidence_v1":
        result = {
            "title": title or "来源与证据",
            "eyebrow": label or "重点",
        }
        caption = _first_text(props, "why_it_matters", "dek", "discussion_summary")
        if caption:
            result["caption"] = caption
        if source_url:
            result["source_url"] = source_url
        if image:
            result["image_url"] = image
        highlights = []
        for point in props.get("key_points", []) or []:
            if isinstance(point, dict):
                value = _first_text(point, "text", "value", "summary")
                if value:
                    highlights.append(value)
        if highlights:
            result["highlights"] = highlights[:4]
        return result
    if template_id in {"comment_single_v1", "comment_dual_v1"}:
        quotes = [
            item
            for item in (props.get("quotes") or props.get("quote_candidates") or [])
            if isinstance(item, dict)
        ]
        texts = [
            _first_text(item, "text", "claim", "quote_cn", "quote") for item in quotes
        ]
        texts = [text for text in texts if text]
        if not texts:
            left = _first_text(props, "left_summary")
            right = _first_text(props, "right_summary")
            if left:
                texts.append(left)
            if right:
                texts.append(right)
        if template_id == "comment_dual_v1":
            return {
                "title": f"HN 评论 · {label}" if label else "评论区的分歧",
                "left_summary": texts[0] if texts else "暂无第一条评论摘录。",
                "right_summary": texts[1] if len(texts) > 1 else "暂无第二条评论摘录。",
                "left_label": _first_text(quotes[0], "stance", "author")
                if quotes
                else _first_text(props, "left_label", "left_stance") or "观点一",
                "right_label": _first_text(quotes[1], "stance", "author")
                if len(quotes) > 1
                else _first_text(props, "right_label", "right_stance") or "观点二",
            }
        quote = (
            texts[0]
            if texts
            else _first_text(props, "comment_summary", "discussion_summary")
        )
        return {
            "eyebrow": f"HN 评论 · {label}" if label else "HN COMMENT",
            "quote": quote or "暂无可用的评论摘录。",
            "author": _first_text(quotes[0], "author")
            if quotes
            else _first_text(props, "author") or "HN community",
            "stance": _first_text(quotes[0], "stance")
            if quotes
            else _first_text(props, "stance", "left_stance") or "观点",
        }
    if template_id == "quick_news_v1":
        result = {
            "eyebrow": "速览",
            "section_label": "速览",
        }
        if title:
            result["title"] = title
        fact = _first_key_point(props) or _first_text(
            props, "fact", "why_it_matters", "discussion_summary", "dek"
        )
        if fact:
            result["fact"] = fact
        if image:
            result["image_src"] = image
        if source_url:
            result["source_url"] = source_url
        index = props.get("index") or props.get("display_index")
        if index is not None:
            result["index"] = index
        return result
    if template_id in {"closing_v1", "closing_signals_v1"}:
        items = _closing_items(props)
        if template_id == "closing_signals_v1":
            title_val = _first_text(props, "title") or "今天留下三条信号"
            return {"title": title_val, "items": items or ["暂无总结信号"]}
        result = {}
        takeaways = props.get("takeaways")
        if takeaways:
            result["takeaways"] = takeaways
        summary_items = props.get("summary_items")
        if summary_items:
            result["summary_items"] = summary_items
        keywords = props.get("keywords")
        if keywords:
            result["keywords"] = keywords
        signal = _first_text(props, "signal")
        if signal:
            result["signal"] = signal
        if items and "summary_items" not in result:
            result["summary_items"] = [
                {"title": item, "signal": item} for item in items
            ]
        totals = props.get("totals")
        if totals:
            result["totals"] = totals
        return result
    if template_id == "cover_v1":
        headline = _first_text(props, "headline", "title") or "每日HN日报"
        date_str = _first_text(props, "date", "date_label") or ""
        result = {"headline": headline}
        if date_str:
            result["date"] = date_str
        subtitle = _first_text(props, "subtitle")
        if subtitle:
            result["subtitle"] = subtitle
        return result
    return {}


def build_storyboard(script: Script, date: str) -> dict[str, Any]:
    """Return a stable, editable storyboard draft without mutating ``script``."""

    event_story_indices: list[int] = []
    for segment in script.segments:
        for element in segment.scene_elements:
            story_index = element.props.get("story_index")
            if (
                element.element_type == "event_card"
                and isinstance(story_index, int)
                and not isinstance(story_index, bool)
            ):
                event_story_indices.append(story_index)
    first_story_index = min(event_story_indices) if event_story_indices else None
    seen_event = False
    shots: list[dict[str, Any]] = []

    for segment_index, segment in enumerate(script.segments):
        for element_index, element in enumerate(segment.scene_elements):
            if element.props.get("is_audio_marker"):
                continue
            template_id, props = _template_for_element(
                element,
                first_story_index=first_story_index,
                seen_event=seen_event,
            )
            if element.element_type == "event_card":
                seen_event = True
            shots.append(
                {
                    "shot_id": f"S{segment_index + 1:02d}-{element_index + 1:02d}",
                    "segment_index": segment_index,
                    "element_index": element_index,
                    "template_id": template_id,
                    "props": props,
                }
            )

    return {
        "schema_version": STORYBOARD_SCHEMA_VERSION,
        "date": date,
        "generated_by": {
            "kind": "heuristic_draft",
            "version": STORYBOARD_DRAFT_VERSION,
        },
        "shots": shots,
    }


def _template_for_element(
    element: SceneElement,
    *,
    first_story_index: int | None,
    seen_event: bool,
) -> tuple[str, dict[str, Any]]:
    props = element.props or {}
    preferred = _preferred_template_id(element, "")
    if preferred:
        return preferred, _preferred_visual_props(element, preferred)
    if element.element_type == "event_card":
        title = _first_text(props, "editor_angle", "title_cn", "source_title", "title")
        story_index = props.get("story_index")
        is_headline = (
            not seen_event
            or first_story_index is not None
            and story_index == first_story_index
        )
        if is_headline:
            return "headline_v1", {
                "title": title or "今日头条",
                "eyebrow": "头条",
                **_optional_props(
                    props,
                    subtitle=("why_it_matters", "dek"),
                    source_label=("category",),
                ),
            }
        fact = _first_key_point(props) or _first_text(
            props, "why_it_matters", "discussion_summary", "dek"
        )
        return "quick_news_v1", {
            "title": title or "今日快讯",
            "fact": fact or "详情见台本段落。",
            **_optional_props(
                props, index=("display_index",), comment_focus=("discussion_summary",)
            ),
        }

    if element.element_type == "atmosphere_card":
        quotes = [
            quote for quote in props.get("quotes", []) or [] if isinstance(quote, dict)
        ]
        quote_texts = [_first_text(quote, "text", "claim") for quote in quotes]
        quote_texts = [text for text in quote_texts if text]
        if len(quote_texts) >= 2:
            return "comment_dual_v1", {
                "left_summary": quote_texts[0],
                "right_summary": quote_texts[1],
                "left_label": _first_text(quotes[0], "stance", "author") or "观点一",
                "right_label": _first_text(quotes[1], "stance", "author") or "观点二",
            }
        if quote_texts:
            return "comment_single_v1", {
                "quote": quote_texts[0],
                "author": _first_text(quotes[0], "author"),
                "stance": _first_text(quotes[0], "stance"),
            }
        return "discussion_v1", {}

    if element.element_type == "closing_card":
        items = _closing_items(props)
        if items:
            return "closing_signals_v1", {"title": "今天留下三条信号", "items": items}
        return "closing_v1", {}

    return ELEMENT_TYPE_TO_TEMPLATE_ID.get(element.element_type, "event_v1"), {}


def _first_text(props: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = props.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _first_key_point(props: dict[str, Any]) -> str:
    points = props.get("key_points") or []
    if not isinstance(points, list):
        return ""
    for point in points:
        if isinstance(point, dict):
            text = _first_text(point, "text", "value", "summary")
            if text:
                return text
    return ""


def _optional_props(props: dict[str, Any], **fields: tuple[str, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for output_key, source_keys in fields.items():
        value = _first_text(props, *source_keys)
        if value:
            result[output_key] = value
    return result


def _closing_items(props: dict[str, Any]) -> list[str]:
    takeaways = props.get("takeaways") or []
    if isinstance(takeaways, list):
        items = [str(item).strip() for item in takeaways if str(item).strip()]
        if items:
            return items[:3]
    summary_items = props.get("summary_items") or []
    if isinstance(summary_items, list):
        items = []
        for entry in summary_items:
            if isinstance(entry, dict):
                value = _first_text(entry, "signal", "title")
                if value:
                    items.append(value)
        return items[:3]
    return []
