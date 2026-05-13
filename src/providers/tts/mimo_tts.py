import base64
import os
import subprocess
import wave
from pathlib import Path
from typing import Optional

import httpx
import numpy as np
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.interfaces import TTSProvider, TTSResult
from src.utils.audio import get_audio_duration
from src.utils.config import get_env
from src.utils.logger import setup_logger

try:
    from src.providers.renderer.binary_finder import find_ffmpeg as _find_ffmpeg
    _FFMPEG = _find_ffmpeg() or "ffmpeg"
except Exception:
    _FFMPEG = "ffmpeg"

_DEFAULT_TONE = """【角色】
一档名为《HN TechPulse》的中文科技新闻播报节目的主持人。专业、沉稳、有洞察力的科技媒体人，对技术趋势有独到见解。声音清亮、磁性，有说服力和亲和力。

【场景】
在专业录音棚中，面对麦克风向每日关注科技动态的听众播报当日最重要的技术新闻。需要在播报中完成榜单速览、深度故事解读、社区评论引述，节奏张弛有度。

【指导】
- 整体基调：干练、沉稳、富有专业感的播报风格，语速中等偏快但不急促，咬字清晰饱满。
- 节奏控制：榜单部分干脆利落，深度故事部分放慢语速、加强重音突出重点。
- 气息与停顿：段落之间自然换气，关键数据和技术名词前稍作停顿以制造悬念。
- 音色质感：实声为主，共鸣饱满。读到社区评论时略微调整音色以示区分。
- 情绪起伏：大部分内容保持沉稳中性，遇到突破性技术或争议话题时适当提高语调，但不过度夸张。"""

_EMOTION_MAP = {
    "warm": "用温暖亲切的语气，像和老朋友交谈一样自然。声音明亮温和，语速中等。",
    "energetic": "用活力充沛的语调，语速稍快，声音明亮有劲，带有对新一天的期待感。",
    "neutral": "用沉稳中性的播报语调，客观冷静地叙述事实。语速适中，重音落在关键信息上。",
    "upbeat": "用轻快上扬的语调，带着对技术亮点的兴奋感。语速稍快，在讲到突破性成果时自然提高语调。",
    "calm": "用从容平和的语气，语速稍慢，声音温和放松，娓娓道来。",
}

_STYLE_TAG = "(干练 沉稳)"


class MimoTTSProvider(TTSProvider):
    def __init__(self, config: dict, debug: bool = False):
        self.config = config
        self.debug = debug
        log_level = config.get("logging", {}).get("level")
        self.logger = setup_logger(__name__, debug=debug, level=log_level)

        tts_config = config.get("tts", {})
        self.base_url = tts_config.get("base_url", "https://api.xiaomimimo.com/v1")
        self.model = tts_config.get("model", "mimo-v2.5-tts")
        self.voice = tts_config.get("voice", "Chloe")
        self.audio_format = tts_config.get("format", "pcm16")
        self.sample_rate = tts_config.get("sample_rate", 24000)
        self.temperature = float(tts_config.get("temperature", 0.2))
        self.top_p = tts_config.get("top_p")
        if self.top_p is not None:
            self.top_p = float(self.top_p)
        self.seed = tts_config.get("seed")

        api_key = tts_config.get("api_key") or get_env("MIMO_API_KEY") or get_env("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("MIMO TTS requires MIMO_API_KEY or OPENAI_API_KEY in environment or tts.api_key config")
        self.client = OpenAI(
            api_key=api_key,
            base_url=self.base_url,
            timeout=httpx.Timeout(connect=30.0, read=300.0, write=60.0, pool=10.0),
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def synthesize(self, text: str, output_path: str, emotion: Optional[str] = None) -> TTSResult:
        self.logger.info(f"Synthesizing audio to {output_path} (voice={self.voice})")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        emotion_hint = _EMOTION_MAP.get(emotion or "", "")
        if emotion_hint:
            tone = _DEFAULT_TONE + "\n\n本段播报的情绪要求：" + emotion_hint
        elif emotion:
            tone = _DEFAULT_TONE + f"\n\n本段播报的情绪要求：{emotion}"
        else:
            tone = _DEFAULT_TONE

        tagged_text = f"{_STYLE_TAG}{text}"

        messages = [
            {"role": "user", "content": tone},
            {"role": "assistant", "content": tagged_text},
        ]

        kwargs: dict = dict(
            model=self.model,
            messages=messages,
            audio={"format": self.audio_format, "voice": self.voice},
            stream=True,
            temperature=self.temperature,
        )
        if self.top_p is not None:
            kwargs["top_p"] = self.top_p
        if self.seed is not None:
            kwargs["seed"] = self.seed

        collected_chunks: list[bytes] = []
        completion = self.client.chat.completions.create(**kwargs)

        for chunk in completion:
            if not chunk.choices:
                continue
            audio = getattr(chunk.choices[0].delta, "audio", None)
            if audio is not None:
                if not isinstance(audio, dict):
                    raise TypeError(f"Expected audio dict, got {type(audio)}")
                collected_chunks.append(base64.b64decode(audio["data"]))

        if not collected_chunks:
            raise RuntimeError("MIMO TTS returned no audio data")

        all_pcm = b"".join(collected_chunks)
        np_pcm = np.frombuffer(all_pcm, dtype=np.int16)

        # Write WAV via stdlib wave, then convert to MP3 via ffmpeg
        wav_path = str(Path(output_path).with_suffix(".wav"))
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(np_pcm.tobytes())

        subprocess.run(
            [_FFMPEG, "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-qscale:a", "2", output_path],
            capture_output=True,
            check=True,
        )
        Path(wav_path).unlink()

        duration = get_audio_duration(output_path)
        self.logger.info(f"Audio generated, duration: {duration:.2f}s")
        return TTSResult(duration=duration)
