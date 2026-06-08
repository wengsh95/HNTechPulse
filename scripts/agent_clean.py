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


def _default_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _date_base(date: str) -> Path:
    return (Path("data") / date).resolve()


def _inside_base(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base)
        return True
    except ValueError:
        return False


def _targets(date: str, scope: str) -> list[Path]:
    base = Path("data") / date
    if scope == "render":
        return [
            base / "output.mp4",
            base / "remotion" / "chunks",
            base / "remotion" / "single.mp4",
            base / "review_stills",
        ]
    if scope == "props":
        return [
            base / "cli_props.json",
            base / "cli_props.json.manifest.json",
            base / "remotion" / "public" / "props.json",
        ]
    if scope == "script":
        return [
            base / "script.json",
            base / "script.json.manifest.json",
            base / "variants",
            base / "selected_variant.json",
            base / "agent_variant_decision.json",
        ]
    if scope == "tts":
        return [base / "audio"]
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
