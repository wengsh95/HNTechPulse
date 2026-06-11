"""Agent-facing event, manifest, and state helpers."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.pipeline.paths import agent_path
from src.utils.atomic_io import atomic_write_json


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def agent_event_path(date: str) -> Path:
    return agent_path(date, "agent_events.jsonl")


def append_agent_event(date: str, event: str, **payload: Any) -> None:
    path = agent_event_path(date)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "time": utc_now(),
        "event": event,
        **payload,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def pipeline_state_path(date: str) -> Path:
    return agent_path(date, "pipeline_state.json")


def load_pipeline_state(date: str) -> dict[str, Any] | None:
    path = pipeline_state_path(date)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def file_sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(data: Any) -> str:
    text = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_artifact_manifest(
    artifact_path: Path | str,
    *,
    step: str,
    date: str,
    inputs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    path = Path(artifact_path)
    manifest_path = path.with_suffix(path.suffix + ".manifest.json")
    payload = {
        "schema_version": 1,
        "created_at": utc_now(),
        "date": date,
        "step": step,
        "artifact": str(path).replace("\\", "/"),
        "artifact_hash": file_sha256(path),
        "inputs": inputs or {},
        "input_hash": stable_hash(inputs or {}),
        "config": {
            "model": (config or {}).get("llm", {}).get("model"),
            "fast_model": (config or {})
            .get("llm", {})
            .get("fast", {})
            .get("model", (config or {}).get("llm", {}).get("fast_model")),
            "target_story_count": (config or {})
            .get("pipeline", {})
            .get("target_story_count"),
        },
        "extra": extra or {},
    }
    atomic_write_json(manifest_path, payload)
    append_agent_event(
        date,
        "artifact_manifest_written",
        step=step,
        artifact=str(path).replace("\\", "/"),
        manifest=str(manifest_path).replace("\\", "/"),
    )
    return manifest_path
