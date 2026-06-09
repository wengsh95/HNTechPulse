#!/usr/bin/env python3
"""Extract frame sequences around each HyperFrames scene start.

This is a visual parity aid for checking whether HyperFrames scene entrances
match the Remotion version. It reads the generated scene_spec.json and extracts
frames at scene_start + offsets from any rendered MP4.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def _default_spec(date: str) -> Path:
    return Path("data") / date / "hyperframes_project" / "data" / "scene_spec.json"


def _default_video(date: str) -> Path:
    return Path("data") / date / "output.mp4"


def _safe_label(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value)
    return cleaned.strip("_") or "scene"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract frames around each scene start for animation review"
    )
    parser.add_argument("--date", required=True, help="Pipeline date or compare date")
    parser.add_argument("--video", default=None, help="Rendered MP4 path")
    parser.add_argument("--scene-spec", default=None, help="HyperFrames scene_spec.json")
    parser.add_argument(
        "--offsets",
        default="0,0.2,0.5,1.0",
        help="Comma-separated seconds after scene start",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Output directory. Defaults to tmp/scene_start_review/{date}",
    )
    args = parser.parse_args()

    video = Path(args.video) if args.video else _default_video(args.date)
    spec_path = Path(args.scene_spec) if args.scene_spec else _default_spec(args.date)
    out_dir = Path(args.out_dir) if args.out_dir else Path("tmp") / "scene_start_review" / args.date
    offsets = [float(part.strip()) for part in args.offsets.split(",") if part.strip()]

    if not video.exists():
        raise FileNotFoundError(f"Video not found: {video}")
    if not spec_path.exists():
        raise FileNotFoundError(f"Scene spec not found: {spec_path}")

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    scenes = spec.get("scenes") or []
    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for idx, scene in enumerate(scenes):
        start = float(scene.get("start") or 0)
        duration = float(scene.get("duration") or 0)
        label = _safe_label(str(scene.get("element_type") or scene.get("comp_id") or idx))
        for offset in offsets:
            if offset >= duration:
                continue
            timestamp = max(0.0, start + offset)
            out_file = out_dir / f"{idx:02d}_{label}_{offset:.1f}s.png"
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(video),
                    "-ss",
                    f"{timestamp:.3f}",
                    "-vframes",
                    "1",
                    "-q:v",
                    "2",
                    str(out_file),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            written.append(out_file)

    print(f"Wrote {len(written)} frames to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
