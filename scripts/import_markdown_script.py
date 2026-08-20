#!/usr/bin/env python3
"""Import an editorial markdown video script into the pipeline.

Usage:
  uv run python scripts/import_markdown_script.py --date YYYY-MM-DD [--file path/to/script.md]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline.content_io import load_content_package
from src.pipeline.script.markdown_importer import import_markdown_script


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import Markdown video script into pipeline."
    )
    parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD format")
    parser.add_argument(
        "--file",
        help="Path to markdown script file (default: data/.../video_script.md)",
    )
    args = parser.parse_args()

    date = args.date
    file_path = Path(args.file) if args.file else None

    # Load content package if exists for story metadata enrichment
    try:
        content = load_content_package(date)
    except Exception:
        content = None

    try:
        script, saved_path = import_markdown_script(
            date, file_path=file_path, content=content
        )
        print(f" Successfully imported Markdown script into {saved_path}")
        print(f" Script title: {script.title}")
        print(f" Total segments: {len(script.segments)}")
        print(
            f" Total scenes/shots: {sum(len(s.scene_elements) for s in script.segments)}"
        )
        print(f" Saved and locked script.json & storyboard.json for {date}")
        return 0
    except Exception as exc:
        print(f" Failed to import markdown script: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
