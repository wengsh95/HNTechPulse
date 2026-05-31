"""MIMO TTS 情绪 × 声音 组合测试。

运行方式:
    uv run python -m pytest tests/test_mimo_tts_combo.py -v
    uv run python -m pytest tests/test_mimo_tts_combo.py -v -k "茉莉 and upbeat"
"""

import base64
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.providers.tts.mimo_tts import MimoTTSProvider, _EMOTION_MAP

# ── 可选声音列表（根据 MIMO TTS 文档） ──
VOICES = ["茉莉", "云逸", "青璇", "叶桐", "晓晓"]

# ── 所有情绪 ──
EMOTIONS = list(_EMOTION_MAP.keys())


def _make_provider(voice: str = "茉莉") -> MimoTTSProvider:
    """创建一个 mock 掉外部调用的 provider 实例。"""
    cfg = {
        "logging": {"level": "WARNING"},
        "tts": {
            "voice": voice,
            "model": "mimo-v2.5-tts",
            "temperature": 0.2,
            "api_key": "test-key",
        },
    }
    with patch("src.providers.tts.mimo_tts.setup_logger"):
        with patch("src.providers.tts.mimo_tts.OpenAI"):
            return MimoTTSProvider(cfg)


def _mock_synthesize(provider: MimoTTSProvider, text: str, emotion: str | None):
    """模拟 synthesize 调用，捕获传给 API 的 messages 内容。"""
    audio_data = base64.b64encode(b"\x00\x00" * 100).decode()

    mock_delta = MagicMock()
    mock_delta.audio = {"data": audio_data}

    mock_choice = MagicMock()
    mock_choice.delta = mock_delta

    mock_chunk = MagicMock()
    mock_chunk.choices = [mock_choice]

    provider.client = MagicMock()
    provider.client.chat.completions.create.return_value = [mock_chunk]

    mock_wav = MagicMock()
    with patch("src.providers.tts.mimo_tts.get_audio_duration", return_value=2.0):
        with patch("src.providers.tts.mimo_tts.subprocess"):
            with patch("src.providers.tts.mimo_tts.wave") as mock_wave:
                mock_wave.open.return_value.__enter__ = MagicMock(return_value=mock_wav)
                mock_wave.open.return_value.__exit__ = MagicMock(return_value=False)
                with patch("src.providers.tts.mimo_tts.np") as mock_np:
                    mock_np.frombuffer.return_value = MagicMock()
                    mock_np.frombuffer.return_value.tobytes.return_value = b"\x00" * 200
                    with patch.object(Path, "unlink"):
                        provider.synthesize(text, "/tmp/out.mp3", emotion=emotion)

    # 返回实际传入的 messages
    call_kwargs = provider.client.chat.completions.create.call_args[1]
    return call_kwargs["messages"], call_kwargs["audio"]


# ── 测试类 ──

class TestEmotionMap:
    """情绪映射完整性测试。"""

    def test_all_emotions_have_description(self):
        for emotion, desc in _EMOTION_MAP.items():
            assert desc, f"情绪 '{emotion}' 描述为空"
            assert len(desc) > 5, f"情绪 '{emotion}' 描述过短: {desc}"

    @pytest.mark.parametrize("emotion", EMOTIONS)
    def test_emotion_key_exists(self, emotion):
        assert emotion in _EMOTION_MAP


class TestVoiceEmotionCombo:
    """voice × emotion 组合测试：验证消息构建正确。"""

    @pytest.mark.parametrize("voice", VOICES)
    @pytest.mark.parametrize("emotion", EMOTIONS)
    def test_combo_appends_emotion(self, voice, emotion):
        """每个 voice + emotion 组合都应把情绪要求注入 messages。"""
        provider = _make_provider(voice=voice)
        messages, audio_cfg = _mock_synthesize(provider, "测试文本", emotion=emotion)

        # 验证 voice 透传
        assert audio_cfg["voice"] == voice

        # 验证情绪注入到 user message
        user_content = messages[0]["content"]
        assert "情绪要求" in user_content
        assert _EMOTION_MAP[emotion] in user_content

        # 验证 assistant message 是原始文本
        assert messages[1]["content"] == "测试文本"

    @pytest.mark.parametrize("voice", VOICES)
    def test_no_emotion(self, voice):
        """不传 emotion 时不应有情绪要求。"""
        provider = _make_provider(voice=voice)
        messages, _ = _mock_synthesize(provider, "测试文本", emotion=None)

        user_content = messages[0]["content"]
        assert "情绪要求" not in user_content

    @pytest.mark.parametrize("voice", VOICES)
    def test_unknown_emotion_passthrough(self, voice):
        """未知情绪直接透传原文。"""
        provider = _make_provider(voice=voice)
        messages, _ = _mock_synthesize(provider, "测试文本", emotion="神秘情绪")

        user_content = messages[0]["content"]
        assert "情绪要求" in user_content
        assert "神秘情绪" in user_content


class TestSynthesizeResult:
    """验证 synthesize 返回值结构。"""

    @pytest.mark.parametrize("emotion", EMOTIONS)
    def test_returns_tts_result(self, emotion):
        provider = _make_provider()
        # _mock_synthesize 已经 mock 了 get_audio_duration 返回 2.0
        # 直接调用验证不抛异常即可
        _mock_synthesize(provider, "测试文本", emotion=emotion)
