from pathlib import Path
from typing import Optional

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.interfaces import TTSProvider, TTSResult
from src.utils.logger import setup_logger
from src.utils.config import get_env
from src.utils.audio import get_audio_duration


class OpenAITTSProvider(TTSProvider):
    def __init__(self, config: dict, debug: bool = False):
        self.config = config
        self.debug = debug
        log_level = config.get("logging", {}).get("level")
        self.logger = setup_logger(__name__, debug=debug, level=log_level)

        api_key = get_env("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set in environment")

        base_url = config.get("tts", {}).get("base_url") or get_env("OPENAI_BASE_URL")
        if base_url:
            self.client = OpenAI(api_key=api_key, base_url=base_url)
            self.logger.info(f"Using OpenAI-compatible TTS API at: {base_url}")
        else:
            self.client = OpenAI(api_key=api_key)
        tts_config = config.get("tts", {})
        self.voice = tts_config.get("voice", "alloy")
        self.model = tts_config.get("model", "tts-1")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def synthesize(self, text: str, output_path: str, emotion: Optional[str] = None) -> TTSResult:
        self.logger.info(f"Synthesizing audio to {output_path}")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        voice = self.voice
        if emotion == "energetic":
            voice = "alloy"
        elif emotion == "analytical":
            voice = "onyx"
        elif emotion == "fast_paced":
            voice = "shimmer"

        response = self.client.audio.speech.create(
            model=self.model,
            voice=voice,
            input=text
        )

        response.stream_to_file(output_path)

        duration = get_audio_duration(output_path)
        self.logger.info(f"Audio generated, duration: {duration:.2f}s")

        return TTSResult(duration=duration)
