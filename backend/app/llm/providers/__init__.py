from __future__ import annotations

from app.config import Provider, Settings
from app.llm.contracts import ProviderError
from app.llm.providers.base import ProviderClient


def build_client(provider: Provider, settings: Settings) -> ProviderClient:
    key = settings.api_key(provider)
    if not key:
        raise ProviderError(f"{provider.upper()}_API_KEY is not set", retryable=False)
    if provider == "anthropic":
        from app.llm.providers.anthropic_client import AnthropicClient

        return AnthropicClient(key)
    if provider == "gemini":
        from app.llm.providers.gemini_client import GeminiClient

        return GeminiClient(key)
    from app.llm.providers.openai_client import OpenAIClient

    return OpenAIClient(key)
