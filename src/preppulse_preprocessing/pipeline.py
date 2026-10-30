"""
End-to-end Stage 2 + Stage 3 pipeline for one document or a whole patient/cohort.

Flow per document:
  stage_1_raw_ocr
     -> chunk_document            (section-aware chunks, written to document_chunks)
     -> extract_document          (LLM facts, terminology-coded)
     -> ground_entities           (verify + bbox + fail-closed review_queue)
     -> Stage2StructuredEntities  (validated, written to patient_documents)
     -> to_fhir_bundle            (FHIR R4, written to patient_documents)

The store, provider, and settings are injected so the same pipeline runs against
the real MongoStore (post-merge) or this repo's adapter, with Ollama or mock.
"""
from __future__ import annotations

from typing import Any

from preppulse_preprocessing.chunk import chunk_document
from preppulse_preprocessing.config import Settings, load_settings
from preppulse_preprocessing.extract import extract_document
from preppulse_preprocessing.fhir import to_fhir_bundle
from preppulse_preprocessing.ground import ground_entities
from preppulse_preprocessing.models import Stage2StructuredEntities
from preppulse_preprocessing.providers import get_llm_provider
from preppulse_preprocessing.providers.base import LLMClient
from preppulse_preprocessing.store import Store


class Pipeline:
    def __init__(self, store: Store, llm: LLMClient, settings: Settings) -> None:
        self.store = store
        self.llm = llm
        self.settings = settings

    @classmethod
    def build(cls, store: Store, settings: Settings | None = None) -> Pipeline:
        settings = settings or load_settings()
        llm = get_llm_provider(settings.llm)
        return cls(store=store, llm=llm, settings=settings)

    # ---- single document ----
    def process_document(self, doc: dict[str, Any], persist: bool = True) -> dict[str, Any]:
        document_id = doc["document_id"]
        patient_id = doc["patient_id"]

        # 1. chunk
        chunks = chunk_document(doc)
        if persist:
            self.store.clear_chunks(document_id)
            for ch in chunks:
                self.store.write_chunk(ch)

        # 2. extract
        raw_entities = extract_document(chunks, self.llm)

        # 3. ground + verify (fail-closed)
        grounded = ground_entities(raw_entities, doc, self.settings.grounding)

        # 4. assemble + validate Stage 2
        stage2 = Stage2StructuredEntities(
            compiled_by=self.settings.compiled_by,
            labs=grounded["labs"],
            medications=grounded["medications"],
            diagnoses=grounded["diagnoses"],
            vitals=grounded["vitals"],
            advice=grounded["advice"],
            review_queue=grounded["review_queue"],
            patient=doc.get("stage_2_structured_entities", {}).get("patient") if doc.get("stage_2_structured_entities") else None,
        )
        stage2_dict = stage2.model_dump()

        # 5. FHIR (Stage 3)
        fhir_bundle = to_fhir_bundle(stage2_dict, patient_id)

        if persist:
            self.store.write_stage2(document_id, stage2_dict)
            self.store.write_stage3(document_id, fhir_bundle)

        return {
            "document_id": document_id,
            "chunks": len(chunks),
            "labs": len(stage2_dict["labs"]),
            "medications": len(stage2_dict["medications"]),
            "diagnoses": len(stage2_dict["diagnoses"]),
            "review_queue": len(stage2_dict["review_queue"]),
            "fhir_entries": len(fhir_bundle["entry"]),
            "stage_2": stage2_dict,
            "stage_3": fhir_bundle,
        }

    # ---- batch ----
    def process_patient(self, patient_id: str, persist: bool = True) -> list[dict[str, Any]]:
        docs = self.store.list_documents(patient_id)
        return [self.process_document(d, persist=persist) for d in docs]

    def process_all(self, persist: bool = True, limit: int = 0) -> list[dict[str, Any]]:
        docs = self.store.list_documents()
        if limit > 0:
            docs = docs[:limit]
        return [self.process_document(d, persist=persist) for d in docs]
