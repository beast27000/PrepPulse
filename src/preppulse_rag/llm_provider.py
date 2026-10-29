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
    def _is_local_server_available(url: str = "http://192.168.1.16:1234/v1/models") -> bool:
        # Fast non-blocking check if local LM Studio server is live
        import urllib.request
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                return resp.status == 200
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def get_chat_model(
        provider: str | None = None,
        model_name: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> BaseChatModel:
        # Returns chat model instance based on provider string or env vars
        env_provider = os.getenv("LLM_PROVIDER")
        if provider:
            resolved_provider = provider.lower()
        elif env_provider:
            resolved_provider = env_provider.lower()
        elif LLMFactory._is_local_server_available():
            resolved_provider = "local"
        else:
            resolved_provider = "mock"

        if resolved_provider in ("local", "lmstudio"):
            try:
                from langchain_openai import ChatOpenAI

                resolved_model = model_name or os.getenv("LOCAL_CHAT_MODEL", "qwen/qwen3-4b-2507")
                resolved_base_url = (
                    base_url
                    or os.getenv("LOCAL_LLM_BASE_URL", "http://192.168.1.16:1234/v1")
                )
                return ChatOpenAI(
                    model=resolved_model,
                    base_url=resolved_base_url,
                    api_key="lm-studio",
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception:  # noqa: BLE001
                return MockClinicalChatModel(model_name="qwen/qwen3-4b-2507")

        elif resolved_provider == "sarvam":
            try:
                from langchain_openai import ChatOpenAI

                resolved_key = (
                    api_key
                    or os.getenv("SARVAM_AI_CREDITS")
                    or os.getenv("SARVAM_API_KEY")
                    or "dummy-key"
                )
                resolved_base_url = (
                    base_url
                    or os.getenv("SARVAM_BASE_URL", "https://api.sarvam.ai/v1")
                )
                resolved_model = model_name or os.getenv("SARVAM_MODEL", "sarvam-2b")
                return ChatOpenAI(
                    model=resolved_model,
                    base_url=resolved_base_url,
                    api_key=resolved_key,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception:  # noqa: BLE001
                return MockClinicalChatModel(model_name="sarvam-fallback")

        elif resolved_provider == "ollama":
            try:
                from langchain_community.chat_models import ChatOllama

                resolved_model = model_name or os.getenv("LLM_MODEL", "qwen2.5:7b")
                resolved_base_url = base_url or os.getenv("LLM_BASE_URL", "http://localhost:11434")
                return ChatOllama(
                    model=resolved_model,
                    base_url=resolved_base_url,
                    temperature=temperature,
                )
            except Exception:  # noqa: BLE001
                return MockClinicalChatModel(model_name=model_name or "qwen2.5:7b")

        # Default mock fallback
        return MockClinicalChatModel(model_name=model_name or "mock-clinical-chat")

    @staticmethod
    def get_embeddings(
        provider: str | None = None,
        model_name: str | None = None,
        base_url: str | None = None,
    ) -> Embeddings:
        # Returns embeddings generator based on provider configuration
        env_provider = os.getenv("LLM_PROVIDER")
        if provider:
            resolved_provider = provider.lower()
        elif env_provider:
            resolved_provider = env_provider.lower()
        elif LLMFactory._is_local_server_available():
            resolved_provider = "local"
        else:
            resolved_provider = "mock"

        if resolved_provider in ("local", "lmstudio"):
            try:
                from langchain_openai import OpenAIEmbeddings

                resolved_model = model_name or os.getenv(
                    "LOCAL_EMBED_MODEL", "text-embedding-qwen3-embedding-0.6b"
                )
                resolved_base_url = (
                    base_url
                    or os.getenv("LOCAL_LLM_BASE_URL", "http://192.168.1.16:1234/v1")
                )
                return OpenAIEmbeddings(
                    model=resolved_model,
                    base_url=resolved_base_url,
                    api_key="lm-studio",
                    check_embedding_ctx_length=False,
                )
            except Exception:  # noqa: BLE001
                return MockEmbeddings()

        elif resolved_provider == "ollama":
            try:
                from langchain_community.embeddings import OllamaEmbeddings

                resolved_model = model_name or os.getenv("OLLAMA_EMBED_MODEL", "qwen2.5:7b")
                resolved_base_url = base_url or os.getenv("LLM_BASE_URL", "http://localhost:11434")
                return OllamaEmbeddings(model=resolved_model, base_url=resolved_base_url)
            except Exception:  # noqa: BLE001
                return MockEmbeddings()

        return MockEmbeddings()
