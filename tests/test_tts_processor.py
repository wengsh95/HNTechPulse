from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.interfaces import TTSProvider, TTSResult
from src.core.models import Script, ScriptSegment
from src.pipeline.tts_processor import TTSProcessor


def _make_config(**overrides):
    cfg = {
        "logging": {"level": "WARNING"},
        "timing": {"segment_gap": 0.0, "story_gap": 0.0, "subtitle_gap": 0.0},
        "tts": {"max_workers": 3},
    }
    cfg.update(overrides)
    return cfg


def _make_provider():
    mock = MagicMock(spec=TTSProvider)
    mock.synthesize.return_value = TTSResult(duration=5.0)
    return mock


def _make_script(segments=None):
    if segments is None:
        segments = [
            ScriptSegment(segment_type="opening", audio_text="Hello", estimated_duration=5.0),
            ScriptSegment(segment_type="closing", audio_text="Goodbye", estimated_duration=5.0),
        ]
    return Script(title="Test", description="", tags=[], segments=segments)


class TestInit:
    def test_max_workers_clamped_low(self):
        with patch("src.pipeline.tts_processor.setup_logger"):
            processor = TTSProcessor(_make_provider(), _make_config(tts={"max_workers": 0}))
        assert processor.max_workers == 1

    def test_max_workers_clamped_high(self):
        with patch("src.pipeline.tts_processor.setup_logger"):
            processor = TTSProcessor(_make_provider(), _make_config(tts={"max_workers": 20}))
        assert processor.max_workers == 8


class TestProcessAudio:
    def test_creates_audio_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        mock_provider = _make_provider()
        with patch("src.pipeline.tts_processor.setup_logger"):
            processor = TTSProcessor(mock_provider, _make_config())
        script = _make_script()

        with patch("src.pipeline.tts_processor.get_audio_duration", return_value=5.0):
            processor.process_audio(script, "2026-04-26")

        assert Path("data/2026-04-26/audio").exists()

    def test_skips_cached_segments(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        mock_provider = _make_provider()
        with patch("src.pipeline.tts_processor.setup_logger"):
            processor = TTSProcessor(mock_provider, _make_config())

        # Pre-create audio file so it's cached
        audio_dir = Path("data/2026-04-26/audio")
        audio_dir.mkdir(parents=True, exist_ok=True)
        (audio_dir / "segment_00.mp3").write_bytes(b"\x00" * 100)
        (audio_dir / "segment_01.mp3").write_bytes(b"\x00" * 100)

        script = _make_script()
        with patch("src.pipeline.tts_processor.get_audio_duration", return_value=5.0):
            processor.process_audio(script, "2026-04-26")

        mock_provider.synthesize.assert_not_called()

    def test_calls_synthesize_for_pending(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        mock_provider = _make_provider()
        with patch("src.pipeline.tts_processor.setup_logger"):
            processor = TTSProcessor(mock_provider, _make_config())
        script = _make_script()

        with patch("src.pipeline.tts_processor.get_audio_duration", return_value=5.0):
            processor.process_audio(script, "2026-04-26")

        assert mock_provider.synthesize.call_count == 2

    def test_sets_actual_duration(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        mock_provider = _make_provider()
        mock_provider.synthesize.return_value = TTSResult(duration=7.5)
        with patch("src.pipeline.tts_processor.setup_logger"):
            processor = TTSProcessor(mock_provider, _make_config())
        script = _make_script()

        with patch("src.pipeline.tts_processor.get_audio_duration", return_value=7.5):
            processor.process_audio(script, "2026-04-26")

        for seg in script.segments:
            assert seg.actual_duration == 7.5
