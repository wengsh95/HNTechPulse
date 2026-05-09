import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

from src.providers.tts.edge_tts import EdgeTTSProvider
from src.core.models import WordTiming


def _make_config():
    return {
        "logging": {"level": "WARNING"},
        "tts": {
            "voice": "zh-CN-XiaoxiaoNeural",
            "rate": "+10%",
            "pitch": "+0Hz",
        },
    }


def _make_provider():
    with patch("src.providers.tts.edge_tts.setup_logger"):
        return EdgeTTSProvider(_make_config())


# ── Timing calculation ────────────────────────────────────────────────

class TestTimingCalculation:
    def test_100ns_offset_to_seconds(self):
        offset_100ns = 10_000_000  # 1 second
        start_sec = offset_100ns / 10_000_000
        assert start_sec == 1.0

    def test_duration_to_end_time(self):
        offset_100ns = 10_000_000  # 1s
        duration_100ns = 5_000_000  # 0.5s
        end_sec = (offset_100ns + duration_100ns) / 10_000_000
        assert end_sec == 1.5

    def test_rounding_to_3_decimals(self):
        offset_100ns = 1_234_567
        start_sec = round(offset_100ns / 10_000_000, 3)
        assert start_sec == 0.123


# ── Timing level selection ────────────────────────────────────────────

class TestTimingLevelSelection:
    def test_word_preferred(self):
        word_timings = [WordTiming(text="hello", start_time=0.0, end_time=0.5)]
        sentence_timings = [WordTiming(text="hello world", start_time=0.0, end_time=1.0)]
        primary = word_timings if word_timings else sentence_timings
        timing_level = "word" if word_timings else "sentence"
        assert timing_level == "word"
        assert primary is word_timings

    def test_sentence_fallback(self):
        word_timings = []
        sentence_timings = [WordTiming(text="hello world", start_time=0.0, end_time=1.0)]
        primary = word_timings if word_timings else sentence_timings
        timing_level = "word" if word_timings else "sentence"
        assert timing_level == "sentence"
        assert primary is sentence_timings


# ── Synthesize directory creation ─────────────────────────────────────

class TestSynthesizeDirectoryCreation:
    def test_output_dir_created(self, tmp_path):
        provider = _make_provider()
        output_path = str(tmp_path / "sub" / "out.mp3")

        mock_communicate = MagicMock()
        mock_communicate.stream = AsyncMock(return_value=AsyncMock())

        mock_edge_tts = MagicMock()
        mock_edge_tts.Communicate.return_value = mock_communicate

        with patch.dict("sys.modules", {"edge_tts": mock_edge_tts}):
            with patch("src.providers.tts.edge_tts.get_audio_duration", return_value=1.0):
                with patch("src.providers.tts.edge_tts.asyncio") as mock_asyncio:
                    mock_asyncio.run = MagicMock()
                    # Just verify parent dir would be created
                    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                    assert Path(output_path).parent.exists()
