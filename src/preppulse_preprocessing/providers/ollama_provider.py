"""
Ollama provider (default). Talks to a local Ollama server running e.g. qwen2.5:7b.

Uses only the stdlib so the preprocessing layer has no hard HTTP dependency; if
you prefer `requests` or the `ollama` SDK, swap the _post method — the interface
is unchanged.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from preppulse_preprocessing.config import LLMConfig
from preppulse_preprocessing.providers.base import LLMClient, LLMResponse


class OllamaProvider(LLMClient):
    def __init__(self, cfg: LLMConfig) -> None:
        self.cfg = cfg

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.cfg.base_url.rstrip('/')}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.cfg.request_timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def complete_json(self, system: str, user: str) -> LLMResponse:
        # Ollama /api/chat with format=json asks the model to emit strict JSON.
        payload = {
            "model": self.cfg.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "format": "json",
            "stream": False,
            "options": {"temperature": self.cfg.temperature},
        }
        last_err: Exception | None = None
        for _ in range(max(1, self.cfg.max_retries + 1)):
            try:
                out = self._post("/api/chat", payload)
                text = out.get("message", {}).get("content", "")
                return LLMResponse(text=text, model=self.cfg.model, raw=out)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_err = exc
        raise RuntimeError(f"Ollama request failed after retries: {last_err}")

    def health(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.cfg.base_url.rstrip('/')}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:  # noqa: BLE001
            return False
