"""Project-level pytest fixtures.

Keeps process-level module caches from leaking between tests. The Whisper
model is memoized in `src.utils.audio_alignment`; without this fixture a
mock loaded by one test would be returned to a later test that re-patches
`whisper.load_model`.
"""

from src.utils.audio_alignment import _clear_whisper_model_cache


def pytest_runtest_setup(item):
    """Reset the Whisper model cache before each test."""
    _clear_whisper_model_cache()
