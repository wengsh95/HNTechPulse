from pathlib import Path
from unittest.mock import MagicMock, patch
import json


from src.core.interfaces import TTSProvider
from src.core.models import Script, ScriptSegment
from src.pipeline.tts_processor import TTSProcessor


def _make_config(**overrides):
    cfg = {
        "logging": {"level": "WARNING"},
        "timing": {"segment_gap": 0.0, "story_gap": 0.0},
        "tts": {
            "whisper_model": "small",
            "whisper_model_path": "",
        },
    }
    cfg.update(overrides)
    return cfg


def _make_provider():
    return MagicMock(spec=TTSProvider)


def _make_script(segments=None):
    if segments is None:
        segments = [
            ScriptSegment(
                segment_type="opening", audio_text="Hello", estimated_duration=5.0
            ),
            ScriptSegment(
                segment_type="closing", audio_text="Goodbye", estimated_duration=5.0
            ),
        ]
    return Script(title="Test", description="", tags=[], segments=segments)


class TestTTSProcessor:
    def test_creates_audio_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        mock_provider = _make_provider()
        with patch("src.pipeline.tts_processor.setup_logger"):
            processor = TTSProcessor(mock_provider, _make_config())
        script = _make_script()

        with patch(
            "src.pipeline.tts_processor.align_audio"
        ) as mock_align, patch(
            "src.pipeline.tts_processor.get_audio_duration", return_value=5.0
        ):
            mock_align.return_value = [
                MagicMock(text="Hello", start_time=0.0, end_time=5.0),
            ]

            processor.process_audio(script, "2026-04-26")

        assert Path("data/2026-04-26/audio").exists()

    def test_calls_synthesize_once_per_segment(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        mock_provider = _make_provider()

        with patch("src.pipeline.tts_processor.setup_logger"):
            processor = TTSProcessor(mock_provider, _make_config())

        script = _make_script()  # 2 segments: opening + closing

        with patch(
            "src.pipeline.tts_processor.align_audio"
        ) as mock_align, patch(
            "src.pipeline.tts_processor.get_audio_duration", return_value=5.0
        ):
            mock_align.return_value = [
                MagicMock(text="Hello", start_time=0.0, end_time=5.0),
            ]

            processor.process_audio(script, "2026-04-26")

        # One TTS call per segment
        assert mock_provider.synthesize.call_count == 2

    def test_skips_synthesis_when_cache_valid(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        mock_provider = _make_provider()

        with patch("src.pipeline.tts_processor.setup_logger"):
            processor = TTSProcessor(mock_provider, _make_config())

        audio_dir = Path("data/2026-04-26/audio")
        audio_dir.mkdir(parents=True, exist_ok=True)

        # Pre-create per-segment audio + manifest with alignment data
        for idx, text in enumerate(["Hello", "Goodbye"]):
            seg_path = audio_dir / f"segment_{idx:02d}.mp3"
            seg_path.write_bytes(b"\x00" * 100)
            text_hash = processor._text_hash(text)
            (audio_dir / f"segment_{idx:02d}.mp3.json").write_text(
                json.dumps(
                    {
                        "text_hash": text_hash,
                        "segments": [
                            {"text": text, "start_time": 0.0, "end_time": 5.0},
                        ],
                    }
                ),
                encoding="utf-8",
            )

        script = _make_script()

        with patch(
            "src.pipeline.tts_processor.get_audio_duration", return_value=5.0
        ):
            processor.process_audio(script, "2026-04-26")

        mock_provider.synthesize.assert_not_called()

    def test_resynthesizes_when_manifest_missing(self, tmp_path, monkeypatch):
        """Audio file exists but no manifest → re-synthesize."""
        monkeypatch.chdir(tmp_path)
        mock_provider = _make_provider()

        with patch("src.pipeline.tts_processor.setup_logger"):
            processor = TTSProcessor(mock_provider, _make_config())

        audio_dir = Path("data/2026-04-26/audio")
        audio_dir.mkdir(parents=True, exist_ok=True)
        (audio_dir / "segment_00.mp3").write_bytes(b"\x00" * 100)
        (audio_dir / "segment_01.mp3").write_bytes(b"\x00" * 100)

        script = _make_script()

        with patch(
            "src.pipeline.tts_processor.align_audio"
        ) as mock_align, patch(
            "src.pipeline.tts_processor.get_audio_duration", return_value=5.0
        ):
            mock_align.return_value = [
                MagicMock(text="Hello", start_time=0.0, end_time=5.0),
            ]

            processor.process_audio(script, "2026-04-26")

        assert mock_provider.synthesize.call_count == 2

    def test_resynthesizes_when_text_hash_changes(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        mock_provider = _make_provider()

        with patch("src.pipeline.tts_processor.setup_logger"):
            processor = TTSProcessor(mock_provider, _make_config())

        audio_dir = Path("data/2026-04-26/audio")
        audio_dir.mkdir(parents=True, exist_ok=True)
        (audio_dir / "segment_00.mp3").write_bytes(b"\x00" * 100)
        (audio_dir / "segment_00.mp3.json").write_text(
            json.dumps(
                {
                    "text_hash": processor._text_hash("Old text"),
                    "segments": [
                        {"text": "Old text", "start_time": 0.0, "end_time": 5.0},
                    ],
                }
            ),
            encoding="utf-8",
        )

        script = _make_script(
            [
                ScriptSegment(
                    segment_type="opening",
                    audio_text="New text",
                    estimated_duration=5.0,
                ),
            ]
        )

        with patch(
            "src.pipeline.tts_processor.align_audio"
        ) as mock_align, patch(
            "src.pipeline.tts_processor.get_audio_duration", return_value=5.0
        ):
            mock_align.return_value = [
                MagicMock(text="New text", start_time=0.0, end_time=5.0),
            ]

            processor.process_audio(script, "2026-04-26")

        mock_provider.synthesize.assert_called_once()

    def test_sets_actual_duration_from_audio_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        mock_provider = _make_provider()

        with patch("src.pipeline.tts_processor.setup_logger"):
            processor = TTSProcessor(mock_provider, _make_config())

        script = _make_script()

        with patch(
            "src.pipeline.tts_processor.align_audio"
        ) as mock_align, patch(
            "src.pipeline.tts_processor.get_audio_duration", return_value=7.5
        ):
            mock_align.return_value = [
                MagicMock(text="Hello", start_time=0.0, end_time=7.5),
            ]

            processor.process_audio(script, "2026-04-26")

        for seg in script.segments:
            assert seg.actual_duration == 7.5
            assert seg.audio_path is not None
            assert "segment_" in str(seg.audio_path)

    def test_empty_segment_not_processed(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        mock_provider = _make_provider()

        with patch("src.pipeline.tts_processor.setup_logger"):
            processor = TTSProcessor(mock_provider, _make_config())

        script = _make_script(
            [
                ScriptSegment(
                    segment_type="opening",
                    audio_text="Hello",
                    estimated_duration=5.0,
                ),
                ScriptSegment(
                    segment_type="story_scan",
                    audio_text="",
                    estimated_duration=0.0,
                    scene_elements=[],
                ),
            ]
        )

        with patch(
            "src.pipeline.tts_processor.align_audio"
        ) as mock_align, patch(
            "src.pipeline.tts_processor.get_audio_duration", return_value=5.0
        ):
            mock_align.return_value = [
                MagicMock(text="Hello", start_time=0.0, end_time=5.0),
            ]

            processor.process_audio(script, "2026-04-26")

        # Only 1 TTS call (empty segment excluded)
        assert mock_provider.synthesize.call_count == 1

    def test_writes_segment_manifest_after_synthesis(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        mock_provider = _make_provider()

        with patch("src.pipeline.tts_processor.setup_logger"):
            processor = TTSProcessor(mock_provider, _make_config())

        script = _make_script(
            [
                ScriptSegment(
                    segment_type="opening",
                    audio_text="Hello",
                    estimated_duration=5.0,
                ),
            ]
        )

        with patch(
            "src.pipeline.tts_processor.align_audio"
        ) as mock_align, patch(
            "src.pipeline.tts_processor.get_audio_duration", return_value=5.0
        ):
            mock_align.return_value = [
                MagicMock(text="Hello", start_time=0.0, end_time=5.0),
            ]

            processor.process_audio(script, "2026-04-26")

        audio_dir = Path("data/2026-04-26/audio")
        manifest_path = audio_dir / "segment_00.mp3.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["text_hash"] == processor._text_hash("Hello")
        assert "segments" in manifest
