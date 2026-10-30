from __future__ import annotations

import time
from ipaddress import ip_address
from urllib.parse import urlparse

import httpx

from preppulse_api.config import TTS_ENDPOINT, TTS_MODEL_ID

_last_probe = 0.0
_probe_ok = False


def _local_endpoint() -> bool:
    if not TTS_ENDPOINT:
        return False
    parsed = urlparse(TTS_ENDPOINT)
    if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password:
        return False
    if parsed.hostname == "localhost":
        return True
    try:
        address = ip_address(parsed.hostname)
    except ValueError:
        return False
    return address.is_loopback or address.is_private


def _wav(data: bytes) -> bool:
    return len(data) >= 44 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"


def synthesize(text: str) -> bytes:
    if not _local_endpoint():
        raise ValueError("Configure a local or private-network TTS audio endpoint")
    with httpx.Client(timeout=60, trust_env=False) as client:
        response = client.post(
            TTS_ENDPOINT,
            json={
                "model": TTS_MODEL_ID,
                "input": text,
                "voice": "alloy",
                "response_format": "wav",
            },
        )
    if response.status_code != 200 or not _wav(response.content):
        raise ValueError("Configured TTS server did not return WAV audio")
    if len(response.content) > 20 * 1024 * 1024:
        raise ValueError("TTS response exceeds 20 MB")
    return response.content


def ready() -> bool:
    global _last_probe, _probe_ok
    if not _local_endpoint():
        return False
    if time.monotonic() - _last_probe > 60:
        _last_probe = time.monotonic()
        try:
            _probe_ok = bool(synthesize("PrepPulse voice check."))
        except (httpx.HTTPError, ValueError):
            _probe_ok = False
    return _probe_ok
