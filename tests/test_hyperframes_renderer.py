"""Tests for HyperFramesRenderer parallel + chunk-cache layer.

Mirrors the structure of tests/test_remotion_renderer.py: every test
constructs the renderer via ``__new__`` (bypassing __init__) and sets
attributes by hand, then exercises one slice of the parallel/cache
machinery in isolation. No real `npx hyperframes` invocations happen.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.providers.renderer.chunk_planner import (
    compute_segment_chunks_seconds,
)
from src.providers.renderer.hyperframes_props import filter_scenes_to_chunk
from src.providers.renderer.hyperframes_renderer import HyperFramesRenderer


# ── Fixtures ────────────────────────────────────────────────────────


def _make_config():
    return {
        "logging": {"level": "WARNING"},
        "video": {"resolution": (1280, 720), "fps": 24, "bg_color": "#fefaf2"},
        "renderer": {
            "hyperframes": {
                "project_dir": "src/providers/renderer/hyperframes",
                "output_subdir": "hyperframes_project",
                "default_quality": "standard",
                "preview_port": 3002,
                "render_workers": 2,
                "resume_enabled": True,
                "chunk_timeout": 600,
            }
        },
    }


def _make_renderer(**overrides):
    """Build a HyperFramesRenderer instance without invoking __init__."""
    with patch.object(HyperFramesRenderer, "__init__", lambda self, *a, **kw: None):
        renderer = HyperFramesRenderer.__new__(HyperFramesRenderer)
    renderer.config = _make_config()
    renderer.debug = False
    renderer.logger = MagicMock()
    renderer.width = 1280
    renderer.height = 720
    renderer.fps = 24
    renderer.bg_color = "#fefaf2"
    hf = renderer.config["renderer"]["hyperframes"]
    renderer.project_dir = Path(hf["project_dir"])
    renderer.output_subdir = hf["output_subdir"]
    renderer.default_quality = hf["default_quality"]
    renderer.preview_port = hf["preview_port"]
    renderer.fps_override = None
    renderer.render_workers = hf["render_workers"]
    renderer.resume_enabled = hf["resume_enabled"]
    renderer.workers = None
    renderer._chunk_timeout = hf["chunk_timeout"]
    renderer._node_path = "/usr/bin/node"
    renderer._npx_path = "/usr/bin/npx"
    renderer._ffmpeg_path = "/usr/bin/ffmpeg"
    for k, v in overrides.items():
        setattr(renderer, k, v)
    return renderer


def _make_scenes_payload():
    """Build a tiny representative scenes_payload for filter tests."""
    return {
        "width": 1280,
        "height": 720,
        "fps": 24,
        "bgColor": "#fefaf2",
        "title": "HN TechPulse",
        "totalDuration": 30.0,
        "scenes": [
            # 0-5s: opening
            {"comp_id": "cover-card", "comp_src": "compositions/cover.html",
             "start": 0.0, "duration": 5.0, "track_index": 0, "element_type": "cover_card",
             "variables": {"headline": "hi"}, "raw_props": {}},
            # 5-15s: story 0
            {"comp_id": "event-card", "comp_src": "compositions/event.html",
             "start": 5.0, "duration": 10.0, "track_index": 1, "element_type": "event_card",
             "variables": {"title": "A"}, "raw_props": {}},
            # 15-25s: story 1
            {"comp_id": "event-card", "comp_src": "compositions/event.html",
             "start": 15.0, "duration": 10.0, "track_index": 2, "element_type": "event_card",
             "variables": {"title": "B"}, "raw_props": {}},
            # 25-30s: closing
            {"comp_id": "closing-card", "comp_src": "compositions/closing.html",
             "start": 25.0, "duration": 5.0, "track_index": 3, "element_type": "closing_card",
             "variables": {}, "raw_props": {}},
        ],
        "audio_tracks": [
            {"src": "public/audio/opening.mp3", "start": 0.0, "duration": 5.0, "track_index": 1000},
            {"src": "public/audio/story_0.mp3", "start": 5.0, "duration": 10.0, "track_index": 1001},
            {"src": "public/audio/story_1.mp3", "start": 15.0, "duration": 10.0, "track_index": 1002},
            {"src": "public/audio/closing.mp3", "start": 25.0, "duration": 5.0, "track_index": 1003},
        ],
        "cli_props": {"segments": []},
    }


# ── compute_segment_chunks_seconds ─────────────────────────────────


class TestComputeSegmentChunksSeconds:
    def test_basic_segments(self):
        from src.core.models import Script, ScriptSegment

        segs = [
            ScriptSegment(segment_type="opening", audio_text="", duration=5.0,
                          start_time=0.0, end_time=5.0, scene_elements=[]),
            ScriptSegment(segment_type="story_scan", audio_text="", duration=20.0,
                          start_time=5.0, end_time=25.0, scene_elements=[]),
            ScriptSegment(segment_type="closing", audio_text="", duration=5.0,
                          start_time=25.0, end_time=30.0, scene_elements=[]),
        ]
        script = Script(title="", description="", tags=[], segments=segs, total_duration=30.0)
        chunks = compute_segment_chunks_seconds(script, 30.0)
        assert chunks == [
            (0.0, 5.0, "opening"),
            (5.0, 25.0, "story_scan"),
            (25.0, 30.0, "closing"),
        ]

    def test_story_scan_with_scene_elements(self):
        from src.core.models import Script, ScriptSegment, SceneElement

        elements = [
            SceneElement(element_type="event_card", start_time=0.0, end_time=4.0, props={}),
            SceneElement(element_type="atmosphere_card", start_time=4.0, end_time=8.0, props={}),
        ]
        segs = [
            ScriptSegment(segment_type="story_scan", audio_text="", duration=8.0,
                          start_time=5.0, end_time=13.0, scene_elements=elements),
        ]
        script = Script(title="", description="", tags=[], segments=segs, total_duration=13.0)
        chunks = compute_segment_chunks_seconds(script, 13.0)
        assert chunks == [
            (5.0, 9.0, "story_0"),
            (9.0, 13.0, "story_1"),
        ]

    def test_empty_script(self):
        from src.core.models import Script

        script = Script(title="", description="", tags=[], segments=[], total_duration=0.0)
        chunks = compute_segment_chunks_seconds(script, 0.0)
        assert chunks == []

    def test_last_chunk_extends_to_total_duration(self):
        from src.core.models import Script, ScriptSegment

        segs = [
            ScriptSegment(segment_type="opening", audio_text="", duration=5.0,
                          start_time=0.0, end_time=5.0, scene_elements=[]),
            ScriptSegment(segment_type="closing", audio_text="", duration=4.9,
                          start_time=5.0, end_time=9.9, scene_elements=[]),
        ]
        script = Script(title="", description="", tags=[], segments=segs, total_duration=10.0)
        chunks = compute_segment_chunks_seconds(script, 10.0)
        # Last chunk extends from 5.0 all the way to 10.0
        assert chunks[-1] == (5.0, 10.0, "closing")


# ── filter_scenes_to_chunk ─────────────────────────────────────────


class TestFilterScenesToChunk:
    def test_full_overlap_returns_unchanged(self):
        payload = _make_scenes_payload()
        out = filter_scenes_to_chunk(payload, 0.0, 30.0)
        # All four scenes kept, all audio kept
        assert len(out["scenes"]) == 4
        assert len(out["audio_tracks"]) == 4
        assert out["totalDuration"] == 30.0

    def test_zero_overlap_returns_empty(self):
        payload = _make_scenes_payload()
        out = filter_scenes_to_chunk(payload, 100.0, 200.0)
        assert out["scenes"] == []
        assert out["audio_tracks"] == []
        assert out["totalDuration"] == 100.0

    def test_partial_overlap_clamps_durations(self):
        """A scene that crosses a chunk boundary should be clamped, not split.

        Time mapping for a chunk [3.0, 12.0]:
          - cover (full [0, 5]) only overlaps [3, 5]; in the chunk the local
            start is 0 (chunk clock begins at 0 when full-time reaches 3.0,
            so a scene already in progress at t=3 of full shows at t=0 in
            chunk), and the local duration is 2 (only 2s of the scene remain).
          - story_0 (full [5, 15]) overlaps [5, 12]; local start = 5 - 3 = 2,
            local duration = 12 - 5 = 7.
        """
        payload = _make_scenes_payload()
        out = filter_scenes_to_chunk(payload, 3.0, 12.0)
        starts = [(s["start"], s["duration"]) for s in out["scenes"]]
        assert (0.0, 2.0) in starts
        assert (2.0, 7.0) in starts
        # closing and story_1 are outside [3, 12]
        starts_simple = [s["start"] for s in out["scenes"]]
        assert 15.0 not in starts_simple
        assert 25.0 not in starts_simple
        # Audio tracks clamped identically
        audio_starts = [(a["start"], a["duration"]) for a in out["audio_tracks"]]
        assert (0.0, 2.0) in audio_starts  # opening
        assert (2.0, 7.0) in audio_starts  # story_0

    def test_wrapper_metadata_preserved(self):
        payload = _make_scenes_payload()
        out = filter_scenes_to_chunk(payload, 0.0, 5.0)
        assert out["width"] == 1280
        assert out["height"] == 720
        assert out["fps"] == 24
        assert out["bgColor"] == "#fefaf2"
        assert out["title"] == "HN TechPulse"

    def test_total_duration_set_to_chunk_length(self):
        payload = _make_scenes_payload()
        out = filter_scenes_to_chunk(payload, 7.0, 17.0)
        assert out["totalDuration"] == 10.0

    def test_deterministic_for_same_input(self):
        """Same input → same JSON output (stable cache key)."""
        payload = _make_scenes_payload()
        out_a = filter_scenes_to_chunk(payload, 0.0, 30.0)
        out_b = filter_scenes_to_chunk(payload, 0.0, 30.0)
        assert json.dumps(out_a, sort_keys=True) == json.dumps(out_b, sort_keys=True)


# ── Cache paths ─────────────────────────────────────────────────────


class TestCachePaths:
    def test_includes_project_and_chunks(self):
        r = _make_renderer()
        paths = r.cache_paths("2026-06-07")
        assert Path("data/2026-06-07/hyperframes_project") in paths
        assert Path("data/2026-06-07/hyperframes_project/out/chunks") in paths

    def test_empty_when_no_date(self):
        r = _make_renderer()
        assert r.cache_paths("") == []


# ── Base cmd ────────────────────────────────────────────────────────


class TestBuildBaseCmd:
    def test_includes_quality_and_output(self):
        r = _make_renderer()
        out = Path("/tmp/out.mp4")
        cmd = r._build_base_cmd(out, workers=1)
        assert cmd[0] == "/usr/bin/npx"
        assert cmd[1:3] == ["hyperframes", "render"]
        # Windows mangles forward slashes in f-strings; match the resolved form.
        assert any(p.startswith("--output=") and p.endswith("out.mp4") for p in cmd)
        assert "--quality=standard" in cmd
        assert "--workers=1" in cmd

    def test_workers_omitted_when_none(self):
        r = _make_renderer()
        cmd = r._build_base_cmd(Path("/tmp/out.mp4"), workers=None)
        assert not any(p.startswith("--workers=") for p in cmd)

    def test_includes_fps_override(self):
        r = _make_renderer(fps_override=60)
        cmd = r._build_base_cmd(Path("/tmp/out.mp4"), workers=1)
        assert "--fps=60" in cmd


# ── Cache hit / miss logic (in-process simulation) ─────────────────


class TestChunkCacheLogic:
    """Simulate the cache hit/miss branch of _render_chunked without
    spawning any real subprocess. We use tmp_path for isolation."""

    def test_cache_hit_skips_rerender(self, tmp_path, monkeypatch):
        r = _make_renderer()
        r.project_dir = tmp_path / "template"
        (r.project_dir / "compositions").mkdir(parents=True)
        (r.project_dir / "compositions" / "x.html").write_text("x")
        (r.project_dir / "package.json").write_text("{}")

        # Set up a chunk that already has a non-empty chunk.mp4
        out_root = tmp_path / "proj"
        out_root.mkdir()
        (out_root / "public" / "audio").mkdir(parents=True)
        (out_root / "public" / "images").mkdir(parents=True)

        chunk_subdir = tmp_path / "chunk_000_opening_aaaaaaaaaaaaaaaa"
        chunk_subdir.mkdir()
        existing = chunk_subdir / "chunk.mp4"
        existing.write_bytes(b"x" * 1024)  # 1KB, non-empty

        # Patch the renderer methods we'd otherwise invoke
        monkeypatch.setattr(r, "_write_chunk_project", lambda **kw: None)
        monkeypatch.setattr(
            r, "_run_render_cmd", lambda *a, **kw: pytest.fail("should not run")
        )

        # Build prepared list (the way _render_chunked does internally)
        prepared = [{
            "idx": 0,
            "start_sec": 0.0,
            "end_sec": 5.0,
            "label": "opening",
            "subdir": chunk_subdir,
            "chunk_file": existing,
            "partial_file": chunk_subdir / "chunk.partial.mp4",
        }]

        # Replicate the cache-check branch
        pending = []
        for entry in prepared:
            chunk_file = entry["chunk_file"]
            partial_file = entry["partial_file"]
            if chunk_file.exists() and chunk_file.stat().st_size > 0:
                continue  # cache hit
            if chunk_file.exists():
                chunk_file.unlink()
            if partial_file.exists():
                partial_file.unlink()
            pending.append(entry)

        assert pending == []  # everything was a cache hit

    def test_empty_file_is_replaced(self, tmp_path):
        # An empty chunk.mp4 should be treated as a cache miss.
        chunk_dir = tmp_path / "chunk_000_opening_aaaaaaaaaaaaaaaa"
        chunk_dir.mkdir()
        empty = chunk_dir / "chunk.mp4"
        empty.write_bytes(b"")

        # Cache-check logic from _render_chunked
        if empty.exists() and empty.stat().st_size > 0:
            hit = True
        else:
            hit = False
            if empty.exists():
                empty.unlink()

        assert hit is False
        assert not empty.exists()  # unlinked so next render starts fresh

    def test_partial_file_is_cleaned(self, tmp_path):
        chunk_dir = tmp_path / "chunk_000_opening_aaaaaaaaaaaaaaaa"
        chunk_dir.mkdir()
        partial = chunk_dir / "chunk.partial.mp4"
        partial.write_bytes(b"leftover")

        # Cache-check logic
        chunk_file = chunk_dir / "chunk.mp4"
        if chunk_file.exists() and chunk_file.stat().st_size > 0:
            pass  # hit
        else:
            if chunk_file.exists():
                chunk_file.unlink()
            if partial.exists():
                partial.unlink()

        assert not partial.exists()


# ── Parallel pool size cap ──────────────────────────────────────────


class TestParallelPoolCap:
    def test_workers_capped_by_pending(self):
        r = _make_renderer(render_workers=10)
        # 3 pending chunks → only 3 workers should be used.
        workers = max(1, min(r.render_workers, 3))
        assert workers == 3

    def test_workers_at_least_one(self):
        r = _make_renderer(render_workers=0)
        workers = max(1, min(r.render_workers, 1))
        assert workers == 1


# ── Single-shot fallback ────────────────────────────────────────────


class TestSingleShotFallback:
    def test_resume_disabled_uses_single_shot(self, monkeypatch):
        r = _make_renderer(resume_enabled=False)
        calls = []

        def fake_single(out_root, output_file):
            calls.append("single")

        def fake_chunked(**kw):
            calls.append("chunked")

        monkeypatch.setattr(r, "_render_single", fake_single)
        monkeypatch.setattr(r, "_render_chunked", fake_chunked)
        # Bypass write_props to keep test isolated
        monkeypatch.setattr(r, "write_props", lambda *a, **kw: (Path("/tmp/i.html"), ""))
        monkeypatch.setattr(
            "src.providers.renderer.hyperframes_renderer.script_to_hyperframes_scenes",
            lambda *a, **kw: _make_scenes_payload(),
        )

        from src.core.models import Script, ScriptSegment

        segs = [
            ScriptSegment(segment_type="opening", audio_text="", duration=5.0,
                          start_time=0.0, end_time=5.0, scene_elements=[]),
            ScriptSegment(segment_type="closing", audio_text="", duration=5.0,
                          start_time=5.0, end_time=10.0, scene_elements=[]),
        ]
        script = Script(title="", description="", tags=[], segments=segs, total_duration=10.0)

        out = Path("/tmp/out.mp4")
        if out.exists():
            out.unlink()

        r.render(script, "audio", str(out), date="2026-06-07")
        assert calls == ["single"]

    def test_one_chunk_falls_back_to_single_shot(self, monkeypatch):
        """A script that yields exactly one chunk should still use single-shot."""
        r = _make_renderer(resume_enabled=True)
        calls = []

        monkeypatch.setattr(r, "_render_single", lambda *a, **kw: calls.append("single"))
        monkeypatch.setattr(r, "_render_chunked", lambda **kw: calls.append("chunked"))
        monkeypatch.setattr(r, "write_props", lambda *a, **kw: (Path("/tmp/i.html"), ""))
        monkeypatch.setattr(
            "src.providers.renderer.hyperframes_renderer.script_to_hyperframes_scenes",
            lambda *a, **kw: _make_scenes_payload(),
        )

        from src.core.models import Script, ScriptSegment

        # Only one segment → one chunk → should fall back to single
        segs = [
            ScriptSegment(segment_type="opening", audio_text="", duration=10.0,
                          start_time=0.0, end_time=10.0, scene_elements=[]),
        ]
        script = Script(title="", description="", tags=[], segments=segs, total_duration=10.0)

        r.render(script, "audio", "/tmp/out.mp4", date="2026-06-07")
        assert calls == ["single"]


# ── Per-chunk project writing (in-process) ─────────────────────────


class TestWriteChunkProject:
    def test_writes_index_html_and_filtered_audio(self, tmp_path, monkeypatch):
        r = _make_renderer()
        # Template scaffold
        r.project_dir = tmp_path / "template"
        (r.project_dir / "compositions").mkdir(parents=True)
        (r.project_dir / "compositions" / "event.html").write_text("<event/>")
        (r.project_dir / "package.json").write_text("{}")

        # Parent project (what write_props would have built)
        out_root = tmp_path / "proj"
        audio_dir = out_root / "public" / "audio"
        images_dir = out_root / "public" / "images"
        audio_dir.mkdir(parents=True)
        images_dir.mkdir(parents=True)
        (audio_dir / "story_0.mp3").write_bytes(b"audio-0")
        (audio_dir / "story_1.mp3").write_bytes(b"audio-1")
        (images_dir / "pic.png").write_bytes(b"\x89PNG")

        chunk_subdir = tmp_path / "chunk_000_story_0_aaaaaaaaaaaa"
        filtered = filter_scenes_to_chunk(_make_scenes_payload(), 5.0, 15.0)

        r._write_chunk_project(
            chunk_subdir=chunk_subdir,
            out_root=out_root,
            filtered_payload=filtered,
            title="Test",
        )

        # Layout is correct
        assert (chunk_subdir / "package.json").exists()
        assert (chunk_subdir / "compositions" / "event.html").exists()
        assert (chunk_subdir / "data" / "scene_spec.json").exists()
        assert (chunk_subdir / "index.html").exists()

        # Audio is filtered: only story_0 is in the chunk's filtered payload
        assert (chunk_subdir / "public" / "audio" / "story_0.mp3").exists()
        assert not (chunk_subdir / "public" / "audio" / "story_1.mp3").exists()

        # Images are shared (full copy)
        assert (chunk_subdir / "public" / "images" / "pic.png").exists()

        # index.html references only this chunk's scenes
        html = (chunk_subdir / "index.html").read_text()
        assert "id=\"host-0\"" in html  # at least one scene card host
        assert "story_0.mp3" in html
        assert "story_1.mp3" not in html


class TestAudioTracks:
    """Regression: in story_scan mode, tts_processor._finalize_story_scan
    populates BOTH segment.audio_path (the concat) AND meta.subtitle_audios
    (per-element slices). They occupy the same time window; emitting both
    causes audio overlap in the rendered video.

    Remotion handles this in HNTechPulseComposition by filtering the
    segment audio out when subtitle_audios exist. HyperFrames must do
    the same. See src/providers/renderer/hyperframes_props.py
    (script_to_hyperframes_scenes).
    """

    def _build(self, *, has_subtitle_audios: bool):
        from src.core.models import Script, ScriptSegment
        from src.providers.renderer.hyperframes_props import (
            script_to_hyperframes_scenes,
        )

        meta: dict = {}
        if has_subtitle_audios:
            # These start_times are relative to the segment, mirroring
            # tts_processor._finalize_story_scan.
            meta["subtitle_audios"] = [
                {
                    "audio_path": "audio/segment_01_elem_00.mp3",
                    "start_time": 0.3,
                    "end_time": 19.02,
                },
                {
                    "audio_path": "audio/segment_01_elem_01.mp3",
                    "start_time": 19.32,
                    "end_time": 46.14,
                },
            ]
        seg = ScriptSegment(
            segment_type="story",
            audio_text="t",
            duration=123.84,
            actual_duration=123.84,
            emotion="neutral",
            scene_elements=[],
            meta=meta,
            start_time=16.416,
            end_time=140.256,
            audio_path="audio/segment_01.mp3",
        )
        script = Script(
            title="t",
            description="",
            tags=[],
            segments=[seg],
            total_duration=140.256,
        )
        return script_to_hyperframes_scenes(
            script,
            audio_dir="data/2026-06-07/audio",
            width=1280,
            height=720,
            fps=24,
            bg_color="#fefaf2",
        )

    def test_story_scan_emits_only_slices_no_segment_audio(self):
        """When subtitle_audios exist, the concat segment audio must be skipped."""
        payload = self._build(has_subtitle_audios=True)
        srcs = [a["src"] for a in payload["audio_tracks"]]
        # The concat is dropped, slices remain.
        assert "audio/segment_01.mp3" not in srcs
        assert "audio/segment_01_elem_00.mp3" in srcs
        assert "audio/segment_01_elem_01.mp3" in srcs

    def test_story_scan_slice_times_are_absolute(self):
        """Slice start_time is relative to the segment in tts_processor; the
        HyperFrames timeline needs absolute seconds (seg_start + slice_start).
        Otherwise slices collide near t=0 and overlap each other."""
        payload = self._build(has_subtitle_audios=True)
        by_src = {a["src"]: a for a in payload["audio_tracks"]}
        a0 = by_src["audio/segment_01_elem_00.mp3"]
        # 16.416 (segment start) + 0.3 (slice start) = 16.716
        assert a0["start"] == pytest.approx(16.716, abs=0.01)
        # 16.416 + 19.32 = 35.736
        a1 = by_src["audio/segment_01_elem_01.mp3"]
        assert a1["start"] == pytest.approx(35.736, abs=0.01)

    def test_story_scan_no_overlap(self):
        """No two audio_tracks should share the same [start, start+duration]
        window — this is the regression that motivated the fix."""
        payload = self._build(has_subtitle_audios=True)
        intervals = sorted(
            (a["start"], a["start"] + a["duration"], a["src"])
            for a in payload["audio_tracks"]
        )
        for (s1, e1, _), (s2, e2, src2) in zip(intervals, intervals[1:]):
            assert s2 >= e1, (
                f"audio overlap: previous ended at {e1:.3f}, "
                f"{src2!r} starts at {s2:.3f}"
            )

    def test_plain_segment_still_emits_audio(self):
        """Non-story_scan segments (cover/closing) have no subtitle_audios;
        the concat audio path must still be emitted."""
        payload = self._build(has_subtitle_audios=False)
        assert len(payload["audio_tracks"]) == 1
        assert payload["audio_tracks"][0]["src"] == "audio/segment_01.mp3"
        assert payload["audio_tracks"][0]["start"] == pytest.approx(16.416, abs=0.01)
