"""LLM backend adapter — resolves API keys and creates OpenAI clients.

This module handles the provider-specific details (which env var holds the key,
where the base URL points) so that callers don't need to.
"""

import os
from urllib.parse import urlparse

import httpx
from openai import OpenAI

from src.utils.logger import setup_logger

# hostname → env var holding the API key
_HOST_KEY_MAP: dict[str, str] = {
    "api.deepseek.com": "DEEPSEEK_API_KEY",
    "api.openai.com": "OPENAI_API_KEY",
    "api.moonshot.cn": "MOONSHOT_API_KEY",
    "api.minimax.chat": "MINIMAX_API_KEY",
    "api.minimaxi.com": "MINIMAX_API_KEY",
}

# Default timeout used when creating an OpenAI client
_DEFAULT_TIMEOUT = httpx.Timeout(connect=30.0, read=300.0, write=60.0, pool=10.0)


class LLMBackend:
    """Encapsulates backend connection details and model config for LLM calls.

    Responsibilities:
      - Resolve the correct API key env var from the configured ``base_url``.
      - Create properly-configured ``openai.OpenAI`` client instances.
      - Expose model configuration (model name, tokens, temperature, etc.).

    Usage::

        backend = LLMBackend(config)
        client = backend.create_client()
        response = client.chat.completions.create(
            model=backend.fast_model,
            messages=[...],
        )
    """

    def __init__(self, config: dict):
        llm_cfg = config.get("llm", {})
        self.base_url = llm_cfg.get("base_url", "") or ""
        self.api_key = self._resolve_api_key(llm_cfg)
        self.base_url = self.base_url or None

        # Main model config
        self.model = llm_cfg.get("model", "gpt-4o")
        self.max_tokens = llm_cfg.get("max_tokens", 8192)
        self.temperature = llm_cfg.get("temperature", 0.7)
        self.json_parse_max_retries = llm_cfg.get("json_parse_max_retries", 3)
        self.max_completion_tokens_cap = llm_cfg.get("max_completion_tokens_cap", 32768)

        # Fast / lightweight model config
        fast_cfg = llm_cfg.get("fast", {})
        self.fast_model = fast_cfg.get("model", self.model)
        self.fast_max_tokens = fast_cfg.get("max_tokens", 4096)
        self.fast_temperature = fast_cfg.get("temperature", 0.3)

    # ── key resolution ──────────────────────────────────────────

    def _resolve_api_key(self, llm_cfg: dict) -> str:
        """Return the API key for the configured backend.

        Resolution order:
        1. Explicit ``api_key_env`` in config — read that env var.
        2. Hostname match against ``_HOST_KEY_MAP``.
        3. Derived guess from hostname (e.g. ``api.foo.com`` → ``FOO_API_KEY``).
        4. Fallback: ``OPENAI_API_KEY`` → ``DEEPSEEK_API_KEY``.
        5. Raise ``ValueError`` with a helpful message.
        """
        # 1. explicit override
        explicit_env = llm_cfg.get("api_key_env")
        if explicit_env:
            key = os.getenv(explicit_env)
            if key:
                return key
            raise ValueError(
                f"LLM api_key_env is set to '{explicit_env}' but that "
                f"environment variable is not set."
            )

        # 2. hostname lookup
        hostname = self._parse_hostname()
        if hostname and hostname in _HOST_KEY_MAP:
            env_var = _HOST_KEY_MAP[hostname]
            key = os.getenv(env_var)
            if key:
                return key
            raise ValueError(
                f"LLM base_url points to {hostname} — "
                f"set {env_var} in your environment or .env file."
            )

        # 3. derived guess for unknown hosts (self-hosted proxies etc.)
        if hostname:
            guessed = self._guess_env_var(hostname)
            if guessed:
                key = os.getenv(guessed)
                if key:
                    return key

        # 4. historical fallbacks
        for env_var in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
            key = os.getenv(env_var)
            if key:
                return key

        # 5. give up
        host_info = f" (host: {hostname})" if hostname else ""
        raise ValueError(
            f"No API key found for LLM base_url{host_info}. "
            f"Set the appropriate API key env var "
            f"(e.g. OPENAI_API_KEY, DEEPSEEK_API_KEY), "
            f"or configure llm.api_key_env in config/llm.yaml."
        )

    def _parse_hostname(self) -> str | None:
        if not self.base_url:
            return None
        try:
            return urlparse(self.base_url).hostname
        except Exception:
            return None

    @staticmethod
    def _guess_env_var(hostname: str) -> str | None:
        """Derive an env var name from a hostname.

        ``api.foo.com`` → ``FOO_API_KEY``; ``llm.mycompany.cn`` → ``MYCOMPANY_API_KEY``.
        Returns ``None`` for ambiguous hostnames (localhost, IPs, single-label).
        """
        parts = hostname.rsplit(":", 1)[0].split(".")
        # skip common prefixes
        for skip in ("api", "llm", "gateway", "proxy", "v1"):
            if parts and parts[0] == skip:
                parts = parts[1:]
        if not parts:
            return None
        # pick the registrable domain label
        candidate = parts[0].upper().replace("-", "_")
        if len(candidate) < 2:
            return None
        return f"{candidate}_API_KEY"

    # ── client creation ─────────────────────────────────────────

    def create_client(self, **timeout_overrides) -> OpenAI:
        """Create a new ``openai.OpenAI`` instance for this backend.

        Keyword arguments override the default timeout values (seconds).
        Example: ``create_client(read=120.0)``.
        """
        timeout = _DEFAULT_TIMEOUT
        if timeout_overrides:
            # Build a new Timeout with overrides applied
            timeout_kwargs = {
                "connect": _DEFAULT_TIMEOUT.connect,
                "read": _DEFAULT_TIMEOUT.read,
                "write": _DEFAULT_TIMEOUT.write,
                "pool": _DEFAULT_TIMEOUT.pool,
            }
            timeout_kwargs.update(timeout_overrides)
            timeout = httpx.Timeout(**timeout_kwargs)

        kwargs: dict = {
            "api_key": self.api_key,
            "timeout": timeout,
        }
        if self.base_url:
            kwargs["base_url"] = self.base_url

        return OpenAI(**kwargs)
