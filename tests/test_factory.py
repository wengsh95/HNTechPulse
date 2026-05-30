import pytest
from src.providers.factory import (
    create_fetcher,
    create_llm_provider,
)


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

        saved_keys = {}
        for env_var in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
            saved_keys[env_var] = os.environ.pop(env_var, None)
        try:
            with pytest.raises(ValueError, match="No API key found"):
                create_llm_provider("openai", config)
        finally:
            for env_var, value in saved_keys.items():
                if value is not None:
                    os.environ[env_var] = value

    def test_create_llm_provider_unknown_raises(self):
        config = {"logging": {"level": "WARNING"}}
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            create_llm_provider("unknown", config)
