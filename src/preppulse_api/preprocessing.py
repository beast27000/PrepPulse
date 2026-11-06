"""Resumable Stage 2/3 integration with immutable result versions."""
import copy
import hashlib
import json
import os

from preppulse_api.store import now
from preppulse_preprocessing.config import load_settings
from preppulse_preprocessing.fhir import to_fhir_bundle
from preppulse_preprocessing.ground import ground_entities
from preppulse_preprocessing.pipeline import Pipeline

VERSION = "grounded-fhir-r4-v2"
RENDER_VERSION = "r4-4.0.1-verified-catalog-v4"


def refresh_fhir(store, doc, settings, catalog=None):
    """Revalidate cached facts and registry demographics without another paid extraction."""
    previous = doc.get("preprocessing", {})
    entities = copy.deepcopy(doc.get("stage_2_structured_entities") or {})
    demographics = {key: (store.patient(doc["patient_id"]) or {}).get(key) for key in ("name", "dob", "sex")}
    if previous.get("render_version") == RENDER_VERSION and entities.get("patient") == demographics:
        return previous.get("review_items", 0)
    grounded = ground_entities(entities, doc, settings.grounding)
    entities.update(grounded)
    # Preserve prior quarantined facts; they must not vanish on a render migration.
    prior_review = (doc.get("stage_2_structured_entities") or {}).get("review_queue", [])
    unique = {json.dumps(item, sort_keys=True, default=str): item
              for item in prior_review + grounded["review_queue"]}
    entities["review_queue"] = list(unique.values())
    entities["patient"] = demographics
    from preppulse_api.verified_measurements import reconcile
    if catalog is None:
        from preppulse_api.evidence_catalog import build_catalog
        catalog = build_catalog(store, doc["patient_id"])
    entities = reconcile(doc, entities, catalog)
    bundle = to_fhir_bundle(entities, doc["patient_id"], doc["document_id"])
    fingerprint = hashlib.sha256((previous.get("fingerprint", "") + RENDER_VERSION
                                  + json.dumps(bundle, sort_keys=True)).encode()).hexdigest()
    store.db.fhir_versions.update_one({"document_id": doc["document_id"], "fingerprint": fingerprint},
        {"$setOnInsert": {"document_id": doc["document_id"], "patient_id": doc["patient_id"],
                          "fingerprint": fingerprint, "stage_2": entities, "stage_3": bundle,
                          "render_version": RENDER_VERSION, "generated_at": now()}}, upsert=True)
    store.db.patient_documents.update_one({"document_id": doc["document_id"]}, {"$set": {
        "stage_2_structured_entities": entities, "stage_3_fhir_output": bundle,
        "preprocessing.render_version": RENDER_VERSION,
        "preprocessing.review_items": len(entities["review_queue"])}})
    return len(entities["review_queue"])


def process_structured(store, mongo, patient_id, progress=None):
    settings = load_settings()
    pipeline = Pipeline.build(mongo, settings)
    from preppulse_api.evidence_catalog import build_catalog
    from preppulse_api.verified_measurements import reconcile
    catalog = build_catalog(store, patient_id)
    counts = {"complete": 0, "failed": 0, "review_items": 0}
    for doc in mongo.get_patient_documents(patient_id):
        from preppulse_api.operations import assert_available
        assert_available(store, patient_id)
        store.db.jobs.update_many({"patient_id": patient_id, "status": "running"},
            {"$set": {"current_file": doc.get("document_name", doc.get("filename", doc["document_id"]))}})
        identity = {"stage1": doc.get("stage_1_raw_ocr"), "provider": settings.llm.provider,
                    "model": os.getenv("SARVAM_MODEL") if settings.llm.provider == "sarvam" else
                    os.getenv("GEMINI_MODEL") if settings.llm.provider == "gemini" else os.getenv("LOCAL_CHAT_MODEL"),
                    "version": VERSION}
        if settings.llm.provider in {"azure", "auto"}:
            from preppulse_api.provider_settings import routing
            identity["cloud_configuration"] = {
                "azure_deployment": os.getenv("AZURE_OPENAI_DEPLOYMENT"),
                "azure_endpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),
                "order": os.getenv("PREPPULSE_AI_PROVIDER_ORDER"),
                "sarvam_model": os.getenv("SARVAM_MODEL"), "mode": routing(),
            }
        fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()
        previous = doc.get("preprocessing", {})
        if previous.get("fingerprint") == fingerprint and previous.get("status") == "complete":
            counts["complete"] += 1
            counts["review_items"] += refresh_fhir(store, doc, settings, catalog)
            continue
        if progress:
            progress("structured_extraction")
        try:
            result = pipeline.process_document(doc, persist=False)
            result["stage_2"]["patient"] = {key: (store.patient(patient_id) or {}).get(key)
                                           for key in ("name", "dob", "sex")}
            result["stage_2"] = reconcile(doc, result["stage_2"], catalog)
            result["stage_3"] = to_fhir_bundle(result["stage_2"], patient_id, doc["document_id"])
            version = {"document_id": doc["document_id"], "patient_id": patient_id,
                       "fingerprint": fingerprint, "stage_2": result["stage_2"],
                       "stage_3": result["stage_3"], "generated_at": now()}
            store.db.fhir_versions.update_one({"document_id": doc["document_id"], "fingerprint": fingerprint},
                                             {"$setOnInsert": version}, upsert=True)
            store.db.patient_documents.update_one({"document_id": doc["document_id"]}, {"$set": {
                "stage_2_structured_entities": result["stage_2"], "stage_3_fhir_output": result["stage_3"],
                "preprocessing": {"status": "complete", "fingerprint": fingerprint, "version": VERSION,
                                  "render_version": RENDER_VERSION,
                                  "completed_at": now(), "review_items": result["review_queue"]},
                "status": "stage_3_complete"}})
            counts["complete"] += 1
            counts["review_items"] += result["review_queue"]
            if progress:
                progress("fhir_validation")
        except Exception as exc:
            counts["failed"] += 1
            details = ({"path": list(exc.absolute_path), "rule": exc.validator}
                       if hasattr(exc, "absolute_path") else
                       {"fields": [list(error["loc"]) for error in exc.errors(include_input=False)]}
                       if hasattr(exc, "errors") else {})
            store.db.patient_documents.update_one({"document_id": doc["document_id"]}, {"$set": {
                "preprocessing": {"status": "failed", "error_type": type(exc).__name__,
                                  "details": details,
                                  "fingerprint": fingerprint, "failed_at": now()}}})
            if os.getenv("PREPPULSE_STRICT_AI") == "1":
                raise
    return counts
