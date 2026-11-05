"""Stage 2 shares cloud routing and budgets with review agents."""
import os

from langchain_core.messages import HumanMessage, SystemMessage

from preppulse_preprocessing.providers.base import LLMClient, LLMResponse
from preppulse_rag.cloud_provider import RoutedChatModel


class RoutedProvider(LLMClient):
    batch_pages = True
    def __init__(self, cfg):
        self.provider = cfg.provider
        self.client = RoutedChatModel(provider=cfg.provider, max_tokens=4096)

    def complete_json(self, system, user):
        result = self.client.invoke([SystemMessage(content=system), HumanMessage(content=user)],
                                    json_mode=True)
        return LLMResponse(text=result.content, model=result.response_metadata.get("model", self.provider),
                           raw=result.response_metadata)

    def health(self):
        from preppulse_rag.runtime import sarvam_accounts
        if self.provider in {"azure", "auto"} and os.getenv("AZURE_OPENAI_API_KEY"):
            return True
        return bool(sarvam_accounts()) if self.provider == "sarvam" else bool(
            os.getenv("Gemini_free_api_keys") or os.getenv("GEMINI_API_KEY"))
