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
import re
import subprocess
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.models import Script, ScriptSegment, SceneElement, WordTiming
from src.core.interfaces import Renderer
from src.utils.logger import setup_logger


def _safe_get_item(content, idx):
    """Return content.items[idx] if idx is a valid in-range int, else None."""
    if idx is None or not isinstance(idx, int):
        return None
    if 0 <= idx < len(content.items):
        return content.items[idx]
    return None


def _safe_get_comment(item, idx):
    """Return item.comments[idx] if idx is a valid in-range int, else None."""
    if idx is None or not isinstance(idx, int):
        return None
    if 0 <= idx < len(item.comments):
        return item.comments[idx]
    return None


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

    def _prepare_render_data(self, script: Script, audio_dir: str, content = None, date: str = "") -> tuple[Path, str]:
        self._prepare_audio_assets(script, audio_dir)
        if content and date:
            self._prepare_image_assets(content, date)

        props_data = self._script_to_props(script, audio_dir, content)
        props_json = json.dumps(props_data, ensure_ascii=False, indent=2)

        public_dir = self.remotion_dir / "public"
        public_dir.mkdir(parents=True, exist_ok=True)
        props_file = public_dir / "props.json"
        props_file.write_text(props_json, encoding="utf-8")
        self.logger.info(f"Props written to {props_file} ({len(props_json)} bytes)")

        return props_file, props_json

    def preview(self, script: Script, audio_dir: str, content = None) -> None:
        self.logger.info("Starting Remotion Studio for preview...")
        self.logger.info("Press Ctrl+C to stop the preview server.")

        if not self._node_path:
            raise RuntimeError("Node.js not found!")

        _, props_json = self._prepare_render_data(script, audio_dir, content, date="")
        self._ensure_dependencies_installed()

        # Write props to a temp file to avoid OS command-line length limits
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
        # 只打印命令概要，省略冗长的 props
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

    def render(self, script: Script, audio_dir: str, output_path: str, content = None, date: str = "") -> None:
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

        # Write props to a temp file to avoid OS command-line length limits
        cli_props_file = self._write_props_file(props_json)

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
        # 只打印命令概要，省略冗长的 props
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

        if props_file.exists():
            props_file.unlink()

        self.logger.info("Rendering complete")

    def _expand_element_props(self, element_type: str, props: Dict[str, Any], content) -> Dict[str, Any]:
        """Dispatch to the per-type expander; fall back to raw props on failure or unknown type."""
        if content is None:
            return props
        expander = _ELEMENT_EXPANDERS.get(element_type)
        if expander is None:
            return props
        try:
            result = expander(self, props, content)
        except Exception as e:
            self.logger.info(f"Failed to expand props for {element_type}: {e}")
            return props
        return result if result is not None else props

    def _expand_story_header(self, props, content):
        item = _safe_get_item(content, props.get("story_index"))
        if item is None:
            return None
        return {
            "story_title": item.title,
            "score": item.score or 0,
            "comments": item.comment_count or 0,
        }

    def _expand_comment_card(self, props, content):
        item = _safe_get_item(content, props.get("story_index"))
        if item is None:
            return None
        comment = _safe_get_comment(item, props.get("comment_index"))
        if comment is None:
            return None
        return {
            "author": comment.author,
            "score": 0,  # comment-level scores not tracked in our model
            "text": comment.content,
            "translation": "",
            "angle_label": "",
        }

    def _expand_comment_bubble(self, props, content):
        item = _safe_get_item(content, props.get("story_index"))
        if item is None:
            return None
        comment = _safe_get_comment(item, props.get("comment_index"))
        if comment is None:
            return None
        return {
            "author": comment.author,
            "original_text": comment.content,
            "chinese_summary": "",
        }

    def _expand_news_carousel_card(self, props, content):
        item = _safe_get_item(content, props.get("story_index"))
        if item is None:
            return None
        result = {
            "story_title": item.title,
            "score": item.score or 0,
            "comment_count": item.comment_count or 0,
            "author": "?",
            "comment_score": 0,
            "comment_text": "",
            "comment_translation": "",
        }
        comment = _safe_get_comment(item, props.get("comment_index"))
        if comment is not None:
            result["author"] = comment.author
            result["comment_text"] = comment.content
        return result

    def _expand_dashboard_card(self, props, content):
        """Trust LLM entries, but overwrite per-entry title/score from content."""
        expanded_entries = []
        for entry in props.get("entries", []):
            expanded = dict(entry)
            item = _safe_get_item(content, entry.get("story_index"))
            if item is not None:
                expanded["original_title"] = item.title
                expanded["title_cn"] = item.title_cn or ""
                expanded["score"] = item.score or 0
                expanded["comment_count"] = item.comment_count or 0
            expanded_entries.append(expanded)
        return {"entries": expanded_entries}

    def _expand_story_scan_card(self, props, content):
        """Overwrite story meta and viewpoint quotes from content; derive stance distribution."""
        if props.get("story_index") is None:
            return None
        result = dict(props)
        item = _safe_get_item(content, props.get("story_index"))
        if item is None:
            return result  # keep props copy, as original behavior
        result["story_title"] = item.title
        result["title_cn"] = item.title_cn or ""
        result["score"] = item.score or 0
        result["comment_count"] = item.comment_count or 0
        viewpoints = result.get("viewpoints", [])
        expanded_vps = []
        for vp in viewpoints:
            evp = dict(vp)
            comment = _safe_get_comment(item, vp.get("comment_index"))
            if comment is not None and not evp.get("quote"):
                evp["quote"] = (comment.content or "")[:50]
            expanded_vps.append(evp)
        result["viewpoints"] = expanded_vps
        if viewpoints and "stance_distribution" not in result:
            stance_counts: Dict[str, int] = {}
            for vp in viewpoints:
                stance = vp.get("stance", "")
                if stance:
                    stance_counts[stance] = stance_counts.get(stance, 0) + 1
            if stance_counts:
                total = sum(stance_counts.values())
                result["stance_distribution"] = {
                    k: round(v / total, 2) for k, v in stance_counts.items()
                }
        return result

    def _expand_perspective_compare(self, props, content):
        def build_side(side):
            if not isinstance(side, dict) or "story_index" not in side or "comment_index" not in side:
                return side
            item = _safe_get_item(content, side.get("story_index"))
            if item is None:
                return side
            comment = _safe_get_comment(item, side.get("comment_index"))
            if comment is None:
                return side
            return {
                "label": side.get("label", ""),
                "text": comment.content,
                "translation": "",
            }

        return {
            "perspective_a": build_side(props.get("perspective_a", {})),
            "perspective_b": build_side(props.get("perspective_b", {})),
        }

    def _expand_image_card(self, props, content):
        if props.get("story_index") is None:
            return None
        item = _safe_get_item(content, props.get("story_index"))
        image_index = props.get("image_index", 0)
        caption = props.get("caption", "")
        if item is not None and image_index < len(item.article_images):
            image_path = item.article_images[image_index]
            return {
                "image_src": f"images/{Path(image_path).name}",
                "caption": caption,
                "image_index": image_index,
            }
        return {"image_src": "", "caption": "", "image_index": 0}

    def _script_to_props(self, script: Script, audio_dir: str, content = None) -> Dict[str, Any]:
        segments_data: List[Dict[str, Any]] = []
        audio_path_obj = Path(audio_dir).resolve()

        for segment in script.segments:
            duration = float(segment.actual_duration or segment.estimated_duration)
            estimated = float(segment.estimated_duration or 0)
            ratio = duration / estimated if estimated > 0 else 1.0

            # 1. 先构建字幕，得到所有句子边界
            cues = self._build_cues(segment, duration, ratio)

            # 2. 提取所有边界点（包括 0 和 duration）
            boundaries = {0.0, duration}
            for cue in cues:
                boundaries.add(cue["start_time"])
                boundaries.add(cue["end_time"])
            sorted_boundaries = sorted(boundaries)

            seg_dict: Dict[str, Any] = {
                "segment_type": segment.segment_type,
                "audio_text": segment.audio_text,
                "cues": cues,
                "duration": duration,
                "start_time": float(segment.start_time or 0),
                "end_time": float(segment.end_time or 0),
                "scene_elements": [],
            }

            if segment.audio_path:
                src_audio = Path(segment.audio_path)
                if not src_audio.is_absolute():
                    src_audio = audio_path_obj / src_audio
                seg_dict["audio_path"] = f"audio/{src_audio.name}"

            # 3. 将场景元素对齐到字幕边界，并扩展 props
            aligned_count = 0
            expanded_count = 0
            for elem in segment.scene_elements:
                # 首选：按 cue 索引把 LLM 估计时间映射到真实音频时间。
                # scene_elements 的时间在 LLM 估计时长空间里，且通常落在 LLM cue 边界上；
                # 用索引映射到真实 cue 可避免 ratio 线性缩放在非均匀 TTS 时长上的漂移。
                mapped = self._map_llm_time_to_real(
                    elem.start_time, elem.end_time, segment.cues, cues
                )
                if mapped is not None:
                    aligned_start = max(0.0, min(mapped[0], duration))
                    aligned_end = max(aligned_start, min(mapped[1], duration))
                    if aligned_end <= aligned_start:
                        continue
                    aligned_count += 1
                else:
                    # 回退：ratio 线性缩放 + snap 到边界（无 cue 数据时）
                    elem_start = max(0.0, min(elem.start_time * ratio, duration))
                    elem_end = max(0.0, min(elem.end_time * ratio, duration))
                    if elem_end <= elem_start:
                        continue

                    aligned_start = self._snap_to_boundary(elem_start, sorted_boundaries)
                    aligned_end = self._snap_to_boundary(elem_end, sorted_boundaries)

                    if aligned_end <= aligned_start:
                        for b in sorted_boundaries:
                            if b > aligned_start:
                                aligned_end = b
                                break
                        if aligned_end <= aligned_start:
                            aligned_end = min(aligned_start + 1.0, duration)

                    if abs(aligned_start - elem_start) > 0.001 or abs(aligned_end - elem_end) > 0.001:
                        aligned_count += 1

                # 根据索引扩展 props
                expanded_props = self._expand_element_props(elem.element_type, elem.props.copy(), content)
                if expanded_props != elem.props:
                    expanded_count += 1

                elem_dict = {
                    "element_type": elem.element_type,
                    "start_time": aligned_start,
                    "end_time": aligned_end,
                    "props": self._sanitize_props(expanded_props),
                }
                seg_dict["scene_elements"].append(elem_dict)

            if aligned_count > 0:
                self.logger.debug(
                    f"Aligned {aligned_count}/{len(segment.scene_elements)} scene elements to cue boundaries"
                )
            if expanded_count > 0:
                self.logger.debug(
                    f"Expanded props for {expanded_count}/{len(segment.scene_elements)} scene elements"
                )

            segments_data.append(seg_dict)

        return {
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "bgColor": self.bg_color,
            "title": script.title,
            "totalDuration": float(script.total_duration or 0),
            "segments": segments_data,
            "audioDir": str(Path(audio_dir).resolve()),
        }

    @staticmethod
    def _map_llm_time_to_real(
        elem_start: float,
        elem_end: float,
        llm_cues: List["Cue"],
        real_cues: List[Dict[str, Any]],
    ) -> Optional[tuple]:
        """把 LLM 估计时间空间的 [elem_start, elem_end] 映射到真实音频时间。

        scene_elements 的时间来自 LLM，落在它自己生成的 cue 边界上；
        real_cues 来自 TTS 的真实 word_timings。用"cue 索引"映射避免 ratio
        线性缩放产生的漂移（真实每句 TTS 时长并不均匀，线性缩放会错位累积）。

        返回 None 表示无法按索引映射，调用方应回退到 ratio 缩放。
        """
        if not llm_cues or not real_cues:
            return None

        n_llm = len(llm_cues)
        n_real = len(real_cues)

        # 找到 start/end 最贴近的 LLM cue 索引（分别匹配 start_time / end_time）
        start_idx = min(range(n_llm), key=lambda i: abs(llm_cues[i].start_time - elem_start))
        end_idx = min(range(n_llm), key=lambda i: abs(llm_cues[i].end_time - elem_end))
        if end_idx < start_idx:
            end_idx = start_idx

        # 按比例映射到 real cue 索引（数量一致时即恒等映射）
        def _to_real(i: int) -> int:
            if n_llm == n_real:
                return i
            j = round(i * n_real / n_llm) if n_llm > 0 else 0
            return max(0, min(j, n_real - 1))

        r_start = _to_real(start_idx)
        r_end = _to_real(end_idx)
        if r_end < r_start:
            r_end = r_start

        # 当 scene_element 的 end_time 对齐到最后一条 LLM cue 的结尾时，
        # 说明该元素意图覆盖全段音频。此时直接映射到最后一条 real cue，
        # 避免 n_llm < n_real 时因索引映射粒度不足导致元素提前结束。
        if end_idx == n_llm - 1 and abs(elem_end - llm_cues[-1].end_time) < 0.01:
            r_end = n_real - 1

        return (
            float(real_cues[r_start]["start_time"]),
            float(real_cues[r_end]["end_time"]),
        )

    @staticmethod
    def _snap_to_boundary(time: float, boundaries: List[float]) -> float:
        """将时间点对齐到最近的边界"""
        if not boundaries:
            return time
        # 找最近的边界
        closest = min(boundaries, key=lambda b: abs(b - time))
        return closest

    def _build_cues(self, segment: "ScriptSegment", duration: float, ratio: float) -> List[Dict[str, Any]]:
        word_timings_raw = segment.meta.get("word_timings", [])
        if word_timings_raw:
            word_timings = [
                WordTiming(text=wt["text"], start_time=wt["start_time"], end_time=wt["end_time"])
                for wt in word_timings_raw
            ]
            timing_level = segment.meta.get("timing_level", "word")
            self.logger.debug(
                f"Using real TTS timings: {timing_level} level, {len(word_timings)} timings"
            )
            if timing_level == "sentence":
                return self._build_cues_from_sentence_timings(word_timings, duration)
            else:
                return self._build_cues_from_word_timings(word_timings, duration)

        if segment.cues:
            self.logger.debug(f"Using LLM-generated cues: {len(segment.cues)} cues")
            result: List[Dict[str, Any]] = []
            for cue in segment.cues:
                scaled_start = max(0.0, min(cue.start_time * ratio, duration))
                scaled_end = max(0.0, min(cue.end_time * ratio, duration))
                if scaled_end <= scaled_start:
                    scaled_end = min(scaled_start + 2.0, duration)
                result.append({
                    "text": cue.text,
                    "start_time": round(scaled_start, 3),
                    "end_time": round(scaled_end, 3),
                })

            if result:
                result[0]["start_time"] = 0.0
                result[-1]["end_time"] = duration

            last_cue_end = segment.cues[-1].end_time if segment.cues else 0
            estimated = segment.estimated_duration or 0
            coverage = last_cue_end / estimated if estimated > 0 else 0

            if coverage >= 0.6:
                return result

            self.logger.debug(
                f"LLM cues coverage too low ({coverage:.0%}, last_end={last_cue_end}s "
                f"vs estimated={estimated}s), falling back to auto-split"
            )

        if not word_timings_raw and not segment.cues:
            self.logger.debug(f"Using auto-split cues: duration={duration:.2f}s")

        return self._split_into_cues(segment.audio_text, duration)

    @staticmethod
    def _build_cues_from_sentence_timings(
        sentence_timings: List["WordTiming"], duration: float
    ) -> List[Dict[str, Any]]:
        if not sentence_timings:
            return []

        cues: List[Dict[str, Any]] = []
        for st in sentence_timings:
            cues.append({
                "text": st.text,
                "start_time": round(st.start_time, 3),
                "end_time": round(st.end_time, 3),
            })

        if cues:
            cues[0]["start_time"] = 0.0
            cues[-1]["end_time"] = duration

        return cues

    @staticmethod
    def _build_cues_from_word_timings(
        word_timings: List["WordTiming"], duration: float
    ) -> List[Dict[str, Any]]:
        if not word_timings:
            return []

        sentence_breaks = set("。！？；.!?;")
        clause_breaks = set("，,、：:;")

        cues: List[Dict[str, Any]] = []
        current_words: List["WordTiming"] = []
        current_text_parts: List[str] = []

        def flush():
            if not current_words:
                return
            text = "".join(current_text_parts)
            cues.append({
                "text": text,
                "start_time": round(current_words[0].start_time, 3),
                "end_time": round(current_words[-1].end_time, 3),
            })

        for wt in word_timings:
            current_words.append(wt)
            current_text_parts.append(wt.text)

            last_char = wt.text[-1] if wt.text else ""
            if last_char in sentence_breaks:
                flush()
                current_words = []
                current_text_parts = []
            elif last_char in clause_breaks and len("".join(current_text_parts)) > 20:
                flush()
                current_words = []
                current_text_parts = []

        if current_words:
            flush()

        if cues:
            cues[0]["start_time"] = 0.0
            cues[-1]["end_time"] = duration

        return cues

    @staticmethod
    def _split_into_cues(text: str, duration: float) -> List[Dict[str, Any]]:
        if not text or duration <= 0:
            return []

        text = re.sub(r'<[^>]+>', '', text).strip()
        if not text:
            return []

        sentences = re.split(r'(?<=[。！？；\.\!\?;])', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return [{"text": text, "start_time": 0.0, "end_time": duration}]

        merged: List[str] = []
        for s in sentences:
            if merged and len(merged[-1]) < 8:
                merged[-1] = merged[-1] + s
            else:
                merged.append(s)

        final: List[str] = []
        for s in merged:
            if len(s) > 40:
                parts = re.split(r'(?<=[，,、：:])', s)
                parts = [p.strip() for p in parts if p.strip()]
                buf = ""
                for part in parts:
                    if buf and len(buf) + len(part) > 40:
                        final.append(buf)
                        buf = part
                    else:
                        buf = buf + part
                if buf:
                    final.append(buf)
            else:
                final.append(s)

        if not final:
            return [{"text": text, "start_time": 0.0, "end_time": duration}]

        total_chars = sum(len(s) for s in final)
        cues: List[Dict[str, Any]] = []
        current_time = 0.0
        for s in final:
            char_ratio = len(s) / total_chars if total_chars > 0 else 1.0 / len(final)
            cue_duration = duration * char_ratio
            cues.append({
                "text": s,
                "start_time": round(current_time, 3),
                "end_time": round(current_time + cue_duration, 3),
            })
            current_time += cue_duration

        if cues:
            cues[-1]["end_time"] = duration

        return cues

    @staticmethod
    def _sanitize_props(props: Dict[str, Any]) -> Dict[str, Any]:
        cleaned: Dict[str, Any] = {}
        for k, v in props.items():
            if v is None:
                cleaned[k] = None
            elif isinstance(v, (str, int, float, bool)):
                cleaned[k] = v
            elif isinstance(v, dict):
                cleaned[k] = RemotionRenderer._sanitize_props(v)
            elif isinstance(v, list):
                cleaned[k] = [
                    RemotionRenderer._sanitize_props(item) if isinstance(item, dict)
                    else str(item) if not isinstance(item, (str, int, float, bool, type(None)))
                    else item
                    for item in v
                ]
            elif hasattr(v, "item"):
                cleaned[k] = v.item()
            elif hasattr(v, "__str__"):
                cleaned[k] = str(v)
            else:
                cleaned[k] = str(v)
        return cleaned

    def _build_env(self) -> Dict[str, str]:
        import os
        env = dict(os.environ)

        node_modules = str(self.remotion_dir / "node_modules")
        existing = env.get("NODE_PATH", "")
        if node_modules not in existing:
            env["NODE_PATH"] = (
                f"{node_modules}:{existing}" if existing else node_modules
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

    def _prepare_image_assets(self, content, date: str):
        """Copy enriched images to Remotion public/images/ for serving."""
        if content is None:
            return
        public_dir = self.remotion_dir / "public"
        image_subdir = public_dir / "images"
        image_subdir.mkdir(parents=True, exist_ok=True)

        copied = 0
        for item in content.items:
            for img_path in item.article_images:
                src = Path(img_path)
                if not src.is_absolute():
                    src = Path(f"data/{date}") / img_path
                if src.exists():
                    dest = image_subdir / src.name
                    if not dest.exists():
                        shutil.copy2(src, dest)
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

    def _write_props_file(self, props_json: str) -> str:
        """Write props JSON to a temp file and return its path.

        Avoids OS command-line length limits when passing large props to the
        Remotion CLI. The caller is responsible for cleanup.
        """
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".json", prefix="remotion_props_")
        with open(fd, "w", encoding="utf-8") as f:
            f.write(props_json)
        self.logger.debug(f"Props written to temp file: {path} ({len(props_json)} bytes)")
        return path


# Dispatch table mapping element_type -> unbound expander method on RemotionRenderer.
# Add a new element type by (1) writing a `_expand_<type>(self, props, content)` method
# and (2) registering it here. Each expander returns an expanded props dict, or None
# to signal "leave props unchanged".
_ELEMENT_EXPANDERS = {
    "story_header": RemotionRenderer._expand_story_header,
    "comment_card": RemotionRenderer._expand_comment_card,
    "comment_bubble": RemotionRenderer._expand_comment_bubble,
    "news_carousel_card": RemotionRenderer._expand_news_carousel_card,
    "dashboard_card": RemotionRenderer._expand_dashboard_card,
    "story_scan_card": RemotionRenderer._expand_story_scan_card,
    "perspective_compare": RemotionRenderer._expand_perspective_compare,
    "image_card": RemotionRenderer._expand_image_card,
}
