from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.providers.tts.mimo_tts import MimoTTSProvider


def _make_config(**overrides):
    cfg = {
        "logging": {"level": "WARNING"},
        "tts": {
            "voice": "Chloe",
            "model": "mimo-v2.5-tts",
            "temperature": 0.2,
            "api_key": "test-key",
        },
    }
    cfg["tts"].update(overrides)
    return cfg


class TestInit:
    def test_reads_config(self):
        with patch("src.providers.tts.mimo_tts.setup_logger"):
            with patch("src.providers.tts.mimo_tts.OpenAI"):
                provider = MimoTTSProvider(_make_config())
        assert provider.voice == "Chloe"
        assert provider.model == "mimo-v2.5-tts"
        assert provider.temperature == 0.2

    def test_requires_api_key(self):
        with patch("src.providers.tts.mimo_tts.setup_logger"):
            with patch.dict("os.environ", {}, clear=False):
                # Remove relevant env vars
                import os

                env = {
                    k: v
                    for k, v in os.environ.items()
                    if k not in ("MIMO_API_KEY", "OPENAI_API_KEY")
                }
                with patch.dict("os.environ", env, clear=True):
                    with pytest.raises(ValueError, match="MIMO_API_KEY"):
                        MimoTTSProvider({"logging": {"level": "WARNING"}, "tts": {}})

    def test_uses_env_api_key(self):
        with patch("src.providers.tts.mimo_tts.setup_logger"):
            with patch("src.providers.tts.mimo_tts.OpenAI") as mock_openai:
                with patch.dict("os.environ", {"MIMO_API_KEY": "env-key"}, clear=False):
                    MimoTTSProvider({"logging": {"level": "WARNING"}, "tts": {}})
        mock_openai.assert_called_once()
        call_kwargs = mock_openai.call_args
        assert call_kwargs[1]["api_key"] == "env-key"


class TestSynthesize:
    def test_builds_emotion_hint(self):
        with patch("src.providers.tts.mimo_tts.setup_logger"):
            with patch("src.providers.tts.mimo_tts.OpenAI"):
                MimoTTSProvider(_make_config())

        # Verify emotion map keys
        from src.providers.tts.mimo_tts import _EMOTION_MAP

        assert "warm" in _EMOTION_MAP
        assert "upbeat" in _EMOTION_MAP
        assert "neutral" in _EMOTION_MAP

    def test_synthesize_appends_emotion_to_tone(self, tmp_path):
        with patch("src.providers.tts.mimo_tts.setup_logger"):
            with patch("src.providers.tts.mimo_tts.OpenAI"):
                provider = MimoTTSProvider(_make_config())

        # Mock the client call chain with proper audio chunk
        import base64

        audio_data = base64.b64encode(b"\x00\x00" * 100).decode()

        mock_delta = MagicMock()
        mock_delta.audio = {"data": audio_data}

        mock_choice = MagicMock()
        mock_choice.delta = mock_delta

        mock_chunk = MagicMock()
        mock_chunk.choices = [mock_choice]

        provider.client = MagicMock()
        provider.client.chat.completions.create.return_value = [mock_chunk]

        output_path = str(tmp_path / "out.mp3")

        # Patch wave.open to write a dummy WAV, subprocess.run to produce the mp3,
        # and Path.unlink to avoid FileNotFoundError on the non-existent wav
        mock_wav = MagicMock()
        with patch("src.providers.tts.mimo_tts.get_audio_duration", return_value=2.0):
            with patch("src.providers.tts.mimo_tts.subprocess") as mock_subprocess:
                mock_subprocess.run = MagicMock()
                with patch("src.providers.tts.mimo_tts.wave") as mock_wave:
                    mock_wave.open.return_value.__enter__ = MagicMock(
                        return_value=mock_wav
                    )
                    mock_wave.open.return_value.__exit__ = MagicMock(return_value=False)
                    with patch("src.providers.tts.mimo_tts.np") as mock_np:
                        mock_np.frombuffer.return_value = MagicMock()
                        mock_np.frombuffer.return_value.tobytes.return_value = (
                            b"\x00" * 200
                        )
                        with patch.object(Path, "unlink"):
                            provider.synthesize(
                                "test text", output_path, emotion="upbeat"
                            )

        # Verify the messages include emotion hint
        call_kwargs = provider.client.chat.completions.create.call_args[1]
        messages = call_kwargs["messages"]
        assert "情绪要求" in messages[0]["content"]
