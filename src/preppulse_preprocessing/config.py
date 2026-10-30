"""
Central configuration for the PrepPulse preprocessing layer (Stage 2 + Stage 3).

Everything is environment-driven so the layer can be reconfigured at deploy time
without touching code. Per the Stage 2/3 spec (Principle B), the LLM provider is
fully decoupled: swapping Ollama for Claude/OpenAI/etc. is a config change only.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class MongoConfig:
    uri: str = field(default_factory=lambda: _env("MONGO_URI", "mongodb://localhost:27017"))
    db_name: str = field(default_factory=lambda: _env("MONGO_DB", "preppulse"))
    server_timeout_ms: int = field(default_factory=lambda: _env_int("MONGO_TIMEOUT_MS", 3000))


@dataclass(frozen=True)
class LLMConfig:
    # provider selector: "ollama" (default) or "mock" for offline/deterministic runs
    provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "ollama"))
    model: str = field(default_factory=lambda: _env("OLLAMA_MODEL", "qwen2.5:7b"))
    base_url: str = field(default_factory=lambda: _env("LLM_BASE_URL", "http://localhost:11434"))
    temperature: float = field(default_factory=lambda: _env_float("LLM_TEMPERATURE", 0.0))
    request_timeout_s: int = field(default_factory=lambda: _env_int("LLM_TIMEOUT_S", 120))
    max_retries: int = field(default_factory=lambda: _env_int("LLM_MAX_RETRIES", 2))


@dataclass(frozen=True)
class GroundingConfig:
    # minimum confidence below which an extracted fact is flagged for human review
    review_threshold: float = field(default_factory=lambda: _env_float("GROUND_REVIEW_THRESHOLD", 0.55))
    # numeric tolerance when matching an extracted lab value back to source text
    numeric_tolerance: float = field(default_factory=lambda: _env_float("GROUND_NUMERIC_TOL", 0.1))
    # fuzzy string ratio (0-1) required to accept a non-exact anchor match
    fuzzy_accept: float = field(default_factory=lambda: _env_float("GROUND_FUZZY_ACCEPT", 0.82))


@dataclass(frozen=True)
class Settings:
    mongo: MongoConfig = field(default_factory=MongoConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    grounding: GroundingConfig = field(default_factory=GroundingConfig)
    compiled_by: str = field(default_factory=lambda: _env("COMPILED_BY", "preprocessing_layer_v1"))


def load_settings() -> Settings:
    """Build a Settings snapshot from the current environment."""
    return Settings()
