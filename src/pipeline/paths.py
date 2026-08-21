"""Centralized per-date data directory layout.

All pipeline artifacts under ``data/{month}/{date}/`` are grouped by lifecycle into
subdirectories. This module is the single source of truth for those paths —
every other module should import from here instead of building
``f"data/{month}/{date}/foo.json"`` strings directly.

Layout::

    data/{month}/{date}/
    ├── raw/         raw_stories.json, downloaded_pages/
    ├── pipeline/    prefilter, enrichment, content, comment_*, script,
    │                audio_manifest, segments/, variants/, audio/
    ├── media/       images/
    ├── render/      remotion/{chunks,public}/, cli_props.json
    ├── publish/     output.mp4, title.json, transcript.md, publish_guide.md,
    │                cover_bg.png, cover.png
    ├── agent/       workflow_video.json, agent_events.jsonl,
    │                agent_tasks.json, report.md
    └── outputs/     (internal/tools/organize_outputs.py mirror — unchanged)

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
    return month_root(date) / date


def month_root(date: str) -> Path:
    """Return the month bucket for a date-like run id."""
    month = date[:7] if len(date) >= 7 and date[4:5] == "-" else date
    return Path("data") / month


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
    "storyboard.json": "storyboard.json",
    "quick_news.json": "quick_news.json",
    "story_images.json": "story_images.json",
    "video_structure.json": "video_structure.json",
    "subtitle_plan.json": "subtitle_plan.json",
    "script_review.json": "script_review.json",
    "audio_manifest.json": "audio_manifest.json",
    "transcript.md": "transcript.md",
}

_MEDIA_FILES: dict[str, str] = {}

_PUBLISH_FILES: dict[str, str] = {
    "output.mp4": "output.mp4",
    "title.json": "title.json",
    "publish_guide.md": "publish_guide.md",
    "cover.png": "cover.png",
    "cover_b1_t1.png": "cover_b1_t1.png",
    "cover_b1_t2.png": "cover_b1_t2.png",
    "cover_b1_t3.png": "cover_b1_t3.png",
    "cover_b2_t1.png": "cover_b2_t1.png",
    "cover_b2_t2.png": "cover_b2_t2.png",
    "cover_b2_t3.png": "cover_b2_t3.png",
    "cover_b3_t1.png": "cover_b3_t1.png",
    "cover_b3_t2.png": "cover_b3_t2.png",
    "cover_b3_t3.png": "cover_b3_t3.png",
}

_AGENT_FILES: dict[str, str] = {
    "workflow_video.json": "workflow_video.json",
    "agent_decision.json": "agent_decision.json",
    "agent_events.jsonl": "agent_events.jsonl",
    "agent_tasks.json": "agent_tasks.json",
    "selection_lock.json": "selection_lock.json",
    "script_lock.json": "script_lock.json",
    "script_approval.json": "script_approval.json",
    "agent_variant_decision.json": "agent_variant_decision.json",
    "report.md": "report.md",
}

_RAW_FILES: dict[str, str] = {
    "raw_stories.json": "raw_stories.json",
}

_RENDER_FILES: dict[str, str] = {
    "cli_props.json": "cli_props.json",
    "cover_bg.png": "cover_bg.png",
    "cover_bg_v2.png": "cover_bg_v2.png",
    "cover_bg_v3.png": "cover_bg_v3.png",
    "cover_bg_v4.png": "cover_bg_v4.png",
    "cover_props_v1.json": "cover_props_v1.json",
    "cover_props_v2.json": "cover_props_v2.json",
    "cover_props_v3.json": "cover_props_v3.json",
    "cover_props_b1_t1.json": "cover_props_b1_t1.json",
    "cover_props_b1_t2.json": "cover_props_b1_t2.json",
    "cover_props_b1_t3.json": "cover_props_b1_t3.json",
    "cover_props_b2_t1.json": "cover_props_b2_t1.json",
    "cover_props_b2_t2.json": "cover_props_b2_t2.json",
    "cover_props_b2_t3.json": "cover_props_b2_t3.json",
    "cover_props_b3_t1.json": "cover_props_b3_t1.json",
    "cover_props_b3_t2.json": "cover_props_b3_t2.json",
    "cover_props_b3_t3.json": "cover_props_b3_t3.json",
    "cover_b1_t1.png": "cover_b1_t1.png",
    "cover_b1_t2.png": "cover_b1_t2.png",
    "cover_b1_t3.png": "cover_b1_t3.png",
    "cover_b2_t1.png": "cover_b2_t1.png",
    "cover_b2_t2.png": "cover_b2_t2.png",
    "cover_b2_t3.png": "cover_b2_t3.png",
    "cover_b3_t1.png": "cover_b3_t1.png",
    "cover_b3_t2.png": "cover_b3_t2.png",
    "cover_b3_t3.png": "cover_b3_t3.png",
}


def pipeline_path(date: str, name: str) -> Path:
    """Resolve a named artifact under ``data/{month}/{date}/pipeline/``."""
    if name not in _PIPELINE_FILES:
        raise KeyError(
            f"Unknown pipeline artifact: {name!r}. Known: {sorted(_PIPELINE_FILES)}"
        )
    return pipeline_root(date) / _PIPELINE_FILES[name]


def media_path(date: str, name: str) -> Path:
    """Resolve a named artifact under ``data/{month}/{date}/media/``."""
    if name not in _MEDIA_FILES:
        raise KeyError(
            f"Unknown media artifact: {name!r}. Known: {sorted(_MEDIA_FILES)}"
        )
    return media_root(date) / _MEDIA_FILES[name]


def publish_path(date: str, name: str) -> Path:
    """Resolve a named artifact under ``data/{month}/{date}/publish/``."""
    if name not in _PUBLISH_FILES:
        raise KeyError(
            f"Unknown publish artifact: {name!r}. Known: {sorted(_PUBLISH_FILES)}"
        )
    return publish_root(date) / _PUBLISH_FILES[name]


def agent_path(date: str, name: str) -> Path:
    """Resolve a named artifact under ``data/{month}/{date}/agent/``."""
    if name not in _AGENT_FILES:
        raise KeyError(
            f"Unknown agent artifact: {name!r}. Known: {sorted(_AGENT_FILES)}"
        )
    return agent_root(date) / _AGENT_FILES[name]


def raw_path(date: str, name: str) -> Path:
    """Resolve a named artifact under ``data/{month}/{date}/raw/``."""
    if name not in _RAW_FILES:
        raise KeyError(f"Unknown raw artifact: {name!r}. Known: {sorted(_RAW_FILES)}")
    return raw_root(date) / _RAW_FILES[name]


def render_path(date: str, name: str) -> Path:
    """Resolve a named artifact under ``data/{month}/{date}/render/``."""
    if name not in _RENDER_FILES:
        raise KeyError(
            f"Unknown render artifact: {name!r}. Known: {sorted(_RENDER_FILES)}"
        )
    return render_root(date) / _RENDER_FILES[name]


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
    "month_root",
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
]
