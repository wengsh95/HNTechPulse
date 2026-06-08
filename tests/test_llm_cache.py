"""Tests for src/providers/llm/llm_cache.py

The LLM segment cache is the load-bearing layer for resumable script
generation. A corrupted cache silently bypasses LLM calls and produces
wrong content with no error — these tests pin down the contract.
"""

import json
from unittest.mock import MagicMock

import pytest

from src.core.models import ScriptSegment, SceneElement
from src.providers.llm.llm_cache import LLMCache


@pytest.fixture
def cache(tmp_path, monkeypatch):
    """LLMCache writing into tmp_path instead of ./data/{date}/."""
    cache = LLMCache(logger=MagicMock(), cache_schema_version=4)

    def _path(date, segment_type, story_index):
        d = tmp_path / date / "segments"
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{segment_type}_{story_index}.json"

    monkeypatch.setattr(cache, "get_segment_cache_path", _path)
    return cache


def _make_segment(
    audio_text="hello world", duration=12.5, segment_type="story_scan_item"
):
    return ScriptSegment(
        segment_type=segment_type,
        audio_text=audio_text,
        duration=duration,
        scene_elements=[
            SceneElement(
                element_type="event_card",
                start_time=0.0,
                end_time=5.0,
                props={"story_index": 0, "title": "foo"},
            )
        ],
        meta={"card_narrations": []},
    )


class TestRoundTrip:
    def test_save_then_load_returns_equivalent_segment(self, cache, tmp_path):
        seg = _make_segment(audio_text="some narration", duration=18.0)
        meta = {"schema_version": 4, "model": "test-model", "temperature": 0.2}

        cache.save_segment_cache(
            "2026-06-03", "story_scan_item", 0, seg, cache_meta=meta
        )
        loaded = cache.load_cached_segment(
            "2026-06-03", "story_scan_item", 0, expected_cache_meta=meta
        )

        assert loaded is not None
        assert loaded.segment_type == seg.segment_type
        assert loaded.audio_text == seg.audio_text
        assert loaded.duration == seg.duration
        assert len(loaded.scene_elements) == 1
        assert loaded.scene_elements[0].element_type == "event_card"
        assert loaded.scene_elements[0].props["story_index"] == 0

    def test_load_missing_file_returns_none(self, cache):
        assert cache.load_cached_segment("2026-06-03", "story_scan_item", 99) is None


class TestCacheMetaInvalidation:
    def test_meta_mismatch_returns_none(self, cache, tmp_path):
        seg = _make_segment()
        save_meta = {"schema_version": 4, "model": "m1", "temperature": 0.2}
        different_meta = {"schema_version": 4, "model": "m2", "temperature": 0.2}

        cache.save_segment_cache(
            "2026-06-03", "story_scan_item", 0, seg, cache_meta=save_meta
        )
        loaded = cache.load_cached_segment(
            "2026-06-03", "story_scan_item", 0, expected_cache_meta=different_meta
        )

        assert loaded is None  # signals "regenerate"

    def test_no_expected_meta_means_accept_anything(self, cache, tmp_path):
        """Backward-compat: callers without cache_meta still get cached results."""
        seg = _make_segment()
        cache.save_segment_cache(
            "2026-06-03", "story_scan_item", 0, seg, cache_meta={"v": 1}
        )

        loaded = cache.load_cached_segment("2026-06-03", "story_scan_item", 0)
        assert loaded is not None

    def test_schema_version_bump_invalidates_old_cache(self, cache, tmp_path):
        """Bumping cache_schema_version forces regeneration (regression for #5)."""
        seg = _make_segment()
        old_meta = {"schema_version": 3, "model": "m", "temperature": 0.0}
        new_meta = {"schema_version": 4, "model": "m", "temperature": 0.0}

        cache.save_segment_cache(
            "2026-06-03", "story_scan_item", 0, seg, cache_meta=old_meta
        )
        loaded = cache.load_cached_segment(
            "2026-06-03", "story_scan_item", 0, expected_cache_meta=new_meta
        )

        assert loaded is None


class TestCorruptionRobustness:
    def test_corrupt_json_returns_none(self, cache, tmp_path):
        path = cache.get_segment_cache_path("2026-06-03", "story_scan_item", 0)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not valid json", encoding="utf-8")

        assert cache.load_cached_segment("2026-06-03", "story_scan_item", 0) is None

    def test_missing_required_fields_returns_none(self, cache, tmp_path):
        """A cache file without segment_type / audio_text must not crash the loader."""
        path = cache.get_segment_cache_path("2026-06-03", "story_scan_item", 0)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"_cache": {}, "duration": 5.0}), encoding="utf-8")

        # Should not raise; returns None so the caller regenerates.
        assert cache.load_cached_segment("2026-06-03", "story_scan_item", 0) is None

    def test_wrong_text_hash_returns_none(self, cache, tmp_path):
        """If the segment's underlying prompt changes, text hash differs and we
        regenerate. This is how LLM-cache invalidation works in practice."""
        seg = _make_segment()
        # Cache was saved with one prompt hash; loading with a different one → None.
        cache.save_segment_cache(
            "2026-06-03",
            "story_scan_item",
            0,
            seg,
            cache_meta={"prompt_hash": "hash-A", "model": "m", "temperature": 0.0},
        )

        loaded = cache.load_cached_segment(
            "2026-06-03",
            "story_scan_item",
            0,
            expected_cache_meta={
                "prompt_hash": "hash-B",
                "model": "m",
                "temperature": 0.0,
            },
        )

        assert loaded is None


class TestIsolation:
    def test_different_story_indices_use_different_files(self, cache, tmp_path):
        seg0 = _make_segment(audio_text="story 0")
        seg1 = _make_segment(audio_text="story 1")
        meta = {"v": 1}

        cache.save_segment_cache(
            "2026-06-03", "story_scan_item", 0, seg0, cache_meta=meta
        )
        cache.save_segment_cache(
            "2026-06-03", "story_scan_item", 1, seg1, cache_meta=meta
        )

        loaded0 = cache.load_cached_segment(
            "2026-06-03", "story_scan_item", 0, expected_cache_meta=meta
        )
        loaded1 = cache.load_cached_segment(
            "2026-06-03", "story_scan_item", 1, expected_cache_meta=meta
        )

        assert loaded0.audio_text == "story 0"
        assert loaded1.audio_text == "story 1"

    def test_second_save_overwrites_first(self, cache, tmp_path):
        """Re-running a step with the same meta should overwrite, not append."""
        meta = {"v": 1}
        seg_v1 = _make_segment(audio_text="version 1")
        seg_v2 = _make_segment(audio_text="version 2")

        cache.save_segment_cache(
            "2026-06-03", "story_scan_item", 0, seg_v1, cache_meta=meta
        )
        cache.save_segment_cache(
            "2026-06-03", "story_scan_item", 0, seg_v2, cache_meta=meta
        )
        loaded = cache.load_cached_segment(
            "2026-06-03", "story_scan_item", 0, expected_cache_meta=meta
        )

        assert loaded.audio_text == "version 2"

    def test_different_dates_are_isolated(self, cache, tmp_path):
        seg = _make_segment()
        meta = {"v": 1}

        cache.save_segment_cache(
            "2026-06-03", "story_scan_item", 0, seg, cache_meta=meta
        )
        # Different date — should not find anything.
        assert (
            cache.load_cached_segment(
                "2026-06-04", "story_scan_item", 0, expected_cache_meta=meta
            )
            is None
        )


class TestBuildCacheMeta:
    def test_meta_includes_all_required_fields(self):
        cache = LLMCache(logger=MagicMock(), cache_schema_version=5)
        meta = cache.build_segment_cache_meta(
            prompt="translate this story",
            story_id="12345",
            model="test-model",
            temperature=0.3,
        )
        assert meta["schema_version"] == 5
        assert meta["model"] == "test-model"
        assert meta["temperature"] == 0.3
        assert meta["story_id"] == "12345"
        assert "prompt_hash" in meta
        assert len(meta["prompt_hash"]) == 64  # sha256 hex

    def test_different_prompts_produce_different_hashes(self):
        cache = LLMCache(logger=MagicMock())
        m1 = cache.build_segment_cache_meta(
            prompt="A", story_id="1", model="m", temperature=0.0
        )
        m2 = cache.build_segment_cache_meta(
            prompt="B", story_id="1", model="m", temperature=0.0
        )
        assert m1["prompt_hash"] != m2["prompt_hash"]


# ── Dict cache (translation step) ───────────────────────────────────
#
# load_dict_cache / save_dict_cache serve the translation pipeline.
# They share the segments/ directory with the segment cache but use
# ``translation_{kind}.json`` filenames. Schema and invalidation match
# the segment cache but the payload is an arbitrary dict (not a
# ScriptSegment), so the contract is slightly different.


@pytest.fixture
def dict_cache(tmp_path, monkeypatch):
    """LLMCache with both cache path helpers redirected to tmp_path."""
    cache = LLMCache(logger=MagicMock(), cache_schema_version=4)

    def _segment_path(date, segment_type, story_index):
        d = tmp_path / date / "segments"
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{segment_type}_{story_index}.json"

    def _dict_path(date, kind):
        d = tmp_path / date / "segments"
        d.mkdir(parents=True, exist_ok=True)
        return d / f"translation_{kind}.json"

    monkeypatch.setattr(cache, "get_segment_cache_path", _segment_path)
    monkeypatch.setattr(cache, "_dict_cache_path", _dict_path)
    return cache


class TestDictCacheRoundTrip:
    def test_save_then_load_returns_equivalent_data(self, dict_cache):
        payload = {"title_1": "标题1", "title_2": "标题2", "title_3": "标题3"}
        meta = {"schema_version": 4, "model": "fast", "temperature": 0.1}

        dict_cache.save_dict_cache("2026-06-08", "titles", payload, cache_meta=meta)
        loaded = dict_cache.load_dict_cache(
            "2026-06-08", "titles", expected_cache_meta=meta
        )

        assert loaded == payload

    def test_preserves_unicode_keys_and_values(self, dict_cache):
        payload = {"comment_0_3": "这是一条评论，保留换行\n和emoji 🚀"}
        meta = {"v": 1}

        dict_cache.save_dict_cache("2026-06-08", "comments", payload, cache_meta=meta)
        loaded = dict_cache.load_dict_cache(
            "2026-06-08", "comments", expected_cache_meta=meta
        )

        assert loaded == payload

    def test_load_missing_returns_none(self, dict_cache):
        assert dict_cache.load_dict_cache("2026-06-08", "titles") is None

    def test_save_creates_parent_directory(self, dict_cache, tmp_path):
        """save_dict_cache must mkdir segments/ if absent (atomic_write_text
        creates parents via .parent.mkdir)."""
        assert not (tmp_path / "2026-06-08" / "segments").exists()
        dict_cache.save_dict_cache(
            "2026-06-08", "titles", {"k": "v"}, cache_meta={"v": 1}
        )
        assert (
            tmp_path / "2026-06-08" / "segments" / "translation_titles.json"
        ).exists()


class TestDictCacheInvalidation:
    def test_meta_mismatch_returns_none(self, dict_cache):
        save_meta = {"schema_version": 4, "model": "m1"}
        different_meta = {"schema_version": 4, "model": "m2"}

        dict_cache.save_dict_cache(
            "2026-06-08", "titles", {"k": "v"}, cache_meta=save_meta
        )
        loaded = dict_cache.load_dict_cache(
            "2026-06-08", "titles", expected_cache_meta=different_meta
        )

        assert loaded is None

    def test_no_expected_meta_means_accept_anything(self, dict_cache):
        """Backward-compat: callers without cache_meta get the cached result."""
        dict_cache.save_dict_cache(
            "2026-06-08", "titles", {"k": "v"}, cache_meta={"v": 1}
        )
        loaded = dict_cache.load_dict_cache("2026-06-08", "titles")
        assert loaded == {"k": "v"}

    def test_schema_version_bump_invalidates(self, dict_cache):
        old_meta = {"schema_version": 3, "model": "m"}
        new_meta = {"schema_version": 4, "model": "m"}

        dict_cache.save_dict_cache(
            "2026-06-08", "titles", {"k": "v"}, cache_meta=old_meta
        )
        loaded = dict_cache.load_dict_cache(
            "2026-06-08", "titles", expected_cache_meta=new_meta
        )

        assert loaded is None

    def test_different_kinds_are_isolated(self, dict_cache):
        meta = {"v": 1}
        dict_cache.save_dict_cache(
            "2026-06-08", "titles", {"k": "titles"}, cache_meta=meta
        )
        dict_cache.save_dict_cache(
            "2026-06-08", "comments", {"k": "comments"}, cache_meta=meta
        )

        assert dict_cache.load_dict_cache(
            "2026-06-08", "titles", expected_cache_meta=meta
        ) == {"k": "titles"}
        assert dict_cache.load_dict_cache(
            "2026-06-08", "comments", expected_cache_meta=meta
        ) == {"k": "comments"}


class TestDictCacheCorruption:
    def test_corrupt_json_returns_none(self, dict_cache, tmp_path):
        # Use the patched _dict_cache_path so we write in tmp_path.
        path = dict_cache._dict_cache_path("2026-06-08", "titles")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not valid json", encoding="utf-8")

        assert dict_cache.load_dict_cache("2026-06-08", "titles") is None

    def test_missing_data_field_returns_none(self, dict_cache, tmp_path):
        """A cache file with only _cache and no data field should not crash."""
        path = dict_cache._dict_cache_path("2026-06-08", "titles")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"_cache": {}}), encoding="utf-8")

        assert dict_cache.load_dict_cache("2026-06-08", "titles") is None

    def test_overwrite_replaces_previous_data(self, dict_cache):
        meta = {"v": 1}
        dict_cache.save_dict_cache("2026-06-08", "titles", {"k": "v1"}, cache_meta=meta)
        dict_cache.save_dict_cache("2026-06-08", "titles", {"k": "v2"}, cache_meta=meta)
        loaded = dict_cache.load_dict_cache(
            "2026-06-08", "titles", expected_cache_meta=meta
        )
        assert loaded == {"k": "v2"}


class TestDictCacheConcurrentWrites:
    def test_two_threads_writing_different_kinds_dont_clobber(self, dict_cache):
        """Different (date, kind) tuples map to different files. Verify two
        threads can write simultaneously without losing data."""
        from concurrent.futures import ThreadPoolExecutor

        def write_titles():
            dict_cache.save_dict_cache(
                "2026-06-08", "titles", {"k": "titles"}, cache_meta={"v": 1}
            )

        def write_comments():
            dict_cache.save_dict_cache(
                "2026-06-08", "comments", {"k": "comments"}, cache_meta={"v": 1}
            )

        with ThreadPoolExecutor(max_workers=2) as ex:
            f1 = ex.submit(write_titles)
            f2 = ex.submit(write_comments)
            f1.result()
            f2.result()

        # Both files must exist with the right contents.
        assert dict_cache.load_dict_cache(
            "2026-06-08", "titles", expected_cache_meta={"v": 1}
        ) == {"k": "titles"}
        assert dict_cache.load_dict_cache(
            "2026-06-08", "comments", expected_cache_meta={"v": 1}
        ) == {"k": "comments"}
