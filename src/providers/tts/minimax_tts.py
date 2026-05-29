import json
import ssl
from pathlib import Path
from typing import Optional

import websockets
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.interfaces import TTSProvider, TTSResult
from src.utils.audio import get_audio_duration
from src.utils.config import get_env
from src.utils.logger import setup_logger
from src.utils.async_helper import run_async


class MinimaxTTSProvider(TTSProvider):
    def __init__(self, config: dict, debug: bool = False):
        self.config = config
        self.debug = debug
        log_level = config.get("logging", {}).get("level")
        self.logger = setup_logger(__name__, debug=debug, level=log_level)

        tts_config = config.get("tts", {})
        self.model = tts_config.get("model", "speech-2.8-hd")
        self.voice_id = tts_config.get("voice_id", "male-qn-qingse")
        self.speed = float(tts_config.get("speed", 1))
        self.vol = float(tts_config.get("vol", 1))
        self.pitch = int(tts_config.get("pitch", 0))
        self.english_normalization = bool(
            tts_config.get("english_normalization", False)
        )
        self.sample_rate = int(tts_config.get("sample_rate", 32000))
        self.bitrate = int(tts_config.get("bitrate", 128000))
        self.audio_format = tts_config.get("format", "mp3")
        self.channel = int(tts_config.get("channel", 1))

        self.api_key = tts_config.get("api_key") or get_env("MINIMAX_API_KEY")
        if not self.api_key:
            raise ValueError(
                "MiniMax TTS requires MINIMAX_API_KEY in environment or tts.api_key config"
            )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def synthesize(
        self, text: str, output_path: str, emotion: Optional[str] = None
    ) -> TTSResult:
        self.logger.info(f"Synthesizing audio to {output_path} (voice={self.voice_id})")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        async def _synthesize():
            ssl_context = ssl.create_default_context()

            headers = {"Authorization": f"Bearer {self.api_key}"}

            ws = await websockets.connect(
                "wss://api.minimaxi.com/ws/v1/t2a_v2",
                additional_headers=headers,
                ssl=ssl_context,
            )
            connected = json.loads(await ws.recv())
            if connected.get("event") != "connected_success":
                raise RuntimeError(f"MiniMax connection failed: {connected}")

            start_msg = {
                "event": "task_start",
                "model": self.model,
                "voice_setting": {
                    "voice_id": self.voice_id,
                    "speed": self.speed,
                    "vol": self.vol,
                    "pitch": self.pitch,
                    "english_normalization": self.english_normalization,
                },
                "audio_setting": {
                    "sample_rate": self.sample_rate,
                    "bitrate": self.bitrate,
                    "format": self.audio_format,
                    "channel": self.channel,
                },
            }
            await ws.send(json.dumps(start_msg))
            response = json.loads(await ws.recv())
            if response.get("event") != "task_started":
                raise RuntimeError(f"MiniMax task start failed: {response}")

            await ws.send(json.dumps({"event": "task_continue", "text": text}))

            audio_data = b""
            while True:
                response = json.loads(await ws.recv())
                if "data" in response and "audio" in response["data"]:
                    audio = response["data"]["audio"]
                    if audio:
                        audio_data += bytes.fromhex(audio)
                if response.get("is_final"):
                    break

            await ws.send(json.dumps({"event": "task_finish"}))
            await ws.close()

            if not audio_data:
                raise RuntimeError("MiniMax TTS returned no audio data")

            with open(output_path, "wb") as f:
                f.write(audio_data)

        run_async(_synthesize())

        duration = get_audio_duration(output_path)
        self.logger.info(f"Audio generated, duration: {duration:.2f}s")
        return TTSResult(duration=duration)
