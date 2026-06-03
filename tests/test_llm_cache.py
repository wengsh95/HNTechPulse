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
