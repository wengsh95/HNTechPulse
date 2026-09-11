"""One home for resolving and staging image assets.

Before this module, "resolve a story/template path to a real local file and
copy it into the Remotion public dir" was implemented four times, each with a
slightly different convention:

- ``remotion_renderer._prepare_image_assets`` / ``remotion_props.regenerate_preview_props``
  resolved relative paths against ``date_root(date)`` with a ``media/``
  fallback, and copied article images + logo + screenshot + story images.
- ``story_images._local_path`` resolved ``images/...`` against
  ``media_images_dir(date)``.
- ``article_enricher._candidate_local_path`` returned the bare relative path.

The renderer copy also silently skipped ``image_candidates`` that the props
copy staged.  This module is the single seam: one path policy, one story→item
disambiguation, one staging walk.  Consumers keep their own output shapes; the
shared fact (where a stored path lives, and which ContentItem a script element
refers to) lives here once.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from src.pipeline.paths import date_root, media_images_dir, pipeline_path

#: Path prefixes treated as remote URLs and therefore never staged locally.
REMOTE_PREFIXES = ("http://", "https://")


def is_remote(path: str | None) -> bool:
    """Return whether a stored path is a remote URL rather than a local file."""
    return bool(path and path.startswith(REMOTE_PREFIXES))


def resolve_local_path(date: str, path: str) -> Path:
    """Resolve a stored path to the local file it names.

    Resolution policy (the same one the renderer already used):
      * absolute paths are returned unchanged;
      * ``images/...`` paths resolve against ``date_root/date/media/images``
        via :func:`src.pipeline.paths.media_images_dir`;
      * anything else resolves against ``date_root(date)`` first, then falls
        back to ``date_root(date)/media`` so legacy stored paths keep working.

    The returned path is *not* required to exist; callers that need an
    existing file should use :func:`resolve_existing_local`.
    """
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    if candidate.parts and candidate.parts[0].lower() == "images":
        return media_images_dir(date) / Path(*candidate.parts[1:])
    resolved = date_root(date) / path
    if not resolved.exists():
        alt = date_root(date) / "media" / path
        if alt.exists():
            return alt
    return resolved


def resolve_existing_local(date: str, path: str) -> Path | None:
    """Resolve a path to an existing local file, or None for remote/missing."""
    if is_remote(path):
        return None
    resolved = resolve_local_path(date, path)
    return resolved if resolved.exists() else None


def relative_image_path(path: str) -> str:
    """Return the canonical store-relative form of a path.

    ``images/foo.jpg`` stays as-is; anything else becomes
    ``images/<basename>`` so every stored candidate names a file under the
    per-date media images dir.
    """
    candidate = Path(path)
    if candidate.parts and candidate.parts[0].lower() == "images":
        return "/".join(candidate.parts)
    return f"images/{candidate.name}"


def content_item_for_story(content: Any, props: dict[str, Any] | None) -> Any | None:
    """Find the ContentItem a script element refers to.

    A script element's ``story_index`` is the position in the *script's*
    ranked list, which can diverge from ``content.items`` when ``write_script``
    drops a story.  The fallback matches the element's ``source_title`` (the
    stable LLM-supplied title) against items.  Mirror of the logic formerly
    duplicated in ``remotion_props._resolve_item`` and
    ``story_images._content_item_for_story``.
    """
    if content is None or not getattr(content, "items", None):
        return None
    props = props or {}
    idx = props.get("story_index")
    target_title = str(props.get("source_title") or "").strip()
    if isinstance(idx, int) and 0 <= idx < len(content.items):
        item = content.items[idx]
        if not target_title or (item.title and item.title.strip() == target_title):
            return item
        for candidate in content.items:
            if (
                candidate.title
                and candidate.title.strip() == target_title
                and target_title
            ):
                return candidate
        return item
    if target_title:
        for candidate in content.items:
            if candidate.title and candidate.title.strip() == target_title:
                return candidate
    return None


def _stage_one(
    source: Path,
    target_dir: Path,
    dest_name: str | None = None,
) -> bool:
    """Copy a single existing file into ``target_dir`` if not already there.

    Returns whether a copy was performed.  Files are deduplicated by
    destination name (matching the legacy copies).
    """
    if not source.exists():
        return False
    dest = target_dir / (dest_name or source.name)
    if dest.exists():
        return False
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    return True


def load_story_image_paths(date: str) -> list[str]:
    """Load the selected story-image paths, including quick-news stories.

    Reads ``story_images.json`` and returns each story's ``selected_image``.
    This is the single reader for the staging walk; the render props module
    delegates here too.
    """
    path = pipeline_path(date, "story_images.json")
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [
        str(story["selected_image"])
        for story in payload.get("stories", [])
        if isinstance(story, dict) and story.get("selected_image")
    ]


def stage_content_images(
    content: Any,
    date: str,
    target_dir: Path,
    *,
    include_candidates: bool = True,
) -> int:
    """Copy every item's article/logo/screenshot (and optional candidate)
    images plus the selected story images into ``target_dir``.

    Returns the number of files copied this call (0 when everything was
    already staged).  This is the single staging walk that used to live in
    both ``remotion_renderer`` and ``remotion_props``.
    """
    copied = 0
    src_paths: list[str] = []
    if content is not None:
        for item in getattr(content, "items", []):
            src_paths.extend(getattr(item, "article_images", None) or [])
            if include_candidates:
                for candidate in getattr(item, "image_candidates", None) or []:
                    if isinstance(candidate, dict):
                        path = candidate.get("path")
                        if path:
                            src_paths.append(str(path))
            for attr in ("logo_image", "screenshot_image"):
                val = getattr(item, attr, None)
                if val:
                    src_paths.append(str(val))

    for src in src_paths:
        if not src:
            continue
        resolved = resolve_existing_local(date, src)
        if resolved and _stage_one(resolved, target_dir):
            copied += 1

    for image_path in load_story_image_paths(date):
        resolved = resolve_existing_local(date, image_path)
        if resolved and _stage_one(resolved, target_dir):
            copied += 1
    return copied


__all__ = [
    "REMOTE_PREFIXES",
    "is_remote",
    "resolve_local_path",
    "resolve_existing_local",
    "relative_image_path",
    "content_item_for_story",
    "load_story_image_paths",
    "stage_content_images",
]
