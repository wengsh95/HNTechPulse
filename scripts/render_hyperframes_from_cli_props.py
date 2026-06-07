#!/usr/bin/env python3
"""Render HyperFrames from an existing data/{date}/cli_props.json.

This is the fast path for visual/template iteration. It avoids re-running
write_script, TTS, title generation, or any LLM-backed pipeline step.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.models import SceneElement, Script, ScriptSegment
from src.providers.renderer.hyperframes_renderer import HyperFramesRenderer
from src.utils.config import load_config


def _load_script_from_cli_props(date: str) -> Script:
    props_path = Path("data") / date / "cli_props.json"
    if not props_path.exists():
        raise FileNotFoundError(f"Missing cli props: {props_path}")

    props = json.loads(props_path.read_text(encoding="utf-8"))
    segments: list[ScriptSegment] = []
    for raw_seg in props.get("segments", []):
        elems = [
            SceneElement(
                element_type=raw_elem.get("element_type", ""),
                start_time=float(raw_elem.get("start_time") or 0),
                end_time=float(raw_elem.get("end_time") or 0),
                props=raw_elem.get("props") or {},
            )
            for raw_elem in raw_seg.get("scene_elements", [])
        ]
        duration = float(raw_seg.get("duration") or 0)
        segments.append(
            ScriptSegment(
                segment_type=raw_seg.get("segment_type", ""),
                audio_text=raw_seg.get("audio_text", ""),
                duration=duration,
                actual_duration=duration,
                start_time=float(raw_seg.get("start_time") or 0),
                end_time=float(raw_seg.get("end_time") or 0),
                audio_path=raw_seg.get("audio_path"),
                scene_elements=elems,
                meta={"subtitle_audios": raw_seg.get("subtitle_audios", [])},
            )
        )

    return Script(
        title=props.get("title") or "HN TechPulse",
        description="",
        tags=[],
        segments=segments,
        total_duration=float(props.get("totalDuration") or 0),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render HyperFrames from data/{date}/cli_props.json"
    )
    parser.add_argument("--date", required=True, help="Date to render, YYYY-MM-DD")
    parser.add_argument(
        "--config",
        default="config/",
        help="Config directory or file path. Defaults to config/",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output MP4 path. Defaults to data/{date}/output.mp4",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Only regenerate data/{date}/hyperframes_project, do not render MP4.",
    )
    args = parser.parse_args()

    script = _load_script_from_cli_props(args.date)
    config = load_config(args.config)
    renderer = HyperFramesRenderer(config)
    audio_dir = str(Path("data") / args.date / "audio")

    if args.prepare_only:
        index_path, _, payload = renderer.write_props(
            script,
            audio_dir,
            content=None,
            date=args.date,
        )
        print(index_path)
        print(
            f"Prepared {len(payload.get('scenes', []))} scenes, "
            f"{len(payload.get('audio_tracks', []))} audio tracks, "
            f"{len(payload.get('subtitle_cues', []))} subtitle cues"
        )
        return 0

    output = args.output or str(Path("data") / args.date / "output.mp4")
    renderer.render(script, audio_dir, output, content=None, date=args.date)
    print(Path(output).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
