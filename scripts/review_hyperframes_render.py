"""
Auto-extract key frames from a HyperFrames render for visual review.

Reads scene_spec.json to find scene timings, then uses ffmpeg to extract
one frame per scene at the midpoint. Outputs to tmp/hyperframes_review/{date}/.

Usage:
    uv run python scripts/review_hyperframes_render.py --date 2026-06-07
    uv run python scripts/review_hyperframes_render.py --date 2026-06-07 --video path/to/output.mp4
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract key frames from HyperFrames render"
    )
    parser.add_argument("--date", required=True, help="Pipeline date (YYYY-MM-DD)")
    parser.add_argument(
        "--video", help="Path to video file (default: data/{date}/publish/output.mp4)"
    )
    parser.add_argument(
        "--out-dir", help="Output directory (default: tmp/hyperframes_review/{date})"
    )
    args = parser.parse_args()

    from src.pipeline.paths import publish_path

    date = args.date
    video_path = Path(args.video) if args.video else publish_path(date, "output.mp4")
    if not video_path.exists():
        print(f"ERROR: Video not found: {video_path}", file=sys.stderr)
        sys.exit(1)

    # Read scene_spec.json
    spec_path = (
        PROJECT_ROOT
        / "data"
        / date
        / "hyperframes_project"
        / "data"
        / "scene_spec.json"
    )
    if not spec_path.exists():
        print(f"ERROR: scene_spec.json not found: {spec_path}", file=sys.stderr)
        sys.exit(1)

    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)

    scenes = spec.get("scenes", [])
    if not scenes:
        print("ERROR: No scenes found in scene_spec.json", file=sys.stderr)
        sys.exit(1)

    # Build frame extraction plan: one frame per scene at midpoint
    frames = []
    for scene in scenes:
        start = float(scene.get("start", 0))
        duration = float(scene.get("duration", 0))
        mid = start + duration / 2
        comp_id = scene.get("comp_id", "unknown")
        element_type = scene.get("element_type", "")
        # Build a readable filename
        label = element_type.replace("_card", "") or comp_id.replace("-card", "")
        # Add scene index for uniqueness
        idx = len(frames)
        frames.append(
            {
                "time": mid,
                "label": label,
                "index": idx,
                "comp_id": comp_id,
                "start": start,
                "duration": duration,
            }
        )

    # Output directory
    out_dir = (
        Path(args.out_dir)
        if args.out_dir
        else PROJECT_ROOT / "tmp" / "hyperframes_review" / date
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Video: {video_path}")
    print(f"Scenes: {len(frames)}")
    print(f"Output: {out_dir}")
    print()

    # Extract frames
    for frame in frames:
        t = frame["time"]
        idx = frame["index"]
        label = frame["label"]
        out_file = out_dir / f"{idx:02d}_{label}.png"

        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{t:.3f}",
            "-i",
            str(video_path),
            "-vframes",
            "1",
            "-q:v",
            "2",
            str(out_file),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"  [{idx:02d}] {label:12s} @ {t:7.2f}s → {out_file.name}")
        else:
            print(
                f"  [{idx:02d}] {label:12s} @ {t:7.2f}s → FAILED: {result.stderr[:200]}",
                file=sys.stderr,
            )

    print(f"\nDone. {len(frames)} frames extracted to {out_dir}")


if __name__ == "__main__":
    main()
