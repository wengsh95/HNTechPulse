"""Tests for src/utils/atomic_io.py

``atomic_write_text`` and ``atomic_write_json`` are the foundation for
crash-safety across the pipeline (content.json, pipeline_state.json,
task files, segment cache). If a partial file ever lands at the
destination after a crash, every downstream step sees corrupt data with
no error. These tests pin the contract:

1. Happy path: tmp → fsync → os.replace → destination.
2. Crash before replace: tmp cleaned up, destination untouched.
3. Crash during os.replace: original destination preserved (or tmp cleaned).
4. fsync failure: tmp cleaned, exception re-raised, destination untouched.
5. Tmp sibling uses .suffix + ".tmp" so a second write of the same
   destination doesn't collide.
"""

import json
import os
from unittest.mock import patch

import pytest

from src.utils.atomic_io import atomic_write_json, atomic_write_text


# ── Happy path ──────────────────────────────────────────────────────


class TestHappyPath:
    def test_text_write_creates_file_with_content(self, tmp_path):
        target = tmp_path / "out.txt"
        atomic_write_text(target, "hello world")

        assert target.read_text(encoding="utf-8") == "hello world"
        # No tmp leftover
        assert not (target.with_suffix(target.suffix + ".tmp")).exists()

    def test_overwrite_replaces_existing_content(self, tmp_path):
        target = tmp_path / "out.txt"
        target.write_text("v1", encoding="utf-8")

        atomic_write_text(target, "v2")
        assert target.read_text(encoding="utf-8") == "v2"

    def test_creates_parent_directories(self, tmp_path):
        target = tmp_path / "deep" / "nested" / "out.txt"
        atomic_write_text(target, "x")
        assert target.exists()

    def test_json_write_produces_valid_json(self, tmp_path):
        target = tmp_path / "data.json"
        payload = {"a": 1, "b": ["x", "y"], "c": "中文 🚀"}

        atomic_write_json(target, payload)
        loaded = json.loads(target.read_text(encoding="utf-8"))
        assert loaded == payload

    def test_json_preserves_unicode_without_escaping(self, tmp_path):
        """ensure_ascii=False should keep Chinese readable on disk."""
        target = tmp_path / "data.json"
        atomic_write_json(target, {"k": "中文"})

        # The file should contain literal Chinese, not \uXXXX
        raw = target.read_text(encoding="utf-8")
        assert "中文" in raw
        assert "\\u" not in raw


# ── Crash recovery: tmp cleanup ──────────────────────────────────────


class TestCrashRecovery:
    def test_fsync_failure_cleans_tmp_and_raises(self, tmp_path):
        target = tmp_path / "out.txt"
        target.write_text("original", encoding="utf-8")  # pre-existing
        tmp = target.with_suffix(target.suffix + ".tmp")

        with patch("src.utils.atomic_io.os.fsync", side_effect=OSError("disk full")):
            with pytest.raises(OSError, match="disk full"):
                atomic_write_text(target, "new content")

        # Destination must remain untouched
        assert target.read_text(encoding="utf-8") == "original"
        # Tmp must be cleaned up
        assert not tmp.exists()

    def test_replace_failure_cleans_tmp_and_raises(self, tmp_path):
        target = tmp_path / "out.txt"
        target.write_text("original", encoding="utf-8")
        tmp = target.with_suffix(target.suffix + ".tmp")

        with patch(
            "src.utils.atomic_io.os.replace", side_effect=OSError("rename failed")
        ):
            with pytest.raises(OSError, match="rename failed"):
                atomic_write_text(target, "new content")

        assert target.read_text(encoding="utf-8") == "original"
        assert not tmp.exists()

    def test_exception_in_write_phase_cleans_tmp(self, tmp_path):
        """If writing to the tmp file itself raises, the tmp must be removed."""
        target = tmp_path / "out.txt"
        tmp = target.with_suffix(target.suffix + ".tmp")

        # Raise inside the `with open(tmp, "w")` block
        with patch("builtins.open", side_effect=OSError("write blocked")):
            with pytest.raises(OSError, match="write blocked"):
                atomic_write_text(target, "x")

        # No tmp leftover, no destination
        assert not tmp.exists()
        assert not target.exists()

    def test_recovery_from_existing_stale_tmp(self, tmp_path):
        """A stale .tmp from a previous crash must not block a fresh write.
        atomic_write opens 'w' (truncates) on the tmp path, so a stale
        sibling is harmless — the test pins that contract."""
        target = tmp_path / "out.txt"
        stale_tmp = target.with_suffix(target.suffix + ".tmp")
        stale_tmp.write_text("leftover from crash", encoding="utf-8")

        atomic_write_text(target, "fresh")

        assert target.read_text(encoding="utf-8") == "fresh"
        assert not stale_tmp.exists()  # replaced away


# ── Tmp filename collisions ──────────────────────────────────────────


class TestTmpFilename:
    def test_tmp_uses_suffix_dot_tmp(self, tmp_path):
        target = tmp_path / "data.json"

        # Patch os.replace to capture the tmp path being renamed
        captured = {}

        real_replace = os.replace

        def spy_replace(src, dst):
            captured["src"] = str(src)
            captured["dst"] = str(dst)
            return real_replace(src, dst)

        with patch("src.utils.atomic_io.os.replace", side_effect=spy_replace):
            atomic_write_text(target, "x")

        assert captured["src"].endswith(".json.tmp")
        assert captured["src"] != captured["dst"]

    def test_concurrent_writes_to_different_targets(self, tmp_path):
        """The realistic concurrency pattern: many threads, many distinct
        destinations. (Same-destination concurrent writes are not in the
        contract — each (date, segment_type, story_index) is unique to a
        single worker.) All targets should land with their intended content."""
        from concurrent.futures import ThreadPoolExecutor

        n = 20
        targets = [tmp_path / f"file_{i:02d}.txt" for i in range(n)]

        with ThreadPoolExecutor(max_workers=8) as ex:
            futures = [
                ex.submit(atomic_write_text, t, f"content-{i:02d}")
                for i, t in enumerate(targets)
            ]
            for f in futures:
                f.result()

        for i, t in enumerate(targets):
            assert t.read_text(encoding="utf-8") == f"content-{i:02d}"
            assert not (t.with_suffix(t.suffix + ".tmp")).exists()


# ── atomic_write_json delegation ────────────────────────────────────


class TestAtomicJson:
    def test_non_serializable_raises(self, tmp_path):
        target = tmp_path / "data.json"
        with pytest.raises(TypeError):
            atomic_write_json(target, {"k": object()})  # not JSON-serializable

        # On failure, no destination or tmp leftover
        assert not target.exists()
        assert not (target.with_suffix(target.suffix + ".tmp")).exists()

    def test_writes_via_text_helper(self, tmp_path):
        """The json variant must reuse atomic_write_text's crash safety."""
        target = tmp_path / "data.json"

        with patch("src.utils.atomic_io.os.fsync", side_effect=OSError("nope")):
            with pytest.raises(OSError):
                atomic_write_json(target, {"a": 1})

        assert not target.exists()
        assert not (target.with_suffix(target.suffix + ".tmp")).exists()

    def test_unicode_round_trip(self, tmp_path):
        target = tmp_path / "data.json"
        payload = {"title": "每日观察", "items": ["苹果 🍎", "香蕉"]}
        atomic_write_json(target, payload)

        loaded = json.loads(target.read_text(encoding="utf-8"))
        assert loaded == payload
