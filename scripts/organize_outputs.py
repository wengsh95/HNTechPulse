#!/usr/bin/env python3
"""Create a tidy, publish-facing outputs folder for a date run.

The pipeline keeps canonical artifacts at data/{date}/ because status checks,
audit, render review, and cache invalidation all depend on those paths. This
script mirrors the useful deliverables into data/{date}/outputs/ so humans can
review/share the run without sorting through every intermediate cache file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


OUTPUT_GROUPS: dict[str, list[str]] = {
    "final": [
        "output.mp4",
        "cover.png",
    ],
    "publish": [
        "publish_guide.md",
        "transcript.md",
        "title.json",
    ],
    "script": [
        "script.json",
        "selected_variant.json",
        "agent_decision.json",
        "agent_variant_decision.json",
    ],
    "render": [
        "cli_props.json",
        "cli_props.json.manifest.json",
    ],
    "sources": [
        "content.json",
        "enrichment.json",
        "comment_analysis.json",
        "comment_judgement.json",
        "translations.json",
        "prefilter.json",
    ],
}


COVER_PATTERNS = [
    "cover_*.png",
    "cover_props*.json",
    "cover_bg.png",
]


def _default_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_file(src: Path, dest: Path) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return {
        "source": str(src.relative_to(ROOT)).replace("\\", "/"),
        "output": str(dest.relative_to(ROOT)).replace("\\", "/"),
        "size": dest.stat().st_size,
        "sha256": _sha256(dest),
    }


def organize_outputs(date: str, *, refresh: bool = False) -> dict[str, Any]:
    base = ROOT / "data" / date
    if not base.exists():
        raise FileNotFoundError(f"Date directory does not exist: {base}")

    output_root = base / "outputs"
    if refresh and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    copied: list[dict[str, Any]] = []
    missing: list[str] = []

    for group, names in OUTPUT_GROUPS.items():
        for name in names:
            src = base / name
            if not src.exists():
                missing.append(str(src.relative_to(ROOT)).replace("\\", "/"))
                continue
            copied.append(_copy_file(src, output_root / group / src.name))

    cover_dest = output_root / "cover"
    seen_cover_sources: set[Path] = set()
    for pattern in COVER_PATTERNS:
        for src in sorted(base.glob(pattern)):
            if not src.is_file() or src in seen_cover_sources:
                continue
            seen_cover_sources.add(src)
            copied.append(_copy_file(src, cover_dest / src.name))

    guide_path = output_root / "README.md"
    guide_path.write_text(
        "\n".join(
            [
                f"# Outputs for {date}",
                "",
                "Canonical pipeline files remain one level up in `data/{date}/`.",
                "This folder is a tidy mirror for review, publishing, and handoff.",
                "",
                "## Folders",
                "",
                "- `final/`: final video and selected cover.",
                "- `publish/`: title metadata, transcript, and publish guide.",
                "- `script/`: selected script and agent decisions.",
                "- `render/`: render props useful for debugging or review stills.",
                "- `sources/`: compact source/context JSON used to produce the script.",
                "- `cover/`: cover background, selected cover, and cover variants.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    manifest = {
        "schema_version": 1,
        "date": date,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "output_root": str(output_root.relative_to(ROOT)).replace("\\", "/"),
        "copied_count": len(copied),
        "missing": missing,
        "files": copied,
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Mirror final artifacts into outputs/")
    parser.add_argument("--date", default=_default_date())
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Delete and recreate data/{date}/outputs before copying.",
    )
    args = parser.parse_args()

    manifest = organize_outputs(args.date, refresh=args.refresh)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
