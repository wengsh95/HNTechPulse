import pytest
from src.providers.factory import create_fetcher, create_llm_provider, create_tts_provider, create_renderer


class TestProviderFactory:
    def test_create_fetcher_default(self):
        config = {"logging": {"level": "WARNING"}, "hn": {}}
        fetcher = create_fetcher("hn", config, debug=True)
        from src.providers.fetcher.hn_fetcher import HNFetcher
        assert isinstance(fetcher, HNFetcher)

    def test_create_fetcher_unknown_raises(self):
        config = {"logging": {"level": "WARNING"}}
        with pytest.raises(ValueError, match="Unknown fetcher"):
            create_fetcher("unknown", config)

    def test_create_llm_provider_openai(self):
        config = {
            "logging": {"level": "WARNING"},
            "llm": {"model": "test"},
        }
        import os
        key = os.environ.pop("OPENAI_API_KEY", None)
        try:
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                create_llm_provider("openai", config)
        finally:
            if key is not None:
                os.environ["OPENAI_API_KEY"] = key

    def test_create_llm_provider_unknown_raises(self):
        config = {"logging": {"level": "WARNING"}}
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            create_llm_provider("unknown", config)

    def test_create_tts_provider_edge(self):
        config = {
            "logging": {"level": "WARNING"},
            "tts": {},
        }
        provider = create_tts_provider("edge-tts", config, debug=True)
        from src.providers.tts.edge_tts import EdgeTTSProvider
        assert isinstance(provider, EdgeTTSProvider)

    def test_create_tts_provider_unknown_raises(self):
        config = {"logging": {"level": "WARNING"}}
        with pytest.raises(ValueError, match="Unknown TTS provider"):
            create_tts_provider("unknown", config)

    def test_create_renderer_remotion(self):
        config = {
            "logging": {"level": "WARNING"},
            "video": {},
            "remotion": {},
        }
        try:
            renderer = create_renderer("remotion", config)
            from src.providers.renderer.remotion_renderer import RemotionRenderer
            assert isinstance(renderer, RemotionRenderer)
        except (RuntimeError, FileNotFoundError):
            pass

    def test_create_renderer_unknown_raises(self):
        config = {"logging": {"level": "WARNING"}}
        with pytest.raises(ValueError, match="Unknown renderer"):
            create_renderer("unknown", config)
