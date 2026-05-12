import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

from src.providers.tts.edge_tts import EdgeTTSProvider


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
                    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                    assert Path(output_path).parent.exists()
