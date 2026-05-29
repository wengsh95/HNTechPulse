"""Tests for src/utils/audio_alignment.py"""

from unittest.mock import MagicMock, patch

from src.utils.audio_alignment import (
    AlignmentSegment,
    _normalize,
    align_audio,
    split_audio,
)


class TestNormalize:
    def test_removes_punctuation_chinese(self):
        assert _normalize("大家好，今天我们来聊聊Tech！") == "大家好今天我们来聊聊tech"

    def test_removes_whitespace(self):
        assert _normalize("Hello World 你好 世界") == "helloworld你好世界"

    def test_keeps_alphanumeric_and_chinese(self):
        assert _normalize("使用 React 19 框架") == "使用react19框架"

    def test_empty_string(self):
        assert _normalize("") == ""

    def test_only_punctuation(self):
        assert _normalize("，。！？") == ""


class TestAlignmentSegment:
    def test_dataclass_fields(self):
        seg = AlignmentSegment(text="hello", start_time=1.5, end_time=3.0)
        assert seg.text == "hello"
        assert seg.start_time == 1.5
        assert seg.end_time == 3.0


def _make_word(start, end, word):
    return {"word": word, "start": start, "end": end}


class TestAlignAudio:
    def test_basic_alignment(self):
        ref_texts = ["你好世界", "今天天气不错"]
        words = [
            _make_word(0.0, 0.8, "你好"),
            _make_word(0.8, 1.2, "世界"),
            _make_word(1.5, 2.3, "今天"),
            _make_word(2.3, 2.8, "天气"),
            _make_word(2.8, 3.5, "不错"),
        ]

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "segments": [
                {"words": words[:2]},
                {"words": words[2:]},
            ],
        }

        with patch("whisper.load_model", return_value=mock_model):
            results = align_audio("fake.mp3", ref_texts, debug=False)

        assert len(results) == 2
        assert results[0].text == "你好世界"
        assert results[0].start_time == 0.0
        assert results[0].end_time > 1.0  # should cover both words

        assert results[1].text == "今天天气不错"
        assert results[1].start_time >= 1.5
        assert results[1].end_time <= 3.5

    def test_fallback_when_no_match(self):
        """When Whisper output doesn't match reference at all, fall back to proportional times."""
        ref_texts = ["完全不同的文本AAA", "另一段BBB"]
        words = [
            _make_word(0.0, 1.0, "unrelated"),
            _make_word(1.0, 2.0, "content"),
        ]

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "segments": [{"words": words}],
        }

        with patch("whisper.load_model", return_value=mock_model):
            results = align_audio("fake.mp3", ref_texts, debug=False)

        assert len(results) == 2
        # Fallback: proportional split of 2.0s total
        assert results[0].start_time >= 0.0
        assert results[0].end_time <= results[1].start_time + 0.01
        assert results[1].end_time <= 2.0

    def test_punctuation_offset_across_segments(self):
        """When earlier segments contain punctuation, later segments must still
        map to the correct word indices via norm_to_raw conversion.

        Without norm_to_raw, the cumulative punctuation offset causes
        char_word_idx to return words that are too early, cutting off speech.
        """
        ref_texts = ["你好，世界。", "今天天气不错"]
        words = [
            _make_word(0.0, 0.5, "你好"),
            _make_word(0.5, 0.6, "，"),
            _make_word(0.6, 1.1, "世界"),
            _make_word(1.1, 1.2, "。"),
            _make_word(1.5, 1.9, "今天"),
            _make_word(1.9, 2.4, "天气"),
            _make_word(2.4, 3.0, "不错"),
        ]

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "segments": [{"words": words}],
        }

        with patch("whisper.load_model", return_value=mock_model):
            results = align_audio("fake.mp3", ref_texts, debug=False)

        assert len(results) == 2

        # Segment 0: "你好，世界。" — should cover "你好" through "。" boundary
        assert results[0].start_time == 0.0
        assert (
            1.1 <= results[0].end_time <= 1.5
        )  # at or after "世界" end, before "今天" start

        # Segment 1: "今天天气不错" — must NOT bleed into "世界" region
        assert results[1].start_time >= 1.5  # "今天" start
        assert results[1].end_time <= 3.0  # "不错" end

    def test_single_reference_text(self):
        ref_texts = ["一段完整的播报文本"]
        words = [
            _make_word(0.0, 0.5, "一段"),
            _make_word(0.5, 1.0, "完整的"),
            _make_word(1.0, 1.5, "播报"),
            _make_word(1.5, 2.0, "文本"),
        ]

        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "segments": [{"words": words}],
        }

        with patch("whisper.load_model", return_value=mock_model):
            results = align_audio("fake.mp3", ref_texts, debug=False)

        assert len(results) == 1
        assert results[0].start_time == 0.0
        assert results[0].end_time == 2.0

    def test_empty_words_raises(self):
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "segments": [{"words": None}, {"words": None}],
        }

        with patch("whisper.load_model", return_value=mock_model):
            try:
                align_audio("fake.mp3", ["test"], debug=False)
            except RuntimeError as e:
                assert "no word timestamps" in str(e).lower()
            else:
                raise AssertionError("Expected RuntimeError")


class TestSplitAudio:
    def test_splits_audio_with_ffmpeg(self):
        segments = [
            AlignmentSegment(text="a", start_time=0.0, end_time=2.5),
            AlignmentSegment(text="b", start_time=2.5, end_time=5.0),
        ]
        output_paths = ["out/seg_00.mp3", "out/seg_01.mp3"]

        with patch("src.utils.audio_alignment.subprocess.run") as mock_run:
            with patch(
                "src.utils.audio_alignment.Path.mkdir"
            ):  # skip actual dir creation
                split_audio("master.mp3", segments, output_paths)

        assert mock_run.call_count == 2

        # First call: segments[0]
        args0 = mock_run.call_args_list[0][0][0]
        assert args0[args0.index("-ss") + 1] == "0.000"
        assert args0[args0.index("-to") + 1] == "2.500"

        # Second call: segments[1]
        args1 = mock_run.call_args_list[1][0][0]
        assert args1[args1.index("-ss") + 1] == "2.500"
        assert args1[args1.index("-to") + 1] == "5.000"

    def test_creates_output_dirs(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        segments = [AlignmentSegment(text="x", start_time=0.0, end_time=1.0)]
        # Use a real directory path
        out = str(tmp_path / "nested" / "output.mp3")

        with patch("src.utils.audio_alignment.subprocess.run") as mock_run:
            split_audio("master.mp3", segments, [out])

        assert (tmp_path / "nested").exists()
        mock_run.assert_called_once()
