"""Script generation: composition, cards, templates, I/O."""

from src.pipeline.script.io import save_script, load_script
from src.pipeline.script.composer import ScriptWriter, SPEECH_CPS
from src.pipeline.script.cards import (
    normalize_atmosphere_card,
    normalize_story_cards,
    coerce_card_narrations_for_mode,
    split_long_subtitle,
    extract_subtitle_texts,
)
from src.pipeline.script.templates import (
    CHINESE_ORDINALS,
    story_angle_from_segment,
    highlight_audio_text,
    generate_fixed_opening,
    generate_fixed_closing,
    build_highlight_entries,
)

__all__ = [
    "save_script",
    "load_script",
    "ScriptWriter",
    "SPEECH_CPS",
    "normalize_atmosphere_card",
    "normalize_story_cards",
    "coerce_card_narrations_for_mode",
    "split_long_subtitle",
    "extract_subtitle_texts",
    "CHINESE_ORDINALS",
    "story_angle_from_segment",
    "highlight_audio_text",
    "generate_fixed_opening",
    "generate_fixed_closing",
    "build_highlight_entries",
]
