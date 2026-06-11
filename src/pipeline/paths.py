"""Centralized per-date data directory layout.

All pipeline artifacts under ``data/{date}/`` are grouped by lifecycle into
subdirectories. This module is the single source of truth for those paths —
every other module should import from here instead of building
``f"data/{date}/foo.json"`` strings directly.

Layout::

    data/{date}/
    ├── raw/         raw_stories.json, downloaded_pages/
    ├── pipeline/    prefilter, enrichment, content, comment_*, script,
    │                segments/, variants/, audio/
    ├── media/       images/, cover_bg.png, cover.png, cover_props.json
    ├── render/      remotion/{chunks,public}/, cli_props.json
    ├── publish/     output.mp4, title.json, transcript.md, publish_guide.md
    ├── agent/       pipeline_state.json, agent_decision.json,
    │                agent_events.jsonl, selected_variant.json, report.md
    └── outputs/     (organize_outputs.py mirror — unchanged)

The helpers return ``pathlib.Path`` so callers can ``.parent.mkdir`` /
``.write_text`` / etc. directly. Paths are not created on import; use
``ensure_date_dirs(date)`` to materialize the layout for a fresh run.
"""

from __future__ import annotations

from pathlib import Path

# Top-level shared roots (not per-date).
COMMENT_CACHE_DIR = Path("data/_comment_cache")
MODELS_DIR = Path("data/models")


def date_root(date: str) -> Path:
    """Return the per-date root directory."""
    return Path(f"data/{date}")


# Bucket roots ─────────────────────────────────────────────────────────────

RAW_DIR = "raw"
PIPELINE_DIR = "pipeline"
MEDIA_DIR = "media"
RENDER_DIR = "render"
PUBLISH_DIR = "publish"
AGENT_DIR = "agent"
OUTPUTS_DIR = "outputs"


def raw_root(date: str) -> Path:
    return date_root(date) / RAW_DIR


def pipeline_root(date: str) -> Path:
    return date_root(date) / PIPELINE_DIR


def media_root(date: str) -> Path:
    return date_root(date) / MEDIA_DIR


def render_root(date: str) -> Path:
    return date_root(date) / RENDER_DIR


def publish_root(date: str) -> Path:
    return date_root(date) / PUBLISH_DIR


def agent_root(date: str) -> Path:
    return date_root(date) / AGENT_DIR


# Pipeline sub-buckets (each holds multiple artifacts)
def pipeline_segments_dir(date: str) -> Path:
    return pipeline_root(date) / "segments"


def pipeline_variants_root(date: str) -> Path:
    return pipeline_root(date) / "variants"


def pipeline_audio_dir(date: str) -> Path:
    return pipeline_root(date) / "audio"


# Raw sub-buckets
def raw_downloaded_pages_dir(date: str) -> Path:
    return raw_root(date) / "downloaded_pages"


# Media sub-buckets
def media_images_dir(date: str) -> Path:
    return media_root(date) / "images"


# Render sub-buckets
def render_remotion_dir(date: str) -> Path:
    return render_root(date) / "remotion"


# Public API — name → (bucket, name) ──────────────────────────────────────
#
# To add a new artifact: pick its lifecycle bucket and add an entry below.
# Use the ``pipeline_path`` / ``media_path`` / etc. helpers to resolve it.

_PIPELINE_FILES: dict[str, str] = {
    "prefilter.json": "prefilter.json",
    "enrichment.json": "enrichment.json",
    "image_selection.json": "image_selection.json",
    "content.json": "content.json",
    "comment_analysis.json": "comment_analysis.json",
    "comment_judgement.json": "comment_judgement.json",
    "translations.json": "translations.json",
    "script.json": "script.json",
    "selected_variant.json": "script.json",  # legacy alias — see agent_variants.promote_variant_script
}

_MEDIA_FILES: dict[str, str] = {
    "cover_bg.png": "cover_bg.png",
    "cover.png": "cover.png",
    "cover_props.json": "cover_props.json",
}

_PUBLISH_FILES: dict[str, str] = {
    "output.mp4": "output.mp4",
    "title.json": "title.json",
    "transcript.md": "transcript.md",
    "publish_guide.md": "publish_guide.md",
}

_AGENT_FILES: dict[str, str] = {
    "pipeline_state.json": "pipeline_state.json",
    "agent_decision.json": "agent_decision.json",
    "agent_events.jsonl": "agent_events.jsonl",
    "agent_tasks.json": "agent_tasks.json",
    "agent_variant_decision.json": "agent_variant_decision.json",
    "selected_variant.json": "selected_variant.json",
    "report.md": "report.md",
}

_RAW_FILES: dict[str, str] = {
    "raw_stories.json": "raw_stories.json",
}

_RENDER_FILES: dict[str, str] = {
    "cli_props.json": "cli_props.json",
}


def pipeline_path(date: str, name: str) -> Path:
    """Resolve a named artifact under ``data/{date}/pipeline/``."""
    if name not in _PIPELINE_FILES:
        raise KeyError(
            f"Unknown pipeline artifact: {name!r}. Known: {sorted(_PIPELINE_FILES)}"
        )
    return pipeline_root(date) / _PIPELINE_FILES[name]


def media_path(date: str, name: str) -> Path:
    """Resolve a named artifact under ``data/{date}/media/``."""
    if name not in _MEDIA_FILES:
        raise KeyError(
            f"Unknown media artifact: {name!r}. Known: {sorted(_MEDIA_FILES)}"
        )
    return media_root(date) / _MEDIA_FILES[name]


def publish_path(date: str, name: str) -> Path:
    """Resolve a named artifact under ``data/{date}/publish/``."""
    if name not in _PUBLISH_FILES:
        raise KeyError(
            f"Unknown publish artifact: {name!r}. Known: {sorted(_PUBLISH_FILES)}"
        )
    return publish_root(date) / _PUBLISH_FILES[name]


def agent_path(date: str, name: str) -> Path:
    """Resolve a named artifact under ``data/{date}/agent/``."""
    if name not in _AGENT_FILES:
        raise KeyError(
            f"Unknown agent artifact: {name!r}. Known: {sorted(_AGENT_FILES)}"
        )
    return agent_root(date) / _AGENT_FILES[name]


def raw_path(date: str, name: str) -> Path:
    """Resolve a named artifact under ``data/{date}/raw/``."""
    if name not in _RAW_FILES:
        raise KeyError(f"Unknown raw artifact: {name!r}. Known: {sorted(_RAW_FILES)}")
    return raw_root(date) / _RAW_FILES[name]


def render_path(date: str, name: str) -> Path:
    """Resolve a named artifact under ``data/{date}/render/``."""
    if name not in _RENDER_FILES:
        raise KeyError(
            f"Unknown render artifact: {name!r}. Known: {sorted(_RENDER_FILES)}"
        )
    return render_root(date) / _RENDER_FILES[name]


# Backwards-compatibility aliases for the pre-refactor flat layout.
# These are the file names the pipeline used to write at data/{date}/<name>
# before this refactor. New code should call the typed helpers above; these
# constants exist so tests and migration logic can reference the old paths.
LEGACY_FLAT_LAYOUT = {
    "raw_stories.json",
    "agent_tasks.json",
    "prefilter.json",
    "enrichment.json",
    "image_selection.json",
    "content.json",
    "comment_analysis.json",
    "comment_judgement.json",
    "translations.json",
    "script.json",
    "audio",
    "downloaded_pages",
    "images",
    "cover_bg.png",
    "cover.png",
    "cover_props.json",
    "remotion",
    "cli_props.json",
    "output.mp4",
    "title.json",
    "transcript.md",
    "publish_guide.md",
    "pipeline_state.json",
    "agent_decision.json",
    "agent_events.jsonl",
    "selected_variant.json",
    "agent_variant_decision.json",
    "report.md",
    "variants",
    "segments",
    "manifest.json",
}


def ensure_date_dirs(date: str) -> None:
    """Create the full per-date directory tree. Idempotent."""
    for d in (
        raw_root(date),
        pipeline_root(date),
        pipeline_segments_dir(date),
        pipeline_variants_root(date),
        pipeline_audio_dir(date),
        media_root(date),
        media_images_dir(date),
        raw_downloaded_pages_dir(date),
        render_root(date),
        render_remotion_dir(date),
        publish_root(date),
        agent_root(date),
    ):
        d.mkdir(parents=True, exist_ok=True)


__all__ = [
    "COMMENT_CACHE_DIR",
    "MODELS_DIR",
    "date_root",
    "raw_root",
    "pipeline_root",
    "media_root",
    "render_root",
    "publish_root",
    "agent_root",
    "pipeline_segments_dir",
    "pipeline_variants_root",
    "pipeline_audio_dir",
    "raw_downloaded_pages_dir",
    "media_images_dir",
    "render_remotion_dir",
    "pipeline_path",
    "media_path",
    "publish_path",
    "agent_path",
    "raw_path",
    "render_path",
    "ensure_date_dirs",
    "LEGACY_FLAT_LAYOUT",
]
