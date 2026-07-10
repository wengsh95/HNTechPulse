from src.utils.subtitles import (
    split_subtitle_text,
    split_subtitle_texts,
    subtitle_display_weight,
)


def test_splits_multiple_sentences_for_tighter_alignment():
    assert split_subtitle_text("First sentence. Second sentence.") == [
        "First sentence.",
        "Second sentence.",
    ]


def test_keeps_version_numbers_intact():
    text = "React 19.1 keeps the old behavior. Developers still need the patch."

    parts = split_subtitle_text(text)

    assert parts == [
        "React 19.1 keeps the old behavior.",
        "Developers still need the patch.",
    ]


def test_splits_long_cjk_text_to_one_line_weight():
    text = (
        "\u8fd9\u6bb5\u5b57\u5e55\u660e\u663e\u592a\u957f\uff0c"
        "\u9700\u8981\u5728\u9017\u53f7\u9644\u8fd1\u62c6\u6210\u4e24\u6bb5\uff0c"
        "\u5426\u5219\u5c31\u4f1a\u5728\u5c4f\u5e55\u4e0a\u6362\u884c"
    )

    parts = split_subtitle_texts([text])

    assert len(parts) == 2
    assert all(subtitle_display_weight(part) <= 24 for part in parts)
