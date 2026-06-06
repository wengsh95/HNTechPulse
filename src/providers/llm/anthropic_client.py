"""Anthropic-compatible LLM client — wraps the Anthropic SDK.

Provides the same ``call_llm_with_json_retry`` interface as :class:`LLMClient`
but talks to Anthropic-compatible endpoints (e.g. MiniMax).
"""

import anthropic
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from src.providers.llm.llm_client import LLMClient


class _AnthropicResponseAdapter:
    """Make an Anthropic response look like an OpenAI response.

    :class:`LLMClient.call_llm_with_json_retry` expects OpenAI-style
    ``response.choices[0].message.content`` / ``.finish_reason`` and
    ``response.usage.prompt_tokens`` / ``.completion_tokens``.
    This adapter translates the Anthropic response accordingly.
    """

    class _Usage:
        def __init__(self, anthropic_usage):
            self.prompt_tokens = anthropic_usage.input_tokens
            self.completion_tokens = anthropic_usage.output_tokens
            self.total_tokens = (
                anthropic_usage.input_tokens + anthropic_usage.output_tokens
            )
            self.prompt_cache_hit_tokens = (
                getattr(anthropic_usage, "cache_read_input_tokens", 0) or 0
            )

    class _Message:
        def __init__(self, anthropic_response):
            # Extract text from content blocks
            text = ""
            self.reasoning_content = ""
            for block in anthropic_response.content:
                if block.type == "text":
                    text = block.text
                elif block.type == "thinking":
                    self.reasoning_content = getattr(block, "thinking", "")
            self.content = text

    class _Choice:
        def __init__(self, anthropic_response):
            self.message = _AnthropicResponseAdapter._Message(anthropic_response)
            # Map Anthropic stop_reason → OpenAI finish_reason
            _STOP_MAP = {
                "end_turn": "stop",
                "max_tokens": "length",
                "stop_sequence": "stop",
            }
            self.finish_reason = _STOP_MAP.get(
                anthropic_response.stop_reason, anthropic_response.stop_reason or ""
            )

    def __init__(self, anthropic_response):
        self._raw = anthropic_response
        self.choices = [_AnthropicResponseAdapter._Choice(anthropic_response)]
        self.usage = _AnthropicResponseAdapter._Usage(anthropic_response.usage)


class AnthropicLLMClient(LLMClient):
    """LLM client for Anthropic-compatible APIs (e.g. MiniMax).

    Overrides the OpenAI-specific parts of :class:`LLMClient` while reusing
    all shared logic: JSON retry, extraction, diagnostics, and spinner.
    """

    def __init__(self, config: dict, debug: bool = False):
        # Skip LLMClient.__init__ — it creates an OpenAI client we don't need.
        # Replicate the shared setup directly.
        self.config = config
        self.debug = debug
        log_level = config.get("logging", {}).get("level")

        from src.utils.logger import setup_logger

        self.logger = setup_logger(__name__, debug=debug, level=log_level)

        from src.providers.llm.backend import LLMBackend

        self._backend = LLMBackend(config)
        self.client = anthropic.Anthropic(
            base_url=self._backend.base_url,
            api_key=self._backend.api_key,
        )
        if self._backend.base_url:
            self.logger.info(
                f"Using Anthropic-compatible API at: {self._backend.base_url}"
            )

        self.model = self._backend.model
        self.max_tokens = self._backend.max_tokens
        self.temperature = self._backend.temperature
        self.json_parse_max_retries = self._backend.json_parse_max_retries
        self.max_completion_tokens_cap = self._backend.max_completion_tokens_cap
        self.fast_model = self._backend.fast_model
        self.fast_max_tokens = self._backend.fast_max_tokens
        self.fast_temperature = self._backend.fast_temperature
        # Cap thinking budget so reasoning models can't burn the entire
        # max_tokens window on internal monologue and leave visible content
        # empty (finish_reason=length with 0 visible chars).
        # Default to 0 = thinking disabled, which we found is the only safe
        # setting for MiniMax-M3 (this Anthropic-compatible API treats
        # "enabled" as "think harder" with no real budget enforcement).
        self.thinking_budget_tokens = int(
            self.config.get("llm", {}).get("thinking_budget_tokens", 0)
        )
        # Per-request socket timeout — the API can hang silently for minutes
        # even on healthy-looking connections. 90s is well above the worst
        # observed good response (~60s) and well below the previous "stuck
        # forever" behavior.
        request_timeout_s = float(
            self.config.get("llm", {}).get("request_timeout_s", 90.0)
        )
        # Rebuild the client with an explicit timeout
        self.client = anthropic.Anthropic(
            base_url=self._backend.base_url,
            api_key=self._backend.api_key,
            timeout=anthropic.Timeout(timeout=request_timeout_s),
        )

    def _resolve_thinking(self, extra_body: dict | None) -> dict | None:
        """Pick a thinking config for this request.

        Priority: explicit caller override in extra_body > configured budget.
        If thinking_budget_tokens == 0, thinking is disabled entirely so the
        model is forced to spend its budget on visible content.
        """
        if extra_body and "thinking" in extra_body:
            return extra_body["thinking"]
        if self.thinking_budget_tokens <= 0:
            return {"type": "disabled"}
        return {
            "type": "enabled",
            "budget_tokens": self.thinking_budget_tokens,
        }

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential_jitter(initial=1, max=20),
        retry=retry_if_exception_type(
            (
                anthropic.APIConnectionError,
                anthropic.APITimeoutError,
                anthropic.RateLimitError,
                anthropic.InternalServerError,
            )
        ),
        reraise=True,
    )
    def _create_chat_completion(
        self,
        messages,
        model,
        max_tokens,
        temperature,
        extra_body=None,
    ):
        # Anthropic uses a top-level ``system`` parameter, not a system message.
        system_text = None
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_text = msg["content"]
            else:
                user_messages.append(msg)

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": user_messages,
        }
        if system_text:
            kwargs["system"] = system_text

        # Always inject a thinking config (capped) so reasoning models
        # can't spend the whole budget on internal monologue.
        thinking = self._resolve_thinking(extra_body)
        if thinking is not None:
            kwargs["thinking"] = thinking

        response = self.client.messages.create(**kwargs)
        return _AnthropicResponseAdapter(response)
