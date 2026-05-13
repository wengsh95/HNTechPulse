import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_audio_duration(audio_path: str, fallback: float = 30.0) -> float:
    try:
        from mutagen.mp3 import MP3
        audio = MP3(audio_path)
        return audio.info.length
    except Exception as e:
        logger.warning(f"Failed to get audio duration, using estimate {fallback}s: {e}")
        return fallback
