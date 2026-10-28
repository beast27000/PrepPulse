from __future__ import annotations

import os
from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage

# ---------- deterministic mock fallback ----------


class MockClinicalChatModel(BaseChatModel):
    # Deterministic fallback model for testing without live LLM or API keys
    model_name: str = "mock-clinical-v1"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> Any:
        from langchain_core.outputs import ChatGeneration, ChatResult

        last_prompt = messages[-1].content if messages else ""
        response_text = f"Clinical assessment response based on retrieved evidence for: {last_prompt[:100]}"
        generation = ChatGeneration(message=AIMessage(content=response_text))
        return ChatResult(generations=[generation])

    @property
    def _llm_type(self) -> str:
        return "mock-clinical-chat"


class MockEmbeddings(Embeddings):
    # Lightweight deterministic embedding generator for local testing
    dimension: int = 128

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        # Feature hashing with signed token buckets normalized to unit sphere
        import hashlib

        tokens = text.lower().replace(".", " ").replace(",", " ").split()
        if not tokens:
            return [0.0] * self.dimension

        vec = [0.0] * self.dimension
        for tok in tokens:
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dimension
            sign = 1.0 if (h >> 20) & 1 else -1.0
            vec[idx] += sign

        norm = sum(x * x for x in vec) ** 0.5 or 1.0
        return [x / norm for x in vec]


# ---------- plug and play llm factory ----------


class LLMFactory:
    # Resolves and instantiates chat models and embeddings from configuration

    @staticmethod
    def get_chat_model(
        provider: str | None = None,
        model_name: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.0,
    ) -> BaseChatModel:
        # Returns chat model instance based on provider string or env vars
        resolved_provider = provider or os.getenv("LLM_PROVIDER", "mock").lower()
        resolved_model = model_name or os.getenv("LLM_MODEL", "qwen2.5:7b")
        resolved_base_url = base_url or os.getenv("LLM_BASE_URL", "http://localhost:11434")

        if resolved_provider == "ollama":
            try:
                from langchain_community.chat_models import ChatOllama

                return ChatOllama(
                    model=resolved_model,
                    base_url=resolved_base_url,
                    temperature=temperature,
                )
            except Exception:  # noqa: BLE001
                # Fallback to mock if Ollama server is offline
                return MockClinicalChatModel(model_name=resolved_model)

        elif resolved_provider in ("sarvam", "openai_compatible"):
            try:
                from langchain_community.chat_models import ChatOpenAI

                resolved_key = (
                    api_key
                    or os.getenv("SARVAM_API_KEY")
                    or os.getenv("OPENAI_API_KEY")
                    or "dummy-key"
                )
                return ChatOpenAI(
                    model=resolved_model,
                    openai_api_base=resolved_base_url,
                    openai_api_key=resolved_key,
                    temperature=temperature,
                )
            except Exception:  # noqa: BLE001
                return MockClinicalChatModel(model_name=resolved_model)

        # Default fallback
        return MockClinicalChatModel(model_name=resolved_model)

    @staticmethod
    def get_embeddings(
        provider: str | None = None,
        model_name: str | None = None,
        base_url: str | None = None,
    ) -> Embeddings:
        # Returns embeddings generator based on provider configuration
        resolved_provider = provider or os.getenv("LLM_PROVIDER", "mock").lower()

        if resolved_provider == "ollama":
            try:
                from langchain_community.embeddings import OllamaEmbeddings

                resolved_model = model_name or os.getenv("OLLAMA_EMBED_MODEL", "qwen2.5:7b")
                resolved_base_url = base_url or os.getenv("LLM_BASE_URL", "http://localhost:11434")
                return OllamaEmbeddings(model=resolved_model, base_url=resolved_base_url)
            except Exception:  # noqa: BLE001
                return MockEmbeddings()

        return MockEmbeddings()
