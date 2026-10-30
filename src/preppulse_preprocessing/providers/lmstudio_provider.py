"""
LM Studio / OpenAI-compatible provider.
Talks to a local LM Studio server running e.g. qwen/qwen3-4b-2507.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from preppulse_preprocessing.config import LLMConfig
from preppulse_preprocessing.providers.base import LLMClient, LLMResponse


class LMStudioProvider(LLMClient):
    def __init__(self, cfg: LLMConfig) -> None:
        self.cfg = cfg
        self.base_url = (
            os.getenv("LOCAL_LLM_BASE_URL")
            or cfg.base_url
            or "http://192.168.1.16:1234/v1"
        ).rstrip("/")
        self.model = os.getenv("LOCAL_CHAT_MODEL") or cfg.model or "qwen/qwen3-4b-2507"

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer lm-studio",
            },
        )
        with urllib.request.urlopen(req, timeout=self.cfg.request_timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def complete_json(self, system: str, user: str) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.cfg.temperature,
        }
        last_err: Exception | None = None
        for _ in range(max(1, self.cfg.max_retries + 1)):
            try:
                out = self._post("/chat/completions", payload)
                choices = out.get("choices", [])
                text = choices[0].get("message", {}).get("content", "") if choices else ""
                return LLMResponse(text=text, model=self.model, raw=out)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_err = exc
        raise RuntimeError(f"LM Studio request failed after retries: {last_err}")

    def health(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.base_url}/models")
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status == 200
        except Exception:  # noqa: BLE001
            return False
