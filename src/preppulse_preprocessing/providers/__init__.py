"""LLM provider selection. One switch (LLM_PROVIDER) chooses the backend."""
from __future__ import annotations

from preppulse_preprocessing.config import LLMConfig
from preppulse_preprocessing.providers.base import LLMClient, LLMResponse
from preppulse_preprocessing.providers.lmstudio_provider import LMStudioProvider
from preppulse_preprocessing.providers.mock_provider import MockProvider
from preppulse_preprocessing.providers.ollama_provider import OllamaProvider

__all__ = ["LLMClient", "LLMResponse", "LMStudioProvider", "MockProvider", "OllamaProvider", "get_llm_provider"]


def get_llm_provider(cfg: LLMConfig) -> LLMClient:
    """Return the configured provider. Add new backends here only."""
    provider = (cfg.provider or "ollama").lower()
    if provider in ("lmstudio", "local", "openai"):
        return LMStudioProvider(cfg)
    if provider == "ollama":
        return OllamaProvider(cfg)
    if provider == "mock":
        return MockProvider(cfg)
    raise ValueError(
        f"Unknown LLM_PROVIDER '{cfg.provider}'. Supported: 'lmstudio', 'local', 'ollama', 'mock'. "
        "Add a new LLMClient subclass and register it in get_llm_provider()."
    )
