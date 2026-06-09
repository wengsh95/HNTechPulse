#!/usr/bin/env python3
"""Refresh cover thumbnail overlays from the latest title.json."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.providers.renderer.binary_finder import find_npx
from src.utils.atomic_io import atomic_write_json


BRAND_HINTS = (
    ("Meta", ("Meta", "Instagram", "AI客服")),
    ("Google", ("Google", "Gemma")),
    ("Cloudflare", ("Cloudflare", "Vite", "VoidZero")),
    ("Steam", ("Steam", "Valve")),
    ("Ladybird", ("Ladybird",)),
    ("NVIDIA", ("NVIDIA", "N1", "N1X")),
    ("Anthropic", ("Anthropic", "Claude")),
    ("Apple", ("Apple", "macOS", "iOS")),
)

COVER_TEMPLATES = (
    "left-hero",
    "right-hero",
    "bottom-banner",
    "poster-panel",
)


def detect_cover_brand(payload: dict) -> str:
    text_parts = [
        str(payload.get("title") or ""),
        str(payload.get("cover_title") or ""),
        str(payload.get("description") or ""),
        str(payload.get("cover_subtitle") or ""),
        " ".join(str(tag) for tag in payload.get("cover_tags") or []),
    ]
    text = "\n".join(text_parts)
    for brand, hints in BRAND_HINTS:
        if any(hint in text for hint in hints):
            return brand
    return ""


def choose_cover_title(payload: dict) -> str:
    cover_title = str(payload.get("cover_title") or "").strip()
    title = str(payload.get("title") or "").strip()
    if title and re.search(r"\d", title) and not re.search(r"\d", cover_title):
        compact = re.sub(r"\s*Instagram\s*", "", title)
        compact = re.sub(r"\s+", " ", compact).strip()
        if len(compact) <= 26:
            return compact
    return cover_title or title or "HN TechPulse"


def refresh_cover(
    date: str,
    *,
    template: str = "left-hero",
    variant_output: bool = False,
) -> Path:
    if template not in COVER_TEMPLATES:
        raise ValueError(
            f"Unknown cover template {template!r}; choose from {COVER_TEMPLATES}"
        )
    base = ROOT / "data" / date
    title_path = base / "title.json"
    bg_path = base / "cover_bg.png"
    props_path = base / (
        f"cover_props.{template}.json" if variant_output else "cover_props.json"
    )
    cover_path = base / (f"cover_{template}.png" if variant_output else "cover.png")

    if not title_path.exists():
        raise FileNotFoundError(f"Missing title metadata: {title_path}")
    if not bg_path.exists():
        raise FileNotFoundError(f"Missing cover background: {bg_path}")

    title_payload = json.loads(title_path.read_text(encoding="utf-8"))
    if not isinstance(title_payload, dict):
        raise ValueError(f"Invalid title metadata: {title_path}")

    props = {
        "backgroundImage": bg_path.name,
        "title": choose_cover_title(title_payload),
        "subtitle": title_payload.get("cover_subtitle") or "",
        "tags": (title_payload.get("cover_tags") or [])[:2],
        "brandLogo": detect_cover_brand(title_payload),
        "coverTemplate": template,
        "dateLabel": date,
    }
    atomic_write_json(props_path, props)

    public_bg = base / "remotion" / "public" / bg_path.name
    public_bg.parent.mkdir(parents=True, exist_ok=True)
    try:
        same_file = public_bg.samefile(bg_path)
    except FileNotFoundError:
        same_file = False
    if not same_file:
        shutil.copy2(bg_path, public_bg)

    npx_path = find_npx()
    if not npx_path:
        raise FileNotFoundError(
            "npx not found; install Node.js or set PATH to include npx"
        )

    remotion_dir = ROOT / "src" / "providers" / "renderer" / "remotion"
    cmd = [
        npx_path,
        "remotion",
        "still",
        "CoverThumbnail",
        f"--props={props_path.resolve()}",
        "--frame=0",
        f"--output={cover_path.resolve()}",
        f"--public-dir={(base / 'remotion' / 'public').resolve()}",
    ]
    result = subprocess.run(
        cmd,
        cwd=str(remotion_dir),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip(), file=sys.stderr)
    if not cover_path.exists() or cover_path.stat().st_size <= 0:
        raise RuntimeError(f"Cover render did not produce a valid file: {cover_path}")
    return cover_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dates", nargs="+")
    parser.add_argument(
        "--template",
        choices=COVER_TEMPLATES,
        default="left-hero",
        help="Template to render into cover.png.",
    )
    parser.add_argument(
        "--all-templates",
        action="store_true",
        help="Render all templates as cover_{template}.png without replacing cover.png.",
    )
    args = parser.parse_args()

    for date in args.dates:
        if args.all_templates:
            for template in COVER_TEMPLATES:
                cover_path = refresh_cover(date, template=template, variant_output=True)
                print(f"Rendered cover template for {date} [{template}]: {cover_path}")
        else:
            cover_path = refresh_cover(date, template=args.template)
            print(
                f"Refreshed cover thumbnail for {date} [{args.template}]: {cover_path}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
