from unittest.mock import patch, MagicMock
from src.utils.audio import get_audio_duration


class TestGetAudioDuration:
    def test_returns_duration_on_success(self):
        mock_mp3_instance = MagicMock()
        mock_mp3_instance.info.length = 25.5
        mock_mp3_class = MagicMock(return_value=mock_mp3_instance)
        with patch.dict(
            "sys.modules",
            {
                "mutagen": MagicMock(),
                "mutagen.mp3": MagicMock(MP3=mock_mp3_class),
            },
        ):
            duration = get_audio_duration("test.mp3")
            assert duration == 25.5
            mock_mp3_class.assert_called_once_with("test.mp3")

    def test_returns_fallback_on_failure(self):
        with patch.dict(
            "sys.modules",
            {
                "mutagen": MagicMock(),
                "mutagen.mp3": MagicMock(
                    MP3=MagicMock(side_effect=Exception("File not found"))
                ),
            },
        ):
            duration = get_audio_duration("missing.mp3", fallback=30.0)
            assert duration == 30.0

    def test_custom_fallback(self):
        with patch.dict(
            "sys.modules",
            {
                "mutagen": MagicMock(),
                "mutagen.mp3": MagicMock(MP3=MagicMock(side_effect=Exception("Error"))),
            },
        ):
            duration = get_audio_duration("bad.mp3", fallback=15.0)
            assert duration == 15.0

    def test_default_fallback(self):
        with patch.dict(
            "sys.modules",
            {
                "mutagen": MagicMock(),
                "mutagen.mp3": MagicMock(MP3=MagicMock(side_effect=Exception("Error"))),
            },
        ):
            duration = get_audio_duration("bad.mp3")
            assert duration == 30.0
