"""Patient maintenance and content-free provider diagnostics."""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from fastapi import Depends, HTTPException
from pydantic import BaseModel

from preppulse_api.config import PRIVATE_ROOT
from preppulse_api.store import now


def assert_available(store, patient_id):
    patient = store.patient(patient_id)
    if not patient or patient.get("maintenance"):
        raise HTTPException(409, "Patient cleanup is in progress. Retry after cleanup completes.")


def assert_not_deleting(store, patient_id):
    patient = store.patient(patient_id) or {}
    if patient.get("maintenance") or store.db.patient_deletions.find_one({"patient_id": patient_id}) or store.db.deletion_receipts.find_one({"patient_id": patient_id}):
        raise HTTPException(409, "Patient cleanup is in progress")


def job_status(store, job):
    if not job:
        return None
    job = dict(job)
    if job.get("status") == "queued":
        job["stage"] = "Waiting for processing"
        job["queue_position"] = 1 + store.db.worker_tasks.count_documents({
            "function": {"$in": ["_job", "_chat_worker"]},
            "status": {"$in": ["queued", "running"]},
            "created_at": {"$lt": job["created_at"]},
        }) if os.getenv("PREPPULSE_DURABLE_JOBS") == "1" else None
    return job


def linked_queries(store, pid):
    visits = [r["visit_id"] for r in store.db.visits.find({"patient_id": pid})]
    plans = [r["pathway_id"] for r in store.db.pathways.find({"patient_id": pid})]
    sessions = [r["session_id"] for r in store.db.chat_sessions.find({"patient_id": pid})]
    jobs = [r["job_id"] for r in store.db.jobs.find({"patient_id": pid})]
    docs = [r["record_id"] for r in store.db.workspace_documents.find({"patient_id": pid})]
    ids = [pid, *visits, *plans, *sessions, *jobs]
    queries = {name: {"patient_id": pid} for name in (
        "patients", "patient_aliases", "patient_access", "caregiver_access", "workspace_documents",
        "workspace_files", "patient_documents", "document_chunks", "fhir_versions", "briefs",
        "analysis_checkpoints", "appointments", "visits", "pathways", "care_segment_cache",
        "chat_sessions", "chat_artifacts", "chat_turns", "jobs", "audit_events",
    )}
    queries["document_chunks"] = {"$or": [{"patient_id": pid}, {"document_id": {"$in": docs}}]}
    for name in ("review_decisions", "pathway_items", "care_drafts", "care_visit_checks"):
        queries[name] = {"$or": [{"patient_id": pid}, {"visit_id": {"$in": visits}}]}
    for name in ("care_translations", "care_reports", "care_notes"):
        queries[name] = {"$or": [{"patient_id": pid}, {"pathway_id": {"$in": plans}}]}
    queries["chat_messages"] = {"session_id": {"$in": sessions}}
    queries["care_language_cache"] = {"identity": {"$in": ids}}
    queries["worker_tasks"] = {"args": {"$in": ids}}
    return queries


def private_file(path, pid):
    root = PRIVATE_ROOT.resolve() / pid
    target = Path(path).resolve()
    if target != root and target.is_relative_to(root):
        target.unlink(missing_ok=True)


def fence(store, pid):
    # Mark before checking workers so newly claimed jobs cannot start writing.
    store.db.patients.update_one({"patient_id": pid}, {"$set": {"maintenance": True}})
    queries = linked_queries(store, pid)
    store.db.worker_tasks.update_many({**queries["worker_tasks"], "status": "queued"},
        {"$set": {"status": "cancelled", "finished_at": now()}})
    running = store.db.worker_tasks.count_documents({**queries["worker_tasks"], "status": "running"})
    running += store.db.jobs.count_documents({"patient_id": pid, "status": "running"})
    running += store.db.chat_turns.count_documents({"patient_id": pid, "status": "running"})
    running += store.db.visits.count_documents({"patient_id": pid, "status": "finalizing"})
    if running:
        raise HTTPException(409, "Processing is stopping for cleanup. Wait for the current step, then retry deletion.")
    return queries


class DeleteIn(BaseModel):
    confirm_id: str


def local_probe():
    import httpx
    endpoint = os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:1234/v1").rstrip("/")
    with httpx.Client(timeout=15, trust_env=False) as connection:
        models = connection.get(endpoint + "/models")
        models.raise_for_status()
        model = os.getenv("LOCAL_CHAT_MODEL", "qwen/qwen3-4b-2507")
        response = connection.post(endpoint + "/chat/completions", json={"model": model,
            "messages": [{"role": "user", "content": "Reply with OK. Connectivity test; no patient data."}], "max_tokens": 32})
        response.raise_for_status()
        if not (response.json().get("choices") or [{}])[0].get("message", {}).get("content"):
            raise ValueError("No inference response")


def install(app, db, admin, clinician, patient_access, queue_brief_job):
    # Both staff roles can inspect/test; changing shared routing remains admin-only.
    from preppulse_api.app import user

    def operator(current=Depends(user)):
        if current["role"] not in {"admin", "doctor"}:
            raise HTTPException(403, "Staff access required")
        return current

    @app.get("/api/ai/status")
    def status(current=Depends(operator)):
        cloud = os.getenv("PREPPULSE_ENV") == "production"
        if cloud:
            from preppulse_api.provider_settings import routing
        return {"mode": routing() if cloud else "local", "cloud": cloud}

    @app.post("/api/ai/test")
    def test(current=Depends(operator), store=Depends(db)):
        cloud = os.getenv("PREPPULSE_ENV") == "production"
        if cloud:
            from preppulse_rag.cloud_provider import RoutedChatModel
            from preppulse_rag.runtime import sarvam_accounts
        results = []
        for provider in (["sarvam", "azure"] if cloud else ["local"]):
            configured = provider == "local" or (bool(sarvam_accounts()) if provider == "sarvam"
                else bool(os.getenv("AZURE_OPENAI_API_KEY") and os.getenv("AZURE_OPENAI_ENDPOINT")))
            started = time.monotonic()
            state, detail = "not_configured", "Provider is not configured"
            if configured:
                try:
                    if cloud:
                        RoutedChatModel(provider=provider, max_tokens=16, request_timeout=15, transient_retries=0).invoke("Reply with OK. Connectivity test; no patient data.")
                    else:
                        local_probe()
                    state, detail = "healthy", "Inference request succeeded"
                except Exception as exc:
                    state = "unavailable"
                    # Provider errors are intentionally sanitized; never return raw SDK URLs or secrets.
                    message = str(exc)
                    detail = next((f"HTTP {code}" for code in (401, 402, 403, 404, 429, 500, 502, 503, 504)
                                   if f"HTTP {code}" in message), "Request failed, timed out, or provider is cooling down")
            results.append({"provider": provider, "status": state, "detail": detail,
                            "elapsed_seconds": round(time.monotonic() - started, 2)})
        store.audit(current, "provider_health_test", extra={"results": results})
        return {"checked_at": now(), "providers": results}

    @app.post("/api/admin/patients/{patient_id}/processing/retry")
    def retry(patient_id: str, current=Depends(admin), store=Depends(db)):
        patient_access(patient_id, current, store)
        return queue_brief_job(store, patient_id)

    @app.get("/api/admin/patients/{patient_id}/deletion-preview")
    def preview(patient_id: str, current=Depends(admin), store=Depends(db)):
        if not store.patient(patient_id):
            raise HTTPException(404, "Patient not found")
        return {"counts": {name: store.db[name].count_documents(query)
                           for name, query in linked_queries(store, patient_id).items()}}

    @app.delete("/api/admin/patients/{patient_id}")
    def delete_patient(patient_id: str, body: DeleteIn, current=Depends(admin), store=Depends(db)):
        if body.confirm_id != patient_id:
            raise HTTPException(400, "Type the permanent PrepPulse ID to confirm")
        receipt = store.db.deletion_receipts.find_one({"patient_id": patient_id, "complete": True})
        if receipt:
            return {"deleted": True}
        if not store.patient(patient_id):
            raise HTTPException(404, "Patient not found")
        queries = fence(store, patient_id)
        # Persist the manifest first: a failed cleanup can resume after some linked rows are gone.
        operation = store.db.patient_deletions.find_one({"patient_id": patient_id})
        if operation:
            queries = operation["queries"]
        else:
            store.db.patient_deletions.insert_one({"patient_id": patient_id, "queries": queries})
        counts = {name: store.db[name].count_documents(query) for name, query in queries.items()}
        target = (PRIVATE_ROOT.resolve() / patient_id).resolve()
        if target.parent != PRIVATE_ROOT.resolve() or not patient_id.startswith("PRP-"):
            raise HTTPException(400, "Invalid private storage target")
        if target.exists():
            shutil.rmtree(target)
        # Keep the locked patient row until everything else has been removed.
        for name, query in queries.items():
            if name != "patients":
                store.db[name].delete_many(query)
        store.db.patients.delete_one({"patient_id": patient_id})
        store.db.deletion_receipts.update_one({"patient_id": patient_id}, {"$set": {
            "complete": True, "actor": current["user_id"], "at": now(), "counts": counts}}, upsert=True)
        store.db.patient_deletions.delete_one({"patient_id": patient_id})
        return {"deleted": True, "counts": counts}

    @app.delete("/api/admin/patients/{patient_id}/documents/{record_id}")
    def delete_record(patient_id: str, record_id: str, body: DeleteIn,
                      current=Depends(admin), store=Depends(db)):
        if body.confirm_id != record_id:
            raise HTTPException(400, "Record confirmation does not match")
        rec = store.db.workspace_documents.find_one({"patient_id": patient_id, "record_id": record_id})
        if not rec:
            return {"deleted": True}
        if rec.get("document_type") == "care_pathway":
            raise HTTPException(409, "Signed care plans are protected. Delete the entire patient to remove signed history.")
        fence(store, patient_id)
        try:
            private_file(rec["source_path"], patient_id)
            for name in ("patient_documents", "document_chunks", "fhir_versions"):
                store.db[name].delete_many({"document_id": record_id})
            store.db.workspace_files.delete_many({"patient_id": patient_id, "file_id": rec.get("file_id", "")})
            store.db.workspace_documents.delete_one({"record_id": record_id})
            # Invalidate all mutable derived output: it may quote the removed source.
            sessions = [r["session_id"] for r in store.db.chat_sessions.find({"patient_id": patient_id})]
            store.db.chat_messages.delete_many({"session_id": {"$in": sessions}})
            for name in ("briefs", "analysis_checkpoints", "chat_artifacts", "chat_turns", "chat_sessions"):
                store.db[name].delete_many({"patient_id": patient_id})
            visits = [r["visit_id"] for r in store.db.visits.find({"patient_id": patient_id, "status": "active"})]
            for name in ("care_drafts", "care_visit_checks", "review_decisions", "pathway_items"):
                store.db[name].delete_many({"visit_id": {"$in": visits}})
            store.db.care_language_cache.delete_many({"identity": {"$in": [patient_id, *visits]}})
            store.db.patients.update_one({"patient_id": patient_id}, {"$set": {"analysis_required": True}})
            store.audit(current, "source_record_deleted", patient_id, {"record_id": record_id})
            return {"deleted": True, "analysis_required": True}
        finally:
            store.db.patients.update_one({"patient_id": patient_id}, {"$unset": {"maintenance": ""}})
