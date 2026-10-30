from __future__ import annotations

import json
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pwdlib import PasswordHash
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError
from starlette.middleware.sessions import SessionMiddleware

from preppulse_api.clinical import answer_chat, process_patient, render_page
from preppulse_api.config import (
    DATASET_ROOT,
    PRIVATE_ROOT,
    SESSION_SECRET,
    STT_MODEL,
    TTS_MODEL_PATH,
)
from preppulse_api.store import WorkspaceStore, new_id, now

if len(SESSION_SECRET) < 32:
    raise RuntimeError("Set PREPPULSE_SESSION_SECRET to a random value of at least 32 characters")

app = FastAPI(title="PrepPulse local workspace API")
workers = ThreadPoolExecutor(max_workers=2)
password_hash = PasswordHash.recommended()
_stt_model = None


def db() -> WorkspaceStore:
    store = WorkspaceStore()
    try:
        yield store
    finally:
        store.client.close()


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
    session_cookie="preppulse_session",
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
    role: Literal["doctor", "admin"] = "doctor"


@app.get("/api/admin/accounts")
def accounts(_: dict = Depends(admin), store: WorkspaceStore = Depends(db)):
    return list(store.db.users.find({}, {"_id": 0, "password_hash": 0}))


@app.post("/api/admin/accounts")
def add_account(
    body: AccountIn, current: dict = Depends(admin), store: WorkspaceStore = Depends(db)
):
    account = {
        "user_id": new_id("USR"),
        "name": body.name.strip(),
        "username": body.username.lower().strip(),
        "role": body.role,
        "password_hash": password_hash.hash(body.password),
        "disabled": False,
        "created_at": now(),
    }
    try:
        store.db.users.insert_one(account)
    except DuplicateKeyError:
        raise HTTPException(409, "Username already exists") from None
    store.audit(current, "account_created", extra={"user_id": account["user_id"]})
    return {k: v for k, v in account.items() if k not in {"_id", "password_hash"}}


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
    return {"ok": True}


class PatientIn(BaseModel):
    name: str = Field(min_length=2)
    dob: str | None = None
    sex: str | None = None
    doctor_id: str


@app.get("/api/patients")
def patients(q: str = "", current: dict = Depends(user), store: WorkspaceStore = Depends(db)):
    return store.search_patients(current, q)


@app.get("/api/patients/{patient_id}")
def patient(patient_id: str, current: dict = Depends(user), store: WorkspaceStore = Depends(db)):
    found = patient_access(patient_id, current, store)
    store.audit(current, "patient_opened", patient_id)
    return {k: v for k, v in found.items() if k not in {"_id", "source_root"}}


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


@app.post("/api/admin/import-samples")
def import_samples(
    doctor_id: str = Form(...), current: dict = Depends(admin), store: WorkspaceStore = Depends(db)
):
    if not store.db.users.find_one({"user_id": doctor_id, "role": "doctor", "disabled": False}):
        raise HTTPException(400, "Active doctor required")
    created = 0
    for folder in sorted(DATASET_ROOT.glob("PP*_*")):
        manifest_path = folder / "manifest.json"
        if not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        # Folder name is authoritative. Some source manifests contain conflicting folder IDs.
        alias = folder.name.split("_", 1)[0]
        alias_link = store.db.patient_aliases.find_one({"alias": folder.name})
        existing = store.patient(alias_link["patient_id"]) if alias_link else None
        if existing:
            patient_id = existing["patient_id"]
        else:
            collision = store.db.patient_aliases.find_one({"alias": alias})
            aliases = [folder.name] if collision else [alias, folder.name]
            patient_id = new_id("PRP")
            store.db.patients.insert_one(
                {
                    "patient_id": patient_id,
                    "name": manifest.get("name") or folder.name.split("_", 1)[-1].replace("_", " "),
                    "name_search": (manifest.get("name") or folder.name).lower(),
                    "dob": manifest.get("dob"),
                    "sex": manifest.get("sex"),
                    "external_aliases": aliases,
                    "created_at": now(),
                }
            )
            for item in aliases:
                store.db.patient_aliases.insert_one({"alias": item, "patient_id": patient_id})
            created += 1
        store.db.patient_access.update_one(
            {"patient_id": patient_id, "doctor_id": doctor_id},
            {"$setOnInsert": {"patient_id": patient_id, "doctor_id": doctor_id}},
            upsert=True,
        )
        for record in manifest.get("records", []):
            filename = record.get("file") or record.get("filename")
            path = (folder / filename).resolve() if filename else None
            if not path or not path.is_file() or not path.is_relative_to(DATASET_ROOT):
                continue
            store.db.workspace_documents.update_one(
                {"patient_id": patient_id, "source_path": str(path)},
                {
                    "$setOnInsert": {
                        "record_id": new_id("DOC"),
                        "patient_id": patient_id,
                        "filename": filename,
                        "source_path": str(path),
                        "document_type": record.get("type", "consult"),
                        "visit_date": record.get("date"),
                        "status": "pending",
                        "created_at": now(),
                    }
                },
                upsert=True,
            )
    store.audit(current, "samples_imported", extra={"created": created})
    return {"patients_created": created}


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
    current: dict = Depends(user),
    store: WorkspaceStore = Depends(db),
):
    patient_access(patient_id, current, store)
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
            {"job_id": job_id}, {"$set": {"status": "running", "updated_at": now()}}
        )
        process_patient(store, patient_id)
        store.db.jobs.update_one(
            {"job_id": job_id}, {"$set": {"status": "complete", "updated_at": now()}}
        )
    except Exception as exc:
        store.db.jobs.update_one(
            {"job_id": job_id},
            {"$set": {"status": "failed", "error": str(exc)[:500], "updated_at": now()}},
        )
    finally:
        store.client.close()


@app.post("/api/patients/{patient_id}/brief/jobs")
def create_brief_job(
    patient_id: str, current: dict = Depends(clinician), store: WorkspaceStore = Depends(db)
):
    patient_access(patient_id, current, store)
    running = store.db.jobs.find_one(
        {"patient_id": patient_id, "status": {"$in": ["queued", "running"]}}, {"_id": 0}
    )
    if running:
        return running
    job = {
        "job_id": new_id("JOB"),
        "patient_id": patient_id,
        "status": "queued",
        "created_at": now(),
    }
    store.db.jobs.insert_one(job)
    workers.submit(_job, job["job_id"], patient_id)
    store.audit(current, "brief_job_started", patient_id)
    return {k: v for k, v in job.items() if k != "_id"}


@app.get("/api/patients/{patient_id}/brief/jobs/latest")
def latest_job(
    patient_id: str, current: dict = Depends(clinician), store: WorkspaceStore = Depends(db)
):
    patient_access(patient_id, current, store)
    return store.db.jobs.find_one({"patient_id": patient_id}, {"_id": 0}, sort=[("created_at", -1)])


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
    day = date_filter or date.today().isoformat()
    criteria = {"date": day}
    if current["role"] == "doctor":
        criteria["doctor_id"] = current["user_id"]
    rows = list(store.db.appointments.find(criteria, {"_id": 0}).sort("time", 1))
    for row in rows:
        p = store.patient(row["patient_id"])
        row["patient_name"] = p["name"] if p else "Unknown patient"
        row["external_aliases"] = p.get("external_aliases", []) if p else []
        row["sex"] = p.get("sex") if p else None
        row["age"] = date.today().year - int(p["dob"][:4]) if p and p.get("dob") else None
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
    row = {
        "visit_id": new_id("VIS"),
        "patient_id": patient_id,
        "doctor_id": current["user_id"],
        "status": "active",
        "admitted": False,
        "started_at": now(),
        "doctor_notes": "",
    }
    store.db.visits.insert_one(row)
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
    version = store.db.pathways.count_documents({"visit_id": visit_id}) + 1
    saved = {
        **draft,
        "pathway_id": new_id("PATH"),
        "visit_id": visit_id,
        "patient_id": visit["patient_id"],
        "version": version,
        "approved_by": current["user_id"],
        "approved_at": now(),
        "needs_review": False,
    }
    store.db.pathways.insert_one(saved)
    store.db.visits.update_one(
        {"visit_id": visit_id},
        {"$set": {"status": "ended", "ended_at": now(), "pathway_id": saved["pathway_id"]}},
    )
    store.audit(current, "visit_ended", visit["patient_id"], {"pathway_id": saved["pathway_id"]})
    return {k: v for k, v in saved.items() if k != "_id"}


class QueryIn(BaseModel):
    patient_id: str
    query: str = Field(min_length=2, max_length=2000)


@app.post("/api/chat/query")
def chat(body: QueryIn, current: dict = Depends(clinician), store: WorkspaceStore = Depends(db)):
    patient_access(body.patient_id, current, store)
    result = answer_chat(store, body.patient_id, body.query)
    store.audit(current, "chat_query", body.patient_id)
    return result


@app.get("/api/voice/capabilities")
def voice_capabilities(_: dict = Depends(clinician)):
    return {
        "dictation": True,
        "tts_ready": False,
        "tts_status": "Awaiting verified local GGUF runtime",
        "tts_model": "mradermacher/Qwen3-1.7B-Multilingual-TTS-GGUF",
        "tts_path_configured": bool(TTS_MODEL_PATH and Path(TTS_MODEL_PATH).is_file()),
    }


@app.post("/api/voice/transcribe")
async def transcribe(file: UploadFile = File(...), current: dict = Depends(clinician)):
    global _stt_model
    data = await file.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "Audio exceeds 10 MB")
    try:
        import tempfile

        from faster_whisper import WhisperModel

        if _stt_model is None:
            _stt_model = WhisperModel(STT_MODEL, device="cpu", compute_type="int8")
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)
        try:
            segments, _ = _stt_model.transcribe(str(tmp_path))
            text = " ".join(s.text.strip() for s in segments).strip()
        finally:
            tmp_path.unlink(missing_ok=True)
    except Exception as exc:
        raise HTTPException(503, f"Local transcription unavailable: {str(exc)[:100]}") from None
    return {"transcript": text, "review_required": True}


@app.get("/api/health")
def health(store: WorkspaceStore = Depends(db)):
    try:
        store.ready()
        return {"status": "ready"}
    except Exception:
        raise HTTPException(503, "MongoDB unavailable") from None
