from .anthropic import AnthropicAdapter
from .base import Environment, ProviderAdapter
from .gemini import GeminiAdapter
from .openai import OpenAIAdapter
from .perplexity import PerplexityAdapter
from .xai import XAIAdapter

ADAPTERS = {
    "openai": OpenAIAdapter,
    "anthropic": AnthropicAdapter,
    "gemini": GeminiAdapter,
    "xai": XAIAdapter,
    "perplexity": PerplexityAdapter,
}


def make_adapter(provider: str, **kwargs: object) -> ProviderAdapter:
    try:
        return ADAPTERS[provider](**kwargs)
    except KeyError as exc:
        raise ValueError(f"unknown provider: {provider}") from exc


__all__ = ["ADAPTERS", "Environment", "ProviderAdapter", "make_adapter"]
