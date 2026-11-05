"""CPU multilingual E5 retrieval with content-hashed, model-scoped SQLite caching."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from functools import lru_cache
from pathlib import Path
from threading import Lock

from langchain_core.embeddings import Embeddings

from preppulse_rag.runtime import ROOT

MODEL = "intfloat/multilingual-e5-small"
MODEL_LOCK = Lock()


@lru_cache(maxsize=1)
def encoder():
    from sentence_transformers import SentenceTransformer
    revision = os.getenv("PREPPULSE_EMBED_REVISION")
    if not revision:
        raise RuntimeError("Set PREPPULSE_EMBED_REVISION to the verified model commit")
    return SentenceTransformer(MODEL, revision=revision, device="cpu",
                               cache_folder=os.getenv("PREPPULSE_EMBED_CACHE", str(ROOT / ".local_models" / "embeddings")),
                               trust_remote_code=False)


class PythonEmbeddings(Embeddings):
    def _encode(self, texts, prefix):
        root = Path(os.getenv("PREPPULSE_PRIVATE_ROOT", str(ROOT / "private_data")))
        root.mkdir(parents=True, exist_ok=True)
        output = []
        with MODEL_LOCK, sqlite3.connect(root / "embeddings.sqlite3", timeout=60) as db:
            db.execute("CREATE TABLE IF NOT EXISTS vectors (key TEXT PRIMARY KEY, vector TEXT)")
            model = encoder()
            for text in texts:
                key = hashlib.sha256((MODEL + os.getenv("PREPPULSE_EMBED_REVISION", "")
                                      + prefix + text).encode()).hexdigest()
                row = db.execute("SELECT vector FROM vectors WHERE key=?", (key,)).fetchone()
                if row:
                    output.append(json.loads(row[0]))
                    continue
                # Split over the model token limit, then mean-pool normalized window vectors.
                tokens = model.tokenizer.encode(text, add_special_tokens=False)
                windows = [tokens[i:i + 440] for i in range(0, len(tokens), 400)] or [[]]
                passages = [prefix + model.tokenizer.decode(w) for w in windows]
                vectors = model.encode(passages, normalize_embeddings=True, show_progress_bar=False)
                vector = vectors.mean(axis=0)
                vector = vector / max(float((vector * vector).sum() ** 0.5), 1e-12)
                values = vector.tolist()
                db.execute("INSERT OR REPLACE INTO vectors VALUES(?,?)", (key, json.dumps(values)))
                output.append(values)
        return output

    def embed_documents(self, texts):
        return self._encode(texts, "passage: ")

    def embed_query(self, text):
        return self._encode([text], "query: ")[0]
