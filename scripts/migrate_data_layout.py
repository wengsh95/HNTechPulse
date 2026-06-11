#!/usr/bin/env python3
"""One-shot migration of data/{date}/ from the flat layout to the bucketed layout.

Pre-refactor, every per-date artifact lived at the top of ``data/{date}/`` —
~30 different files, including intermediate caches, media, and agent state.
After the refactor, they're grouped into ``raw/``, ``pipeline/``, ``media/``,
``render/``, ``publish/``, ``agent/`` (see ``src/pipeline/paths.py``).

This script:

1. Walks every per-date directory under ``data/`` (skipping cross-day
   directories like ``data/_comment_cache`` and ``data/models``).
2. For each file/dir at the date root, decides which bucket it belongs to
   based on the ``LEGACY_FLAT_LAYOUT`` mapping.
3. Atomically renames each entry into its target bucket directory.
4. Rewrites any ``*.manifest.json`` files: the ``artifact`` field is updated
   to the new path so audits don't flag stale manifests.
5. Removes the four known orphan files: ``comment_intel.json``,
   ``comment_audit.md``, ``comment_audit.json``, ``comment_stance.json``,
   ``stance_distribution.local.json`` (the last is a user-side training
   artifact and is not part of the new layout).

Idempotent: if a date directory is already in the new layout (no flat
artifacts at the root), it is skipped.

Usage::

    uv run python scripts/migrate_data_layout.py             # migrate in place
    uv run python scripts/migrate_data_layout.py --dry-run   # show plan, no changes
    uv run python scripts/migrate_data_layout.py --date 2026-06-11  # single day
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline.paths import (  # noqa: E402
    agent_path,
    date_root,
    ensure_date_dirs,
    media_path,
    pipeline_audio_dir,
    pipeline_path,
    pipeline_segments_dir,
    pipeline_variants_root,
    publish_path,
    raw_downloaded_pages_dir,
    raw_path,
    render_path,
    render_remotion_dir,
)


# Map of legacy top-level entry name → (bucket_dir_factory, resolver).
# Each tuple's first element is a function that returns the target directory
# under data/{date}/, the second returns the typed-path version of the file
# (used for manifest rewriting).
def _pipeline_target(date: str, name: str) -> Path:
    return pipeline_path(date, name)


def _pipeline_audio_target(date: str, name: str) -> Path:
    return pipeline_audio_dir(date)


def _pipeline_segments_target(date: str, name: str) -> Path:
    return pipeline_segments_dir(date)


def _pipeline_variants_target(date: str, name: str) -> Path:
    return pipeline_variants_root(date)


def _raw_target(date: str, name: str) -> Path:
    return raw_path(date, name)


def _raw_pages_target(date: str, name: str) -> Path:
    return raw_downloaded_pages_dir(date)


def _media_target(date: str, name: str) -> Path:
    return media_path(date, name)


def _media_images_target(date: str, name: str) -> Path:
    from src.pipeline.paths import media_images_dir

    return media_images_dir(date)


def _render_target(date: str, name: str) -> Path:
    return render_path(date, name)


def _render_remotion_target(date: str, name: str) -> Path:
    return render_remotion_dir(date)


def _publish_target(date: str, name: str) -> Path:
    return publish_path(date, name)


def _agent_target(date: str, name: str) -> Path:
    return agent_path(date, name)


# Build the full mapping. The key is the legacy flat name; the value
# is a function that takes (date, name) and returns the typed target path.
PIPELINE_FILES = {
    "prefilter.json": _pipeline_target,
    "enrichment.json": _pipeline_target,
    "image_selection.json": _pipeline_target,
    "content.json": _pipeline_target,
    "comment_analysis.json": _pipeline_target,
    "comment_judgement.json": _pipeline_target,
    "translations.json": _pipeline_target,
    "script.json": _pipeline_target,
    "selected_variant.json": _pipeline_target,  # legacy alias — see agent_variants
}

PIPELINE_DIRS = {
    "audio": _pipeline_audio_target,
    "segments": _pipeline_segments_target,
    "variants": _pipeline_variants_target,
}

RAW_FILES = {"raw_stories.json": _raw_target}
RAW_DIRS = {"downloaded_pages": _raw_pages_target}

MEDIA_FILES = {
    "cover_bg.png": _media_target,
    "cover.png": _media_target,
    "cover_props.json": _media_target,
}
MEDIA_DIRS = {"images": _media_images_target}

RENDER_FILES = {"cli_props.json": _render_target}
RENDER_DIRS = {"remotion": _render_remotion_target}

PUBLISH_FILES = {
    "output.mp4": _publish_target,
    "title.json": _publish_target,
    "transcript.md": _publish_target,
    "publish_guide.md": _publish_target,
}

AGENT_FILES = {
    "pipeline_state.json": _agent_target,
    "agent_decision.json": _agent_target,
    "agent_events.jsonl": _agent_target,
    "agent_tasks.json": _agent_target,
    "selected_variant.json": _agent_target,
    "report.md": _agent_target,
    "agent_variant_decision.json": _agent_target,
}

# Orphans — files with no current code writer. Delete on migration.
ORPHAN_FILES = {
    "comment_intel.json",
    "comment_audit.md",
    "comment_audit.json",
    "comment_stance.json",
}


@dataclass
class DatePlan:
    date: str
    moves: list[tuple[Path, Path]] = field(default_factory=list)
    manifest_rewrites: list[Path] = field(default_factory=list)
    orphans_deleted: list[Path] = field(default_factory=list)
    already_migrated: bool = False


def _resolve_target(date: str, name: str) -> Path | None:
    """Pick the target path for a legacy flat entry. None if unknown."""
    # AGENT_FILES is checked first so that names like "selected_variant.json"
    # (which has a legacy alias under PIPELINE_FILES pointing to script.json)
    # go to the new agent/ bucket.
    for table in (
        AGENT_FILES,
        PIPELINE_FILES,
        RAW_FILES,
        MEDIA_FILES,
        RENDER_FILES,
        PUBLISH_FILES,
    ):
        if name in table:
            return table[name](date, name)
    for table in (PIPELINE_DIRS, RAW_DIRS, MEDIA_DIRS, RENDER_DIRS):
        if name in table:
            return table[name](date, name)
    return None


def _is_already_migrated(date_root_path: Path) -> bool:
    """Heuristic: a date is already migrated if it has no legacy flat files left."""
    for name in (
        list(PIPELINE_FILES)
        + list(PIPELINE_DIRS)
        + list(RAW_FILES)
        + list(RAW_DIRS)
        + list(MEDIA_FILES)
        + list(MEDIA_DIRS)
        + list(RENDER_FILES)
        + list(RENDER_DIRS)
        + list(PUBLISH_FILES)
        + list(AGENT_FILES)
    ):
        if (date_root_path / name).exists():
            return False
    return True


def _rewrite_manifest(manifest_path: Path) -> bool:
    """Update the ``artifact`` field of a manifest to its current path. Idempotent."""
    if not manifest_path.exists():
        return False
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    artifact = data.get("artifact")
    if not isinstance(artifact, str):
        return False
    # Manifests live next to the artifact: manifest_path = <artifact>.manifest.json
    new_artifact = manifest_path.with_suffix("")  # strip ".manifest.json"
    try:
        new_artifact = new_artifact.relative_to(ROOT)
    except ValueError:
        return False
    new_str = str(new_artifact).replace("\\", "/")
    if artifact == new_str:
        return False
    data["artifact"] = new_str
    manifest_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return True


def _rewrite_orphan_manifests() -> int:
    """Pass 2: scan for *.manifest.json whose ``artifact`` field no longer
    matches its on-disk path. Covers the case where a previous migration
    move left the manifest field stale."""
    count = 0
    for manifest_path in ROOT.glob("data/**/*.manifest.json"):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        artifact = data.get("artifact")
        if not isinstance(artifact, str):
            continue
        new_artifact = manifest_path.with_suffix("")
        try:
            new_artifact = new_artifact.relative_to(ROOT)
        except ValueError:
            continue
        new_str = str(new_artifact).replace("\\", "/")
        if artifact == new_str:
            continue
        data["artifact"] = new_str
        manifest_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        count += 1
    return count


def _plan_date(date: str) -> DatePlan:
    plan = DatePlan(date=date)
    base = date_root(date)
    if not base.exists():
        return plan
    if _is_already_migrated(base):
        plan.already_migrated = True
        return plan

    for entry in sorted(base.iterdir()):
        # Skip the new buckets (they may already exist as the result of a
        # partial migration).
        if entry.name in {
            "raw",
            "pipeline",
            "media",
            "render",
            "publish",
            "agent",
            "outputs",
        }:
            continue
        # Orphans
        if entry.name in ORPHAN_FILES:
            plan.orphans_deleted.append(entry)
            continue

        # Manifest sidecars piggyback on their artifact: when an artifact
        # moves, its .manifest.json should follow it. We record the manifest
        # path for rewriting only when the artifact itself is being moved.
        is_manifest = entry.name.endswith(".manifest.json")
        artifact_name = (
            entry.name[: -len(".manifest.json")] if is_manifest else entry.name
        )
        artifact_target = _resolve_target(date, artifact_name)
        if artifact_target is None:
            continue

        if is_manifest:
            manifest_target = artifact_target.with_name(
                artifact_target.name + ".manifest.json"
            )
            plan.moves.append((entry, manifest_target))
            plan.manifest_rewrites.append(manifest_target)
            continue

        plan.moves.append((entry, artifact_target))
        manifest_src = entry.with_name(entry.name + ".manifest.json")
        if manifest_src.exists():
            plan.manifest_rewrites.append(manifest_src)
    return plan


def _apply_plan(plan: DatePlan) -> None:
    if plan.already_migrated:
        return
    ensure_date_dirs(plan.date)
    for src, dest in plan.moves:
        if dest.exists():
            # Don't clobber a newer artifact in the new bucket. If both exist,
            # prefer the new-bucket version (the source in the new layout is
            # always the canonical one).
            if dest.is_dir():
                # Merge directory contents: move every child of src into dest.
                src.mkdir(parents=True, exist_ok=True)
                for child in src.iterdir():
                    child_dest = dest / child.name
                    if child_dest.exists():
                        continue
                    shutil.move(str(child), str(child_dest))
                # Best-effort: remove the now-empty source dir
                try:
                    src.rmdir()
                except OSError:
                    pass
            else:
                # New bucket file already exists; drop the legacy copy.
                if src.is_dir():
                    shutil.rmtree(src)
                else:
                    src.unlink()
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))

    for orphan in plan.orphans_deleted:
        try:
            if orphan.is_dir():
                shutil.rmtree(orphan)
            else:
                orphan.unlink()
        except OSError:
            pass

    for manifest in plan.manifest_rewrites:
        _rewrite_manifest(manifest)


def _format_plan(plan: DatePlan) -> dict[str, object]:
    def _rel(p: Path) -> str:
        try:
            return str(p.relative_to(ROOT)).replace("\\", "/")
        except ValueError:
            return str(p).replace("\\", "/")

    return {
        "date": plan.date,
        "already_migrated": plan.already_migrated,
        "moves": [{"from": _rel(src), "to": _rel(dest)} for src, dest in plan.moves],
        "manifest_rewrites": [_rel(p) for p in plan.manifest_rewrites],
        "orphans_deleted": [_rel(p) for p in plan.orphans_deleted],
    }


def _iter_dates(root: Path) -> Iterable[str]:
    data_dir = root / "data"
    if not data_dir.exists():
        return
    for child in sorted(data_dir.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("_") or child.name in {"models"}:
            continue
        yield child.name


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=None, help="Migrate a single date")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without moving anything",
    )
    args = parser.parse_args()

    dates = [args.date] if args.date else list(_iter_dates(ROOT))
    if not dates:
        print("No date directories found under data/", file=sys.stderr)
        return 0

    total_moved = 0
    total_orphans = 0
    total_already = 0
    for date in dates:
        plan = _plan_date(date)
        if plan.already_migrated:
            total_already += 1
            print(f"[skip] {date}: already migrated")
            continue
        print(
            f"[plan] {date}: "
            f"{len(plan.moves)} moves, "
            f"{len(plan.manifest_rewrites)} manifest rewrites, "
            f"{len(plan.orphans_deleted)} orphans"
        )
        if args.dry_run:
            print(json.dumps(_format_plan(plan), ensure_ascii=False, indent=2))
            continue
        _apply_plan(plan)
        total_moved += len(plan.moves)
        total_orphans += len(plan.orphans_deleted)
        print(f"[done] {date}")

    if not args.dry_run:
        # Second pass: any manifest whose ``artifact`` field doesn't match its
        # on-disk path is rewritten. This catches cases where a prior partial
        # migration left the field pointing at the old flat path.
        rewritten = _rewrite_orphan_manifests()
        print(
            f"\nMigrated {len(dates) - total_already} date(s): "
            f"{total_moved} moves, {total_orphans} orphans deleted, "
            f"{total_already} already migrated, "
            f"{rewritten} manifest(s) rewritten"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
