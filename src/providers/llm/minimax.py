"""Anthropic-flavored LLM provider.

All shared logic lives in :class:`LLMProviderBase`; this module only picks
which transport client to instantiate.
"""

from src.providers.llm.anthropic_client import AnthropicLLMClient
from src.providers.llm.llm_provider_base import LLMProviderBase


class MiniMaxLLMProvider(LLMProviderBase):
    llm_client_class = AnthropicLLMClient
