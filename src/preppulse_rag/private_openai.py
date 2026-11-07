"""Protect external OpenAI-compatible clients; LAN/local inference is unchanged."""
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from preppulse_rag.privacy import PrivacyFilter, local_endpoint


class PrivateChatOpenAI(ChatOpenAI):
    # The app consumes complete replies. Route stream()/astream() through the
    # protected generate boundary instead of inherited raw token streaming.
    disable_streaming: bool = True

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        privacy = None if local_endpoint(self.openai_api_base or "https://api.openai.com") else PrivacyFilter()
        result = super()._generate(privacy.messages(messages) if privacy else messages,
                                   stop=stop, run_manager=run_manager, **kwargs)
        if privacy:
            for generation in result.generations:
                generation.message.content = privacy.restore(generation.message.content)
                generation.message.response_metadata["privacy"] = "pseudonymized"
        return result

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        privacy = None if local_endpoint(self.openai_api_base or "https://api.openai.com") else PrivacyFilter()
        result = await super()._agenerate(privacy.messages(messages) if privacy else messages,
                                          stop=stop, run_manager=run_manager, **kwargs)
        if privacy:
            for generation in result.generations:
                generation.message.content = privacy.restore(generation.message.content)
        return result


class PrivateOpenAIEmbeddings(OpenAIEmbeddings):
    def embed_documents(self, texts, chunk_size=None, **kwargs):
        if not local_endpoint(self.openai_api_base or "https://api.openai.com"):
            privacy = PrivacyFilter()
            texts = [privacy.redact(text) for text in texts]
        return super().embed_documents(texts, chunk_size=chunk_size, **kwargs)

    async def aembed_documents(self, texts, chunk_size=None, **kwargs):
        if not local_endpoint(self.openai_api_base or "https://api.openai.com"):
            privacy = PrivacyFilter()
            texts = [privacy.redact(text) for text in texts]
        return await super().aembed_documents(texts, chunk_size=chunk_size, **kwargs)
