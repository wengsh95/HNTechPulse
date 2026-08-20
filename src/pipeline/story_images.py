"""Ensure every story represented in a video has one usable local image.

Deep stories already receive candidates from ``ArticleEnricher``.  The quick-news
layer is built from the prefilter pool and therefore needs its own lightweight
image pass; when no article image exists, a source-page screenshot is the final
candidate.  Selection still follows the existing agent image-selection contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.models import ContentPackage, Script
from src.pipeline.agent_io import write_artifact_manifest
from src.pipeline.paths import media_images_dir, pipeline_path
from src.pipeline.script.io import save_script_lock, script_editorial_hash
from src.utils.async_helper import run_async
from src.utils.atomic_io import atomic_write_json


STORY_IMAGES_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class StoryImagePreparation:
    stories: list[dict[str, Any]]
    pending: list[dict[str, Any]]
    changed: bool


def missing_story_images(script: Script, date: str) -> list[str]:
    """Return story ids whose current script has no usable local image."""

    missing: list[str] = []
    for ref in _story_refs(script, None):
        selected = ""
        for element in ref["elements"]:
            props = element.props or {}
            selected = str(props.get("image_src") or props.get("story_image") or "")
            if selected:
                break
        if (
            not selected
            or _is_remote(selected)
            or not _local_path(date, selected).exists()
        ):
            missing.append(str(ref["story_id"]))
    return missing


def require_story_images(script: Script, date: str) -> None:
    """Fail before rendering when any story violates the image hard gate."""

    missing = missing_story_images(script, date)
    if missing:
        raise ValueError(
            "Every story requires at least one usable local image; "
            f"missing story ids: {', '.join(missing)}"
        )


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _is_remote(path: str) -> bool:
    return path.startswith(("http://", "https://"))


def _local_path(date: str, path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    if candidate.parts and candidate.parts[0].lower() == "images":
        return media_images_dir(date) / Path(*candidate.parts[1:])
    return media_images_dir(date) / candidate


def _relative_image_path(path: str) -> str:
    candidate = Path(path)
    if candidate.parts and candidate.parts[0].lower() == "images":
        return "/".join(candidate.parts)
    return f"images/{candidate.name}"


def _candidate(path: str, *, source: str, label: str, rank: int) -> dict[str, Any]:
    return {
        "path": _relative_image_path(path),
        "source": source,
        "label": label,
        "rank": rank,
    }


def _content_item_for_story(content: ContentPackage | None, props: dict[str, Any]):
    if content is None:
        return None
    story_index = props.get("story_index")
    source_title = str(props.get("source_title") or "").strip()
    if isinstance(story_index, int) and 0 <= story_index < len(content.items):
        item = content.items[story_index]
        if not source_title or item.title == source_title:
            return item
    if source_title:
        return next(
            (item for item in content.items if item.title == source_title), None
        )
    return None


def _story_refs(script: Script, content: ContentPackage | None) -> list[dict[str, Any]]:
    refs: dict[str, dict[str, Any]] = {}
    for segment in script.segments:
        for element in segment.scene_elements:
            props = element.props or {}
            quick_id = props.get("quick_story_id")
            if quick_id:
                key = str(quick_id)
                ref = refs.setdefault(
                    key,
                    {
                        "story_id": key,
                        "title": str(props.get("title") or ""),
                        "url": str(props.get("source_url") or ""),
                        "elements": [],
                    },
                )
                ref["elements"].append(element)
                continue

            if not isinstance(props.get("story_index"), int):
                continue
            item = _content_item_for_story(content, props)
            key = (
                str(item.source_id)
                if item is not None
                else f"story-{props['story_index']}"
            )
            ref = refs.setdefault(
                key,
                {
                    "story_id": key,
                    "title": str(
                        props.get("source_title")
                        or props.get("title")
                        or props.get("editor_angle")
                        or ""
                    ),
                    "url": str(props.get("source_url") or (item.url if item else "")),
                    "elements": [],
                },
            )
            if item is not None:
                ref["title"] = item.title or ref["title"]
                ref["url"] = item.url or ref["url"]
            ref["elements"].append(element)
    return list(refs.values())


def _existing_candidates(
    date: str,
    ref: dict[str, Any],
    content: ContentPackage | None,
    selection_entry: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(path: Any, source: str, label: str) -> None:
        if not path or not isinstance(path, str) or _is_remote(path):
            return
        normalized = _relative_image_path(path)
        if normalized in seen or not _local_path(date, normalized).exists():
            return
        seen.add(normalized)
        candidates.append(
            _candidate(normalized, source=source, label=label, rank=len(candidates))
        )

    for item in selection_entry.get("candidates") or []:
        if isinstance(item, dict):
            add(
                item.get("path"),
                str(item.get("source") or "candidate"),
                str(item.get("label") or "候选图片"),
            )

    item = next(
        (
            item
            for item in (content.items if content is not None else [])
            if str(item.source_id) == str(ref["story_id"])
        ),
        None,
    )
    if item is not None:
        for path in item.article_images or []:
            add(path, "article", "文章配图")
        add(item.screenshot_image, "screenshot", "页面截图")
        add(item.logo_image, "logo", "来源标识")
        for image in item.image_candidates or []:
            if isinstance(image, dict):
                add(
                    image.get("path"),
                    str(image.get("source") or "candidate"),
                    str(image.get("label") or "候选图片"),
                )

    return candidates


def _selection_confirmed(
    entry: dict[str, Any], candidates: list[dict[str, Any]], date: str
) -> bool:
    selected = entry.get("selected_image")
    if not isinstance(selected, str) or not selected:
        return False
    normalized = _relative_image_path(selected)
    if normalized not in {str(item.get("path")) for item in candidates}:
        return False
    sources = {entry.get("selection_source")}
    candidate = next(
        (item for item in candidates if item.get("path") == normalized), None
    )
    if candidate:
        sources.add(candidate.get("selection_source"))
    if "heuristic" in sources or "llm" in sources:
        return False
    return _local_path(date, normalized).exists()


def _task(
    ref: dict[str, Any], candidates: list[dict[str, Any]], date: str
) -> dict[str, Any]:
    task_candidates = []
    for candidate in candidates:
        item = dict(candidate)
        item["local_path"] = str(
            _local_path(date, str(candidate["path"])).resolve()
        ).replace("\\", "/")
        task_candidates.append(item)
    return {
        "story_id": str(ref["story_id"]),
        "title": ref.get("title") or "",
        "url": ref.get("url") or "",
        "selection_file": str(pipeline_path(date, "image_selection.json")).replace(
            "\\", "/"
        ),
        "candidates": task_candidates,
    }


def _image_targets(ref: dict[str, Any]) -> list[Any]:
    """Return the single visual beat that owns a story's evidence image."""

    elements = ref.get("elements") or []
    explicit = [
        element
        for element in elements
        if bool((element.props or {}).get("image_target"))
    ]
    if explicit:
        return explicit[:1]
    # Backward compatibility for scripts created before video_structure.json.
    return elements[:1]


def _capture_missing_screenshots(
    refs: list[dict[str, Any]],
    date: str,
    fetcher,
    logger=None,
) -> None:
    if fetcher is None:
        return

    async def capture() -> None:
        for ref in refs:
            source_url = str(ref.get("url") or "")
            urls = [source_url] if source_url else []
            hn_url = f"https://news.ycombinator.com/item?id={ref['story_id']}"
            if hn_url not in urls:
                urls.append(hn_url)
            path = None
            for url in urls:
                try:
                    path = await fetcher.capture_screenshot(
                        url, media_images_dir(date), str(ref["story_id"])
                    )
                except Exception as exc:  # pragma: no cover - browser-specific failure
                    if logger:
                        logger.warning(
                            "  Story image screenshot failed for %s: %s",
                            ref["story_id"],
                            exc,
                        )
                if path:
                    break
            if path:
                ref["captured_image"] = path

    run_async(capture())


def prepare_story_images(
    script: Script,
    content: ContentPackage | None,
    date: str,
    *,
    fetcher=None,
    agent_mode: bool = False,
    config: dict[str, Any] | None = None,
    logger=None,
) -> StoryImagePreparation:
    refs = _story_refs(script, content)
    selection_path = pipeline_path(date, "image_selection.json")
    selection = _load_json(selection_path, {"date": date, "items": {}})
    if not isinstance(selection, dict):
        selection = {"date": date, "items": {}}
    selection.setdefault("date", date)
    selection.setdefault("items", {})

    missing_refs: list[dict[str, Any]] = []
    prepared: list[dict[str, Any]] = []
    for ref in refs:
        entry = selection["items"].get(str(ref["story_id"]), {})
        ref["candidates"] = _existing_candidates(date, ref, content, entry)
        if not ref["candidates"]:
            missing_refs.append(ref)

    _capture_missing_screenshots(missing_refs, date, fetcher, logger=logger)

    changed = False
    pending: list[dict[str, Any]] = []
    for ref in refs:
        key = str(ref["story_id"])
        entry = dict(selection["items"].get(key) or {})
        candidates = _existing_candidates(date, ref, content, entry)
        if ref.get("captured_image"):
            candidates = _existing_candidates(date, ref, content, entry)
            captured = _relative_image_path(str(ref["captured_image"]))
            if captured not in {str(item["path"]) for item in candidates}:
                candidates.append(
                    _candidate(
                        captured,
                        source="screenshot",
                        label="来源页面截图",
                        rank=len(candidates),
                    )
                )
        entry["title"] = ref.get("title") or entry.get("title") or ""
        entry["url"] = ref.get("url") or entry.get("url") or ""
        entry["candidates"] = candidates

        confirmed = _selection_confirmed(entry, candidates, date)
        selected = (
            _relative_image_path(str(entry.get("selected_image")))
            if entry.get("selected_image")
            else ""
        )
        if not confirmed:
            if agent_mode:
                pending.append(_task(ref, candidates, date))
                selected = ""
            elif candidates:
                selected = str(candidates[0]["path"])
                entry["selected_image"] = selected
                entry["selection_source"] = "heuristic"
            else:
                selected = ""
        if selected:
            entry["selected_image"] = selected
            targets = _image_targets(ref)
            for element in ref["elements"]:
                element.props.pop("image_src", None)
                element.props.pop("story_image", None)
            for element in targets:
                element.props["image_src"] = selected
                element.props["story_image"] = selected
        else:
            for element in ref["elements"]:
                element.props.pop("image_src", None)
                element.props.pop("story_image", None)
            entry.pop("selected_image", None)
        if selection["items"].get(key) != entry:
            selection["items"][key] = entry
            changed = True

        prepared.append(
            {
                "story_id": key,
                "title": ref.get("title") or "",
                "url": ref.get("url") or "",
                "selected_image": selected or None,
                "candidates": candidates,
                "status": "ok" if selected else "missing",
                "element_count": len(ref["elements"]),
            }
        )

    if changed:
        atomic_write_json(selection_path, selection)

    artifact = pipeline_path(date, "story_images.json")
    atomic_write_json(
        artifact,
        {
            "schema_version": STORY_IMAGES_SCHEMA_VERSION,
            "date": date,
            "stories": prepared,
            "missing_story_ids": [
                item["story_id"] for item in prepared if item["status"] != "ok"
            ],
        },
    )
    write_artifact_manifest(
        artifact,
        step="prepare_story_images",
        date=date,
        config=config,
        inputs={
            "script_editorial_hash": script_editorial_hash(script),
            "selection_path": str(selection_path).replace("\\", "/"),
        },
    )
    if changed:
        save_script_lock(script, date, source="prepare_story_images")
    return StoryImagePreparation(stories=prepared, pending=pending, changed=changed)
