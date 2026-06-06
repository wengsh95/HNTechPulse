import logging
import subprocess

logger = logging.getLogger(__name__)


def get_audio_duration(audio_path: str, fallback: float = 30.0) -> float:
    """Get audio file duration in seconds.

    Tries ffprobe first (works on MP3s with incomplete XING headers, which
    some TTS providers emit), then falls back to mutagen, then to the
    configured fallback. Returns ``fallback`` if all methods fail.
    """
    # 1) ffprobe — most reliable, handles raw / partially-headered MP3s
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                audio_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            value = float(result.stdout.strip())
            if value > 0:
                return value
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError) as e:
        logger.debug(f"ffprobe failed for {audio_path}: {e}")

    # 2) mutagen — works on ID3-tagged MP3s but not raw streams
    try:
        from mutagen.mp3 import MP3

        audio = MP3(audio_path)
        if audio.info is not None and audio.info.length > 0:
            return float(audio.info.length)
    except Exception as e:
        logger.debug(f"mutagen failed for {audio_path}: {e}")

    logger.warning(f"Failed to get audio duration, using estimate {fallback}s: {audio_path}")
    return fallback
