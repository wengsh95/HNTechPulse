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
from src.providers.renderer.remotion_props import script_to_props
from src.providers.renderer.binary_finder import (
    find_node,
    find_npm,
    find_npx,
    find_chrome,
    find_ffmpeg,
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

        self.chrome_path = remotion_config.get("browser_executable") or find_chrome()
        if self.chrome_path:
            self.logger.info(f"Using browser: {self.chrome_path}")
        else:
            self.logger.info(
                "System Chrome not found, Remotion will download/use its own Chromium"
            )

        self._ensure_dependencies_installed()

    def _prepare_render_data(
        self, script: Script, audio_dir: str, content=None, date: str = ""
    ) -> tuple[Path, str]:
        self._prepare_audio_assets(script, audio_dir)
        if content and date:
            self._prepare_image_assets(content, date)

        self._prepare_sound_effects()

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

        public_dir = self.remotion_dir / "public"
        public_dir.mkdir(parents=True, exist_ok=True)
        props_file = public_dir / "props.json"
        props_file.write_text(props_json, encoding="utf-8")
        self.logger.info(f"Props written to {props_file} ({len(props_json)} bytes)")

        return props_file, props_json

    def preview(
        self, script: Script, audio_dir: str, content=None, date: str = ""
    ) -> None:
        self.logger.info("Starting Remotion Studio for preview...")
        self.logger.info("Press Ctrl+C to stop the preview server.")

        if not self._node_path:
            raise RuntimeError("Node.js not found!")

        _, props_json = self._prepare_render_data(script, audio_dir, content, date=date)
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
        _, props_json = self._prepare_render_data(script, audio_dir, content, date=date)
        self._write_props_file(props_json, date=date)
        self.logger.info("Props synced. Remotion Studio will hot-reload on next change.")

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

        props_file, props_json = self._prepare_render_data(
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
            # Render whole video at once
            remotion_output = self.remotion_dir / "out" / "output.mp4"
            cmd = base_cmd + [f"--output={remotion_output}"]
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

                if chunk_file.exists():
                    self.logger.info(
                        f"Chunk {idx + 1}/{len(chunks)} already exists, skipping ({label})"
                    )
                    continue

                pending.append((idx, start, end, label, chunk_file))

            # Render pending chunks in parallel
            if pending:
                workers = min(self.render_workers, len(pending))
                self.logger.info(
                    f"Rendering {len(pending)} chunks with {workers} workers"
                )

                def _render_chunk(idx, start, end, label, chunk_file):
                    self.logger.info(
                        f"Rendering chunk {idx + 1}/{len(chunks)} [{label}]: frames {start}-{end}"
                    )
                    cmd = base_cmd + [
                        f"--output={chunk_file}",
                        f"--frames={start}-{end}",
                    ]
                    self._run_render_cmd(cmd)
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
                    # Clean up partial outputs so re-run doesn't skip them
                    for _, _, _, _, chunk_file in pending:
                        if chunk_file.exists() and chunk_file.stat().st_size == 0:
                            chunk_file.unlink()
                    raise

            # Concatenate chunks with ffmpeg
            self.logger.info(f"Concatenating {len(chunk_files)} chunks via ffmpeg...")
            concat_list = chunk_dir / "concat.txt"
            with open(concat_list, "w", encoding="utf-8") as f:
                for chunk_file in chunk_files:
                    # ffmpeg requires forward slashes and escaping or proper quoting
                    path_str = str(chunk_file.absolute()).replace("\\", "/")
                    # Escape single quotes for ffmpeg concat demuxer
                    path_escaped = path_str.replace("'", "'\\''")
                    f.write(f"file '{path_escaped}'\n")

            concat_cmd = [
                self._ffmpeg_path,
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

        self.logger.info("Rendering complete")

    def _run_render_cmd(self, cmd: list) -> None:
        cmd_summary = []
        for part in cmd:
            if part.startswith("--props="):
                cmd_summary.append("--props={...}")
            else:
                cmd_summary.append(part)
        self.logger.debug(f"Command: {' '.join(cmd_summary)}")

        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.remotion_dir),
                capture_output=False,
                text=True,
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

    def _prepare_audio_assets(self, script: "Script", audio_dir: str):
        public_dir = self.remotion_dir / "public"
        audio_subdir = public_dir / "audio"
        audio_subdir.mkdir(parents=True, exist_ok=True)

        audio_path_obj = Path(audio_dir).resolve()
        copied_files: set = set()

        def _copy_audio(src_path: str) -> str | None:
            """Copy one audio file to public/audio/ if not already copied.
            Returns the relative path (audio/filename) or None on failure.
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
            self.logger.debug(f"Copied audio: {src.name} -> public/audio/")
            return f"audio/{src.name}"

        for segment in script.segments:
            if getattr(segment, "audio_path", None):
                rel = _copy_audio(segment.audio_path)
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

    def _prepare_image_assets(self, content, date: str):
        """Copy enriched images to Remotion public/images/ for serving."""
        if content is None:
            return
        public_dir = self.remotion_dir / "public"
        image_subdir = public_dir / "images"
        image_subdir.mkdir(parents=True, exist_ok=True)

        def _resolve_local(path: str) -> Path | None:
            """Resolve a path to an existing local file, skipping remote URLs."""
            if self._is_remote_url(path):
                return None
            src = Path(path)
            if not src.is_absolute():
                src = Path(f"data/{date}") / path
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

    def _prepare_sound_effects(self) -> None:
        """Copy story-gap click sound effect to Remotion public/."""
        click_src = Path("double-click-computer-mouse.mp3")
        if not click_src.exists():
            return
        public_dir = self.remotion_dir / "public"
        public_dir.mkdir(parents=True, exist_ok=True)
        dest = public_dir / click_src.name
        if not dest.exists():
            shutil.copy2(click_src, dest)
            self.logger.debug(f"Copied sound effect: {click_src.name} -> public/")

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
            props_path = Path("data") / date / "cli_props.json"
        else:
            props_path = Path("data") / "cli_props.json"
        props_path.parent.mkdir(parents=True, exist_ok=True)
        props_path.write_text(props_json, encoding="utf-8")
        self.logger.info(f"Props written to {props_path} ({len(props_json)} bytes)")
        return str(props_path.resolve())

    def _chunk_cache_dir(self, date: str, props_json: str) -> Path:
        """Return a chunk cache directory scoped to the exact render input."""
        date_label = re.sub(r"[^0-9A-Za-z_-]+", "_", date).strip("_") or "undated"
        props_hash = sha256(props_json.encode("utf-8")).hexdigest()[:12]
        return self.remotion_dir / "out" / "chunks" / f"{date_label}_{props_hash}"
