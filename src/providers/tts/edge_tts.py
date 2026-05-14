import asyncio
from pathlib import Path
from typing import Optional

from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.interfaces import TTSProvider, TTSResult
from src.utils.audio import get_audio_duration
from src.utils.logger import setup_logger


class EdgeTTSProvider(TTSProvider):
    def __init__(self, config: dict, debug: bool = False):
        self.config = config
        self.debug = debug
        log_level = config.get("logging", {}).get("level")
        self.logger = setup_logger(__name__, debug=debug, level=log_level)

        tts_config = config.get("tts", {})
        self.voice = tts_config.get("voice", "zh-CN-XiaoxiaoNeural")
        self.rate = tts_config.get("rate", "+10%")
        self.pitch = tts_config.get("pitch", "+0Hz")

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def synthesize(
        self, text: str, output_path: str, emotion: Optional[str] = None
    ) -> TTSResult:
        self.logger.info(f"Synthesizing audio to {output_path}")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        import edge_tts

        async def _synthesize():
            communicate = edge_tts.Communicate(
                text=text, voice=self.voice, rate=self.rate, pitch=self.pitch
            )
            with open(output_path, "wb") as f:
                async for chunk in communicate.stream():
                    if chunk.get("type", "") == "audio":
                        f.write(chunk["data"])

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(_synthesize())
        else:
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(asyncio.run, _synthesize()).result()

        duration = get_audio_duration(output_path)
        self.logger.info(f"Audio generated, duration: {duration:.2f}s")
        return TTSResult(duration=duration)
