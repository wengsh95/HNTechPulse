"""Tests for src/providers/llm/backend.py."""

from unittest.mock import patch

import pytest

from src.providers.llm.backend import LLMBackend


def _make_config(**overrides):
    cfg: dict = {"llm": {}}
    for k, v in overrides.items():
        cfg["llm"][k] = v
    return cfg


def _make_backend(monkeypatch, **config_overrides):
    """Construct LLMBackend with OPENAI_API_KEY set so init doesn't raise."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    return LLMBackend(_make_config(**config_overrides))


# ── Config parsing ─────────────────────────────────────────────────────


class TestConfigParsing:
    def test_defaults(self, monkeypatch):
        backend = _make_backend(monkeypatch)
        assert backend.model == "gpt-4o"
        assert backend.max_tokens == 8192
        assert backend.temperature == 0.7
        assert backend.json_parse_max_retries == 3
        assert backend.max_completion_tokens_cap == 32768
        assert backend.fast_model == "gpt-4o"
        assert backend.fast_max_tokens == 4096
        assert backend.fast_temperature == 0.3

    def test_main_model_overrides(self, monkeypatch):
        backend = _make_backend(
            monkeypatch,
            model="gpt-4-turbo",
            max_tokens=4096,
            temperature=0.3,
            json_parse_max_retries=5,
            max_completion_tokens_cap=16384,
        )
        assert backend.model == "gpt-4-turbo"
        assert backend.max_tokens == 4096
        assert backend.temperature == 0.3
        assert backend.json_parse_max_retries == 5
        assert backend.max_completion_tokens_cap == 16384

    def test_fast_model_overrides(self, monkeypatch):
        backend = _make_backend(
            monkeypatch,
            fast={
                "model": "gpt-4o-mini",
                "max_tokens": 2048,
                "temperature": 0.1,
            },
        )
        assert backend.fast_model == "gpt-4o-mini"
        assert backend.fast_max_tokens == 2048
        assert backend.fast_temperature == 0.1

    def test_base_url_set(self, monkeypatch):
        backend = _make_backend(monkeypatch, base_url="https://api.openai.com/v1")
        assert backend.base_url == "https://api.openai.com/v1"

    def test_base_url_empty_string_becomes_none(self, monkeypatch):
        backend = _make_backend(monkeypatch, base_url="")
        assert backend.base_url is None


# ── Hostname parsing ───────────────────────────────────────────────────


class TestParseHostname:
    def test_standard_url(self, monkeypatch):
        backend = _make_backend(monkeypatch, base_url="https://api.openai.com/v1")
        assert backend._parse_hostname() == "api.openai.com"

    def test_no_base_url(self, monkeypatch):
        backend = _make_backend(monkeypatch)
        assert backend._parse_hostname() is None

    def test_custom_port(self, monkeypatch):
        backend = _make_backend(monkeypatch, base_url="http://localhost:8080/v1")
        assert backend._parse_hostname() == "localhost"


# ── Env var guessing ───────────────────────────────────────────────────


class TestGuessEnvVar:
    def test_standard_api_host(self):
        assert LLMBackend._guess_env_var("api.deepseek.com") == "DEEPSEEK_API_KEY"

    def test_custom_host_strips_api_prefix(self):
        assert LLMBackend._guess_env_var("api.foo.com") == "FOO_API_KEY"

    def test_custom_host_strips_llm_prefix(self):
        assert LLMBackend._guess_env_var("llm.mycompany.cn") == "MYCOMPANY_API_KEY"

    def test_single_label_returns_none(self):
        assert LLMBackend._guess_env_var("api") is None


# ── API key resolution ────────────────────────────────────────────────


class TestResolveApiKey:
    def test_explicit_env_var(self, monkeypatch):
        monkeypatch.setenv("MY_CUSTOM_KEY", "sk-custom")
        backend = LLMBackend(_make_config(api_key_env="MY_CUSTOM_KEY"))
        assert backend.api_key == "sk-custom"

    def test_explicit_env_var_unset_raises(self, monkeypatch):
        # The constructor calls _resolve_api_key eagerly, so it raises
        # before we even assign to a variable.
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        with pytest.raises(ValueError, match="MISSING_KEY"):
            LLMBackend(_make_config(api_key_env="MISSING_KEY"))

    def test_hostname_match_openai(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
        backend = LLMBackend(_make_config(base_url="https://api.openai.com/v1"))
        assert backend.api_key == "sk-openai"

    def test_hostname_match_deepseek(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek")
        backend = LLMBackend(_make_config(base_url="https://api.deepseek.com/v1"))
        assert backend.api_key == "sk-deepseek"

    def test_hostname_match_moonshot(self, monkeypatch):
        monkeypatch.setenv("MOONSHOT_API_KEY", "sk-moonshot")
        backend = LLMBackend(_make_config(base_url="https://api.moonshot.cn/v1"))
        assert backend.api_key == "sk-moonshot"

    def test_hostname_match_minimax_chat(self, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax")
        backend = LLMBackend(_make_config(base_url="https://api.minimax.chat/v1"))
        assert backend.api_key == "sk-minimax"

    def test_hostname_match_minimaxi(self, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-minimax")
        backend = LLMBackend(_make_config(base_url="https://api.minimaxi.com/v1"))
        assert backend.api_key == "sk-minimax"

    def test_hostname_match_missing_key_raises(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            LLMBackend(_make_config(base_url="https://api.openai.com/v1"))

    def test_guess_env_var_from_unknown_host(self, monkeypatch):
        monkeypatch.setenv("MYPROXY_API_KEY", "sk-proxy")
        backend = LLMBackend(_make_config(base_url="https://api.myproxy.io/v1"))
        assert backend.api_key == "sk-proxy"

    def test_fallback_to_openai_key(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-fallback")
        backend = LLMBackend({"llm": {}})
        assert backend.api_key == "sk-fallback"

    def test_fallback_to_deepseek_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
        backend = LLMBackend({"llm": {}})
        assert backend.api_key == "sk-ds"

    def test_fallback_openai_before_deepseek(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-first")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-second")
        backend = LLMBackend({"llm": {}})
        assert backend.api_key == "sk-openai-first"

    def test_no_key_found_raises(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        with pytest.raises(ValueError, match="No API key found"):
            LLMBackend({"llm": {}})


# ── Client creation ────────────────────────────────────────────────────


class TestCreateClient:
    def test_creates_client_with_api_key(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        with patch("src.providers.llm.backend.OpenAI") as mock_openai:
            backend = LLMBackend({"llm": {}})
            backend.create_client()
            call_kwargs = mock_openai.call_args.kwargs
            assert call_kwargs["api_key"] == "sk-test"

    def test_creates_client_with_base_url(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        with patch("src.providers.llm.backend.OpenAI") as mock_openai:
            backend = LLMBackend(_make_config(base_url="https://api.openai.com/v1"))
            backend.create_client()
            call_kwargs = mock_openai.call_args.kwargs
            assert call_kwargs["base_url"] == "https://api.openai.com/v1"

    def test_no_base_url_when_none(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        with patch("src.providers.llm.backend.OpenAI") as mock_openai:
            backend = LLMBackend({"llm": {}})
            backend.create_client()
            call_kwargs = mock_openai.call_args.kwargs
            assert "base_url" not in call_kwargs

    def test_timeout_override(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        with patch("src.providers.llm.backend.OpenAI") as mock_openai:
            backend = LLMBackend({"llm": {}})
            backend.create_client(read=120.0)
            call_kwargs = mock_openai.call_args.kwargs
            assert call_kwargs["timeout"].read == 120.0


# ── Integration: backend + key resolution edge cases ───────────────────


class TestBackendIntegration:
    def test_explicit_key_takes_priority_over_hostname(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "sk-explicit")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-ignored")
        backend = LLMBackend(
            _make_config(
                api_key_env="MY_KEY",
                base_url="https://api.openai.com/v1",
            )
        )
        assert backend.api_key == "sk-explicit"

    def test_key_cached_after_first_access(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-cached")
        backend = LLMBackend({"llm": {}})
        key1 = backend.api_key
        key2 = backend.api_key
        assert key1 == "sk-cached"
        assert key1 == key2
