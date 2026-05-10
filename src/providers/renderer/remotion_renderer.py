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
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from src.core.models import Script
from src.core.interfaces import Renderer
from src.providers.renderer.remotion_props import script_to_props
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

        self._node_path = self._find_node()
        self._npm_path = self._find_npm()
        self._npx_path = self._find_npx()

        self.chrome_path = (
            remotion_config.get("browser_executable")
            or self._find_chrome()
        )
        if self.chrome_path:
            self.logger.info(f"Using browser: {self.chrome_path}")
        else:
            self.logger.info(
                "System Chrome not found, "
                "Remotion will download/use its own Chromium"
            )

        self._ensure_dependencies_installed()

    def _find_node(self) -> Optional[str]:
        node = shutil.which("node")
        if not node:
            for p in [
                r"C:\Program Files\nodejs\node.exe",
                str(Path(sys.prefix) / "nodejs" / "node.exe"),
                str(Path.home() / "AppData" / "Local" / "Programs" / "nodejs" / "node.exe"),
            ]:
                if Path(p).exists():
                    return p
            return None
        return node

    def _find_npm(self) -> Optional[str]:
        npm = shutil.which("npm")
        if not npm and self._node_path:
            node_dir = Path(self._node_path).parent
            candidate = node_dir / "npm.cmd"
            if candidate.exists():
                return str(candidate)
            candidate = node_dir / "npm"
            if candidate.exists():
                return str(candidate)
        return npm or None

    def _find_npx(self) -> Optional[str]:
        npx = shutil.which("npx")
        if not npx and self._node_path:
            node_dir = Path(self._node_path).parent
            candidate = node_dir / "npx.cmd"
            if candidate.exists():
                return str(candidate)
            candidate = node_dir / "npx"
            if candidate.exists():
                return str(candidate)
        return npx or None

    def _find_chrome(self) -> Optional[str]:
        chrome = shutil.which("chrome") or shutil.which("chromium")
        if chrome:
            return chrome

        for p in [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Chromium\Application\chrome.exe",
        ]:
            if Path(p).exists():
                return p

        macos_paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
        for p in macos_paths:
            if Path(p).exists():
                return p

        linux_paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/snap/bin/chromium",
        ]
        for p in linux_paths:
            if Path(p).exists():
                return p

        return None

    def _prepare_render_data(self, script: Script, audio_dir: str, content=None, date: str = "") -> tuple[Path, str]:
        self._prepare_audio_assets(script, audio_dir)
        if content and date:
            self._prepare_image_assets(content, date)

        props_data = script_to_props(
            script, audio_dir,
            self.width, self.height, self.fps, self.bg_color,
            content=content, logger=self.logger,
        )
        props_json = json.dumps(props_data, ensure_ascii=False, indent=2)

        public_dir = self.remotion_dir / "public"
        public_dir.mkdir(parents=True, exist_ok=True)
        props_file = public_dir / "props.json"
        props_file.write_text(props_json, encoding="utf-8")
        self.logger.info(f"Props written to {props_file} ({len(props_json)} bytes)")

        return props_file, props_json

    def preview(self, script: Script, audio_dir: str, content=None, date: str = "") -> None:
        self.logger.info("Starting Remotion Studio for preview...")
        self.logger.info("Press Ctrl+C to stop the preview server.")

        if not self._node_path:
            raise RuntimeError("Node.js not found!")

        _, props_json = self._prepare_render_data(script, audio_dir, content, date=date)
        self._ensure_dependencies_installed()

        props_file = self._write_props_file(props_json)

        cmd = [
            str(self._node_path),
            self._get_remotion_cli_path(),
            "studio",
            "--port", "3000",
            f"--props={props_file}",
        ]

        if self.chrome_path:
            cmd.append(f"--browser-executable={self.chrome_path}")

        self.logger.info(f"Studio URL: http://localhost:3000")
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

    def render(self, script: Script, audio_dir: str, output_path: str, content=None, date: str = "") -> None:
        self.logger.info(f"Rendering video to {output_path}")
        self.logger.info(f"Resolution: {self.width}x{self.height} @ {self.fps}fps")

        if not self._node_path:
            raise RuntimeError(
                "Node.js not found! Please install Node.js from https://nodejs.org/ "
                "or ensure it's in your PATH."
            )
        if not self._npm_path:
            raise RuntimeError(
                "npm not found! It should come with Node.js. "
                "Try reinstalling Node.js."
            )
        if not self._npx_path:
            raise RuntimeError(
                "npx not found! It should come with Node.js. "
                "Try: npm install -g npx"
            )

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        props_file, props_json = self._prepare_render_data(script, audio_dir, content, date=date)

        self._ensure_dependencies_installed()

        remotion_output = self.remotion_dir / "out" / "output.mp4"

        cli_props_file = self._write_props_file(props_json, date=date)

        cmd = [
            str(self._node_path),
            self._get_remotion_cli_path(),
            "render",
            "src/index.ts",
            "HNTechPulseComposition",
            f"--props={cli_props_file}",
            f"--output={remotion_output}",
        ]

        if self.chrome_path:
            cmd.append(f"--browser-executable={self.chrome_path}")

        if self.codec == "h264":
            cmd.extend(["--codec=h264"])
        elif self.codec == "h265":
            cmd.extend(["--codec=h265"])

        if self.crf is not None:
            cmd.extend([f"--crf={self.crf}"])

        if self.image_format == "jpeg":
            cmd.extend(["--image-format=jpeg"])
            if self.pixels_per_frame:
                cmd.extend([f"--pixels-per-frame={self.pixels_per_frame}"])

        if self.concurrency:
            cmd.extend([f"--concurrency={self.concurrency}"])

        cmd.append("--overwrite")

        total_frames = int((script.total_duration or 0) * self.fps)
        self.logger.info(
            f"Rendering {len(script.segments)} segments, "
            f"{total_frames} frames ({script.total_duration:.1f}s)"
        )
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
                raise RuntimeError(f"Remotion render failed with code {result.returncode}")

        except subprocess.TimeoutExpired:
            self.logger.error("Render timed out after 10 minutes!")
            raise
        except FileNotFoundError as e:
            self.logger.error(f"Command not found: {e}")
            raise

        if remotion_output.exists():
            output_file.parent.mkdir(parents=True, exist_ok=True)
            if output_file.exists():
                output_file.unlink()
            shutil.move(str(remotion_output), str(output_file))
            file_size_mb = output_file.stat().st_size / (1024 * 1024)
            self.logger.info(f"Video complete: {output_path} ({file_size_mb:.1f} MB)")
        else:
            raise FileNotFoundError(
                f"Remotion did not produce expected output at {remotion_output}"
            )

        self.logger.info("Rendering complete")

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

        for segment in script.segments:
            if not getattr(segment, "audio_path", None):
                continue

            src_audio = Path(segment.audio_path)
            if not src_audio.is_absolute():
                src_audio = audio_path_obj / src_audio

            if not src_audio.exists():
                fallback = audio_path_obj / src_audio.name
                if fallback.exists():
                    src_audio = fallback
                else:
                    self.logger.info(f"Audio file not found: {src_audio}")
                    continue

            dest_name = src_audio.name
            dest_path = audio_subdir / dest_name

            if str(src_audio) not in copied_files:
                shutil.copy2(src_audio, dest_path)
                copied_files.add(str(src_audio))
                self.logger.debug(f"Copied audio: {src_audio.name} -> public/audio/")

            segment.audio_path = f"audio/{dest_name}"

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
            "--prefix", str(self.remotion_dir),
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
            self.remotion_dir
            / "node_modules"
            / "@remotion"
            / "cli"
            / "remotion-cli.js"
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
