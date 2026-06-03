"""OpenAI-compatible LLM provider.

All shared logic lives in :class:`LLMProviderBase`; this module only picks
which transport client to instantiate.
"""

from src.providers.llm.llm_client import LLMClient
from src.providers.llm.llm_provider_base import LLMProviderBase


class OpenAILLMProvider(LLMProviderBase):
    llm_client_class = LLMClient
