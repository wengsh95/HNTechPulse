"""
RemotionRenderer - Video rendering with React/Remotion

Architecture:
  Python (Script dataclass) -> JSON -> Remotion CLI -> MP4

Advantages:
  - Browser-native text rendering (GPU-accelerated), no Pillow/Pango needed
  - Parallel frame rendering (multiple Chrome workers), no single-thread bottleneck
  - CSS Flexbox/Grid layout, code is more intuitive
  - Native support for NVENC GPU encoding (via FFmpeg)
"""

import json
import math
import shutil
import subprocess
import sys
import re
from hashlib import sha256
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict

from src.core.models import Script
from src.core.interfaces import Renderer
from src.pipeline.paths import date_root, render_path, render_remotion_dir
from src.providers.renderer.remotion_props import script_to_props
from src.providers.renderer.binary_finder import (
    find_node,
    find_npm,
    find_npx,
    find_chrome,
    find_ffmpeg,
    find_ffprobe,
)
from src.providers.renderer.chunk_planner import compute_segment_chunks
from src.utils.logger import setup_logger


class RemotionRenderer(Renderer):
    """
    Render video with Remotion (React).

    Implements Renderer interface, uses browser engine for frame rendering.
    """

    def __init__(self, config: dict, debug: bool = False):
        self.config = config
        self.debug = debug
        log_level = config.get("logging", {}).get("level")
        self.logger = setup_logger(__name__, debug=debug, level=log_level)

        video_config = config.get("video", {})
        self.width, self.height = video_config.get("resolution", (1280, 720))
        self.fps = video_config.get("fps", 24)
        self.bg_color = video_config.get("bg_color", "#0d1117")

        remotion_config = config.get("remotion", {})
        self.remotion_dir = Path(__file__).parent / "remotion"
        self.concurrency = remotion_config.get("concurrency", None)
        self.image_format = remotion_config.get("image_format", "jpeg")
        self.codec = remotion_config.get("codec", "h264")
        self.crf = remotion_config.get("crf", 23)
        self.pixels_per_frame = remotion_config.get("pixels_per_frame", None)
        self.gl = remotion_config.get("gl", None)
        self.chunk_frames = remotion_config.get("chunk_frames", 1500)
        self.resume_enabled = remotion_config.get("resume_enabled", True)
        self.render_workers = remotion_config.get("render_workers", 2)

        self._node_path = find_node()
        self._npm_path = find_npm(self._node_path)
        self._npx_path = find_npx(self._node_path)
        self._ffmpeg_path = find_ffmpeg()
        self._ffprobe_path = find_ffprobe(self._ffmpeg_path)
        if not self._ffprobe_path:
            self.logger.warning(
                "ffprobe not found; chunk/final video integrity checks will be "
                "skipped. Install ffmpeg (which ships ffprobe) to enable them."
            )

        self.chrome_path = remotion_config.get("browser_executable") or find_chrome()
        if self.chrome_path:
            self.logger.info(f"Using browser: {self.chrome_path}")
        else:
            self.logger.info(
                "System Chrome not found, Remotion will download/use its own Chromium"
            )

        self._ensure_dependencies_installed()

    def write_props(
        self, script: Script, audio_dir: str, content=None, date: str = ""
    ) -> tuple[Path, str, None]:
        data_dir = self._remotion_data_dir(date) if date else None
        if data_dir:
            audio_target_dir = data_dir / "public" / "audio"
            image_target_dir = data_dir / "public" / "images"
        else:
            # Fallback: no date means nowhere under data/ to scope, so keep
            # the historical "remotion/public" layout as a last resort.
            audio_target_dir = self.remotion_dir / "public" / "audio"
            image_target_dir = self.remotion_dir / "public" / "images"
        self._prepare_audio_assets(script, audio_dir, target_dir=audio_target_dir)
        if content and date:
            self._prepare_image_assets(content, date, target_dir=image_target_dir)

        props_data = script_to_props(
            script,
            audio_dir,
            self.width,
            self.height,
            self.fps,
            self.bg_color,
            content=content,
            logger=self.logger,
        )
        props_json = json.dumps(props_data, ensure_ascii=False, indent=2)

        # Always also write to data/{date}/cli_props.json for CLI use.
        # The data/{date}/remotion/public/props.json copy is the file
        # Remotion Studio hot-reloads from when --public-dir points there.
        cli_props_path = self._write_props_file(props_json, date=date)
        if data_dir:
            public_dir = data_dir / "public"
            public_dir.mkdir(parents=True, exist_ok=True)
            public_props = public_dir / "props.json"
            public_props.write_text(props_json, encoding="utf-8")
            self.logger.info(
                f"Props (public mirror) written to {public_props} ({len(props_json)} bytes)"
            )

        return Path(cli_props_path), props_json, None

    def preview(
        self, script: Script, audio_dir: str, content=None, date: str = ""
    ) -> None:
        self.logger.info("Starting Remotion Studio for preview...")
        self.logger.info("Press Ctrl+C to stop the preview server.")

        if not self._node_path:
            raise RuntimeError("Node.js not found!")

        _, props_json, _ = self.write_props(script, audio_dir, content, date=date)
        self._ensure_dependencies_installed()

        props_file = self._write_props_file(props_json, date=date)

        cmd = [
            str(self._node_path),
            self._get_remotion_cli_path(),
            "studio",
            "--port",
            "3000",
            f"--props={props_file}",
        ]
        if date:
            public_dir = (self._remotion_data_dir(date) / "public").resolve()
            cmd.append(f"--public-dir={public_dir}")

        if self.chrome_path:
            cmd.append(f"--browser-executable={self.chrome_path}")

        self.logger.info("Studio URL: http://localhost:3000")
        cmd_summary = []
        for part in cmd:
            if part.startswith("--props="):
                cmd_summary.append("--props={...}")
            else:
                cmd_summary.append(part)
        self.logger.debug(f"Command: {' '.join(cmd_summary)}")

        try:
            subprocess.run(
                cmd,
                cwd=str(self.remotion_dir),
                timeout=None,
                env=self._build_env(),
            )
            self.logger.info("Studio closed.")
        except KeyboardInterrupt:
            self.logger.info("Preview interrupted by user.")
        except FileNotFoundError as e:
            self.logger.error(f"Command not found: {e}")
            raise
        finally:
            pass

    def sync_props(
        self, script: Script, audio_dir: str, content=None, date: str = ""
    ) -> None:
        """Regenerate props.json and static assets without starting the studio."""
        self.logger.info("Syncing preview props...")
        _, props_json, _ = self.write_props(script, audio_dir, content, date=date)
        self._write_props_file(props_json, date=date)
        self.logger.info(
            "Props synced. Remotion Studio will hot-reload on next change."
        )

    def render(
        self,
        script: Script,
        audio_dir: str,
        output_path: str,
        content=None,
        date: str = "",
    ) -> None:
        self.logger.info(f"Rendering video to {output_path}")
        self.logger.info(f"Resolution: {self.width}x{self.height} @ {self.fps}fps")

        if not self._node_path:
            raise RuntimeError(
                "Node.js not found! Please install Node.js from https://nodejs.org/ "
                "or ensure it's in your PATH."
            )
        if not self._npm_path:
            raise RuntimeError(
                "npm not found! It should come with Node.js. Try reinstalling Node.js."
            )
        if not self._npx_path:
            raise RuntimeError(
                "npx not found! It should come with Node.js. Try: npm install -g npx"
            )
        if not self._ffmpeg_path and self.resume_enabled:
            self.logger.warning(
                "ffmpeg not found, falling back to full render without resume support."
            )
            self.resume_enabled = False

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        props_file, props_json, _ = self.write_props(
            script, audio_dir, content, date=date
        )

        self._ensure_dependencies_installed()

        cli_props_file = self._write_props_file(props_json, date=date)

        total_frames = math.ceil((script.total_duration or 0) * self.fps)
        if total_frames <= 0:
            self.logger.error("Script has 0 frames.")
            return

        self.logger.info(
            f"Total segments: {len(script.segments)}, "
            f"Total frames: {total_frames} ({script.total_duration:.1f}s)"
        )

        base_cmd = [
            str(self._node_path),
            self._get_remotion_cli_path(),
            "render",
            "src/index.ts",
            "HNTechPulseComposition",
            f"--width={self.width}",
            f"--height={self.height}",
            f"--props={cli_props_file}",
        ]
        if date:
            public_dir = (self._remotion_data_dir(date) / "public").resolve()
            base_cmd.append(f"--public-dir={public_dir}")

        if self.chrome_path:
            base_cmd.append(f"--browser-executable={self.chrome_path}")
        if self.gl:
            base_cmd.append(f"--gl={self.gl}")
        if self.codec in ["h264", "h265"]:
            base_cmd.extend([f"--codec={self.codec}"])
        if self.crf is not None:
            base_cmd.extend([f"--crf={self.crf}"])
        if self.image_format == "jpeg":
            base_cmd.extend(["--image-format=jpeg"])
            if self.pixels_per_frame:
                base_cmd.extend([f"--pixels-per-frame={self.pixels_per_frame}"])
        if self.concurrency:
            base_cmd.extend([f"--concurrency={self.concurrency}"])
        base_cmd.append("--overwrite")

        if not self.resume_enabled or len(script.segments) <= 1:
            # Render whole video at once. Single-shot temp goes under
            # data/{date}/remotion/ (not the Remotion source dir) so the
            # source tree stays clean.
            remotion_output = (
                self._remotion_data_dir(date) / "single.mp4"
                if date
                else self.remotion_dir / "out" / "output.mp4"
            )
            cmd = base_cmd + [f"--output={remotion_output.resolve()}"]
            self._run_render_cmd(cmd)
            self._finalize_output(remotion_output, output_file)
        else:
            # Segment-based chunked rendering (parallel)
            chunks = compute_segment_chunks(script, self.fps, total_frames)

            chunk_files = []
            chunk_dir = self._chunk_cache_dir(date=date, props_json=props_json)
            chunk_dir.mkdir(parents=True, exist_ok=True)

            self.logger.info(f"Split rendering into {len(chunks)} segment chunks")
            self.logger.info(f"Chunk cache: {chunk_dir}")

            # Build list of chunks that need rendering
            pending = []
            for idx, (start, end, label) in enumerate(chunks):
                chunk_file = chunk_dir / f"chunk_{idx:03d}_{label}.mp4"
                chunk_files.append(chunk_file)

                if chunk_file.exists() and chunk_file.stat().st_size > 0:
                    # File is on disk and non-empty — but Remotion/Chromium
                    # can crash mid-render and still leave a "successful"
                    # half-written MP4. Verify before trusting the cache, so
                    # a corrupt chunk never silently slips into concat.
                    try:
                        self._verify_chunk(chunk_file, label)
                    except RuntimeError as e:
                        self.logger.warning(
                            f"Chunk {idx + 1}/{len(chunks)} on disk failed "
                            f"verification: {e}. Deleting and re-rendering."
                        )
                        chunk_file.unlink()
                    else:
                        self.logger.info(
                            f"Chunk {idx + 1}/{len(chunks)} already exists, skipping ({label})"
                        )
                        continue
                if chunk_file.exists():
                    # Empty final file left by a prior crashed run.
                    self.logger.warning(
                        f"Chunk {idx + 1}/{len(chunks)} exists but is empty "
                        f"({chunk_file.stat().st_size} bytes); will re-render ({label})"
                    )
                    chunk_file.unlink()

                # Render to a .partial.mp4 temp file first; only rename to .mp4 on
                # a clean exit. A crashed/timeout render leaves the .partial.mp4
                # behind, invisible to the resume check above, so the next run
                # re-renders cleanly instead of silently reusing a half-written
                # MP4 in concat. Note: the .mp4 suffix MUST remain at the end so
                # Remotion's h264/aac filename validator accepts it.
                partial_file = chunk_file.with_name(
                    f"{chunk_file.stem}.partial{chunk_file.suffix}"
                )
                if partial_file.exists():
                    self.logger.warning(
                        f"Chunk {idx + 1}/{len(chunks)} has leftover .partial; "
                        f"re-rendering ({label})"
                    )
                    partial_file.unlink()
                pending.append((idx, start, end, label, chunk_file, partial_file))

            # Render pending chunks in parallel
            if pending:
                workers = min(self.render_workers, len(pending))
                self.logger.info(
                    f"Rendering {len(pending)} chunks with {workers} workers"
                )

                def _render_chunk(idx, start, end, label, chunk_file, partial_file):
                    self.logger.info(
                        f"Rendering chunk {idx + 1}/{len(chunks)} [{label}]: frames {start}-{end}"
                    )
                    cmd = base_cmd + [
                        f"--output={partial_file.resolve()}",
                        f"--frames={start}-{end}",
                    ]
                    self._run_render_cmd(cmd, label=label)
                    # Remotion's --overwrite can complete with exit 0 even when
                    # Chromium crashed inside, leaving a partial MP4. Probe the
                    # partial before promoting it; if it's corrupt, raise so
                    # the outer except cleans up and the next run re-renders.
                    duration = self._probe_duration(partial_file)
                    if duration is None or duration <= 0.0:
                        raise RuntimeError(
                            f"Chunk {label} (frames {start}-{end}) produced a "
                            "non-decodable MP4 (Chromium likely crashed "
                            "mid-render)."
                        )
                    partial_file.rename(chunk_file)
                    return idx

                try:
                    with ThreadPoolExecutor(max_workers=workers) as pool:
                        futures = {
                            pool.submit(_render_chunk, *args): args[0]
                            for args in pending
                        }
                        for future in as_completed(futures):
                            idx = futures[future]
                            future.result()  # raises on failure
                            label = chunks[idx][2]
                            self.logger.info(
                                f"Chunk {idx + 1}/{len(chunks)} done ({label})"
                            )
                except Exception:
                    # Clean up partial outputs and any half-promoted chunks so
                    # the next run re-renders them from scratch.
                    for _, _, _, _, chunk_file, partial_file in pending:
                        if partial_file.exists():
                            partial_file.unlink()
                        if chunk_file.exists():
                            chunk_file.unlink()
                    raise

            # Concatenate chunks with ffmpeg
            self.logger.info(f"Concatenating {len(chunk_files)} chunks via ffmpeg...")
            # Pre-concat safety net: even with the per-chunk verify in the
            # render loop, a chunk that became corrupt after promotion (e.g.
            # disk full, antivirus interference) would still poison the final
            # output. Re-verify right before we hand the list to ffmpeg and
            # bail out with a clear error if any chunk is no good.
            for chunk_file in chunk_files:
                # chunk_files are listed in (idx, label) order; pull label
                # from the filename suffix for a readable error message.
                label = chunk_file.stem.split("_", 2)[-1]
                self._verify_chunk(chunk_file, label)
            concat_list = chunk_dir / "concat.txt"
            with open(concat_list, "w", encoding="utf-8") as f:
                for chunk_file in chunk_files:
                    # ffmpeg requires forward slashes and escaping or proper quoting
                    path_str = str(chunk_file.absolute()).replace("\\", "/")
                    # Escape single quotes for ffmpeg concat demuxer
                    path_escaped = path_str.replace("'", "'\\''")
                    f.write(f"file '{path_escaped}'\n")

            concat_cmd: list[str] = [
                str(self._ffmpeg_path),
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list),
                "-c",
                "copy",
                str(output_file.absolute()),
            ]

            try:
                subprocess.run(concat_cmd, check=True, capture_output=True)
                self.logger.info(f"Video complete: {output_path}")
            except subprocess.CalledProcessError as e:
                self.logger.error(
                    f"ffmpeg concat failed: {e.stderr.decode('utf-8', errors='ignore')}"
                )
                raise RuntimeError("ffmpeg concat failed")

            # Post-concat safety net: ffmpeg's `-c copy` concat can produce a
            # short, decodable-looking file when one chunk was actually
            # corrupt. Require the final duration to be close to the planned
            # total before we let downstream steps treat the render as good.
            if self._ffprobe_path:
                actual_duration = self._verify_final_output(
                    output_file, script.total_duration or 0
                )
                self.logger.info(
                    f"Final video duration: {actual_duration:.2f}s "
                    f"(target {(script.total_duration or 0):.2f}s)"
                )

        self.logger.info("Rendering complete")

    # Remotion prints one stdout line per rendered frame (e.g.
    # "Rendered 228/517, time remaining: 16s"). With multiple workers in
    # parallel, this floods the log. We match the progress line and throttle
    # it to ~5% granularity; non-progress lines (Bundling, Encoding, errors,
    # warnings, final summary) pass through unchanged.
    _RENDER_PROGRESS_RE = re.compile(
        r"^Rendered\s+(\d+)/(\d+),\s+time\s+remaining:\s+\S+$"
    )
    _PROGRESS_LOG_STEP = 0.05  # log at most every 5% of total frames

    def _run_render_cmd(self, cmd: list, label: str | None = None) -> None:
        cmd_summary = []
        for part in cmd:
            if part.startswith("--props="):
                cmd_summary.append("--props={...}")
            else:
                cmd_summary.append(part)
        self.logger.debug(f"Command: {' '.join(cmd_summary)}")

        if label is None:
            # Single render — keep live streaming (no interleaving risk).
            try:
                result = subprocess.run(
                    cmd,
                    cwd=str(self.remotion_dir),
                    capture_output=False,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=600,
                    env=self._build_env(),
                )
                if result.returncode != 0:
                    raise RuntimeError(
                        f"Remotion render failed with code {result.returncode}"
                    )
            except subprocess.TimeoutExpired:
                self.logger.error("Render timed out after 10 minutes!")
                raise
            except FileNotFoundError as e:
                self.logger.error(f"Command not found: {e}")
                raise
        else:
            # Parallel chunk render — capture and label each line so output
            # from concurrent subprocesses doesn't interleave on the terminal.
            try:
                process = subprocess.Popen(
                    cmd,
                    cwd=str(self.remotion_dir),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=self._build_env(),
                )
                assert process.stdout is not None
                # Per-call throttle state: which progress percentages have
                # already been logged for this chunk's render.
                last_pct = -1.0
                for line in process.stdout:
                    stripped = line.rstrip("\n\r")
                    if not stripped:
                        continue
                    m = self._RENDER_PROGRESS_RE.match(stripped)
                    if m:
                        current = int(m.group(1))
                        total = int(m.group(2))
                        pct = current / total if total else 1.0
                        # Always log the first and last frame; throttle the
                        # rest to ~5% steps to keep the log readable.
                        if (
                            current != total
                            and (pct - last_pct) < self._PROGRESS_LOG_STEP
                        ):
                            continue
                        last_pct = pct
                    self.logger.info(f"[{label}] {stripped}")
                process.wait(timeout=600)
                if process.returncode != 0:
                    raise RuntimeError(
                        f"Remotion render failed with code {process.returncode}"
                    )
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                self.logger.error(f"[{label}] Render timed out after 10 minutes!")
                raise
            except FileNotFoundError as e:
                self.logger.error(f"Command not found: {e}")
                raise

    def _finalize_output(self, remotion_output: Path, output_file: Path) -> None:
        if remotion_output.exists():
            output_file.parent.mkdir(parents=True, exist_ok=True)
            if output_file.exists():
                output_file.unlink()
            shutil.move(str(remotion_output), str(output_file))
            file_size_mb = output_file.stat().st_size / (1024 * 1024)
            self.logger.info(f"Video complete: {output_file} ({file_size_mb:.1f} MB)")
        else:
            raise FileNotFoundError(
                f"Remotion did not produce expected output at {remotion_output}"
            )

    # ------------------------------------------------------------------
    # Chunk / final video integrity checks
    # ------------------------------------------------------------------
    #
    # Remotion can crash mid-render inside Chromium and still return exit 0,
    # leaving a partially-written MP4 on disk (header intact, no decodable
    # streams). The previous code trusted exit code alone and concatenated
    # such files blindly, producing videos truncated to the first chunk
    # (~10s of a 115s target). These helpers defend against that by probing
    # the output with ffprobe before treating it as valid. ffprobe is
    # optional — if missing, we log and skip the check (best-effort).

    def _probe_duration(self, path: Path) -> float | None:
        """Return the container duration in seconds, or None on any failure.

        Uses ffprobe's CSV output and prefers format duration; falls back to
        the longest stream duration if format duration is missing (Remotion's
        concat'd MP4s sometimes have format.duration = N/A).
        """
        if not self._ffprobe_path or not path.exists():
            return None
        try:
            r = subprocess.run(
                [
                    self._ffprobe_path,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration:stream=duration",
                    "-of",
                    "csv=p=0",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            self.logger.warning(f"ffprobe timed out or failed for {path}: {e}")
            return None
        if r.returncode != 0:
            return None
        durations = []
        for line in r.stdout.splitlines():
            line = line.strip()
            if not line or line.upper() == "N/A":
                continue
            try:
                durations.append(float(line))
            except ValueError:
                continue
        return max(durations) if durations else None

    def _verify_chunk(self, chunk_file: Path, label: str) -> float:
        """Verify a chunk MP4 is decodable and non-empty.

        Returns the probed duration in seconds on success. Raises
        ``RuntimeError`` if the file is missing, has no decodable streams, or
        has zero/negative duration — these are the signatures of a Chromium
        crash that left a half-written MP4 behind.
        """
        if not chunk_file.exists() or chunk_file.stat().st_size == 0:
            raise RuntimeError(
                f"Chunk {label}: file missing or empty at {chunk_file}"
            )
        duration = self._probe_duration(chunk_file)
        if duration is None:
            raise RuntimeError(
                f"Chunk {label}: ffprobe could not read any streams from "
                f"{chunk_file} (file size {chunk_file.stat().st_size} bytes). "
                "Remotion likely crashed mid-render; the chunk must be "
                "re-rendered."
            )
        if duration <= 0.0:
            raise RuntimeError(
                f"Chunk {label}: probed duration is {duration:.3f}s "
                f"({chunk_file}). Re-render required."
            )
        return duration

    def _verify_final_output(
        self, output_file: Path, expected_duration: float, tolerance: float = 0.05
    ) -> float:
        """Verify the concatenated final video covers the expected duration.

        Ffmpeg's ``-c copy`` concat can silently produce a short file when one
        of the input chunks is corrupt — it just copies as much as it can
        decode. We probe the final file and require its duration to be within
        ``tolerance`` of the expected total (default 5%).

        Returns the actual probed duration.
        """
        if not output_file.exists() or output_file.stat().st_size == 0:
            raise RuntimeError(
                f"Final video missing or empty at {output_file}"
            )
        actual = self._probe_duration(output_file)
        if actual is None:
            raise RuntimeError(
                f"Final video {output_file} has no decodable streams. "
                "ffmpeg concat likely consumed a corrupt chunk — check "
                "individual chunks and re-render."
            )
        if expected_duration > 0:
            min_acceptable = expected_duration * (1.0 - tolerance)
            if actual < min_acceptable:
                raise RuntimeError(
                    f"Final video {output_file} is {actual:.2f}s, expected "
                    f"~{expected_duration:.2f}s (tolerance {tolerance*100:.0f}%). "
                    "ffmpeg concat truncated the output — one or more chunks "
                    "are likely corrupt. Re-render the affected chunks."
                )
        return actual

    def _build_env(self) -> Dict[str, str]:
        import os

        env = dict(os.environ)

        node_modules = str(self.remotion_dir / "node_modules")
        existing = env.get("NODE_PATH", "")
        if node_modules not in existing:
            sep = ";" if sys.platform == "win32" else ":"
            env["NODE_PATH"] = (
                f"{node_modules}{sep}{existing}" if existing else node_modules
            )

        return env

    def _prepare_audio_assets(
        self, script: "Script", audio_dir: str, target_dir: Path | None = None
    ):
        audio_subdir = target_dir or self.remotion_dir / "public" / "audio"
        audio_subdir.mkdir(parents=True, exist_ok=True)

        audio_path_obj = Path(audio_dir).resolve()
        copied_files: set = set()

        def _copy_audio(src_path: str) -> str | None:
            """Copy one audio file to the target public/audio/ if not already
            copied. Returns the relative path (audio/filename) or None on
            failure.
            """
            src = Path(src_path)
            if not src.is_absolute():
                src = audio_path_obj / src
            if not src.exists():
                fallback = audio_path_obj / src.name
                if fallback.exists():
                    src = fallback
                else:
                    self.logger.info(f"Audio file not found: {src}")
                    return None
            if str(src) in copied_files:
                return f"audio/{src.name}"
            shutil.copy2(src, audio_subdir / src.name)
            copied_files.add(str(src))
            self.logger.debug(f"Copied audio: {src.name} -> {audio_subdir}")
            return f"audio/{src.name}"

        for segment in script.segments:
            seg_audio = getattr(segment, "audio_path", None)
            if seg_audio:
                rel = _copy_audio(seg_audio)
                if rel:
                    segment.audio_path = rel

            subtitle_audios = segment.meta.get("subtitle_audios", [])
            for sa in subtitle_audios:
                sa_audio_path = sa.get("audio_path", "")
                if sa_audio_path:
                    _copy_audio(sa_audio_path)

        self.logger.info(f"Prepared {len(copied_files)} audio files in public/")

    @staticmethod
    def _is_remote_url(path: str) -> bool:
        return path.startswith(("http://", "https://"))

    def _prepare_image_assets(self, content, date: str, target_dir: Path | None = None):
        """Copy enriched images to the Remotion public/images/ for serving.

        ``target_dir`` defaults to ``remotion/public/images`` for backwards
        compatibility when no date is supplied.
        """
        if content is None:
            return
        image_subdir = target_dir or (self.remotion_dir / "public" / "images")
        image_subdir.mkdir(parents=True, exist_ok=True)

        def _resolve_local(path: str) -> Path | None:
            """Resolve a path to an existing local file, skipping remote URLs."""
            if self._is_remote_url(path):
                return None
            src = Path(path)
            if not src.is_absolute():
                src = date_root(date) / path
            return src if src.exists() else None

        def _copy(src: Path) -> bool:
            dest = image_subdir / src.name
            if not dest.exists():
                shutil.copy2(src, dest)
                return True
            return False

        copied = 0
        for item in content.items:
            for img_path in item.article_images:
                src = _resolve_local(img_path)
                if src and _copy(src):
                    copied += 1
            if item.logo_image:
                src = _resolve_local(item.logo_image)
                if src and _copy(src):
                    copied += 1
            if item.screenshot_image:
                src = _resolve_local(item.screenshot_image)
                if src and _copy(src):
                    copied += 1
        if copied > 0:
            self.logger.info(f"Copied {copied} images to public/images/")

    def _ensure_dependencies_installed(self):
        node_modules = self.remotion_dir / "node_modules"
        remotion_cli = node_modules / "@remotion" / "cli" / "remotion-cli.js"

        if remotion_cli.exists():
            self.logger.debug("Dependencies already installed")
            return

        self.logger.info("Installing dependencies (first time setup)...")

        install_cmd = [
            str(self._npm_path),
            "install",
            "--prefix",
            str(self.remotion_dir),
        ]

        try:
            result = subprocess.run(
                install_cmd,
                cwd=str(self.remotion_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
                env=self._build_env(),
            )

            if result.returncode != 0:
                self.logger.error(f"npm install failed:\n{result.stderr}")
                raise RuntimeError(
                    f"Failed to install Remotion dependencies. "
                    f"Exit code: {result.returncode}\n\n{result.stderr}"
                )

            if not remotion_cli.exists():
                raise RuntimeError(
                    "npm install completed but @remotion/cli not found in node_modules. "
                    "Check package.json for correct dependencies."
                )

            self.logger.info("Dependencies installed successfully")

        except subprocess.TimeoutExpired:
            self.logger.error("npm install timed out after 5 minutes!")
            raise RuntimeError("npm install timed out")

    def _get_remotion_cli_path(self) -> str:
        cli_path = (
            self.remotion_dir / "node_modules" / "@remotion" / "cli" / "remotion-cli.js"
        )
        if not cli_path.exists():
            raise FileNotFoundError(
                f"@remotion/cli not found at {cli_path}. "
                "Run 'npm install' in the remotion directory first."
            )
        return str(cli_path)

    def _write_props_file(self, props_json: str, date: str = "") -> str:
        """Write props JSON to a persistent file and return its path.

        Avoids OS command-line length limits when passing large props to the
        Remotion CLI. The file is persisted under data/{date}/ for debugging.
        """
        if date:
            props_path = render_path(date, "cli_props.json")
        else:
            props_path = Path("data") / "cli_props.json"
        props_path.parent.mkdir(parents=True, exist_ok=True)
        props_path.write_text(props_json, encoding="utf-8")
        self.logger.info(f"Props written to {props_path} ({len(props_json)} bytes)")
        return str(props_path.resolve())

    def _chunk_cache_dir(self, date: str, props_json: str) -> Path:
        """Return a chunk cache directory scoped to the exact render input.

        Chunks live under ``data/{date}/remotion/chunks/`` so the source tree
        stays clean. Falls back to ``remotion/out/chunks/`` when no date is
        supplied (test/legacy path).
        """
        date_label = re.sub(r"[^0-9A-Za-z_-]+", "_", date).strip("_") or "undated"
        props_hash = sha256(props_json.encode("utf-8")).hexdigest()[:12]
        base = self._remotion_data_dir(date) if date else self.remotion_dir / "out"
        return base / "chunks" / f"{date_label}_{props_hash}"

    def _remotion_data_dir(self, date: str) -> Path:
        """Return the per-date Remotion runtime dir under ``data/``.

        All non-source runtime files (public/ assets, chunk caches, single
        render temp output) live here so the source tree in
        ``src/providers/renderer/remotion/`` stays clean.
        """
        if not date:
            raise ValueError(
                "RemotionRenderer requires a non-empty date for runtime dirs"
            )
        d = render_remotion_dir(date)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def cache_paths(self, date: str) -> list[Path]:
        """Paths the orchestrator should clear on a forced re-render."""
        if not date:
            return []
        d = self._remotion_data_dir(date)
        return [d / "chunks", d / "single.mp4", d / "public"]
