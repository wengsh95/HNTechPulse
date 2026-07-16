"""Shared freshness inputs for the xhs_guide artifact.

Mirrors :mod:`src.pipeline.publish_guide_inputs`: both the orchestrator (when
writing ``xhs_guide.md`` + its manifest) and any future audit must compute the
*same* manifest inputs, or the guide is flagged stale forever. Both call
:func:`xhs_guide_manifest_inputs`, which reads the canonical on-disk artifacts
(content.json, script.json, title.json, comment_judgement.json,
translations.json) and returns the dict that gets hashed into the manifest.

The comment_judgement.json and translations.json are hashed at file level
rather than field level: the xhs guide consumes ``quote_candidates`` plus their
Chinese translations as opening hooks, and any change to either file should
invalidate the cached guide.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.pipeline.agent_io import file_sha256
from src.pipeline.paths import pipeline_path, publish_path

_PROMPT_PATH = Path("prompts/xhs_guide.md")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def xhs_guide_manifest_inputs(date: str) -> dict[str, Any]:
    """Build the manifest freshness inputs for ``xhs_guide.md``.

    Reads content/script/title from disk so the orchestrator and any audit
    derive an identical hash. The set of item fields mirrors what the xhs guide
    prompt is sensitive to (title, angle, category, keywords, score,
    comment count). comment_judgement.json and translations.json are hashed at
    file level because the guide pulls quote_candidates + their translations as
    opening hooks.
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

    judgement_path = pipeline_path(date, "comment_judgement.json")
    translations_path = pipeline_path(date, "translations.json")

    return {
        "script_title": title_data.get("title")
        or script_data.get("title")
        or "HN每日观察",
        "script_description": title_data.get("description")
        or script_data.get("description")
        or "",
        "items_json": json.dumps(items_payload, ensure_ascii=False, indent=2),
        "judgement_hash": file_sha256(judgement_path),
        "translations_hash": file_sha256(translations_path),
        "prompt_hash": file_sha256(_PROMPT_PATH),
        "date": date,
    }
