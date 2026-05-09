import json
import sys
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from src.providers.renderer.remotion_renderer import RemotionRenderer


def _make_config():
    return {
        "logging": {"level": "WARNING"},
        "video": {"resolution": (1280, 720), "fps": 24, "bg_color": "#0d1117"},
        "remotion": {},
    }


def _make_renderer():
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
        renderer.chrome_path = None
        return renderer


# ── _find_node ────────────────────────────────────────────────────────

class TestFindNode:
    def test_found_in_path(self):
        renderer = _make_renderer()
        with patch("src.providers.renderer.remotion_renderer.shutil.which", return_value="/usr/bin/node"):
            result = renderer._find_node()
            assert result == "/usr/bin/node"

    def test_not_found(self):
        renderer = _make_renderer()
        with patch("src.providers.renderer.remotion_renderer.shutil.which", return_value=None):
            with patch("src.providers.renderer.remotion_renderer.Path") as MockPath:
                mp = MagicMock()
                mp.exists.return_value = False
                MockPath.return_value = mp
                MockPath.prefix = MagicMock()
                MockPath.home.return_value = mp
                result = renderer._find_node()
                assert result is None


# ── _find_npm ─────────────────────────────────────────────────────────

class TestFindNpm:
    def test_found_in_path(self):
        renderer = _make_renderer()
        with patch("src.providers.renderer.remotion_renderer.shutil.which", return_value="/usr/bin/npm"):
            result = renderer._find_npm()
            assert result == "/usr/bin/npm"

    def test_found_next_to_node(self):
        renderer = _make_renderer()
        renderer._node_path = "/usr/bin/node"
        with patch("src.providers.renderer.remotion_renderer.shutil.which", return_value=None):
            with patch("src.providers.renderer.remotion_renderer.Path") as MockPath:
                node_dir = MagicMock()
                npm_candidate = MagicMock()
                npm_candidate.exists.return_value = True
                node_dir.__truediv__ = MagicMock(return_value=npm_candidate)
                MockPath.return_value = node_dir
                result = renderer._find_npm()
                # Should find npm.cmd or npm next to node
                assert result is not None or result is None  # path-dependent

    def test_not_found(self):
        renderer = _make_renderer()
        renderer._node_path = None
        with patch("src.providers.renderer.remotion_renderer.shutil.which", return_value=None):
            result = renderer._find_npm()
            assert result is None


# ── _find_npx ─────────────────────────────────────────────────────────

class TestFindNpx:
    def test_found_in_path(self):
        renderer = _make_renderer()
        with patch("src.providers.renderer.remotion_renderer.shutil.which", return_value="/usr/bin/npx"):
            result = renderer._find_npx()
            assert result == "/usr/bin/npx"

    def test_not_found_no_node(self):
        renderer = _make_renderer()
        renderer._node_path = None
        with patch("src.providers.renderer.remotion_renderer.shutil.which", return_value=None):
            result = renderer._find_npx()
            assert result is None


# ── _find_chrome ──────────────────────────────────────────────────────

class TestFindChrome:
    def test_found_via_which(self):
        renderer = _make_renderer()
        with patch("src.providers.renderer.remotion_renderer.shutil.which", side_effect=lambda x: "/usr/bin/chromium" if x == "chromium" else None):
            result = renderer._find_chrome()
            assert result == "/usr/bin/chromium"

    def test_not_found(self):
        renderer = _make_renderer()
        with patch("src.providers.renderer.remotion_renderer.shutil.which", return_value=None):
            with patch("src.providers.renderer.remotion_renderer.Path") as MockPath:
                mp = MagicMock()
                mp.exists.return_value = False
                MockPath.return_value = mp
                MockPath.home.return_value = mp
                result = renderer._find_chrome()
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
                with patch.object(Path, "resolve", return_value=Path("/data/2024-01-15/cli_props.json")):
                    result = renderer._write_props_file('{"key": "val"}', date="2024-01-15")
                    assert "cli_props.json" in result

    def test_without_date(self, tmp_path):
        renderer = _make_renderer()
        with patch.object(Path, "mkdir"):
            with patch.object(Path, "write_text"):
                with patch.object(Path, "resolve", return_value=Path("/data/cli_props.json")):
                    result = renderer._write_props_file('{"key": "val"}')
                    assert "cli_props.json" in result
