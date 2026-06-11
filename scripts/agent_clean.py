#!/usr/bin/env python3
"""Date-scoped cleanup helper for agents.

Defaults to dry-run. Use --yes to actually delete the listed files/directories.
All targets are constrained under data/{date} to avoid accidental workspace
damage.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline.paths import (  # noqa: E402
    agent_path,
    date_root,
    pipeline_audio_dir,
    pipeline_path,
    pipeline_variants_root,
    publish_path,
    render_path,
    render_remotion_dir,
)


def _default_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _date_base(date: str) -> Path:
    return date_root(date).resolve()


def _inside_base(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base)
        return True
    except ValueError:
        return False


def _targets(date: str, scope: str) -> list[Path]:
    base = date_root(date)
    if scope == "render":
        return [
            publish_path(date, "output.mp4"),
            render_remotion_dir(date) / "chunks",
            render_remotion_dir(date) / "single.mp4",
            base / "review_stills",
        ]
    if scope == "props":
        return [
            render_path(date, "cli_props.json"),
            render_path(date, "cli_props.json").with_suffix(
                render_path(date, "cli_props.json").suffix + ".manifest.json"
            ),
            render_remotion_dir(date) / "public" / "props.json",
        ]
    if scope == "script":
        script_path = pipeline_path(date, "script.json")
        return [
            script_path,
            script_path.with_suffix(script_path.suffix + ".manifest.json"),
            pipeline_variants_root(date),
            agent_path(date, "selected_variant.json"),
            agent_path(date, "agent_variant_decision.json"),
        ]
    if scope == "tts":
        return [pipeline_audio_dir(date)]
    raise ValueError(f"Unknown scope: {scope}")


def _existing(paths: Iterable[Path], base: Path) -> list[Path]:
    result = []
    for path in paths:
        resolved = path.resolve()
        if not _inside_base(resolved, base):
            raise RuntimeError(f"Refusing to clean outside {base}: {resolved}")
        if resolved.exists():
            result.append(resolved)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean date-scoped agent artifacts")
    parser.add_argument("--date", default=_default_date())
    parser.add_argument(
        "--scope",
        choices=["render", "props", "script", "tts"],
        required=True,
    )
    parser.add_argument("--yes", action="store_true", help="Actually delete targets")
    args = parser.parse_args()

    base = _date_base(args.date)
    targets = _existing(_targets(args.date, args.scope), base)
    payload = {
        "date": args.date,
        "scope": args.scope,
        "dry_run": not args.yes,
        "targets": [str(t).replace("\\", "/") for t in targets],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not args.yes:
        return 0

    for target in targets:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
