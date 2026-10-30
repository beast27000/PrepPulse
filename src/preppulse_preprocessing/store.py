"""
Thin MongoDB adapter for the preprocessing layer.

This is a SEPARATE repo (per AGENTS.md: build additions outside the frozen OCR
base, merge later), so it cannot import the owners' `preppulse_db` package. To
keep a future merge trivial, this adapter speaks the EXACT same collections,
document_id keys, and field shapes as their `MongoStore`:

  - reads  stage_1_raw_ocr   from  patient_documents
  - writes document_chunks   to    document_chunks
  - writes stage_2 entities  to    patient_documents.stage_2_structured_entities
  - writes stage_3 fhir      to    patient_documents.stage_3_fhir_output

Method names mirror theirs (get_document, list_documents, write_chunk,
write_stage2, write_stage3) so at merge time this file can be deleted and the
pipeline pointed at their MongoStore with no other change.
"""
from __future__ import annotations

from typing import Any

from pymongo import ASCENDING, MongoClient

from preppulse_preprocessing.config import MongoConfig

DOCS = "patient_documents"
CHUNKS = "document_chunks"


class Store:
    def __init__(self, cfg: MongoConfig) -> None:
        self.cfg = cfg
        self._client: MongoClient | None = None
        self._db = None

    def connect(self) -> Store:
        if self._client is None:
            self._client = MongoClient(self.cfg.uri, serverSelectionTimeoutMS=self.cfg.server_timeout_ms)
            self._db = self._client[self.cfg.db_name]
            self._db[CHUNKS].create_index([("chunk_id", ASCENDING)], unique=True)
            self._db[CHUNKS].create_index([("document_id", ASCENDING)])
        return self

    @property
    def db(self):
        if self._db is None:
            self.connect()
        return self._db

    # ---- reads (Stage 1 input) ----
    def get_document(self, document_id: str) -> dict[str, Any] | None:
        return self.db[DOCS].find_one({"document_id": document_id}, {"_id": 0})

    def list_documents(self, patient_id: str | None = None) -> list[dict[str, Any]]:
        query = {"patient_id": patient_id} if patient_id else {}
        return list(self.db[DOCS].find(query, {"_id": 0}).sort("visit_date", ASCENDING))

    def count_documents(self, patient_id: str | None = None) -> int:
        query = {"patient_id": patient_id} if patient_id else {}
        return self.db[DOCS].count_documents(query)

    # ---- chunk writes (Stage 2 intermediate) ----
    def write_chunk(self, chunk: dict[str, Any]) -> str:
        chunk_id = chunk["chunk_id"]
        self.db[CHUNKS].update_one({"chunk_id": chunk_id}, {"$set": chunk}, upsert=True)
        return chunk_id

    def get_chunks(self, document_id: str) -> list[dict[str, Any]]:
        return list(self.db[CHUNKS].find({"document_id": document_id}, {"_id": 0}))

    def clear_chunks(self, document_id: str) -> int:
        return self.db[CHUNKS].delete_many({"document_id": document_id}).deleted_count

    # ---- stage 2 / 3 writes (same shape as owners' MongoStore) ----
    def write_stage2(self, document_id: str, entities: dict[str, Any]) -> bool:
        res = self.db[DOCS].update_one(
            {"document_id": document_id},
            {"$set": {"stage_2_structured_entities": entities, "status": "stage_2_complete"}},
        )
        return res.matched_count > 0

    def write_stage3(self, document_id: str, fhir_bundle: dict[str, Any]) -> bool:
        res = self.db[DOCS].update_one(
            {"document_id": document_id},
            {"$set": {"stage_3_fhir_output": fhir_bundle, "status": "stage_3_complete"}},
        )
        return res.matched_count > 0

    def clear_database(self) -> None:
        self.db[DOCS].drop()
        self.db[CHUNKS].drop()

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
            self._db = None
