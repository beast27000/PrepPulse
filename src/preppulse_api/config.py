from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MONGO_URI = os.getenv("PREPPULSE_MONGO_URI", "mongodb://127.0.0.1:27017")
MONGO_DB = os.getenv("PREPPULSE_MONGO_DB", "preppulse")
DATASET_ROOT = Path(
    os.getenv("PREPPULSE_DATASET_ROOT", str(ROOT / "datasets" / "PrepPulse Dataset"))
).resolve()
PRIVATE_ROOT = Path(os.getenv("PREPPULSE_PRIVATE_ROOT", str(ROOT / "private_data"))).resolve()
SESSION_SECRET = os.getenv("PREPPULSE_SESSION_SECRET", "")
TTS_MODEL_PATH = os.getenv("PREPPULSE_TTS_MODEL_PATH", "")
TTS_ENDPOINT = os.getenv("PREPPULSE_TTS_ENDPOINT", "")
TTS_MODEL_ID = os.getenv("PREPPULSE_TTS_MODEL_ID", "qwen3-1.7b-multilingual-tts")
STT_MODEL = os.getenv("PREPPULSE_STT_MODEL", "small")
