"""Whisper-based forced alignment for TTS batch mode.

Splits a single master TTS audio file into per-segment clips by aligning
known reference texts against Whisper word-level timestamps.
"""

import re
import subprocess
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from src.providers.renderer.binary_finder import find_ffmpeg
from src.utils.logger import setup_logger

_FFMPEG = find_ffmpeg() or "ffmpeg"


@dataclass
class AlignmentSegment:
    text: str
    start_time: float
    end_time: float


def _normalize(text: str) -> str:
    """Remove punctuation and whitespace, keep only content characters."""
    result = re.sub(r"[^一-鿿\w]", "", text)
    return result.lower()


def align_audio(
    audio_path: str,
    reference_texts: list[str],
    model_size: str = "large-v3",
    model_path: str = "",
    language: str = "zh",
    debug: bool = False,
) -> list[AlignmentSegment]:
    """Run Whisper forced alignment to map reference texts to audio timestamps.

    Args:
        audio_path: Path to the master audio file.
        reference_texts: Ordered list of text segments to align.
        model_size: Whisper model size (e.g. "large-v3", "medium", "small").
        model_path: Directory containing .pt model files. If empty, downloads from HuggingFace.
        language: Language code for Whisper.
        debug: Enable debug logging.

    Returns:
        List of AlignmentSegment, one per reference_text, with start/end times.
    """
    import whisper

    logger = setup_logger(__name__, debug=debug)

    if model_path:
        model_file = str(Path(model_path) / f"{model_size}.pt")
        logger.info(f"Loading Whisper model from local path: {model_file}")
        model = whisper.load_model(model_file, device="cpu")  # type: ignore[attr-defined]
    else:
        logger.info(f"Loading Whisper model '{model_size}'")
        model = whisper.load_model(model_size, device="cpu")  # type: ignore[attr-defined]

    logger.info(f"Transcribing {audio_path} with word timestamps...")
    result = model.transcribe(
        audio_path,
        language=language,
        word_timestamps=True,
        verbose=debug,
    )

    raw_segments = result.get("segments", [])
    words: list[dict] = []
    for seg in raw_segments:
        seg_words = seg.get("words") or []
        words.extend(seg_words)

    if not words:
        raise RuntimeError("Whisper produced no word timestamps")

    logger.info(
        f"Whisper returned {len(words)} words, aligning to {len(reference_texts)} reference texts..."
    )

    # Build whisper transcript and per-character word-index lookup.
    whisper_chars: list[str] = []
    char_word_idx: list[int] = []  # raw_char_position → word index in `words`
    norm_to_raw: list[int] = []  # normalized_char_position → raw_char_position
    for wi, word in enumerate(words):
        for ch in word["word"]:
            if _normalize(ch):
                norm_to_raw.append(len(whisper_chars))
            whisper_chars.append(ch)
            char_word_idx.append(wi)

    whisper_text = "".join(whisper_chars)
    norm_whisper = _normalize(whisper_text)

    # Build concatenated reference text with per-text offsets
    ref_texts_norm = [_normalize(t) for t in reference_texts]
    ref_offsets: list[int] = []
    offset = 0
    for nt in ref_texts_norm:
        ref_offsets.append(offset)
        offset += len(nt)
    concatenated_norm = "".join(ref_texts_norm)

    # Align normalized whisper transcript to normalized reference
    matcher = SequenceMatcher(None, norm_whisper, concatenated_norm)
    blocks = matcher.get_matching_blocks()

    # Build whisper_char_pos → ref_char_pos mapping from matching blocks
    whisper_to_ref: dict[int, int] = {}
    for block in blocks:
        if block.size == 0:
            continue
        for k in range(block.size):
            whisper_to_ref[block.a + k] = block.b + k

    # For each reference text, find its time range via matched whisper positions.
    # Use word["start"] / word["end"] for clean boundaries (not interpolated char times).
    total_chars = len(concatenated_norm) or 1
    total_duration = words[-1]["end"] if words else 0.0

    results: list[AlignmentSegment] = []
    for idx, ref_text in enumerate(reference_texts):
        ref_start = ref_offsets[idx]
        ref_end = ref_start + len(ref_texts_norm[idx])

        matched_positions = [
            w_pos
            for w_pos, r_pos in whisper_to_ref.items()
            if ref_start <= r_pos < ref_end
        ]

        if not matched_positions:
            # Fallback: proportional position estimate
            start_time = (ref_start / total_chars) * total_duration
            end_time = (ref_end / total_chars) * total_duration
        else:
            start_char_norm = min(matched_positions)
            end_char_norm = max(matched_positions)
            start_char_raw = norm_to_raw[start_char_norm]
            end_char_raw = norm_to_raw[end_char_norm]
            start_word_idx = char_word_idx[start_char_raw]
            end_word_idx = char_word_idx[end_char_raw]
            start_time = words[start_word_idx]["start"]
            end_time = words[end_word_idx]["end"]
            # For non-last segments, extend end_time slightly to avoid gaps
            if end_word_idx + 1 < len(words):
                end_time = words[end_word_idx + 1]["start"]

        results.append(
            AlignmentSegment(
                text=ref_text,
                start_time=start_time,
                end_time=end_time,
            )
        )

    logger.info(
        f"Alignment complete: {len(results)} segments, "
        f"total duration {results[-1].end_time:.1f}s"
    )
    return results


def split_audio(
    audio_path: str,
    segments: list[AlignmentSegment],
    output_paths: list[str],
) -> None:
    """Split a master audio file into per-segment clips using ffmpeg.

    Re-encodes via libmp3lame for clean cuts at exact timestamps.
    """
    for seg, out_path in zip(segments, output_paths):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            _FFMPEG,
            "-y",
            "-i",
            audio_path,
            "-ss",
            f"{seg.start_time:.3f}",
            "-to",
            f"{seg.end_time:.3f}",
            "-acodec",
            "libmp3lame",
            "-q:a",
            "2",
            out_path,
        ]
        subprocess.run(cmd, capture_output=True, check=True)
