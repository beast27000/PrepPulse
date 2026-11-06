"""Explicit Sarvam/Gemini/local routing; no clinical mock fallback or secret logging."""
from __future__ import annotations

import os
import time

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from preppulse_rag.runtime import BudgetExceeded, cooldown, finish, reserve, sarvam_accounts


class ProviderUnavailable(RuntimeError):
    pass


class ProviderRateLimited(ProviderUnavailable):
    pass


class TransientProviderFailure(ProviderUnavailable):
    pass


class RoutedChatModel(BaseChatModel):
    provider: str = "sarvam"
    model_name: str | None = None
    temperature: float = 0
    max_tokens: int = 2048
    request_timeout: float | None = None
    transient_retries: int | None = None

    @property
    def _llm_type(self):
        return "preppulse-provider-router"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        providers = [self.provider]
        from preppulse_api.provider_settings import routing
        mode = routing() if os.getenv("PREPPULSE_ENV") == "production" else "auto"
        if mode == "disabled":
            raise ProviderUnavailable("AI processing is disabled by the administrator")
        if os.getenv("PREPPULSE_AI_ENABLED", "1") != "1":
            raise ProviderUnavailable("AI processing is disabled; saved records remain available")
        if self.provider == "auto":
            configured = os.getenv("PREPPULSE_AI_PROVIDER_ORDER", "")
            providers = [p.strip() for p in configured.split(",") if p.strip()] if configured else ["sarvam"]
            if os.getenv("PREPPULSE_GEMINI_ENABLED", "0") == "1" and "gemini" not in providers:
                providers.append("gemini")
            if not configured and os.getenv("PREPPULSE_ALLOW_LOCAL_AI", "1") == "1":
                providers.append("local")
        if self.provider == "auto" and mode in {"azure", "sarvam"}:
            providers = [mode]
        errors = []
        for provider in providers:
            if provider not in {"azure", "sarvam", "gemini", "local"}:
                errors.append("Unsupported provider configuration")
                continue
            if provider == "local" and os.getenv("PREPPULSE_ALLOW_LOCAL_AI", "1") != "1":
                continue
            if provider == "gemini" and os.getenv("PREPPULSE_SYNTHETIC_ONLY", "0") != "1":
                errors.append("gemini: synthetic-data mode required")
                continue
            accounts = sarvam_accounts() if provider == "sarvam" else [
                (provider.upper(), os.getenv("Gemini_free_api_keys") or os.getenv("GEMINI_API_KEY", ""))
            ]
            if provider == "local":
                accounts = [("LOCAL", "lm-studio")]
            elif provider == "azure":
                accounts = [("AZURE_CHAT", os.getenv("AZURE_OPENAI_API_KEY", ""))]
            for alias, key in accounts:
                if not key:
                    continue
                try:
                    text, metadata = self._request(provider, alias, key, messages, stop, kwargs)
                    return ChatResult(generations=[ChatGeneration(message=AIMessage(
                        content=text, response_metadata=metadata))], llm_output=metadata)
                except ProviderRateLimited as exc:
                    errors.append(f"{provider}: {exc}")
                    break
                except (ProviderUnavailable, BudgetExceeded) as exc:
                    errors.append(f"{provider}/{alias}: {exc}")
        raise ProviderUnavailable("; ".join(errors) or "No configured provider credential")

    def _request(self, provider, alias, key, messages, stop, kwargs):
        attempts = min(2, max(0, self.transient_retries if self.transient_retries is not None
                              else int(os.getenv("PREPPULSE_AI_TRANSIENT_RETRIES", "2"))))
        for attempt in range(attempts + 1):
            try:
                return self._request_once(provider, alias, key, messages, stop, kwargs)
            except TransientProviderFailure:
                if attempt == attempts:
                    raise
                time.sleep(1.5 * (2 ** attempt))

    def _request_once(self, provider, alias, key, messages, stop, kwargs):
        model = self.model_name or {
            "sarvam": os.getenv("SARVAM_MODEL", "sarvam-105b"),
            "gemini": os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
            "local": os.getenv("LOCAL_CHAT_MODEL", "qwen/qwen3-4b-2507"),
            "azure": os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini"),
        }[provider]
        urls = {"sarvam": os.getenv("SARVAM_BASE_URL", "https://api.sarvam.ai/v1"),
                "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
                "local": os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:1234/v1")}
        if provider == "azure":
            from preppulse_api.azure_services import chat_url
            urls["azure"] = chat_url()
        wire = [{"role": {"human": "user", "ai": "assistant"}.get(m.type, m.type),
                 "content": m.content} for m in messages]
        # Reserve a deliberately conservative upper estimate, including tokenizer variation.
        input_estimate = sum(len(str(m["content"]).encode()) for m in wire) + 1024
        input_rate = float(os.getenv("SARVAM_INPUT_INR_PER_MILLION", "30"))
        output_rate = float(os.getenv("SARVAM_OUTPUT_INR_PER_MILLION", "100"))
        output_limit = max(self.max_tokens, 2048) if provider != "local" else self.max_tokens
        cost = (input_estimate * input_rate + output_limit * output_rate) / 1_000_000
        azure_cost = (input_estimate * float(os.getenv("AZURE_INPUT_USD_PER_MILLION", "5"))
                      + output_limit * float(os.getenv("AZURE_OUTPUT_USD_PER_MILLION", "20"))) / 1_000_000
        call_id = reserve(provider, alias, "chat", cost if provider == "sarvam" else azure_cost if provider == "azure" else 0)
        payload = {"model": model, "messages": wire, "temperature": self.temperature,
                   "max_tokens": output_limit}
        if provider == "sarvam":
            payload["reasoning_effort"] = None  # Do not consume the answer budget with hidden reasoning.
        if provider == "gemini":
            payload["reasoning_effort"] = "none" if model.startswith("gemini-2.5") else "minimal"
        if kwargs.get("json_mode"):
            payload["response_format"] = {"type": "json_object"}
        if stop:
            payload["stop"] = stop
        headers = {"api-subscription-key": key} if provider == "sarvam" else {
            "Authorization": "Bearer " + key}
        if provider == "azure":
            headers = {"api-key": key}
        started = time.monotonic()
        try:
            with httpx.Client(timeout=self.request_timeout or float(os.getenv("PREPPULSE_AI_TIMEOUT", "90")),
                              trust_env=False) as client:
                response = client.post(urls[provider] if provider == "azure" else urls[provider].rstrip("/") + "/chat/completions",
                                       headers=headers, json=payload)
            if response.status_code != 200:
                if provider == "azure" and response.status_code in {401, 403, 404}:
                    cooldown("AZURE_CHAT", 120)
                if response.status_code == 402:
                    cooldown(alias, 3600)
                elif response.status_code == 429:
                    cooldown(alias, 60)
                    cooldown(provider, 60)
                    # A rate limit belongs to the organisation; do not rotate Sarvam keys to evade it.
                    finish(call_id, "http_429")
                    raise ProviderRateLimited("Provider rate limit; retry after cooldown")
                finish(call_id, f"http_{response.status_code}")
                if response.status_code in {408, 500, 502, 503, 504}:
                    raise TransientProviderFailure(f"HTTP {response.status_code}; temporary provider failure")
                raise ProviderUnavailable(f"HTTP {response.status_code}")
            data = response.json()
            usage = data.get("usage") or {}
            prompt, completion = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
            actual = ((prompt * input_rate + completion * output_rate) / 1_000_000
                      if provider == "sarvam" else 0)
            if provider == "azure":
                actual = (prompt * float(os.getenv("AZURE_INPUT_USD_PER_MILLION", "5"))
                          + completion * float(os.getenv("AZURE_OUTPUT_USD_PER_MILLION", "20"))) / 1_000_000
            choices = data.get("choices") or [{}]
            text = (choices[0].get("message") or {}).get("content")
            if not isinstance(text, str) or not text.strip() or choices[0].get("finish_reason") == "length":
                finish(call_id, "incomplete", actual, prompt, completion)
                raise ProviderUnavailable("Empty or truncated response")
            finish(call_id, "ok", actual, prompt, completion)
            return text, {"provider": provider, "model": model, "account": alias,
                          "usage": usage, "elapsed_seconds": round(time.monotonic() - started, 3)}
        except (httpx.HTTPError, ValueError):
            finish(call_id, "transport_or_json_error")
            raise TransientProviderFailure("Transport or response decoding failed") from None
