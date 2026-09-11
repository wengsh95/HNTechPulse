"""Typed artifact-presence facts for the video pipeline.

One table answers "is the artifact for step X ready (present/fresh enough to
reuse), and in one line why or why not".  It replaces the hard-coded presence
views that used to live in two places:

- ``PipelineProgress._check_cache`` (run-start summary, step-keyed triples)
- ``agent_audit._artifact_check`` (pre-publish audit, ``{name}_exists`` issues)

The two consumers keep their distinct outputs (progress text vs audit issues);
this module owns only the shared fact: which artifact path backs a step and
whether it is ready.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.pipeline.paths import (
    pipeline_audio_dir,
    pipeline_path,
    publish_path,
    render_path,
)


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


@dataclass(frozen=True)
class ArtifactPresence:
    """One step's readiness fact: artifact path, whether ready, and why."""

    name: str
    path: Path
    ready: bool
    detail: str


# Steps whose ready-state is decided by an artifact file existing, matching
# the legacy progress view's second block (content already loaded).
_FILE_READY_STEPS = [
    ("judge_comments", "comment_judgement.json", "comment judgement"),
    ("write_script", "script.json", "script"),
]


def presence_for_step(date: str) -> list[ArtifactPresence]:
    """Answer step-by-step readiness for a run, one record per step.

    The judgment and wording mirror the legacy ``_check_cache`` output
    byte-for-byte; order follows the video chain.  Returns every step in the
    chain regardless of the actual request; consumers filter by their own
    step list, matching the legacy progress summary.
    """
    entries: list[ArtifactPresence] = []

    content_path = pipeline_path(date, "content.json")
    content_data = _read_json(content_path)

    # fetch
    if content_data is not None:
        n = len(content_data.get("items", []))
        entries.append(
            ArtifactPresence("fetch", content_path, True, f"{n} items cached")
        )
    else:
        entries.append(ArtifactPresence("fetch", content_path, False, "will fetch"))

    # Content-mutating steps: judged from content.json when present, otherwise
    # all say "fetch first".  Later steps run unconditionally, matching the
    # legacy progress view (their readiness is independent of content).
    if content_data is None:
        for step in ("prefilter", "fetch_comments", "enrich_articles"):
            entries.append(ArtifactPresence(step, content_path, False, "fetch first"))
    else:
        items = content_data.get("items", [])

        # prefilter
        prefilter_path = pipeline_path(date, "prefilter.json")
        prefilter_ready = prefilter_path.exists()
        entries.append(
            ArtifactPresence(
                "prefilter",
                prefilter_path,
                prefilter_ready,
                "prefilter cached" if prefilter_ready else "will prefilter",
            )
        )

        # fetch_comments: ready when every item has comments attached
        comments_path = content_path
        comments_ready = bool(items) and all(
            i.get("comment_count", 0) > 0 for i in items
        )
        entries.append(
            ArtifactPresence(
                "fetch_comments",
                comments_path,
                comments_ready,
                "comments attached" if comments_ready else "will fetch comments",
            )
        )

        # enrich_articles: no item still pending enrichment
        pending_states = {None, "pending", "fetch_failed", "extraction_failed"}
        pending = [i for i in items if i.get("enrichment_source") in pending_states]
        enrich_ready = bool(items) and not pending
        entries.append(
            ArtifactPresence(
                "enrich_articles",
                content_path,
                enrich_ready,
                (
                    "articles enriched"
                    if enrich_ready
                    else f"{len(pending)}/{len(items)} need enrichment"
                ),
            )
        )

    # judge_comments / write_script
    for step, filename, label in _FILE_READY_STEPS:
        ready_path = pipeline_path(date, filename)
        ready = ready_path.exists()
        entries.append(
            ArtifactPresence(
                step,
                ready_path,
                ready,
                f"{label} cached" if ready else f"will generate {label}",
            )
        )

    # synthesize_audio: non-empty audio dir
    audio_dir = pipeline_audio_dir(date)
    audio_ready = audio_dir.exists() and any(audio_dir.iterdir())
    entries.append(
        ArtifactPresence(
            "synthesize_audio",
            audio_dir,
            audio_ready,
            "audio cached" if audio_ready else "will synthesize",
        )
    )

    # title
    title_path = publish_path(date, "title.json")
    title_ready = title_path.exists()
    entries.append(
        ArtifactPresence(
            "title",
            title_path,
            title_ready,
            "title cached" if title_ready else "will generate title",
        )
    )

    # cover_image (background art)
    cover_bg_path = render_path(date, "cover_bg.png")
    cover_bg_ready = cover_bg_path.exists()
    entries.append(
        ArtifactPresence(
            "cover_image",
            cover_bg_path,
            cover_bg_ready,
            "cover image cached" if cover_bg_ready else "will generate cover image",
        )
    )

    # cover_thumbnail
    cover_path = publish_path(date, "cover.png")
    cover_ready = cover_path.exists()
    entries.append(
        ArtifactPresence(
            "cover_thumbnail",
            cover_path,
            cover_ready,
            "cover thumbnail cached" if cover_ready else "will render cover thumbnail",
        )
    )

    # storyboard drives both draft_storyboard and apply_storyboard
    storyboard_path = pipeline_path(date, "storyboard.json")
    storyboard_ready = storyboard_path.exists()
    entries.append(
        ArtifactPresence(
            "draft_storyboard",
            storyboard_path,
            storyboard_ready,
            "storyboard cached" if storyboard_ready else "will draft storyboard",
        )
    )
    entries.append(
        ArtifactPresence(
            "apply_storyboard",
            storyboard_path,
            storyboard_ready,
            (
                "storyboard cached"
                if storyboard_ready
                else "no storyboard; keep generated templates"
            ),
        )
    )

    # prepare_render (also writes publish_guide.md)
    props_file = render_path(date, "cli_props.json")
    guide_file = publish_path(date, "publish_guide.md")
    props_ready = props_file.exists()
    if props_ready:
        detail = "props.json cached"
        if guide_file.exists():
            detail += "; publish guide cached"
    else:
        detail = "will write props.json + publish guide"
    entries.append(ArtifactPresence("prepare_render", props_file, props_ready, detail))

    return entries


def publish_presence(date: str) -> list[ArtifactPresence]:
    """Presence facts for the managed publish tail.

    ``cover`` here means the rendered cover thumbnail (``cover.png``), matching
    the pre-publish audit's ``cover_exists`` check.
    """
    records = [
        ("title", publish_path(date, "title.json")),
        ("cover", publish_path(date, "cover.png")),
        ("publish_guide", publish_path(date, "publish_guide.md")),
    ]
    return [
        ArtifactPresence(
            name,
            path,
            path.exists(),
            f"{path.name} present" if path.exists() else f"{path.name} missing",
        )
        for name, path in records
    ]
