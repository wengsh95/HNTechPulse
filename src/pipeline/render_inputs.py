"""Stable input fingerprints used by the render-stage artifact cache."""

from typing import Any, Optional

from src.core.models import ContentPackage, Script
from src.pipeline.agent_io import file_sha256
from src.pipeline.paths import pipeline_path
from src.pipeline.script.io import script_editorial_hash


def build_render_inputs(
    script: Script,
    content: Optional[ContentPackage],
    date: str,
    renderer_name: str,
) -> dict[str, Any]:
    """Build the cache inputs shared by ``prepare_render`` and ``render``.

    Keeping this fingerprint in one pure helper prevents the two render steps
    from drifting apart as new cache inputs are added.
    """
    return {
        "script_editorial_hash": script_editorial_hash(script),
        "audio_manifest_hash": file_sha256(pipeline_path(date, "audio_manifest.json")),
        "content_hash": file_sha256(pipeline_path(date, "content.json")),
        "renderer": renderer_name,
        "content_item_count": len(content.items) if content is not None else 0,
    }
