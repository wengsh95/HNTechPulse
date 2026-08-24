"""Agent-authored quick-news layer for the video script."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from src.core.models import (
    ContentItem,
    ContentPackage,
    SceneElement,
    Script,
    ScriptSegment,
)
from src.pipeline.agent_io import write_artifact_manifest
from src.pipeline.content_io import ContentPreparer
from src.pipeline.paths import pipeline_path, raw_path
from src.pipeline.script.io import save_script_lock, script_editorial_hash
from src.utils.atomic_io import atomic_write_json


QUICK_NEWS_SCHEMA_VERSION = 2
QUICK_NEWS_COUNT = 3
SPEECH_CPS = 3.5


@dataclass(frozen=True)
class QuickNewsDraft:
    items: list[dict[str, Any]]
    changed: bool


def _load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON artifact: {path}") from exc


def _candidate_pool(date: str, deep_story_ids: set[str]) -> list[dict[str, Any]]:
    raw = _load_json(raw_path(date, "raw_stories.json"))
    prefilter = _load_json(pipeline_path(date, "prefilter.json"))
    decisions = prefilter.get("decisions") or {}
    stories = raw.get("stories") or []
    candidates: list[dict[str, Any]] = []
    for story in stories:
        story_id = str(story.get("id") or "")
        decision = (
            decisions.get(story_id) or decisions.get(int(story_id))
            if story_id.isdigit()
            else decisions.get(story_id)
        )
        if not isinstance(decision, dict) or decision.get("keep") is not True:
            continue
        if story_id in deep_story_ids:
            continue
        candidates.append(
            {
                "story_id": story_id,
                "title": story.get("title") or "",
                "url": story.get("url") or "",
                "score": story.get("score") or 0,
                "comment_count": story.get("descendants") or 0,
                "post_text": story.get("text") or "",
                "news_focus": decision.get("news_focus") or 0,
                "reason": decision.get("reason") or "",
            }
        )
    return candidates


def _clean_sentence(value: Any) -> str:
    text = str(value or "").strip().lstrip("-•* ")
    text = text.replace("；", "，").replace(";", "，")
    if text and text[-1] not in "。！？.!?":
        text += "。"
    return text


def _fact_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", str(value or "").lower())


def _validate_quick_items(items: list[dict[str, Any]]) -> None:
    if len(items) < 2:
        raise ValueError("Quick news requires at least two valid items")
    for item in items:
        title_key = _fact_key(item.get("title"))
        source_title_key = _fact_key(item.get("source_title"))
        fact = str(item.get("fact") or "").strip()
        fact_key = _fact_key(fact)
        if not re.search(r"[\u4e00-\u9fff]", fact):
            raise ValueError(
                f"Quick-news fact for story {item.get('story_id')} must be Chinese"
            )
        if fact_key in {title_key, source_title_key}:
            raise ValueError(
                f"Quick-news fact for story {item.get('story_id')} merely repeats its title"
            )


def _enrich_candidate_context(
    candidates: list[dict[str, Any]],
    date: str,
    article_enricher: Any,
) -> list[dict[str, Any]]:
    """Fetch/extract quick-story bodies before asking the LLM to summarize."""

    package = ContentPackage(
        date=date,
        items=[
            ContentItem(
                source="hackernews",
                source_id=str(candidate["story_id"]),
                title=str(candidate.get("title") or ""),
                url=str(candidate.get("url") or "") or None,
                score=int(candidate.get("score") or 0),
                comment_count=int(candidate.get("comment_count") or 0),
                news_focus=int(candidate.get("news_focus") or 0),
                self_post_text=str(candidate.get("post_text") or "") or None,
            )
            for candidate in candidates
        ],
    )
    enriched = article_enricher.enrich(package, date)
    by_id = {str(item.source_id): item for item in enriched.items}
    usable = 0
    result: list[dict[str, Any]] = []
    for candidate in candidates:
        item = by_id.get(str(candidate["story_id"]))
        context = {
            "enrichment_source": getattr(item, "enrichment_source", None),
            "article_summary": getattr(item, "article_summary", None),
            "editor_angle": getattr(item, "editor_angle", None),
            "why_it_matters": getattr(item, "why_it_matters", None),
            "key_points": (getattr(item, "key_points", None) or [])[:4],
            "article_excerpt": (getattr(item, "article_text", None) or "")[:1200],
        }
        if (
            context["article_summary"]
            or context["key_points"]
            or context["article_excerpt"]
        ):
            usable += 1
        result.append({**candidate, "source_context": context})
    if usable < 2:
        raise ValueError(
            "Quick-news source enrichment produced fewer than two usable articles"
        )
    return result


def _normalize_agent_result(
    result: Any, candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if len(candidates) < 2:
        raise ValueError("Not enough prefilter-approved candidates for quick news")
    if isinstance(result, dict):
        result = result.get("quick_news") or result.get("items") or []
    if not isinstance(result, list):
        result = []
    by_id = {str(item["story_id"]): item for item in candidates}
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in result:
        if not isinstance(entry, dict):
            continue
        story_id = str(entry.get("story_id") or "")
        candidate = by_id.get(story_id)
        if candidate is None or story_id in seen:
            continue
        title = str(entry.get("title") or candidate["title"]).strip()
        fact = _clean_sentence(entry.get("fact"))
        if not title or not fact:
            continue
        normalized.append(
            {
                "story_id": story_id,
                "title": title,
                "fact": fact,
                "source_url": candidate["url"],
                "source_title": candidate["title"],
                "score": candidate["score"],
                "comment_count": candidate["comment_count"],
                "source_context": candidate.get("source_context") or {},
            }
        )
        seen.add(story_id)
        if len(normalized) >= QUICK_NEWS_COUNT:
            break
    _validate_quick_items(normalized)
    return normalized


def _existing_quick_segment(script: Script) -> ScriptSegment | None:
    return next(
        (
            segment
            for segment in script.segments
            if segment.segment_type == "quick_news"
        ),
        None,
    )


def _load_cached_items(date: str) -> list[dict[str, Any]]:
    """Reuse a completed quick-news artifact during downstream recovery."""

    artifact = pipeline_path(date, "quick_news.json")
    if not artifact.exists():
        return []
    payload = _load_json(artifact)
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != QUICK_NEWS_SCHEMA_VERSION
    ):
        return []
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list) or len(items) < 2:
        return []
    normalized: list[dict[str, Any]] = []
    for item in items[:QUICK_NEWS_COUNT]:
        if not isinstance(item, dict):
            continue
        story_id = str(item.get("story_id") or "")
        title = str(item.get("title") or "").strip()
        fact = _clean_sentence(item.get("fact"))
        if story_id and title and fact:
            normalized.append(
                {**item, "story_id": story_id, "title": title, "fact": fact}
            )
    try:
        _validate_quick_items(normalized)
    except ValueError:
        return []
    return normalized


def _build_segment(items: list[dict[str, Any]]) -> ScriptSegment:
    elements: list[SceneElement] = []
    subtitle_groups: list[list[str]] = []
    durations: list[float] = []
    count_label = {2: "两", 3: "三"}.get(len(items), str(len(items)))
    intro = f"接下来是{count_label}条速览。"
    audio_parts: list[str] = [intro]
    for index, item in enumerate(items, 1):
        title = item["title"]
        fact = item["fact"]
        audio_text = f"{title}。{fact}"
        duration = max(3.0, len(audio_text) / SPEECH_CPS)
        subtitles = [f"{title}。", fact]
        elements.append(
            SceneElement(
                element_type="quick_card",
                start_time=0.0,
                end_time=duration,
                sub_segment_index=index - 1,
                props={
                    "index": f"{index:02d}",
                    "title": title,
                    "fact": fact,
                    "source_url": item.get("source_url", ""),
                    "source_title": item.get("source_title", title),
                    "quick_story_id": item["story_id"],
                    "subtitle_texts": subtitles,
                },
            )
        )
        subtitle_groups.append(subtitles)
        durations.append(duration)
        audio_parts.append(audio_text)
    return ScriptSegment(
        segment_type="quick_news",
        audio_text=" ".join(audio_parts),
        duration=sum(durations) + 2.0,
        emotion="neutral",
        scene_elements=elements,
        meta={
            "quick_story_ids": [item["story_id"] for item in items],
            "intro_text": intro,
            "sub_segment_subtitle_texts": subtitle_groups,
            "sub_segment_estimated_durations": durations,
        },
    )


def draft_quick_news(
    script: Script,
    date: str,
    *,
    llm_provider=None,
    article_enricher=None,
    config: dict[str, Any] | None = None,
    logger=None,
) -> QuickNewsDraft:
    existing = _existing_quick_segment(script)
    if existing is not None:
        existing_items = [
            {
                "story_id": element.props.get("quick_story_id"),
                "title": element.props.get("title"),
                "source_title": element.props.get("source_title")
                or element.props.get("title"),
                "fact": element.props.get("fact"),
            }
            for element in existing.scene_elements
        ]
        try:
            _validate_quick_items(existing_items)
        except ValueError:
            script.segments.remove(existing)
        else:
            return QuickNewsDraft(items=[], changed=False)

    cached_items = _load_cached_items(date)
    if cached_items:
        closing_index = next(
            (
                index
                for index, segment in enumerate(script.segments)
                if segment.segment_type == "closing"
            ),
            len(script.segments),
        )
        script.segments.insert(closing_index, _build_segment(cached_items))
        save_script_lock(script, date, source="draft_quick_news_cache")
        if logger:
            logger.info(
                "  Quick news restored from existing artifact: %d items",
                len(cached_items),
            )
        return QuickNewsDraft(items=cached_items, changed=True)

    content = ContentPreparer(config or {}).load_content(date)
    deep_story_ids = {str(item.source_id) for item in content.items}
    candidates = sorted(
        _candidate_pool(date, deep_story_ids),
        key=lambda item: (item.get("news_focus", 0), item.get("score", 0)),
        reverse=True,
    )[:QUICK_NEWS_COUNT]
    if not candidates:
        raise ValueError("No prefilter-approved stories remain for quick news")
    if article_enricher is not None:
        candidates = _enrich_candidate_context(candidates, date, article_enricher)

    if llm_provider is not None:
        context = {
            "date": date,
            "quick_news_count": str(min(QUICK_NEWS_COUNT, len(candidates))),
            "candidates_json": json.dumps(candidates, ensure_ascii=False, indent=2),
        }

        def _validator(payload: dict) -> None:
            _normalize_agent_result(payload, candidates)

        result = llm_provider.complete_prompt(
            "prompts/quick_news.md",
            context,
            label="draft_quick_news",
            expect_json=True,
            max_tokens=6000,
            model=llm_provider.fast_model,
            temperature=llm_provider.fast_temperature,
            validator=_validator,
        )
    else:
        result = []
    items = _normalize_agent_result(result, candidates)
    quick_segment = _build_segment(items)
    closing_index = next(
        (
            index
            for index, segment in enumerate(script.segments)
            if segment.segment_type == "closing"
        ),
        len(script.segments),
    )
    script.segments.insert(closing_index, quick_segment)

    artifact = pipeline_path(date, "quick_news.json")
    atomic_write_json(
        artifact,
        {
            "schema_version": QUICK_NEWS_SCHEMA_VERSION,
            "date": date,
            "generated_by": {"kind": "agent", "version": 1},
            "deep_story_ids": sorted(deep_story_ids),
            "items": items,
        },
    )
    write_artifact_manifest(
        artifact,
        step="draft_quick_news",
        date=date,
        config=config,
        inputs={
            "script_editorial_hash": script_editorial_hash(script),
            "candidate_count": len(candidates),
            "quick_story_ids": [item["story_id"] for item in items],
        },
    )
    save_script_lock(script, date, source="draft_quick_news")
    if logger:
        logger.info("  Quick news generated: %d items", len(items))
    return QuickNewsDraft(items=items, changed=True)
