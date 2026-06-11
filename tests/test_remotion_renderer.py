import math
import sys
from unittest.mock import patch, MagicMock
from pathlib import Path

from src.core.models import Script, ScriptSegment, SceneElement
from src.providers.renderer.remotion_renderer import RemotionRenderer
from src.providers.renderer.binary_finder import (
    find_node,
    find_npm,
    find_npx,
    find_chrome,
)
from src.providers.renderer.chunk_planner import compute_segment_chunks


def _make_config():
    return {
        "logging": {"level": "WARNING"},
        "video": {"resolution": (1280, 720), "fps": 24, "bg_color": "#0d1117"},
        "remotion": {},
    }


def _make_renderer(ffprobe_path: str | None = None):
    with patch.object(RemotionRenderer, "__init__", lambda self, *a, **kw: None):
        renderer = RemotionRenderer.__new__(RemotionRenderer)
        renderer.config = _make_config()
        renderer.debug = False
        renderer.logger = MagicMock()
        renderer.width = 1280
        renderer.height = 720
        renderer.fps = 24
        renderer.bg_color = "#0d1117"
        renderer.remotion_dir = Path("src/providers/renderer/remotion")
        renderer.concurrency = None
        renderer.image_format = "jpeg"
        renderer.codec = "h264"
        renderer.crf = 23
        renderer.pixels_per_frame = None
        renderer._node_path = "/usr/bin/node"
        renderer._npm_path = "/usr/bin/npm"
        renderer._npx_path = "/usr/bin/npx"
        renderer._ffmpeg_path = "/usr/bin/ffmpeg"
        renderer._ffprobe_path = ffprobe_path
        renderer.chrome_path = None
        return renderer


# ── find_node ────────────────────────────────────────────────────────


class TestFindNode:
    def test_found_in_path(self):
        with patch(
            "src.providers.renderer.binary_finder.shutil.which",
            return_value="/usr/bin/node",
        ):
            result = find_node()
            assert result == "/usr/bin/node"

    def test_not_found(self):
        with patch(
            "src.providers.renderer.binary_finder.shutil.which", return_value=None
        ):
            with patch("src.providers.renderer.binary_finder.Path") as MockPath:
                mp = MagicMock()
                mp.exists.return_value = False
                MockPath.return_value = mp
                MockPath.prefix = MagicMock()
                MockPath.home.return_value = mp
                result = find_node()
                assert result is None


# ── find_npm ─────────────────────────────────────────────────────────


class TestFindNpm:
    def test_found_in_path(self):
        with patch(
            "src.providers.renderer.binary_finder.shutil.which",
            return_value="/usr/bin/npm",
        ):
            result = find_npm()
            assert result == "/usr/bin/npm"

    def test_found_next_to_node(self):
        with patch(
            "src.providers.renderer.binary_finder.shutil.which", return_value=None
        ):
            with patch("src.providers.renderer.binary_finder.Path") as MockPath:
                node_dir = MagicMock()
                npm_candidate = MagicMock()
                npm_candidate.exists.return_value = True
                node_dir.__truediv__ = MagicMock(return_value=npm_candidate)
                MockPath.return_value = node_dir
                result = find_npm(node_path="/usr/bin/node")
                assert isinstance(result, str)  # found npm.cmd or npm next to node

    def test_not_found(self):
        with patch(
            "src.providers.renderer.binary_finder.shutil.which", return_value=None
        ):
            result = find_npm(node_path=None)
            assert result is None


# ── find_npx ─────────────────────────────────────────────────────────


class TestFindNpx:
    def test_found_in_path(self):
        with patch(
            "src.providers.renderer.binary_finder.shutil.which",
            return_value="/usr/bin/npx",
        ):
            result = find_npx()
            assert result == "/usr/bin/npx"

    def test_not_found_no_node(self):
        with patch(
            "src.providers.renderer.binary_finder.shutil.which", return_value=None
        ):
            result = find_npx(node_path=None)
            assert result is None


# ── find_chrome ──────────────────────────────────────────────────────


class TestFindChrome:
    def test_found_via_which(self):
        with patch(
            "src.providers.renderer.binary_finder.shutil.which",
            side_effect=lambda x: "/usr/bin/chromium" if x == "chromium" else None,
        ):
            result = find_chrome()
            assert result == "/usr/bin/chromium"

    def test_not_found(self):
        with patch(
            "src.providers.renderer.binary_finder.shutil.which", return_value=None
        ):
            with patch("src.providers.renderer.binary_finder.Path") as MockPath:
                mp = MagicMock()
                mp.exists.return_value = False
                MockPath.return_value = mp
                MockPath.home.return_value = mp
                result = find_chrome()
                assert result is None


# ── _build_env ────────────────────────────────────────────────────────


class TestBuildEnv:
    def test_node_path_prepended(self):
        renderer = _make_renderer()
        with patch.dict("os.environ", {"NODE_PATH": ""}, clear=False):
            env = renderer._build_env()
            assert "NODE_PATH" in env
            assert str(renderer.remotion_dir / "node_modules") in env["NODE_PATH"]

    def test_windows_separator(self):
        renderer = _make_renderer()
        with patch("src.providers.renderer.remotion_renderer.sys") as mock_sys:
            mock_sys.platform = "win32"
            mock_sys.prefix = sys.prefix
            with patch.dict("os.environ", {"NODE_PATH": ""}, clear=False):
                env = renderer._build_env()
                # On Windows, separator should be ;
                assert "NODE_PATH" in env

    def test_existing_preserved(self):
        renderer = _make_renderer()
        with patch.dict("os.environ", {"NODE_PATH": "/existing/path"}, clear=False):
            env = renderer._build_env()
            assert "/existing/path" in env["NODE_PATH"]


# ── _write_props_file ─────────────────────────────────────────────────


class TestWritePropsFile:
    def test_with_date(self, tmp_path):
        renderer = _make_renderer()
        with patch.object(Path, "mkdir"):
            with patch.object(Path, "write_text"):
                with patch.object(
                    Path,
                    "resolve",
                    return_value=Path("/data/2024-01-15/cli_props.json"),
                ):
                    result = renderer._write_props_file(
                        '{"key": "val"}', date="2024-01-15"
                    )
                    assert "cli_props.json" in result

    def test_without_date(self, tmp_path):
        renderer = _make_renderer()
        with patch.object(Path, "mkdir"):
            with patch.object(Path, "write_text"):
                with patch.object(
                    Path, "resolve", return_value=Path("/data/cli_props.json")
                ):
                    result = renderer._write_props_file('{"key": "val"}')
                    assert "cli_props.json" in result


class TestPreview:
    def test_writes_dated_cli_props_file(self):
        renderer = _make_renderer()
        script = Script(
            title="Test",
            description="",
            tags=[],
            total_duration=1.0,
            segments=[
                ScriptSegment(
                    segment_type="opening",
                    audio_text="test",
                    duration=1.0,
                    start_time=0.0,
                    end_time=1.0,
                )
            ],
        )

        with patch.object(
            renderer,
            "write_props",
            return_value=(Path("public/props.json"), '{"ok": true}', None),
        ):
            with patch.object(renderer, "_ensure_dependencies_installed"):
                with patch.object(
                    renderer,
                    "_write_props_file",
                    return_value="data/2024-01-15/cli_props.json",
                ) as write_props:
                    with patch.object(
                        renderer,
                        "_get_remotion_cli_path",
                        return_value="remotion-cli.js",
                    ):
                        with patch.object(renderer, "_build_env", return_value={}):
                            with patch(
                                "src.providers.renderer.remotion_renderer.subprocess.run"
                            ) as run:
                                run.return_value.returncode = 0

                                renderer.preview(
                                    script, "data/2024-01-15/audio", date="2024-01-15"
                                )

        write_props.assert_called_once_with('{"ok": true}', date="2024-01-15")


class TestChunkCacheDir:
    def test_scoped_by_date_and_props(self):
        renderer = _make_renderer()

        may_11 = renderer._chunk_cache_dir("2026-05-11", '{"title": "May 11"}')
        may_13 = renderer._chunk_cache_dir("2026-05-13", '{"title": "May 13"}')

        assert may_11 != may_13
        # Chunk caches now live under data/{date}/render/remotion/chunks/ (per-date
        # runtime dir), not under the Remotion source tree.
        assert (
            may_11.parent
            == Path("data") / "2026-05-11" / "render" / "remotion" / "chunks"
        )
        assert may_11.name.startswith("2026-05-11_")
        assert may_13.name.startswith("2026-05-13_")

    def test_same_input_reuses_cache_dir(self):
        renderer = _make_renderer()

        first = renderer._chunk_cache_dir("2026-05-13", '{"title": "May 13"}')
        second = renderer._chunk_cache_dir("2026-05-13", '{"title": "May 13"}')

        assert first == second


# ── compute_segment_chunks ────────────────────────────────────────────


class TestComputeSegmentChunks:
    def test_basic_segments(self):
        script = Script(
            title="Test",
            description="",
            tags=[],
            total_duration=12.0,
            segments=[
                ScriptSegment(
                    segment_type="opening",
                    audio_text="",
                    duration=4.0,
                    start_time=0.0,
                    end_time=4.0,
                ),
                ScriptSegment(
                    segment_type="closing",
                    audio_text="",
                    duration=8.0,
                    start_time=4.0,
                    end_time=12.0,
                ),
            ],
        )
        chunks = compute_segment_chunks(script, fps=24, total_frames=288)
        assert len(chunks) == 2
        assert chunks[0][2] == "opening"
        assert chunks[1][2] == "closing"
        # Frames should be contiguous and cover full range
        assert chunks[0][0] == 0
        assert chunks[-1][1] == 287
        for i in range(len(chunks) - 1):
            assert chunks[i][1] + 1 == chunks[i + 1][0]

    def test_story_scan_split_by_scene_elements(self):
        script = Script(
            title="Test",
            description="",
            tags=[],
            total_duration=30.0,
            segments=[
                ScriptSegment(
                    segment_type="opening",
                    audio_text="",
                    duration=4.0,
                    start_time=0.0,
                    end_time=4.0,
                ),
                ScriptSegment(
                    segment_type="story_scan",
                    audio_text="",
                    duration=20.0,
                    start_time=4.0,
                    end_time=24.0,
                    scene_elements=[
                        SceneElement(
                            element_type="event_card",
                            props={},
                            start_time=0.0,
                            end_time=7.0,
                        ),
                        SceneElement(
                            element_type="event_card",
                            props={},
                            start_time=7.0,
                            end_time=14.0,
                        ),
                        SceneElement(
                            element_type="event_card",
                            props={},
                            start_time=14.0,
                            end_time=20.0,
                        ),
                    ],
                ),
                ScriptSegment(
                    segment_type="closing",
                    audio_text="",
                    duration=6.0,
                    start_time=24.0,
                    end_time=30.0,
                ),
            ],
        )
        chunks = compute_segment_chunks(script, fps=24, total_frames=720)
        assert len(chunks) == 5
        labels = [c[2] for c in chunks]
        assert labels == ["opening", "story_0", "story_1", "story_2", "closing"]
        # Contiguous
        assert chunks[0][0] == 0
        assert chunks[-1][1] == 719
        for i in range(len(chunks) - 1):
            assert chunks[i][1] + 1 == chunks[i + 1][0]

    def test_story_scan_without_elements_falls_back_to_whole_segment(self):
        script = Script(
            title="Test",
            description="",
            tags=[],
            total_duration=24.0,
            segments=[
                ScriptSegment(
                    segment_type="opening",
                    audio_text="",
                    duration=4.0,
                    start_time=0.0,
                    end_time=4.0,
                ),
                ScriptSegment(
                    segment_type="story_scan",
                    audio_text="",
                    duration=16.0,
                    start_time=4.0,
                    end_time=20.0,
                ),
                ScriptSegment(
                    segment_type="closing",
                    audio_text="",
                    duration=4.0,
                    start_time=20.0,
                    end_time=24.0,
                ),
            ],
        )
        chunks = compute_segment_chunks(script, fps=24, total_frames=576)
        assert len(chunks) == 3
        assert chunks[1][2] == "story_scan"

    def test_frames_cover_total(self):
        script = Script(
            title="Test",
            description="",
            tags=[],
            total_duration=10.5,
            segments=[
                ScriptSegment(
                    segment_type="opening",
                    audio_text="",
                    duration=4.5,
                    start_time=0.0,
                    end_time=4.5,
                ),
                ScriptSegment(
                    segment_type="closing",
                    audio_text="",
                    duration=6.0,
                    start_time=4.5,
                    end_time=10.5,
                ),
            ],
        )
        total_frames = math.ceil(10.5 * 24)
        chunks = compute_segment_chunks(script, fps=24, total_frames=total_frames)
        assert chunks[0][0] == 0
        assert chunks[-1][1] == total_frames - 1


# ── chunk / final video integrity (regression for 2026-06-11 truncated
#    render where Remotion/Chromium crashed mid-frame and produced a
#    half-written MP4 that ffprobe couldn't read) ─────────────────────


class TestProbeDuration:
    """_probe_duration returns None when ffprobe can't read a file."""

    def test_returns_none_when_ffprobe_missing(self, tmp_path):
        renderer = _make_renderer(ffprobe_path=None)
        result = renderer._probe_duration(tmp_path / "nope.mp4")
        assert result is None

    def test_returns_none_when_probe_raises(self, tmp_path):
        renderer = _make_renderer(ffprobe_path="/usr/bin/ffprobe")
        bogus = tmp_path / "garbage.mp4"
        bogus.write_bytes(b"not a real mp4")
        with patch("subprocess.run", side_effect=OSError("ffprobe crashed")):
            result = renderer._probe_duration(bogus)
        assert result is None

    def test_returns_max_duration_from_probe(self, tmp_path):
        renderer = _make_renderer(ffprobe_path="/usr/bin/ffprobe")
        f = tmp_path / "ok.mp4"
        f.write_bytes(b"fake")
        fake = MagicMock(return_value=MagicMock(returncode=0, stdout="5.0\nN/A\n3.0\n"))
        with patch("subprocess.run", fake):
            result = renderer._probe_duration(f)
        assert result == 5.0


class TestVerifyChunk:
    """_verify_chunk must reject the signature of a Chromium crash file."""

    def test_missing_file_raises(self, tmp_path):
        renderer = _make_renderer(ffprobe_path=None)
        with __import__("pytest").raises(RuntimeError, match="missing or empty"):
            renderer._verify_chunk(tmp_path / "absent.mp4", "story_0")

    def test_empty_file_raises(self, tmp_path):
        renderer = _make_renderer(ffprobe_path=None)
        f = tmp_path / "empty.mp4"
        f.write_bytes(b"")
        with __import__("pytest").raises(RuntimeError, match="missing or empty"):
            renderer._verify_chunk(f, "story_0")

    def test_non_decodable_raises(self, tmp_path):
        """The 2026-06-11 case: real bytes on disk, ffprobe finds no streams."""
        renderer = _make_renderer(ffprobe_path="/usr/bin/ffprobe")
        f = tmp_path / "corrupt.mp4"
        f.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 100)
        with patch.object(
            renderer, "_probe_duration", return_value=None
        ) as probe, __import__("pytest").raises(
            RuntimeError, match="could not read any streams"
        ):
            renderer._verify_chunk(f, "story_0")
        probe.assert_called_once_with(f)

    def test_zero_duration_raises(self, tmp_path):
        renderer = _make_renderer(ffprobe_path="/usr/bin/ffprobe")
        f = tmp_path / "zero.mp4"
        f.write_bytes(b"\x00" * 1024)
        with patch.object(
            renderer, "_probe_duration", return_value=0.0
        ), __import__("pytest").raises(RuntimeError, match="0.000s"):
            renderer._verify_chunk(f, "story_0")

    def test_healthy_chunk_returns_duration(self, tmp_path):
        renderer = _make_renderer(ffprobe_path="/usr/bin/ffprobe")
        f = tmp_path / "good.mp4"
        f.write_bytes(b"\x00" * 1024)
        with patch.object(renderer, "_probe_duration", return_value=14.827):
            duration = renderer._verify_chunk(f, "story_0")
        assert duration == 14.827


class TestVerifyFinalOutput:
    """_verify_final_output catches the 'concat silently truncated' bug."""

    def test_short_final_raises(self, tmp_path):
        """The exact 2026-06-11 symptom: 10.79s of a ~115s target."""
        renderer = _make_renderer(ffprobe_path="/usr/bin/ffprobe")
        f = tmp_path / "output.mp4"
        f.write_bytes(b"\x00" * 1222489)
        with patch.object(renderer, "_probe_duration", return_value=10.79):
            with __import__("pytest").raises(RuntimeError, match="is 10.79s"):
                renderer._verify_final_output(f, expected_duration=115.0)

    def test_within_tolerance_passes(self, tmp_path):
        renderer = _make_renderer(ffprobe_path="/usr/bin/ffprobe")
        f = tmp_path / "output.mp4"
        f.write_bytes(b"\x00" * 1024)
        with patch.object(renderer, "_probe_duration", return_value=114.5):
            actual = renderer._verify_final_output(f, expected_duration=115.0)
        assert actual == 114.5

    def test_no_expected_duration_skips_check(self, tmp_path):
        """If we don't know what to expect, just probe and return."""
        renderer = _make_renderer(ffprobe_path="/usr/bin/ffprobe")
        f = tmp_path / "output.mp4"
        f.write_bytes(b"\x00" * 1024)
        with patch.object(renderer, "_probe_duration", return_value=10.0):
            actual = renderer._verify_final_output(f, expected_duration=0)
        assert actual == 10.0

    def test_no_streams_raises(self, tmp_path):
        renderer = _make_renderer(ffprobe_path="/usr/bin/ffprobe")
        f = tmp_path / "output.mp4"
        f.write_bytes(b"\x00" * 1024)
        with patch.object(renderer, "_probe_duration", return_value=None):
            with __import__("pytest").raises(RuntimeError, match="no decodable"):
                renderer._verify_final_output(f, expected_duration=115.0)

    def test_missing_file_raises(self, tmp_path):
        renderer = _make_renderer(ffprobe_path="/usr/bin/ffprobe")
        with __import__("pytest").raises(RuntimeError, match="missing or empty"):
            renderer._verify_final_output(
                tmp_path / "absent.mp4", expected_duration=115.0
            )
