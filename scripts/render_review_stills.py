#!/usr/bin/env python3
"""Render representative Remotion stills for visual review.

Uses data/{date}/cli_props.json, so it does not rerun script generation, TTS, or
the full video render. Outputs PNGs and a manifest under
data/{date}/review_stills/remotion/.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline.paths import date_root, render_path, render_remotion_dir  # noqa: E402
from src.providers.renderer.binary_finder import find_node  # noqa: E402


REMOTION_DIR = Path("src/providers/renderer/remotion")
COMPOSITION_ID = "HNTechPulseComposition"


def _default_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _load_props(date: str) -> dict[str, Any]:
    props_path = render_path(date, "cli_props.json")
    if not props_path.exists():
        return {}
    return json.loads(props_path.read_text(encoding="utf-8"))


def _frame(seconds: float, fps: int) -> int:
    return max(0, int(round(seconds * fps)))


def _safe_name(text: str) -> str:
    keep = []
    for ch in text.lower():
        if ch.isalnum():
            keep.append(ch)
        elif ch in {"_", "-"}:
            keep.append(ch)
        else:
            keep.append("_")
    return "_".join("".join(keep).strip("_").split("_")) or "still"


def _review_points(props: dict[str, Any], fps: int) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    segments = props.get("segments") or []
    for seg_index, seg in enumerate(segments):
        seg_start = float(seg.get("start_time") or 0)
        seg_duration = float(seg.get("duration") or 0)
        seg_type = str(seg.get("segment_type") or f"segment_{seg_index}")
        elems = seg.get("scene_elements") or []
        typed = [
            elem
            for elem in elems
            if elem.get("element_type")
            in {"cover_card", "event_card", "atmosphere_card", "closing_card"}
        ]
        if typed:
            for elem_index, elem in enumerate(typed):
                start = seg_start + float(elem.get("start_time") or 0)
                end = seg_start + float(elem.get("end_time") or 0)
                if end <= start:
                    end = start + max(1.0, seg_duration / max(1, len(typed)))
                element_type = str(elem.get("element_type") or "element")
                label = f"{seg_index:02d}_{elem_index:02d}_{element_type}"
                points.append(
                    {
                        "label": label,
                        "segment_index": seg_index,
                        "segment_type": seg_type,
                        "element_type": element_type,
                        "time_seconds": round((start + end) / 2, 3),
                        "frame": _frame((start + end) / 2, fps),
                    }
                )
        elif seg_duration > 0:
            label = f"{seg_index:02d}_{seg_type}"
            points.append(
                {
                    "label": label,
                    "segment_index": seg_index,
                    "segment_type": seg_type,
                    "element_type": None,
                    "time_seconds": round(seg_start + seg_duration / 2, 3),
                    "frame": _frame(seg_start + seg_duration / 2, fps),
                }
            )
    return points


def _render_still(
    *,
    props_path: Path,
    public_dir: Path,
    output_path: Path,
    frame: int,
    scale: float | None,
) -> None:
    node_path = find_node()
    if not node_path:
        raise RuntimeError("Node.js not found")
    remotion_cli = (
        REMOTION_DIR / "node_modules" / "@remotion" / "cli" / "remotion-cli.js"
    )
    if not remotion_cli.exists():
        raise RuntimeError(f"Remotion CLI not found: {remotion_cli}")
    cmd = [
        str(node_path),
        str(remotion_cli.resolve()),
        "still",
        "src/index.ts",
        COMPOSITION_ID,
        str(output_path.resolve()),
        f"--props={props_path.resolve()}",
        f"--frame={frame}",
        f"--public-dir={public_dir.resolve()}",
    ]
    if scale is not None:
        cmd.append(f"--scale={scale}")
    subprocess.run(
        cmd,
        cwd=REMOTION_DIR,
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Render Remotion review stills")
    parser.add_argument("--date", default=_default_date())
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--scale", type=float, default=None)
    parser.add_argument(
        "--limit", type=int, default=0, help="Render only first N stills"
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    props = _load_props(args.date)
    props_path = render_path(args.date, "cli_props.json")
    if not props:
        print(
            json.dumps(
                {
                    "date": args.date,
                    "error": "missing_cli_props",
                    "path": str(props_path).replace("\\", "/"),
                    "next_command": f"uv run python scripts/agent_run.py --date {args.date} --resume",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    public_dir = render_remotion_dir(args.date) / "public"
    out_dir = date_root(args.date) / "review_stills" / "remotion"
    out_dir.mkdir(parents=True, exist_ok=True)
    points = _review_points(props, args.fps)
    if args.limit > 0:
        points = points[: args.limit]

    manifest_items = []
    for point in points:
        filename = f"{_safe_name(point['label'])}_f{point['frame']}.png"
        output_path = out_dir / filename
        item = {**point, "path": str(output_path).replace("\\", "/")}
        manifest_items.append(item)
        if not args.dry_run:
            _render_still(
                props_path=props_path,
                public_dir=public_dir,
                output_path=output_path,
                frame=int(point["frame"]),
                scale=args.scale,
            )

    manifest = {
        "date": args.date,
        "composition": COMPOSITION_ID,
        "fps": args.fps,
        "dry_run": args.dry_run,
        "stills": manifest_items,
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
