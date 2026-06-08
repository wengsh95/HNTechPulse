"""
HyperFramesRenderer — Video rendering with HTML + GSAP via `npx hyperframes`.

Architecture:
  Python (Script dataclass) -> index.html + media assets -> npx hyperframes render -> MP4

Why an alternative to Remotion:
  - No React toolchain (no node_modules compile step for the video app itself)
  - Single HTML/JS composition per render; easy to template
  - Native audio-reactive and visual effects (HyperFrames/GSAP ecosystem)
  - Easier to evolve card visuals without rebuilding the whole React tree

Parallel rendering (mirrors remotion_renderer):
  - Timeline is split at segment boundaries via chunk_planner.
  - For each chunk, a self-contained mini project is generated (filtered
    index.html + filtered audio subset + shared compositions + shared images).
  - All chunks are rendered in parallel via a ThreadPoolExecutor that spawns
    N `npx hyperframes render` subprocesses. Outputs are concatenated with
    ffmpeg concat (no re-encode, just stream copy).
  - Per-chunk MP4s are cached under out/chunks/{date_label}_{hash12}/. Cache
    key is sha256 of the per-chunk filtered scene_spec — same input → same
    hash → cache hit, re-run is instant.
  - `.partial.mp4` rename dance for crash safety, identical to Remotion.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.core.interfaces import Renderer
from src.core.models import Script
from src.providers.renderer.binary_finder import (
    find_ffmpeg,
    find_node,
    find_npx,
)
from src.providers.renderer.chunk_planner import compute_segment_chunks_seconds
from src.providers.renderer.hyperframes_props import (
    filter_scenes_to_chunk,
    render_index_html,
    script_to_hyperframes_scenes,
)
from src.utils.logger import setup_logger


class HyperFramesRenderer(Renderer):
    """Render video with HyperFrames (HTML + GSAP)."""

    def __init__(self, config: dict, debug: bool = False):
        self.config = config
        self.debug = debug
        log_level = config.get("logging", {}).get("level")
        self.logger = setup_logger(__name__, debug=debug, level=log_level)

        video_config = config.get("video", {})
        resolution = video_config.get("resolution", (1280, 720))
        # Some configs store resolution as a list, others as a tuple
        if isinstance(resolution, list):
            resolution = tuple(resolution)
        self.width, self.height = resolution
        self.fps = video_config.get("fps", 24)
        self.bg_color = video_config.get("bg_color", "#fefaf2")

        hf_config = config.get("renderer", {}).get("hyperframes", {}) or {}
        default_template = Path(__file__).parent / "hyperframes"
        self.project_dir = Path(
            hf_config.get("project_dir", str(default_template))
        ).resolve()
        # Output location is per-date so multiple dates can be rendered in parallel
        self.output_subdir = hf_config.get(
            "output_subdir", "hyperframes_project"
        )  # appended under data/{date}/
        self.default_quality = hf_config.get("default_quality", "standard")
        self.preview_port = int(hf_config.get("preview_port", 3002))
        self.fps_override = hf_config.get("fps", None)
        # Parallel render: number of `npx hyperframes render` subprocesses
        # running concurrently. HyperFrames currently allocates its internal
        # localhost port by itself; on Windows, parallel chunks can collide
        # with Chromium's unsafe port list (for example 10080). Default to 1
        # for production stability and let config opt into higher concurrency.
        self.render_workers = int(hf_config.get("render_workers", 1))
        # When True, split the timeline into per-segment chunks and render
        # them in parallel with per-chunk caching. When False, single-shot.
        self.resume_enabled = bool(hf_config.get("resume_enabled", True))
        # Inner parallelism: passed to npx hyperframes --workers. None means
        # let HyperFrames auto-detect.
        self.workers = hf_config.get("workers", None)
        # Per-chunk render timeout (seconds). Each npx subprocess gets this.
        self._chunk_timeout = int(hf_config.get("chunk_timeout", 1800))
        # GPU knobs. browser_gpu controls Chrome's WebGL/canvas backend
        # (rendering side); gpu_encoding controls ffmpeg's encoder
        # (final mp4 side). Both default off here — hyperframes' own
        # default for --browser-gpu is "auto" (probe, fall back). We only
        # pass the flag when the config opts in explicitly; pass-through
        # of None leaves auto-probe behavior intact.
        self.browser_gpu = hf_config.get("browser_gpu", None)
        self.gpu_encoding = bool(hf_config.get("gpu_encoding", False))
        # Always persist npx stdout+stderr to <cwd>/render.log so we can
        # postmortem timing/phase output even on successful runs. Without
        # this, hyperframes' per-stage timestamps live and die inside the
        # subprocess pipe.
        self._always_log_render = bool(hf_config.get("always_log_render", True))

        self._node_path = find_node()
        self._npx_path = find_npx(self._node_path)
        self._ffmpeg_path = find_ffmpeg()

        if not self._node_path:
            raise RuntimeError(
                "Node.js not found. Install Node 22+ from https://nodejs.org/"
            )
        if not self._npx_path:
            raise RuntimeError("npx not found. Reinstall Node.js to include npm/npx.")
        if not self._ffmpeg_path:
            # HyperFrames render requires ffmpeg; we don't silently fall back
            raise RuntimeError(
                "ffmpeg not found. Install ffmpeg and ensure it's on PATH."
            )

        if not (self.project_dir / "package.json").exists():
            raise RuntimeError(
                f"HyperFrames template project not found at {self.project_dir} "
                "(missing package.json). Did the scaffold get checked in?"
            )

    # ── Renderer ABC methods ────────────────────────────────────────

    def write_props(
        self,
        script: Script,
        audio_dir: str,
        content: Optional[object] = None,
        date: str = "",
        scenes_payload: Optional[Dict] = None,
    ) -> Tuple[Path, str, Dict]:
        """Generate per-date HyperFrames project under data/{date}/<output_subdir>/.

        Returns (index.html absolute path, html string, scenes_payload).
        The caller can pass a pre-computed `scenes_payload` (e.g. from
        `render()`) to skip the heavy `script_to_hyperframes_scenes` build.

        Side effects:
          - Clears and recreates the project directory
          - Copies sub-compositions from the template
          - Copies audio files into public/audio/
          - Copies image assets into public/images/
          - Writes the index.html and a scene_spec.json for debugging

        Defensive: if the script's scene_element timings are still 0/0
        (script loaded from a partial cache, dry-run, or interrupted step),
        this method calls TimingEngine.set_scene_element_times() to fill them
        in from sub_segment_estimated_durations before serialization.
        """
        if not date:
            raise ValueError("HyperFramesRenderer.write_props requires a date string")

        # Defensive: ensure scene_element timings are populated. Without this,
        # scripts loaded from disk (e.g. after a crashed run) can have
        # scene_elements with start_time=0.0 end_time=0.0 which we'd filter out.
        self._ensure_scene_element_times(script)

        out_root = Path("data") / date / self.output_subdir
        self._clean(out_root)
        (out_root / "compositions").mkdir(parents=True, exist_ok=True)
        (out_root / "public" / "audio").mkdir(parents=True, exist_ok=True)
        (out_root / "public" / "images").mkdir(parents=True, exist_ok=True)
        (out_root / "data").mkdir(parents=True, exist_ok=True)

        # Copy the template scaffolding (package.json + compositions/)
        shutil.copy2(self.project_dir / "package.json", out_root / "package.json")
        for comp_file in (self.project_dir / "compositions").glob("*.html"):
            shutil.copy2(comp_file, out_root / "compositions" / comp_file.name)

        # Copy audio + image assets (best-effort; missing audio is logged)
        self._copy_audio_assets(script, audio_dir, out_root)
        if content is not None:
            self._copy_image_assets(content, date, out_root)

        # Build the scene spec — reuse caller's payload if provided.
        if scenes_payload is None:
            scenes_payload = script_to_hyperframes_scenes(
                script,
                audio_dir=str(Path(audio_dir).resolve()),
                width=self.width,
                height=self.height,
                fps=self.fps,
                bg_color=self.bg_color,
                content=content,
                date=date,
                logger=self.logger,
            )

        # Adjust audio src to be relative to the output root.
        # remotion_props.py normalizes audio paths to "audio/<filename>"
        # (Remotion serves that directly from its public/ mapping). HyperFrames
        # resolves asset URLs relative to the project root — there is no magic
        # "public/" directory — so we always rewrite to "public/audio/<name>"
        # unless the src is already prefixed or points at a remote URL.
        for track in scenes_payload["audio_tracks"]:
            src = track.get("src", "")
            if not src or src.startswith("public/"):
                continue
            if src.startswith(("http://", "https://")):
                continue
            track["src"] = "public/audio/" + Path(src).name

        # Same for image_src in variables
        for s in scenes_payload["scenes"]:
            img = (s.get("variables") or {}).get("image_src")
            if (
                not img
                or img.startswith("public/")
                or img.startswith(("http://", "https://"))
            ):
                continue
            s["variables"]["image_src"] = "public/images/" + Path(img).name
        self._copy_scene_image_assets(scenes_payload, date, out_root)

        # Write scene_spec.json + cli_props.json (debug aids)
        spec_path = out_root / "data" / "scene_spec.json"
        spec_path.write_text(
            json.dumps(scenes_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        cli_path = out_root / "data" / "cli_props.json"
        cli_path.write_text(
            json.dumps(scenes_payload["cli_props"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Render the root index.html
        html = render_index_html(scenes_payload, title=script.title or "HN TechPulse")
        index_path = out_root / "index.html"
        index_path.write_text(html, encoding="utf-8")
        self.logger.info(
            f"HyperFrames project prepared: {out_root} "
            f"({len(scenes_payload['scenes'])} scenes, "
            f"{len(scenes_payload['audio_tracks'])} audio tracks)"
        )
        return index_path, html, scenes_payload

    def render(
        self,
        script: Script,
        audio_dir: str,
        output_path: str,
        content: Optional[object] = None,
        date: str = "",
    ) -> None:
        """Render the script to MP4 via `npx hyperframes render`.

        Two paths:
          - Single-shot: one `npx hyperframes render` over the whole timeline
            (when resume_enabled is False or there is only one segment).
          - Chunked: split the timeline at segment boundaries, generate a
            self-contained mini project per chunk, render all chunks in
            parallel via a ThreadPoolExecutor, concat with ffmpeg. Per-chunk
            MP4s are cached on disk so a re-run with unchanged input is
            instant.
        """
        if not date:
            raise ValueError("HyperFramesRenderer.render requires a date string")

        out_root = Path("data") / date / self.output_subdir
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        if output_file.exists():
            output_file.unlink()

        # Always write_props to populate the project (for preview sync +
        # single-shot fallback). Returns the full scene_spec.
        self.logger.info(f"Rendering via HyperFrames -> {output_path}")
        self.logger.info(
            f"Resolution: {self.width}x{self.height} @ {self.fps}fps, "
            f"quality={self.default_quality}"
        )

        # Build the full scene spec once so we can both filter for chunks and
        # use it for the single-shot fallback. Pass it through write_props so
        # we don't recompute it (script_to_hyperframes_scenes iterates every
        # segment + builds alignment cues — non-trivial cost).
        self._ensure_scene_element_times(script)
        full_scenes_payload = script_to_hyperframes_scenes(
            script,
            audio_dir=str(Path(audio_dir).resolve()),
            width=self.width,
            height=self.height,
            fps=self.fps,
            bg_color=self.bg_color,
            content=content,
            date=date,
            logger=self.logger,
        )
        # Reuse write_props' asset copying and index.html emission; pass the
        # pre-computed payload to skip a second build.
        self.write_props(
            script, audio_dir, content, date=date, scenes_payload=full_scenes_payload
        )

        total_duration = float(script.total_duration or 0)
        if total_duration <= 0:
            self.logger.error("Script has 0 duration; nothing to render.")
            return

        # Decide single-shot vs chunked. Mirrors remotion's branch at
        # remotion_renderer.py:249: only chunk if we actually have multiple
        # chunks to play with.
        chunks: List[Tuple[float, float, str]] = []
        if self.resume_enabled and self._ffmpeg_path:
            chunks = compute_segment_chunks_seconds(script, total_duration)

        if len(chunks) <= 1:
            self._render_single(out_root, output_file)
            return

        # Chunked path: build per-chunk projects, render in parallel, concat.
        self._render_chunked(
            date=date,
            out_root=out_root,
            full_scenes_payload=full_scenes_payload,
            chunks=chunks,
            output_file=output_file,
        )

    def _render_single(self, out_root: Path, output_file: Path) -> None:
        """Single-shot render: one npx hyperframes render over the full timeline."""
        cmd = self._build_base_cmd(output_file, workers=self.workers, cwd=out_root)
        self._run_render_cmd(cmd, cwd=out_root, label="single-shot")
        if not output_file.exists():
            raise FileNotFoundError(
                f"HyperFrames did not produce output at {output_file}"
            )
        size_mb = output_file.stat().st_size / (1024 * 1024)
        self.logger.info(f"Video complete: {output_file} ({size_mb:.1f} MB)")

    def _render_chunked(
        self,
        date: str,
        out_root: Path,
        full_scenes_payload: Dict,
        chunks: List[Tuple[float, float, str]],
        output_file: Path,
    ) -> None:
        """Parallel chunk render with per-chunk cache + ffmpeg concat.

        Steps:
          1. Build a per-chunk mini project (filtered index.html + filtered
             audio + shared compositions + shared images).
          2. For each chunk, look up its cache file; queue missing/empty ones.
          3. Render pending chunks in parallel via ThreadPoolExecutor.
          4. ffmpeg concat all chunk files (stream copy) into output_file.
        """
        # Per-date chunk cache root: data/{date}/hyperframes_project/out/chunks
        chunk_root = out_root / "out" / "chunks"
        chunk_root.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"Split rendering into {len(chunks)} segment chunks")
        self.logger.info(f"Chunk cache: {chunk_root}")

        # Build per-chunk projects. Returns the list of (idx, start, end,
        # label, chunk_subdir, chunk_file, partial_file) tuples.
        prepared: List[Dict] = []
        for idx, (start_sec, end_sec, label) in enumerate(chunks):
            filtered = filter_scenes_to_chunk(full_scenes_payload, start_sec, end_sec)
            payload_json = json.dumps(filtered, ensure_ascii=False, sort_keys=True)
            payload_hash = sha256(payload_json.encode("utf-8")).hexdigest()[:12]
            chunk_subdir = chunk_root / f"chunk_{idx:03d}_{label}_{payload_hash}"
            chunk_subdir.mkdir(parents=True, exist_ok=True)
            self._write_chunk_project(
                chunk_subdir=chunk_subdir,
                out_root=out_root,
                filtered_payload=filtered,
                title=full_scenes_payload.get("title") or "HN TechPulse",
            )
            chunk_file = chunk_subdir / "chunk.mp4"
            partial_file = chunk_subdir / "chunk.partial.mp4"
            prepared.append(
                {
                    "idx": idx,
                    "start_sec": start_sec,
                    "end_sec": end_sec,
                    "label": label,
                    "subdir": chunk_subdir,
                    "chunk_file": chunk_file,
                    "partial_file": partial_file,
                }
            )

        # Cache check: skip chunks that already have a non-empty .mp4.
        pending: List[Dict] = []
        for entry in prepared:
            chunk_file = entry["chunk_file"]
            partial_file = entry["partial_file"]
            idx = entry["idx"]
            label = entry["label"]
            if chunk_file.exists() and chunk_file.stat().st_size > 0:
                self.logger.info(
                    f"Chunk {idx + 1}/{len(prepared)} cache hit, skipping ({label})"
                )
                continue
            if chunk_file.exists():
                # Empty final file from a prior crashed run.
                self.logger.warning(
                    f"Chunk {idx + 1}/{len(prepared)} exists but is empty; "
                    f"re-rendering ({label})"
                )
                chunk_file.unlink()
            if partial_file.exists():
                self.logger.warning(
                    f"Chunk {idx + 1}/{len(prepared)} has leftover .partial; "
                    f"re-rendering ({label})"
                )
                partial_file.unlink()
            pending.append(entry)

        # Render pending chunks in parallel.
        if pending:
            workers = max(1, min(self.render_workers, len(pending)))
            self.logger.info(
                f"Rendering {len(pending)} chunks with {workers} workers "
                f"(out of {self.render_workers} configured)"
            )

            def _render_one(entry: Dict) -> int:
                idx = entry["idx"]
                label = entry["label"]
                subdir: Path = entry["subdir"]
                partial_file: Path = entry["partial_file"]
                chunk_file: Path = entry["chunk_file"]
                self.logger.info(
                    f"Rendering chunk {idx + 1}/{len(prepared)} [{label}]: "
                    f"{entry['start_sec']:.2f}s-{entry['end_sec']:.2f}s"
                )
                # Inner workers come from config (renderer.hyperframes.workers).
                # None → let hyperframes auto-detect. Hardcoding 1 here would
                # silently cap each chunk to one Chrome process regardless of
                # config. Outer × inner = total Chrome processes; tune both
                # together against host RAM (~256 MB / worker).
                cmd = self._build_base_cmd(
                    partial_file, workers=self.workers, cwd=subdir
                )
                self._run_render_cmd(cmd, cwd=subdir, label=label)
                # Atomic rename on success. os.replace is atomic on both POSIX
                # and Windows (Path.rename on Windows can fall back to copy
                # when the destination exists or a virus scanner holds a
                # handle). CLAUDE.md flags this same pitfall for the Remotion
                # renderer's .partial.mp4 dance.
                os.replace(partial_file, chunk_file)
                return idx

            try:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = {pool.submit(_render_one, e): e["idx"] for e in pending}
                    for future in as_completed(futures):
                        idx = futures[future]
                        future.result()  # raises on failure
                        label = prepared[idx]["label"]
                        self.logger.info(
                            f"Chunk {idx + 1}/{len(prepared)} done ({label})"
                        )
            except Exception:
                # Clean up partial outputs so re-run can re-render them.
                for entry in pending:
                    pf = entry["partial_file"]
                    if pf.exists():
                        try:
                            pf.unlink()
                        except OSError:
                            pass
                raise

        # Concatenate chunks with ffmpeg.
        chunk_files = [e["chunk_file"] for e in prepared]
        self.logger.info(f"Concatenating {len(chunk_files)} chunks via ffmpeg...")
        concat_list = chunk_root / "concat.txt"
        with open(concat_list, "w", encoding="utf-8") as f:
            for chunk_file in chunk_files:
                # ffmpeg concat demuxer wants forward slashes + single-quote escape
                path_str = str(chunk_file.absolute()).replace("\\", "/")
                path_escaped = path_str.replace("'", "'\\''")
                f.write(f"file '{path_escaped}'\n")

        concat_cmd: list = [
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
        except subprocess.CalledProcessError as e:
            self.logger.error(
                f"ffmpeg concat failed: {e.stderr.decode('utf-8', errors='ignore')}"
            )
            raise RuntimeError("ffmpeg concat failed")

        size_mb = output_file.stat().st_size / (1024 * 1024)
        self.logger.info(f"Video complete: {output_file} ({size_mb:.1f} MB)")

    def _build_base_cmd(
        self,
        output_file: Path,
        workers: Optional[int] = 1,
        cwd: Optional[Path] = None,
    ) -> list:
        """Build the `npx hyperframes render` command for one chunk/single-shot.

        On Windows, hyperframes treats the ``--output`` value as relative to
        its working directory even when given an absolute path with a drive
        letter — the file ends up nested under the cwd (e.g. ``chunk_005/
        data/.../chunk.partial.mp4``). To avoid the rename race, we pass the
        path relative to ``cwd`` and resolve it locally so callers can keep
        using the absolute path for the rename step.
        """
        if cwd is not None:
            try:
                rel_output = (
                    Path(output_file).resolve().relative_to(Path(cwd).resolve())
                )
                output_arg = str(rel_output).replace("\\", "/")
            except ValueError:
                # output_file is not under cwd — fall back to absolute
                output_arg = str(output_file)
        else:
            output_arg = str(output_file)
        cmd = [
            str(self._npx_path),
            "hyperframes",
            "render",
            f"--output={output_arg}",
            f"--quality={self.default_quality}",
        ]
        if self.fps_override:
            cmd.append(f"--fps={self.fps_override}")
        if workers is not None:
            cmd.append(f"--workers={workers}")
        # GPU flags. browser_gpu: True → force-on, False → force-off (SwiftShader),
        # None → leave hyperframes' default auto-probe (recommended unless you
        # know your machine). gpu_encoding: True → ffmpeg uses NVENC/QSV/AMF.
        if self.browser_gpu is True:
            cmd.append("--browser-gpu")
        elif self.browser_gpu is False:
            cmd.append("--no-browser-gpu")
        if self.gpu_encoding:
            cmd.append("--gpu")
        return cmd

    def _run_render_cmd(self, cmd: list, cwd: Path, label: str = "") -> None:
        """Run one npx hyperframes render subprocess. Raises on non-zero exit.

        Always writes captured stdout+stderr to ``<cwd>/render.log`` when
        ``always_log_render`` is True (default), so per-stage timing from
        hyperframes survives the run. Without this, npx's output streams to
        the parent terminal but disappears the moment the ThreadPoolExecutor
        unwinds the worker, leaving no trace in the run log. On failure,
        the log path is surfaced in the exception for postmortem.
        """
        self.logger.debug(f"Command ({label}): {' '.join(cmd)} (cwd={cwd})")
        log_path = Path(cwd) / "render.log"
        try:
            result = subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self._chunk_timeout,
                env=self._build_env(),
            )
            if self._always_log_render or result.returncode != 0:
                try:
                    log_path.write_text(
                        f"--- cmd ---\n{' '.join(cmd)}\n--- cwd ---\n{cwd}\n"
                        f"--- exit ---\n{result.returncode}\n"
                        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}\n",
                        encoding="utf-8",
                    )
                except OSError as e:
                    self.logger.warning(f"Could not write {log_path}: {e}")
            if result.returncode != 0:
                tail = (result.stderr or result.stdout or "").strip().splitlines()
                tail_text = "\n".join(tail[-20:]) if tail else "(no output captured)"
                self.logger.error(
                    f"HyperFrames render failed (code={result.returncode}, {label}). "
                    f"Log: {log_path}\nLast output:\n{tail_text}"
                )
                raise RuntimeError(
                    f"HyperFrames render failed with code {result.returncode} ({label}); "
                    f"see {log_path}"
                )
        except subprocess.TimeoutExpired:
            self.logger.error(
                f"HyperFrames render timed out after {self._chunk_timeout}s ({label})!"
            )
            raise
        except FileNotFoundError as e:
            self.logger.error(f"Command not found: {e}")
            raise

    def _write_chunk_project(
        self,
        chunk_subdir: Path,
        out_root: Path,
        filtered_payload: Dict,
        title: str,
    ) -> None:
        """Write a self-contained mini project for one chunk.

        Layout under chunk_subdir:
          package.json            (copied from template)
          compositions/*.html     (copied from template; identical sub-comps)
          public/audio/*.{mp3,...} (filtered: only this chunk's audio)
          public/images/*         (copied: shared across all chunks)
          data/scene_spec.json   (debug aid: filtered scene spec)
          index.html              (filtered root composition)
        """
        # Layout
        (chunk_subdir / "compositions").mkdir(parents=True, exist_ok=True)
        audio_target = chunk_subdir / "public" / "audio"
        audio_target.mkdir(parents=True, exist_ok=True)
        images_target = chunk_subdir / "public" / "images"
        images_target.mkdir(parents=True, exist_ok=True)
        (chunk_subdir / "data").mkdir(parents=True, exist_ok=True)

        # Template scaffolding (always copied; identical across chunks).
        shutil.copy2(self.project_dir / "package.json", chunk_subdir / "package.json")
        for comp_file in (self.project_dir / "compositions").glob("*.html"):
            shutil.copy2(comp_file, chunk_subdir / "compositions" / comp_file.name)

        # Audio subset: only the files referenced by this chunk.
        chunk_audio_names: set = set()
        for track in filtered_payload.get("audio_tracks", []):
            src = track.get("src", "")
            if not src:
                continue
            # src is "public/audio/<name>" — copy from the parent project
            # which has the full audio set copied in by write_props.
            src_name = Path(src).name
            chunk_audio_names.add(src_name)
            src_abs = out_root / "public" / "audio" / src_name
            if src_abs.exists():
                shutil.copy2(src_abs, audio_target / src_name)
            else:
                self.logger.debug(f"Chunk audio source missing (skipping): {src_abs}")

        # Images: copy the full set from the parent project. They're shared
        # across chunks (same article images), and copy2 is a no-op if the
        # file is already up to date in the destination.
        parent_images = out_root / "public" / "images"
        if parent_images.exists():
            for img in parent_images.iterdir():
                if img.is_file():
                    shutil.copy2(img, images_target / img.name)

        # scene_spec.json (debug aid) + index.html.
        spec_path = chunk_subdir / "data" / "scene_spec.json"
        spec_path.write_text(
            json.dumps(filtered_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        html = render_index_html(filtered_payload, title=title)
        (chunk_subdir / "index.html").write_text(html, encoding="utf-8")

    def preview(
        self,
        script: Script,
        audio_dir: str,
        content: Optional[object] = None,
        date: str = "",
    ) -> None:
        """Start `npx hyperframes preview` for live editing."""
        if not date:
            raise ValueError("HyperFramesRenderer.preview requires a date string")

        out_root = Path("data") / date / self.output_subdir
        self.write_props(script, audio_dir, content, date=date)
        self.logger.info(f"Starting HyperFrames preview on port {self.preview_port}...")
        self.logger.info("Press Ctrl+C to stop.")

        cmd = [
            str(self._npx_path),
            "hyperframes",
            "preview",
            f"--port={self.preview_port}",
        ]
        try:
            subprocess.run(
                cmd,
                cwd=str(out_root),
                timeout=None,
                env=self._build_env(),
            )
        except KeyboardInterrupt:
            self.logger.info("Preview interrupted by user.")

    def sync_props(
        self,
        script: Script,
        audio_dir: str,
        content: Optional[object] = None,
        date: str = "",
    ) -> None:
        """Regenerate the per-date project so a running preview can hot-reload."""
        if not date:
            return
        self.write_props(script, audio_dir, content, date=date)
        self.logger.info("HyperFrames project resynced (preview will hot-reload).")

    # ── Cache paths (for orchestrator --force cleanup) ──────────────

    def cache_paths(self, date: str) -> List[Path]:
        if not date:
            return []
        root = Path("data") / date / self.output_subdir
        # Return both the project root and the chunk cache so `pipeline
        # --force` wipes both. The project root is regenerated on the next
        # write_props() call, so wiping it costs nothing.
        return [root, root / "out" / "chunks"]

    # ── Internals ───────────────────────────────────────────────────

    def _clean(self, root: Path) -> None:
        if not root.exists():
            return
        for child in root.iterdir():
            try:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            except OSError as e:
                self.logger.warning(f"Failed to clean {child}: {e}")

    def _copy_audio_assets(self, script: Script, audio_dir: str, out_root: Path) -> int:
        """Copy each segment's audio file into <out>/public/audio/."""
        audio_dir_path = Path(audio_dir).resolve()
        target = out_root / "public" / "audio"
        copied: set = set()

        def _copy(src_path: str) -> None:
            if not src_path:
                return
            src = Path(src_path)
            if not src.is_absolute():
                src = audio_dir_path / src
            if not src.exists():
                fallback = audio_dir_path / src.name
                if fallback.exists():
                    src = fallback
                else:
                    self.logger.info(f"Audio not found, skipping: {src}")
                    return
            if str(src) in copied:
                return
            try:
                shutil.copy2(src, target / src.name)
                copied.add(str(src))
            except OSError as e:
                self.logger.warning(f"Failed to copy audio {src}: {e}")

        for segment in script.segments:
            seg_audio = getattr(segment, "audio_path", None)
            if seg_audio:
                _copy(seg_audio)
            for sa in segment.meta.get("subtitle_audios", []) or []:
                _copy(sa.get("audio_path") or "")

        self.logger.info(f"Copied {len(copied)} audio files to {target}")
        return len(copied)

    def _copy_image_assets(self, content, date: str, out_root: Path) -> int:
        """Copy enriched article images to <out>/public/images/."""
        target = out_root / "public" / "images"
        copied: set = set()

        def _resolve(p: str) -> Optional[Path]:
            if not p or p.startswith(("http://", "https://")):
                return None
            src = Path(p)
            if not src.is_absolute():
                src = Path(f"data/{date}") / p
            return src if src.exists() else None

        for item in getattr(content, "items", []) or []:
            for img in getattr(item, "article_images", []) or []:
                src = _resolve(img)
                if src and str(src) not in copied:
                    shutil.copy2(src, target / src.name)
                    copied.add(str(src))
            for candidate in getattr(item, "image_candidates", []) or []:
                if not isinstance(candidate, dict):
                    continue
                src = _resolve(candidate.get("path", ""))
                if src and str(src) not in copied:
                    shutil.copy2(src, target / src.name)
                    copied.add(str(src))
            for attr in ("logo_image", "screenshot_image"):
                val = getattr(item, attr, None)
                src = _resolve(val)
                if src and str(src) not in copied:
                    shutil.copy2(src, target / src.name)
                    copied.add(str(src))
        self.logger.info(f"Copied {len(copied)} images to {target}")
        return len(copied)

    def _copy_scene_image_assets(
        self, scenes_payload: Dict, date: str, out_root: Path
    ) -> int:
        """Copy image_src files referenced directly by scene variables.

        This covers the fast CLI-props re-render path where ``content`` is not
        available, but cli_props already points cards at public/images/<file>.
        """
        target = out_root / "public" / "images"
        target.mkdir(parents=True, exist_ok=True)
        copied: set[str] = set()

        def _candidates(src: str) -> List[Path]:
            name = Path(src).name
            paths = [Path(src)]
            if date:
                paths.extend(
                    [
                        Path("data") / date / src,
                        Path("data") / date / "images" / name,
                    ]
                )
            paths.append(self.project_dir / "public" / "images" / name)
            paths.append(Path("src/providers/renderer/remotion/public/images") / name)
            return paths

        for scene in scenes_payload.get("scenes", []):
            src = ((scene.get("variables") or {}).get("image_src") or "").strip()
            if not src or src.startswith(("http://", "https://")):
                continue
            for candidate in _candidates(src):
                if candidate.exists() and candidate.is_file():
                    key = str(candidate.resolve())
                    if key not in copied:
                        shutil.copy2(candidate, target / candidate.name)
                        copied.add(key)
                    break
        if copied:
            self.logger.info(f"Copied {len(copied)} scene images to {target}")
        return len(copied)

    def _build_env(self) -> Dict[str, str]:
        import os

        env = dict(os.environ)
        # npx may download hyperframes on first use; keep cache outside the project
        env.setdefault("NPM_CONFIG_CACHE", str(Path.home() / ".npm" / "_npx"))
        return env

    @staticmethod
    def _ensure_scene_element_times(script: Script) -> None:
        """Fill in scene_element start_time/end_time if they are 0/0.

        The orchestrator normally does this during synthesize_audio via
        TimingEngine.set_scene_element_times(). When a renderer is invoked
        on a script loaded straight from disk (interrupted run, dry-run),
        timings can be missing — we'd then filter out every element and
        produce an empty video. Call TimingEngine here so the renderer is
        self-sufficient.
        """
        needs_fix = False
        for seg in script.segments:
            for elem in seg.scene_elements:
                if float(elem.end_time or 0) <= float(elem.start_time or 0):
                    needs_fix = True
                    break
            if needs_fix:
                break
        if not needs_fix:
            return
        try:
            from src.pipeline.timing_engine import TimingEngine

            engine = TimingEngine(segment_gap=0.0, debug=False)
            engine.set_scene_element_times(script)
        except Exception as e:  # pragma: no cover - defensive
            import logging

            logging.getLogger(__name__).warning(
                f"Failed to backfill scene_element timings: {e}"
            )
            return

        # Sanity check: the engine should have populated at least one element
        # with positive duration. If it didn't (e.g. a regression in the
        # engine API or zero-duration input), don't silently emit an empty
        # video — surface the issue so the operator sees a clear failure
        # instead of an MP4 with no scenes.
        populated = sum(
            1
            for seg in script.segments
            for elem in seg.scene_elements
            if float(elem.end_time or 0) > float(elem.start_time or 0)
        )
        if populated == 0:
            raise RuntimeError(
                "TimingEngine.set_scene_element_times() ran but produced no "
                "elements with positive duration; refusing to render an empty "
                "video. Check the script's sub_segment_estimated_durations."
            )
