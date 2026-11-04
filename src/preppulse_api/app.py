from __future__ import annotations

import logging
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from threading import Lock
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pwdlib import PasswordHash
from pydantic import BaseModel, Field, ValidationError
from pymongo.errors import DuplicateKeyError
from starlette.middleware.sessions import SessionMiddleware

from preppulse_api.administration import register_administration_routes
from preppulse_api.care import (
    archive_pdf,
    ensure_draft,
    local_day,
    register_care_routes,
    translate_signed_job,
)
from preppulse_api.chat_service import run_chat_turn
from preppulse_api.clinical import answer_chat, locate_citation, process_patient, render_page
from preppulse_api.config import (
    PRIVATE_ROOT,
    SESSION_SECRET,
    STT_MODEL,
    TTS_MODEL_PATH,
)
from preppulse_api.folder_import import save_patient_folder
from preppulse_api.store import WorkspaceStore, new_id, now
from preppulse_api.voice import ready as tts_ready
from preppulse_api.voice import synthesize

if len(SESSION_SECRET) < 32:
    raise RuntimeError("Set PREPPULSE_SESSION_SECRET to a random value of at least 32 characters")

app = FastAPI(title="PrepPulse local workspace API")
workers = ThreadPoolExecutor(max_workers=2)
active_chat_turns: set[str] = set()
active_brief_jobs: set[str] = set()
password_hash = PasswordHash.recommended()
_stt_model = None
_schema_ready = False
_schema_lock = Lock()
_request_store = None


def db() -> WorkspaceStore:
    global _schema_ready, _request_store
    # MongoClient is thread-safe. Share its pool instead of creating monitoring
    # sockets for every poll/login request (important for Atlas free limits).
    with _schema_lock:
        if _request_store is None:
            _request_store = WorkspaceStore()
        if not _schema_ready:
            _request_store.indexes()
            _schema_ready = True
    yield _request_store


@app.on_event("shutdown")
def close_request_store():
    global _request_store, _schema_ready
    if _request_store is not None:
        _request_store.client.close()
        _request_store = None
    _schema_ready = False


def user(request: Request, store: WorkspaceStore = Depends(db)) -> dict:
    uid = request.session.get("user_id")
    found = (
        store.db.users.find_one(
            {"user_id": uid, "disabled": {"$ne": True}}, {"_id": 0, "password_hash": 0}
        )
        if uid
        else None
    )
    if not found:
        raise HTTPException(401, "Sign in required")
    if not found.get("account_id"):
        found = store.account_identity(found)
    return found


def admin(current: dict = Depends(user)) -> dict:
    if current["role"] != "admin":
        raise HTTPException(403, "Admin access required")
    return current


def clinician(current: dict = Depends(user)) -> dict:
    if current["role"] != "doctor":
        raise HTTPException(403, "Doctor access required")
    return current


def patient_access(patient_id: str, current: dict, store: WorkspaceStore) -> dict:
    if current["role"] == "caregiver":
        raise HTTPException(403, "Use the caregiver portal for signed instructions")
    patient = store.patient(patient_id)
    if not patient:
        raise HTTPException(404, "Patient not found")
    if not store.allowed(current, patient_id):
        raise HTTPException(403, "Patient access denied")
    return patient


@app.middleware("http")
async def csrf(request: Request, call_next):
    if (
        request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and request.url.path != "/api/auth/login"
    ):
        token = request.session.get("csrf")
        if not token or not secrets.compare_digest(token, request.headers.get("X-CSRF-Token", "")):
            return Response("CSRF token required", status_code=403)
    return await call_next(request)


# Starlette applies the last-added middleware first. Sessions must wrap CSRF.
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie=os.getenv("PREPPULSE_SESSION_COOKIE", "preppulse_session"),
    same_site="strict",
    https_only=False,
    max_age=60 * 60 * 8,
)


class Login(BaseModel):
    username: str
    password: str


@app.post("/api/auth/login")
def login(body: Login, request: Request, store: WorkspaceStore = Depends(db)):
    found = store.db.users.find_one({"username": body.username.lower().strip()})
    valid = password_hash.verify(body.password, found["password_hash"]) if found else False
    if not valid or found.get("disabled"):
        raise HTTPException(401, "Invalid credentials")
    request.session.clear()
    request.session["user_id"] = found["user_id"]
    request.session["csrf"] = secrets.token_urlsafe(24)
    store.audit(found, "login")
    return {
        "user_id": found["user_id"],
        "name": found["name"],
        "username": found["username"],
        "role": found["role"],
        "csrf": request.session["csrf"],
    }


@app.get("/api/auth/me")
def me(request: Request, current: dict = Depends(user)):
    return {**current, "csrf": request.session["csrf"]}


@app.post("/api/auth/logout")
def logout(request: Request, current: dict = Depends(user), store: WorkspaceStore = Depends(db)):
    store.audit(current, "logout")
    request.session.clear()
    return {"ok": True}


class AccountIn(BaseModel):
    name: str = Field(min_length=2)
    username: str = Field(min_length=3)
    password: str = Field(min_length=12)
    role: Literal["doctor", "admin", "caregiver"] = "doctor"
    caregiver_type: Literal["family", "professional"] | None = None


@app.get("/api/admin/accounts")
def accounts(q: str = "", _: dict = Depends(admin), store: WorkspaceStore = Depends(db)):
    rows = [
        store.account_identity(a) for a in store.db.users.find({}, {"_id": 0, "password_hash": 0})
    ]
    query = q.strip().casefold()
    return [
        a
        for a in rows
        if not query
        or any(
            query in str(a.get(k, "")).casefold()
            for k in ("name", "username", "user_id", "account_id", "account_aliases")
        )
    ]


@app.post("/api/admin/accounts")
def add_account(
    body: AccountIn, current: dict = Depends(admin), store: WorkspaceStore = Depends(db)
):
    if body.role == "caregiver" and not body.caregiver_type:
        raise HTTPException(400, "Choose family or in-hospital caregiver explicitly")
    account = {
        "user_id": new_id("USR"),
        "name": body.name.strip(),
        "username": body.username.lower().strip(),
        "role": body.role,
        **(
            {"caregiver_type": body.caregiver_type, "availability": "free"}
            if body.role == "caregiver"
            else {}
        ),
        "password_hash": password_hash.hash(body.password),
        "disabled": False,
        "created_at": now(),
    }
    try:
        store.db.users.insert_one(account)
    except DuplicateKeyError:
        raise HTTPException(409, "Username already exists") from None
    store.audit(current, "account_created", extra={"user_id": account["user_id"]})
    return store.account_identity(account)


@app.patch("/api/admin/accounts/{user_id}/disable")
def disable_account(
    user_id: str, current: dict = Depends(admin), store: WorkspaceStore = Depends(db)
):
    if user_id == current["user_id"]:
        raise HTTPException(400, "Cannot disable own account")
    if not store.db.users.update_one(
        {"user_id": user_id}, {"$set": {"disabled": True}}
    ).matched_count:
        raise HTTPException(404, "Account not found")
    store.audit(current, "account_disabled", extra={"user_id": user_id})
    store.account_identity(
        store.db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    )
    return {"ok": True}


class PatientIn(BaseModel):
    name: str = Field(min_length=2)
    dob: str | None = None
    age: int | None = Field(default=None, ge=0, le=130)
    sex: Literal["Female", "Male", "Other"] | None = None
    doctor_id: str


@app.get("/api/patients")
def patients(q: str = "", current: dict = Depends(user), store: WorkspaceStore = Depends(db)):
    return store.search_patients(current, q)


@app.get("/api/patients/{patient_id}")
def patient(patient_id: str, current: dict = Depends(user), store: WorkspaceStore = Depends(db)):
    found = patient_access(patient_id, current, store)
    store.audit(current, "patient_opened", patient_id)
    return {k: v for k, v in found.items() if k not in {"_id", "source_root"}}


@app.get("/api/admin/patients/{patient_id}/overview")
def admin_patient_overview(
    patient_id: str, current: dict = Depends(admin), store: WorkspaceStore = Depends(db)
):
    found = patient_access(patient_id, current, store)
    assigned = list(store.db.patient_access.find({"patient_id": patient_id}, {"_id": 0}))
    doctors = []
    for link in assigned:
        doctor = store.db.users.find_one(
            {"user_id": link["doctor_id"]}, {"_id": 0, "password_hash": 0}
        )
        if doctor:
            doctors.append({"user_id": doctor["user_id"], "name": doctor["name"]})
    documents = list(
        store.db.workspace_documents.find(
            {"patient_id": patient_id}, {"_id": 0, "source_path": 0}
        ).sort("visit_date", -1)
    )
    visits = list(
        store.db.visits.find({"patient_id": patient_id}, {"_id": 0, "doctor_notes": 0}).sort(
            "started_at", -1
        )
    )
    appointments = list(
        store.db.appointments.find({"patient_id": patient_id}, {"_id": 0}).sort("date", -1)
    )
    job = store.db.jobs.find_one({"patient_id": patient_id}, {"_id": 0}, sort=[("created_at", -1)])
    store.audit(current, "admin_patient_overview", patient_id)
    return {
        "patient": {k: v for k, v in found.items() if k != "source_root"},
        "doctors": doctors,
        "documents": documents,
        "visits": visits,
        "appointments": appointments,
        "stored_files": store.db.workspace_files.count_documents({"patient_id": patient_id}),
        "latest_job": job,
    }


@app.post("/api/patients")
def register_patient(
    body: PatientIn, current: dict = Depends(admin), store: WorkspaceStore = Depends(db)
):
    doctor = store.db.users.find_one(
        {"user_id": body.doctor_id, "role": "doctor", "disabled": False}
    )
    if not doctor:
        raise HTTPException(400, "Active doctor required")
    if body.dob:
        try:
            date.fromisoformat(body.dob)
        except ValueError:
            raise HTTPException(400, "Date of birth must be YYYY-MM-DD") from None
    found = {
        "patient_id": new_id("PRP"),
        "name": body.name.strip(),
        "name_search": body.name.strip().lower(),
        "dob": body.dob,
        "age": body.age,
        "age_recorded_on": local_day().isoformat(),
        "sex": body.sex,
        "external_aliases": [],
        "created_at": now(),
    }
    store.db.patients.insert_one(found)
    store.db.patient_access.insert_one(
        {"patient_id": found["patient_id"], "doctor_id": body.doctor_id}
    )
    store.audit(current, "patient_registered", found["patient_id"])
    return {k: v for k, v in found.items() if k != "_id"}


@app.post("/api/admin/import-folder")
async def import_folder(
    doctor_id: str = Form(...),
    paths: list[str] = Form(...),
    files: list[UploadFile] = File(...),
    patient_id: str | None = Form(None),
    name: str | None = Form(None),
    dob: str | None = Form(None),
    age: int | None = Form(None),
    sex: str | None = Form(None),
    current: dict = Depends(admin),
    store: WorkspaceStore = Depends(db),
):
    if not store.db.users.find_one({"user_id": doctor_id, "role": "doctor", "disabled": False}):
        raise HTTPException(400, "Active doctor required")
    store.indexes()
    try:
        details = PatientIn(
            name=name or "Folder patient",
            dob=dob or None,
            age=age,
            sex=sex or None,
            doctor_id=doctor_id,
        )
    except ValidationError:
        raise HTTPException(400, "Check patient name, age and sex") from None
    if details.dob:
        try:
            if date.fromisoformat(details.dob) > local_day():
                raise ValueError()
        except ValueError:
            raise HTTPException(400, "Invalid date of birth") from None
    if patient_id:
        patient_access(patient_id, current, store)
    result = await save_patient_folder(
        store,
        doctor_id,
        files,
        paths,
        patient_id=patient_id,
        details={
            k: v
            for k, v in {"name": name, "dob": dob, "age": age, "sex": sex}.items()
            if v is not None and v != ""
        },
    )
    if result["documents_queued"]:
        result["job"] = queue_brief_job(store, result["patient_id"])
    store.audit(
        current,
        "folder_imported",
        result["patient_id"],
        {"files_saved": result["files_saved"], "documents_queued": result["documents_queued"]},
    )
    return result


@app.patch("/api/patients/{patient_id}/demographics")
def update_demographics(
    patient_id: str,
    body: PatientIn,
    current: dict = Depends(admin),
    store: WorkspaceStore = Depends(db),
):
    patient_access(patient_id, current, store)
    if not store.db.users.find_one(
        {"user_id": body.doctor_id, "role": "doctor", "disabled": False}
    ):
        raise HTTPException(400, "Active doctor required")
    if body.dob:
        try:
            if date.fromisoformat(body.dob) > local_day():
                raise ValueError()
        except ValueError:
            raise HTTPException(400, "Invalid date of birth") from None
    changes = {
        "name": body.name.strip(),
        "name_search": body.name.strip().lower(),
        "dob": body.dob,
        "age": body.age,
        "sex": body.sex,
        "age_recorded_on": local_day().isoformat(),
    }
    store.db.patients.update_one({"patient_id": patient_id}, {"$set": changes})
    store.db.patient_access.update_one(
        {"patient_id": patient_id, "doctor_id": body.doctor_id},
        {"$setOnInsert": {"patient_id": patient_id, "doctor_id": body.doctor_id}},
        upsert=True,
    )
    store.audit(current, "demographics_updated", patient_id)
    return store.patient(patient_id)


@app.post("/api/patients/{patient_id}/folder")
async def append_folder(
    patient_id: str,
    paths: list[str] = Form(...),
    files: list[UploadFile] = File(...),
    current: dict = Depends(user),
    store: WorkspaceStore = Depends(db),
):
    patient_access(patient_id, current, store)
    if current["role"] == "doctor":
        doctor_id = current["user_id"]
    else:
        assignment = store.db.patient_access.find_one({"patient_id": patient_id})
        if not assignment:
            raise HTTPException(400, "Assign a doctor before uploading")
        doctor_id = assignment["doctor_id"]
    result = await save_patient_folder(store, doctor_id, files, paths, patient_id=patient_id)
    if result["documents_queued"]:
        result["job"] = queue_brief_job(store, patient_id)
    store.audit(current, "folder_appended", patient_id, {"files_saved": result["files_saved"]})
    return result


@app.post("/api/patients/{patient_id}/assign/{doctor_id}")
def assign_patient(
    patient_id: str,
    doctor_id: str,
    current: dict = Depends(admin),
    store: WorkspaceStore = Depends(db),
):
    patient_access(patient_id, current, store)
    if not store.db.users.find_one({"user_id": doctor_id, "role": "doctor", "disabled": False}):
        raise HTTPException(400, "Active doctor required")
    store.db.patient_access.update_one(
        {"patient_id": patient_id, "doctor_id": doctor_id},
        {"$setOnInsert": {"patient_id": patient_id, "doctor_id": doctor_id}},
        upsert=True,
    )
    store.audit(current, "patient_assigned", patient_id, {"doctor_id": doctor_id})
    return {"ok": True}


@app.get("/api/patients/{patient_id}/documents")
def documents(patient_id: str, current: dict = Depends(user), store: WorkspaceStore = Depends(db)):
    patient_access(patient_id, current, store)
    return list(
        store.db.workspace_documents.find(
            {"patient_id": patient_id}, {"_id": 0, "source_path": 0}
        ).sort("visit_date", -1)
    )


@app.post("/api/patients/{patient_id}/documents")
async def upload_document(
    patient_id: str,
    file: UploadFile = File(...),
    document_type: str = Form("consult"),
    visit_date: str = Form(""),
    visit_id: str | None = Form(None),
    current: dict = Depends(user),
    store: WorkspaceStore = Depends(db),
):
    patient_access(patient_id, current, store)
    linked_visit = None
    if visit_id:
        linked_visit = store.db.visits.find_one({"patient_id": patient_id, "visit_id": visit_id})
        if not linked_visit:
            raise HTTPException(400, "Visit does not belong to this patient")
    else:
        criteria = {"patient_id": patient_id, "status": "active"}
        if current["role"] == "doctor":
            criteria["doctor_id"] = current["user_id"]
        linked_visit = store.db.visits.find_one(criteria)
    if file.filename is None or Path(file.filename).suffix.lower() not in {
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
    }:
        raise HTTPException(400, "PDF, PNG, or JPEG required")
    if visit_date:
        try:
            date.fromisoformat(visit_date)
        except ValueError:
            raise HTTPException(400, "Visit date must be YYYY-MM-DD") from None
    record_id = new_id("DOC")
    PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)
    target_dir = PRIVATE_ROOT / patient_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{record_id}{Path(file.filename).suffix.lower()}"
    size = 0
    try:
        with target.open("xb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > 30 * 1024 * 1024:
                    raise HTTPException(413, "File exceeds 30 MB")
                output.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    record = {
        "record_id": record_id,
        "visit_id": linked_visit["visit_id"] if linked_visit else None,
        "patient_id": patient_id,
        "filename": Path(file.filename).name,
        "source_path": str(target),
        "document_type": document_type,
        "visit_date": visit_date or None,
        "status": "pending",
        "created_at": now(),
        "size": size,
    }
    store.db.workspace_documents.insert_one(record)
    store.audit(current, "document_uploaded", patient_id, {"record_id": record_id})
    return {k: v for k, v in record.items() if k not in {"_id", "source_path"}}


@app.get("/api/patients/{patient_id}/documents/search")
def search_document_pages(
    patient_id: str,
    q: str = "",
    current: dict = Depends(clinician),
    store: WorkspaceStore = Depends(db),
):
    patient_access(patient_id, current, store)
    term = q.strip().casefold()
    if len(term) < 2 or len(term) > 120:
        return []
    records = {
        item["record_id"]: item
        for item in store.db.workspace_documents.find(
            {"patient_id": patient_id}, {"_id": 0, "record_id": 1, "filename": 1}
        )
    }
    matches = []
    for item in store.db.patient_documents.find(
        {"patient_id": patient_id},
        {"document_id": 1, "stage_1_raw_ocr.pages": 1},
    ):
        record = records.get(item.get("document_id"))
        if not record:
            continue
        for page in item.get("stage_1_raw_ocr", {}).get("pages", []):
            content = page.get("full_text", "")
            index = content.casefold().find(term)
            filename_match = term in record["filename"].casefold()
            if index < 0 and not filename_match:
                continue
            token = next(
                (t for t in page.get("tokens", []) if term in t.get("text", "").casefold()),
                None,
            )
            precise = (
                locate_citation(
                    store,
                    patient_id,
                    {
                        "document_id": item["document_id"],
                        "page_number": page["page_number"],
                        "bbox": [1, 1, 999, 999],
                        "snippet": term,
                    },
                )
                if index >= 0 and " " in term
                else None
            )
            matches.append(
                {
                    "document_id": item["document_id"],
                    "document_title": record["filename"],
                    "page_number": page["page_number"],
                    "snippet": content[max(0, index - 75) : index + len(term) + 95].strip()
                    if index >= 0
                    else "Filename match",
                    "bbox": precise or (token.get("bbox") if token else None),
                }
            )
            if len(matches) >= 50:
                return matches
    store.audit(current, "document_search", patient_id, {"result_count": len(matches)})
    return matches


@app.get("/api/patients/{patient_id}/documents/{record_id}/page/{page_number}")
def document_page(
    patient_id: str,
    record_id: str,
    page_number: int,
    current: dict = Depends(user),
    store: WorkspaceStore = Depends(db),
):
    patient_access(patient_id, current, store)
    rec = store.db.workspace_documents.find_one({"patient_id": patient_id, "record_id": record_id})
    if not rec:
        raise HTTPException(404, "Document not found")
    try:
        image = render_page(rec, page_number)
    except (ValueError, FileNotFoundError):
        raise HTTPException(404, "Page unavailable") from None
    store.audit(
        current, "document_page_viewed", patient_id, {"record_id": record_id, "page": page_number}
    )
    return Response(image, media_type="image/png", headers={"Cache-Control": "private, no-store"})


def _job(job_id: str, patient_id: str):
    store = WorkspaceStore()
    try:
        store.db.jobs.update_one(
            {"job_id": job_id}, {"$set": {"status": "running", "stage": "ocr", "updated_at": now()}}
        )
        total = store.db.workspace_documents.count_documents({"patient_id": patient_id})
        last_stage = None

        def progress(stage: str = "ocr") -> None:
            nonlocal last_stage
            ready = store.db.workspace_documents.count_documents(
                {"patient_id": patient_id, "status": "ready"}
            )
            failed = store.db.workspace_documents.count_documents(
                {"patient_id": patient_id, "status": "failed"}
            )
            store.db.jobs.update_one(
                {"job_id": job_id},
                {
                    "$set": {
                        "documents_total": total,
                        "documents_ready": ready,
                        "documents_failed": failed,
                        "stage": stage,
                        "updated_at": now(),
                    }
                },
            )
            if stage != last_stage:
                store.db.jobs.update_one(
                    {"job_id": job_id}, {"$push": {"steps": {"stage": stage, "at": now()}}}
                )
                last_stage = stage

        progress()
        brief = process_patient(store, patient_id, progress=progress)
        store.db.jobs.update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "status": "complete",
                    "stage": "complete",
                    "evidence_chunks": brief.get("raw_evidence_count", 0),
                    "verified_findings": len(brief.get("priority_findings", [])),
                    "updated_at": now(),
                }
            },
        )
    except Exception as exc:
        store.db.jobs.update_one(
            {"job_id": job_id},
            {"$set": {"status": "failed", "error": str(exc)[:500], "updated_at": now()}},
        )
    finally:
        active_brief_jobs.discard(job_id)
        store.client.close()


def recover_brief_job(store: WorkspaceStore, job: dict | None) -> dict | None:
    if (
        job
        and job.get("status") in {"queued", "running"}
        and job["job_id"] not in active_brief_jobs
    ):
        values = {
            "status": "failed",
            "stage": "Interrupted",
            "error": "The server restarted before analysis completed. Select Analyze records to retry.",
            "updated_at": now(),
        }
        store.db.jobs.update_one({"job_id": job["job_id"]}, {"$set": values})
        return {**job, **values}
    return job


def queue_brief_job(store: WorkspaceStore, patient_id: str) -> dict:
    running = store.db.jobs.find_one(
        {"patient_id": patient_id, "status": {"$in": ["queued", "running"]}}, {"_id": 0}
    )
    running = recover_brief_job(store, running)
    if running and running["status"] in {"queued", "running"}:
        return running
    job = {
        "job_id": new_id("JOB"),
        "patient_id": patient_id,
        "status": "queued",
        "stage": "ocr",
        "created_at": now(),
    }
    active_brief_jobs.add(job["job_id"])
    try:
        store.db.jobs.insert_one(job)
        workers.submit(_job, job["job_id"], patient_id)
    except Exception:
        active_brief_jobs.discard(job["job_id"])
        raise
    return {k: v for k, v in job.items() if k != "_id"}


@app.post("/api/patients/{patient_id}/brief/jobs")
def create_brief_job(
    patient_id: str, current: dict = Depends(clinician), store: WorkspaceStore = Depends(db)
):
    patient_access(patient_id, current, store)
    job = queue_brief_job(store, patient_id)
    store.audit(current, "brief_job_started", patient_id)
    return job


@app.get("/api/patients/{patient_id}/brief/jobs/latest")
def latest_job(
    patient_id: str, current: dict = Depends(clinician), store: WorkspaceStore = Depends(db)
):
    patient_access(patient_id, current, store)
    return recover_brief_job(
        store,
        store.db.jobs.find_one({"patient_id": patient_id}, {"_id": 0}, sort=[("created_at", -1)]),
    )


@app.get("/api/patients/{patient_id}/brief")
def brief(patient_id: str, current: dict = Depends(clinician), store: WorkspaceStore = Depends(db)):
    patient_access(patient_id, current, store)
    result = store.db.briefs.find_one({"patient_id": patient_id}, {"_id": 0})
    if not result:
        raise HTTPException(404, "Brief not generated")
    store.audit(current, "brief_viewed", patient_id)
    return result


class AppointmentIn(BaseModel):
    patient_id: str
    doctor_id: str
    date: str
    time: str
    reason: str = ""


@app.get("/api/appointments")
def appointments(
    date_filter: str | None = None,
    current: dict = Depends(user),
    store: WorkspaceStore = Depends(db),
):
    if current["role"] == "caregiver":
        raise HTTPException(403, "Doctor or admin access required")
    day = date_filter or local_day().isoformat()
    criteria = {"date": day}
    if current["role"] == "doctor":
        criteria["doctor_id"] = current["user_id"]
    rows = list(store.db.appointments.find(criteria, {"_id": 0}).sort("time", 1))
    for row in rows:
        p = store.patient(row["patient_id"])
        row["patient_name"] = p["name"] if p else "Unknown patient"
        row["external_aliases"] = p.get("external_aliases", []) if p else []
        row["sex"] = p.get("sex") if p else None
        row["age"] = (
            date.today().year - int(p["dob"][:4])
            if p and p.get("dob")
            else p.get("age")
            if p
            else None
        )
    return rows


@app.post("/api/appointments")
def create_appointment(
    body: AppointmentIn, current: dict = Depends(admin), store: WorkspaceStore = Depends(db)
):
    patient_access(body.patient_id, current, store)
    if not store.db.patient_access.find_one(
        {"patient_id": body.patient_id, "doctor_id": body.doctor_id}
    ):
        raise HTTPException(400, "Assign the doctor to this patient first")
    try:
        date.fromisoformat(body.date)
        datetime.strptime(body.time, "%H:%M")
    except ValueError:
        raise HTTPException(400, "Invalid date or time") from None
    row = {
        **body.model_dump(),
        "appointment_id": new_id("APT"),
        "status": "scheduled",
        "updated_at": now(),
    }
    store.db.appointments.insert_one(row)
    store.audit(
        current, "appointment_created", body.patient_id, {"appointment_id": row["appointment_id"]}
    )
    return {k: v for k, v in row.items() if k != "_id"}


@app.patch("/api/appointments/{appointment_id}")
def update_appointment(
    appointment_id: str,
    body: AppointmentIn,
    current: dict = Depends(admin),
    store: WorkspaceStore = Depends(db),
):
    patient_access(body.patient_id, current, store)
    if not store.db.patient_access.find_one(
        {"patient_id": body.patient_id, "doctor_id": body.doctor_id}
    ):
        raise HTTPException(400, "Assign the doctor first")
    try:
        date.fromisoformat(body.date)
        datetime.strptime(body.time, "%H:%M")
    except ValueError:
        raise HTTPException(400, "Invalid date or time") from None
    if not store.db.appointments.update_one(
        {"appointment_id": appointment_id}, {"$set": {**body.model_dump(), "updated_at": now()}}
    ).matched_count:
        raise HTTPException(404, "Appointment not found")
    store.audit(current, "appointment_updated", body.patient_id, {"appointment_id": appointment_id})
    return {"ok": True}


@app.post("/api/appointments/{appointment_id}/cancel")
def cancel_appointment(
    appointment_id: str, current: dict = Depends(admin), store: WorkspaceStore = Depends(db)
):
    row = store.db.appointments.find_one({"appointment_id": appointment_id})
    if not row:
        raise HTTPException(404, "Appointment not found")
    store.db.appointments.update_one(
        {"appointment_id": appointment_id}, {"$set": {"status": "cancelled", "updated_at": now()}}
    )
    store.audit(current, "appointment_cancelled", row["patient_id"])
    return {"ok": True}


@app.get("/api/patients/{patient_id}/visits")
def visits(
    patient_id: str, current: dict = Depends(clinician), store: WorkspaceStore = Depends(db)
):
    patient_access(patient_id, current, store)
    return list(store.db.visits.find({"patient_id": patient_id}, {"_id": 0}).sort("started_at", -1))


@app.get("/api/patients/{patient_id}/pathways")
def pathway_history(
    patient_id: str, current: dict = Depends(clinician), store: WorkspaceStore = Depends(db)
):
    patient_access(patient_id, current, store)
    return list(
        store.db.pathways.find({"patient_id": patient_id}, {"_id": 0}).sort("approved_at", -1)
    )


@app.post("/api/patients/{patient_id}/visits")
def start_visit(
    patient_id: str, current: dict = Depends(clinician), store: WorkspaceStore = Depends(db)
):
    patient_access(patient_id, current, store)
    active = store.db.visits.find_one(
        {"patient_id": patient_id, "doctor_id": current["user_id"], "status": "active"}, {"_id": 0}
    )
    if active:
        return active
    appointment = store.db.appointments.find_one(
        {
            "patient_id": patient_id,
            "doctor_id": current["user_id"],
            "date": local_day().isoformat(),
            "status": "scheduled",
        },
        sort=[("time", 1)],
    )
    row = {
        "appointment_id": appointment["appointment_id"] if appointment else None,
        "visit_id": new_id("VIS"),
        "patient_id": patient_id,
        "doctor_id": current["user_id"],
        "status": "active",
        "admitted": False,
        "started_at": now(),
        "doctor_notes": "",
    }
    store.db.visits.insert_one(row)
    if appointment:
        store.db.appointments.update_one(
            {"appointment_id": appointment["appointment_id"]},
            {"$set": {"visit_id": row["visit_id"], "status": "in_progress"}},
        )
    store.audit(current, "visit_started", patient_id, {"visit_id": row["visit_id"]})
    return {k: v for k, v in row.items() if k != "_id"}


def own_visit(visit_id: str, current: dict, store: WorkspaceStore) -> dict:
    visit = store.db.visits.find_one(
        {"visit_id": visit_id, "doctor_id": current["user_id"], "status": "active"}
    )
    if not visit:
        raise HTTPException(404, "Active visit not found")
    patient_access(visit["patient_id"], current, store)
    return visit


class AdmissionIn(BaseModel):
    admitted: bool


@app.post("/api/visits/{visit_id}/admission")
def admission(
    visit_id: str,
    body: AdmissionIn,
    current: dict = Depends(clinician),
    store: WorkspaceStore = Depends(db),
):
    visit = own_visit(visit_id, current, store)
    store.db.visits.update_one(
        {"visit_id": visit_id}, {"$set": {"admitted": body.admitted, "admission_changed_at": now()}}
    )
    store.audit(current, "admission_flag_changed", visit["patient_id"], {"admitted": body.admitted})
    return {"admitted": body.admitted}


class NotesIn(BaseModel):
    notes: str = Field(max_length=10000)


@app.post("/api/visits/{visit_id}/notes")
def save_notes(
    visit_id: str,
    body: NotesIn,
    current: dict = Depends(clinician),
    store: WorkspaceStore = Depends(db),
):
    visit = own_visit(visit_id, current, store)
    store.db.visits.update_one(
        {"visit_id": visit_id}, {"$set": {"doctor_notes": body.notes, "notes_updated_at": now()}}
    )
    store.audit(current, "visit_notes_saved", visit["patient_id"])
    return {"ok": True}


class PathwayItemIn(BaseModel):
    text: str = Field(min_length=3, max_length=1000)


@app.post("/api/visits/{visit_id}/pathway/items")
def add_pathway_item(
    visit_id: str,
    body: PathwayItemIn,
    current: dict = Depends(clinician),
    store: WorkspaceStore = Depends(db),
):
    visit = own_visit(visit_id, current, store)
    item = {
        "item_id": new_id("ITEM"),
        "visit_id": visit_id,
        "patient_id": visit["patient_id"],
        "text": body.text.strip(),
        "completed": False,
        "approved_by": current["user_id"],
        "created_at": now(),
    }
    store.db.pathway_items.insert_one(item)
    store.audit(current, "pathway_item_added", visit["patient_id"], {"item_id": item["item_id"]})
    return {k: v for k, v in item.items() if k != "_id"}


class PathwayCheckIn(BaseModel):
    completed: bool


@app.patch("/api/visits/{visit_id}/pathway/items/{item_id}")
def check_pathway_item(
    visit_id: str,
    item_id: str,
    body: PathwayCheckIn,
    current: dict = Depends(clinician),
    store: WorkspaceStore = Depends(db),
):
    visit = own_visit(visit_id, current, store)
    if not store.db.pathway_items.update_one(
        {"visit_id": visit_id, "item_id": item_id},
        {"$set": {"completed": body.completed, "updated_at": now()}},
    ).matched_count:
        raise HTTPException(404, "Pathway item not found")
    store.audit(
        current,
        "pathway_item_checked",
        visit["patient_id"],
        {"item_id": item_id, "completed": body.completed},
    )
    return {"ok": True}


class DecisionIn(BaseModel):
    finding_id: str
    decision: Literal["accepted", "edited", "rejected"]
    edited_text: str | None = None


@app.post("/api/visits/{visit_id}/decisions")
def decide(
    visit_id: str,
    body: DecisionIn,
    current: dict = Depends(clinician),
    store: WorkspaceStore = Depends(db),
):
    visit = own_visit(visit_id, current, store)
    brief = store.db.briefs.find_one({"patient_id": visit["patient_id"]})
    findings = brief.get("brief", {}).get("priority_findings", []) if brief else []
    if not any(f["finding_id"] == body.finding_id for f in findings):
        raise HTTPException(400, "Finding not in current brief")
    if body.decision == "edited" and not body.edited_text:
        raise HTTPException(400, "Edited text required")
    store.db.review_decisions.update_one(
        {"visit_id": visit_id, "finding_id": body.finding_id},
        {
            "$set": {
                "visit_id": visit_id,
                "finding_id": body.finding_id,
                "patient_id": visit["patient_id"],
                "decision": body.decision,
                "edited_text": body.edited_text,
                "doctor_id": current["user_id"],
                "updated_at": now(),
            }
        },
        upsert=True,
    )
    store.audit(
        current,
        "finding_reviewed",
        visit["patient_id"],
        {"finding_id": body.finding_id, "decision": body.decision},
    )
    return {"ok": True}


@app.get("/api/visits/{visit_id}/pathway")
def pathway(visit_id: str, current: dict = Depends(clinician), store: WorkspaceStore = Depends(db)):
    visit = own_visit(visit_id, current, store)
    brief = store.db.briefs.find_one({"patient_id": visit["patient_id"]})
    findings = brief.get("brief", {}).get("priority_findings", []) if brief else []
    decisions = {d["finding_id"]: d for d in store.db.review_decisions.find({"visit_id": visit_id})}
    accepted = [
        {
            "title": decisions[f["finding_id"]].get("edited_text") or f["title"],
            "citation": f.get("citation"),
        }
        for f in findings
        if f["finding_id"] in decisions
        and decisions[f["finding_id"]]["decision"] != "rejected"
        and (f.get("citation") or {}).get("source_verified")
    ]
    items = list(
        store.db.pathway_items.find({"visit_id": visit_id}, {"_id": 0}).sort("created_at", 1)
    )
    suggestions = (
        [
            x.get("text_en", "")
            for x in brief.get("brief", {}).get("caregiver_prep", {}).get("checklist", [])
        ]
        if brief
        else []
    )
    return {
        "mode": "caregiver" if visit.get("admitted") else "family",
        "doctor_notes": visit.get("doctor_notes", ""),
        "reviewed_evidence": accepted,
        "items": items,
        "agent_suggestions": suggestions,
        "needs_review": True,
        "message": "Clinician notes and verified, reviewed evidence only. Confirm before finalizing.",
    }


class EndIn(BaseModel):
    confirm: bool
    confirm_evidence_only: bool = False
    draft_revision: int | None = None


@app.post("/api/visits/{visit_id}/end")
def end_visit(
    visit_id: str,
    body: EndIn,
    current: dict = Depends(clinician),
    store: WorkspaceStore = Depends(db),
):
    visit = own_visit(visit_id, current, store)
    if not body.confirm or (
        not visit.get("doctor_notes", "").strip()
        and not store.db.pathway_items.count_documents({"visit_id": visit_id})
        and not body.confirm_evidence_only
    ):
        raise HTTPException(
            400,
            "Review the pathway and provide notes or explicitly confirm an evidence-only record",
        )
    draft = pathway(visit_id, current, store)
    care = ensure_draft(store, visit)
    if body.draft_revision is not None and body.draft_revision != care["revision"]:
        raise HTTPException(409, "Care draft changed. Reload and review before sign-off")
    draft.update({k: v for k, v in care.items() if k not in {"visit_id", "patient_id", "_id"}})
    version = store.db.pathways.count_documents({"visit_id": visit_id}) + 1
    saved = {
        **draft,
        "pathway_id": new_id("PATH"),
        "visit_id": visit_id,
        "patient_id": visit["patient_id"],
        "version": version,
        "approved_by": current["user_id"],
        "approved_name": current["name"],
        "approved_day": local_day().isoformat(),
        "patient_snapshot": store.patient(visit["patient_id"]),
        "brief_snapshot": (
            store.db.briefs.find_one({"patient_id": visit["patient_id"]}, {"_id": 0}) or {}
        ).get("brief"),
        "document_ids": [
            r["record_id"]
            for r in store.db.workspace_documents.find(
                {"patient_id": visit["patient_id"]}, {"record_id": 1}
            )
        ],
        "approved_at": now(),
        "needs_review": False,
    }
    saved.pop("_id", None)
    claimed = store.db.visits.update_one(
        {"visit_id": visit_id, "status": "active"}, {"$set": {"status": "finalizing"}}
    )
    if not claimed.matched_count:
        raise HTTPException(409, "Visit is already being finalized")
    try:
        store.db.pathways.insert_one(saved)
    except Exception:
        store.db.visits.update_one({"visit_id": visit_id}, {"$set": {"status": "active"}})
        raise
    store.db.visits.update_one(
        {"visit_id": visit_id},
        {"$set": {"status": "ended", "ended_at": now(), "pathway_id": saved["pathway_id"]}},
    )
    if visit.get("appointment_id"):
        store.db.appointments.update_one(
            {"appointment_id": visit["appointment_id"]},
            {"$set": {"status": "completed", "visit_id": visit_id}},
        )
    try:
        archive_pdf(store, saved)
    except Exception:
        logging.getLogger(__name__).exception("Signed pathway saved; PDF archive can be retried")
    store.audit(current, "visit_ended", visit["patient_id"], {"pathway_id": saved["pathway_id"]})
    workers.submit(translate_signed_job, saved["pathway_id"])
    return {k: v for k, v in saved.items() if k != "_id"}


register_care_routes(app, db, user, admin, clinician, patient_access, own_visit, workers)
register_administration_routes(app, db, user, admin, clinician, patient_access)


class QueryIn(BaseModel):
    patient_id: str
    query: str = Field(min_length=2, max_length=2000)


class ChatSessionIn(BaseModel):
    patient_id: str


class ChatTurnIn(BaseModel):
    query: str = Field(min_length=2, max_length=4000)


def owned_chat_session(session_id: str, current: dict, store: WorkspaceStore) -> dict:
    session = store.db.chat_sessions.find_one(
        {"session_id": session_id, "user_id": current["user_id"]}, {"_id": 0}
    )
    if not session:
        raise HTTPException(404, "Conversation not found")
    patient_access(session["patient_id"], current, store)
    active_id = session.get("active_turn_id")
    if active_id and active_id not in active_chat_turns:
        store.db.chat_turns.update_one(
            {"turn_id": active_id, "status": {"$in": ["queued", "running"]}},
            {
                "$set": {
                    "status": "failed",
                    "stage": "Interrupted",
                    "error": "The server restarted before this response completed. Please retry.",
                    "updated_at": now(),
                }
            },
        )
        store.db.chat_sessions.update_one(
            {"session_id": session_id}, {"$set": {"active_turn_id": None}}
        )
        session["active_turn_id"] = None
    return session


@app.get("/api/chat/sessions")
def list_chat_sessions(
    patient_id: str, current: dict = Depends(clinician), store: WorkspaceStore = Depends(db)
):
    patient_access(patient_id, current, store)
    return list(
        store.db.chat_sessions.find(
            {"patient_id": patient_id, "user_id": current["user_id"]}, {"_id": 0}
        )
        .sort("updated_at", -1)
        .limit(50)
    )


@app.post("/api/chat/sessions")
def create_chat_session(
    body: ChatSessionIn, current: dict = Depends(clinician), store: WorkspaceStore = Depends(db)
):
    patient_access(body.patient_id, current, store)
    store.indexes()
    session = {
        "session_id": new_id("CHAT"),
        "patient_id": body.patient_id,
        "user_id": current["user_id"],
        "title": "New conversation",
        "created_at": now(),
        "updated_at": now(),
        "active_turn_id": None,
    }
    store.db.chat_sessions.insert_one(session)
    store.audit(current, "chat_session_created", body.patient_id)
    return {key: value for key, value in session.items() if key != "_id"}


@app.get("/api/chat/sessions/{session_id}")
def get_chat_session(
    session_id: str, current: dict = Depends(clinician), store: WorkspaceStore = Depends(db)
):
    session = owned_chat_session(session_id, current, store)
    return {
        "session": session,
        "messages": list(
            store.db.chat_messages.find({"session_id": session_id}, {"_id": 0}).sort(
                "created_at", 1
            )
        ),
        "artifacts": list(
            store.db.chat_artifacts.find({"session_id": session_id}, {"_id": 0}).sort(
                "created_at", 1
            )
        ),
        "active_turn": store.db.chat_turns.find_one(
            {"turn_id": session.get("active_turn_id")}, {"_id": 0}
        )
        if session.get("active_turn_id")
        else None,
    }


def _chat_worker(turn_id: str, session_id: str, question: str):
    store = WorkspaceStore()
    try:
        session = store.db.chat_sessions.find_one({"session_id": session_id}, {"_id": 0})

        def progress(label: str, step: str):
            store.db.chat_turns.update_one(
                {"turn_id": turn_id},
                {
                    "$set": {
                        "status": "running",
                        "stage": label,
                        "step": step,
                        "updated_at": now(),
                    },
                    "$push": {"steps": {"label": label, "at": now()}},
                },
            )

        previous = list(
            store.db.chat_messages.find(
                {"session_id": session_id, "turn_id": {"$ne": turn_id}}, {"_id": 0}
            ).sort("created_at", 1)
        )
        result = run_chat_turn(store, session, question, previous, progress)
        for artifact in result.pop("artifacts", []):
            store.db.chat_artifacts.insert_one(
                {**artifact, "user_id": session["user_id"], "turn_id": turn_id}
            )
        store.db.chat_messages.insert_one(
            {
                **result,
                "session_id": session_id,
                "patient_id": session["patient_id"],
                "user_id": session["user_id"],
                "turn_id": turn_id,
            }
        )
        store.db.chat_turns.update_one(
            {"turn_id": turn_id},
            {
                "$set": {
                    "status": "complete",
                    "stage": "Complete",
                    "message_id": result["message_id"],
                    "updated_at": now(),
                }
            },
        )
    except Exception:
        logging.getLogger(__name__).exception("Patient chat turn failed: %s", turn_id)
        store.db.chat_turns.update_one(
            {"turn_id": turn_id},
            {
                "$set": {
                    "status": "failed",
                    "stage": "Response failed",
                    "error": "The response could not be completed. Your message is saved; retry when the local model is ready.",
                    "updated_at": now(),
                }
            },
        )
    finally:
        store.db.chat_sessions.update_one(
            {"session_id": session_id, "active_turn_id": turn_id},
            {"$set": {"active_turn_id": None, "updated_at": now()}},
        )
        active_chat_turns.discard(turn_id)
        store.client.close()


@app.post("/api/chat/sessions/{session_id}/turns")
def send_chat_turn(
    session_id: str,
    body: ChatTurnIn,
    current: dict = Depends(clinician),
    store: WorkspaceStore = Depends(db),
):
    session = owned_chat_session(session_id, current, store)
    turn_id = new_id("TURN")
    # Register before publishing the ID so a concurrent poll cannot mistake it for
    # an orphan from a previous server process.
    active_chat_turns.add(turn_id)
    try:
        claimed = store.db.chat_sessions.update_one(
            {"session_id": session_id, "active_turn_id": None},
            {
                "$set": {
                    "active_turn_id": turn_id,
                    "updated_at": now(),
                    "title": body.query[:65]
                    if session["title"] == "New conversation"
                    else session["title"],
                }
            },
        )
    except Exception:
        active_chat_turns.discard(turn_id)
        raise
    if not claimed.modified_count:
        active_chat_turns.discard(turn_id)
        raise HTTPException(409, "A response is already being prepared in this conversation")
    turn = {
        "turn_id": turn_id,
        "session_id": session_id,
        "patient_id": session["patient_id"],
        "user_id": current["user_id"],
        "status": "queued",
        "stage": "Waiting for analysis",
        "query": body.query,
        "created_at": now(),
        "updated_at": now(),
        "steps": [],
    }
    store.db.chat_turns.insert_one(turn)
    store.db.chat_messages.insert_one(
        {
            "message_id": new_id("MSG"),
            "turn_id": turn_id,
            "session_id": session_id,
            "patient_id": session["patient_id"],
            "user_id": current["user_id"],
            "role": "user",
            "text": body.query,
            "created_at": now(),
        }
    )
    workers.submit(_chat_worker, turn_id, session_id, body.query)
    store.audit(current, "chat_turn_started", session["patient_id"])
    return {key: value for key, value in turn.items() if key != "_id"}


@app.get("/api/chat/turns/{turn_id}")
def get_chat_turn(
    turn_id: str, current: dict = Depends(clinician), store: WorkspaceStore = Depends(db)
):
    turn = store.db.chat_turns.find_one(
        {"turn_id": turn_id, "user_id": current["user_id"]}, {"_id": 0}
    )
    if not turn:
        raise HTTPException(404, "Response not found")
    owned_chat_session(turn["session_id"], current, store)
    return store.db.chat_turns.find_one({"turn_id": turn_id}, {"_id": 0})


@app.post("/api/chat/query")
def chat(body: QueryIn, current: dict = Depends(clinician), store: WorkspaceStore = Depends(db)):
    patient_access(body.patient_id, current, store)
    result = answer_chat(store, body.patient_id, body.query)
    store.audit(current, "chat_query", body.patient_id)
    return result


@app.get("/api/voice/capabilities")
def voice_capabilities(_: dict = Depends(clinician)):
    available = tts_ready()
    cloud = os.getenv("PREPPULSE_VOICE_PROVIDER") == "sarvam"
    return {
        "dictation": True,
        "tts_ready": available,
        "tts_status": "Sarvam configured; audio verified on playback" if cloud and available else "Local audio endpoint verified"
        if available
        else "No compatible audio endpoint verified",
        "tts_model": "bulbul:v3" if cloud else "mradermacher/Qwen3-1.7B-Multilingual-TTS-GGUF",
        "tts_path_configured": bool(TTS_MODEL_PATH and Path(TTS_MODEL_PATH).is_file()),
    }


class SpeakIn(BaseModel):
    patient_id: str
    text: str = Field(min_length=1, max_length=1200)


@app.post("/api/voice/speak")
def speak(body: SpeakIn, current: dict = Depends(clinician), store: WorkspaceStore = Depends(db)):
    patient_access(body.patient_id, current, store)
    if not tts_ready():
        raise HTTPException(503, "Speech audio is unavailable")
    try:
        data = synthesize(body.text)
    except Exception:
        raise HTTPException(503, "Speech audio failed") from None
    store.audit(current, "voice_playback", body.patient_id)
    return Response(data, media_type="audio/wav", headers={"Cache-Control": "no-store"})


@app.post("/api/voice/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    language: str = Form(""),
    current: dict = Depends(clinician),
):
    global _stt_model
    if language not in {"", "en", "hi", "ta", "bn", "te", "or"}:
        raise HTTPException(400, "Unsupported dictation language")
    data = await file.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "Audio exceeds 10 MB")
    if os.getenv("PREPPULSE_VOICE_PROVIDER") == "sarvam":
        from preppulse_api.cloud_services import transcribe_sarvam
        try:
            from starlette.concurrency import run_in_threadpool
            text = await run_in_threadpool(transcribe_sarvam, data, language)
            return {"transcript": text, "review_required": True}
        except Exception:
            if os.getenv("PREPPULSE_VOICE_FALLBACK", "local") != "local":
                raise HTTPException(503, "Speech service unavailable; please retry or type") from None
    try:
        import tempfile

        from faster_whisper import WhisperModel

        if _stt_model is None:
            _stt_model = WhisperModel(STT_MODEL, device="cpu", compute_type="int8")
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)
        try:
            segments, _ = _stt_model.transcribe(str(tmp_path), language=language or None)
            text = " ".join(s.text.strip() for s in segments).strip()
        finally:
            tmp_path.unlink(missing_ok=True)
    except Exception:
        raise HTTPException(503, "Transcription unavailable; please retry or type") from None
    return {"transcript": text, "review_required": True}


@app.get("/api/health")
def health(store: WorkspaceStore = Depends(db)):
    try:
        store.ready()
        return {"status": "ready"}
    except Exception:
        raise HTTPException(503, "MongoDB unavailable") from None


@app.get("/api/patients/{patient_id}/documents/{record_id}/fhir")
def document_fhir(patient_id: str, record_id: str, current: dict = Depends(clinician),
                  store: WorkspaceStore = Depends(db)):
    patient_access(patient_id, current, store)
    doc = store.db.patient_documents.find_one({"patient_id": patient_id, "document_id": record_id})
    if not doc:
        raise HTTPException(404, "Processed document not found")
    if doc.get("preprocessing", {}).get("status") != "complete":
        raise HTTPException(409, "Structured processing is incomplete; analyze records first")
    store.audit(current, "fhir_viewed", patient_id, {"record_id": record_id})
    return Response(__import__("json").dumps(doc["stage_3_fhir_output"]),
                    media_type="application/fhir+json", headers={"Cache-Control": "no-store"})
