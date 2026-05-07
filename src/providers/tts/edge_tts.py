import asyncio
from pathlib import Path
from typing import Optional, List

from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.interfaces import TTSProvider, TTSResult
from src.core.models import WordTiming
from src.utils.logger import setup_logger
from src.utils.audio import get_audio_duration

_BOUNDARY_TYPES = {"WordBoundary", "SentenceBoundary"}


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

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def synthesize(self, text: str, output_path: str, emotion: Optional[str] = None) -> TTSResult:
        self.logger.info(f"Synthesizing audio to {output_path}")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        import edge_tts

        word_timings: List[WordTiming] = []
        sentence_timings: List[WordTiming] = []

        async def _synthesize():
            nonlocal word_timings, sentence_timings
            communicate = edge_tts.Communicate(
                text=text,
                voice=self.voice,
                rate=self.rate,
                pitch=self.pitch
            )

            with open(output_path, "wb") as f:
                async for chunk in communicate.stream():
                    chunk_type = chunk.get("type", "")
                    if chunk_type == "audio":
                        f.write(chunk["data"])
                    elif chunk_type in _BOUNDARY_TYPES:
                        offset_100ns = chunk.get("offset", 0)
                        duration_100ns = chunk.get("duration", 0)
                        boundary_text = chunk.get("text", "")
                        start_sec = offset_100ns / 10_000_000
                        end_sec = (offset_100ns + duration_100ns) / 10_000_000
                        timing = WordTiming(
                            text=boundary_text,
                            start_time=round(start_sec, 3),
                            end_time=round(end_sec, 3),
                        )
                        if chunk_type == "WordBoundary":
                            word_timings.append(timing)
                        elif chunk_type == "SentenceBoundary":
                            sentence_timings.append(timing)

        asyncio.run(_synthesize())

        duration = get_audio_duration(output_path)

        primary_timings = word_timings if word_timings else sentence_timings
        timing_level = "word" if word_timings else "sentence"
        self.logger.info(
            f"Audio generated, duration: {duration:.2f}s, "
            f"word timings: {len(word_timings)}, "
            f"sentence timings: {len(sentence_timings)}, "
            f"using: {timing_level} boundaries"
        )

        return TTSResult(duration=duration, word_timings=primary_timings, timing_level=timing_level)
