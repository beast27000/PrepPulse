"""
Pluggable LLM provider interface.

Per Stage 2/3 spec Principle B: all LLM-calling logic sits behind this clean
interface. Swapping Ollama for Claude/OpenAI/DeepSeek/etc. means adding one
provider class and changing LLM_PROVIDER — zero changes to extraction, schema
validation, or database code.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass
class LLMResponse:
    text: str
    model: str
    raw: dict | None = None


class LLMClient(abc.ABC):
    """Minimal contract every provider must satisfy."""

    @abc.abstractmethod
    def complete_json(self, system: str, user: str) -> LLMResponse:
        """
        Send a prompt and return the model's response text.

        Implementations should request JSON output and keep temperature low.
        The caller is responsible for parsing/validating the JSON (see
        extract.py), because robust parsing + schema validation is provider
        independent and must not live inside a provider.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def health(self) -> bool:
        """Return True if the provider is reachable/usable right now."""
        raise NotImplementedError
