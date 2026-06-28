"""Shared freshness inputs for the publish_guide artifact.

Both the orchestrator (when writing ``publish_guide.md`` + its manifest) and the
publishability audit (when checking whether the guide is stale) must compute the
*same* manifest inputs, or the guide is flagged stale forever: the orchestrator
thinks it is fresh and skips regeneration while the audit thinks it changed.

To keep the two in lockstep, both call :func:`publish_guide_manifest_inputs`,
which reads the canonical on-disk artifacts (content.json, script.json,
title.json) and returns the dict that gets hashed into the manifest.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.pipeline.agent_io import file_sha256
from src.pipeline.paths import pipeline_path, publish_path

_PROMPT_PATH = Path("prompts/publish_guide.md")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def publish_guide_manifest_inputs(date: str) -> dict[str, Any]:
    """Build the manifest freshness inputs for ``publish_guide.md``.

    Reads content/script/title from disk so the orchestrator and the audit
    derive an identical hash. The set of item fields mirrors what the publish
    guide prompt is sensitive to (title, angle, category, keywords, score,
    comment count).
    """
    content_data = _read_json(pipeline_path(date, "content.json"))
    script_data = _read_json(pipeline_path(date, "script.json"))
    title_data = _read_json(publish_path(date, "title.json"))

    items_payload = []
    for item in content_data.get("items") or []:
        if not isinstance(item, dict):
            continue
        items_payload.append(
            {
                "title_cn": item.get("title_cn") or item.get("title"),
                "title": item.get("title"),
                "editor_angle": item.get("editor_angle") or item.get("dek") or "",
                "category": item.get("category") or "",
                "keywords": item.get("keywords") or [],
                "score": item.get("score"),
                "comment_count": item.get("comment_count"),
            }
        )

    return {
        "script_title": title_data.get("title")
        or script_data.get("title")
        or "HN每日观察",
        "script_description": title_data.get("description")
        or script_data.get("description")
        or "",
        "items_json": json.dumps(items_payload, ensure_ascii=False, indent=2),
        "prompt_hash": file_sha256(_PROMPT_PATH),
        "date": date,
    }
