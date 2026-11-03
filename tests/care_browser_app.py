"""Isolated, in-memory browser fixture: never opens the user's MongoDB.

Run: python -m uvicorn tests.care_browser_app:app --port 8001 (or use --app-dir tests).
Requires the dev dependency mongomock. All data below is synthetic test data.
"""

import importlib
import os
from pathlib import Path

import fitz
import mongomock

os.environ["PREPPULSE_SESSION_SECRET"] = "isolated-browser-review-secret-more-than-32-characters"
os.environ["LLM_PROVIDER"] = "mock"

from preppulse_agents.schemas import ConsultationBrief
from preppulse_api.app import app, db, password_hash
from preppulse_api.care import local_day
from preppulse_api.store import WorkspaceStore

api = importlib.import_module("preppulse_api.app")
care = importlib.import_module("preppulse_api.care")
clinical = importlib.import_module("preppulse_api.clinical")
store_module = importlib.import_module("preppulse_api.store")
folder = importlib.import_module("preppulse_api.folder_import")
store = WorkspaceStore.__new__(WorkspaceStore)
store.client = mongomock.MongoClient()
store.db = store.client["preppulse_browser_fixture"]
store.indexes()
root = Path(__file__).resolve().parents[1] / ".tmp" / "care-browser"
root.mkdir(parents=True, exist_ok=True)
for module in (care, clinical, folder, api):
    module.PRIVATE_ROOT = root
api.WorkspaceStore = lambda: store
store_module.WorkspaceStore = lambda: store


def override_db():
    yield store


app.dependency_overrides[db] = override_db
for role in ("doctor", "admin", "caregiver"):
    store.db.users.insert_one(
        {
            "user_id": role,
            "name": f"Review {role.title()}",
            "username": role,
            "role": role,
            "password_hash": password_hash.hash("review-test-password"),
            "disabled": False,
        }
    )
store.db.patients.insert_one(
    {
        "patient_id": "PRP-REVIEW",
        "name": "Review Patient",
        "name_search": "review patient",
        "age": 45,
        "sex": "Female",
        "external_aliases": ["PP-REVIEW"],
    }
)
store.db.patient_access.insert_one({"patient_id": "PRP-REVIEW", "doctor_id": "doctor"})
store.db.caregiver_access.insert_one(
    {"patient_id": "PRP-REVIEW", "caregiver_id": "caregiver", "kind": "family"}
)
pdf = fitz.open()
page = pdf.new_page()
page.insert_text((60, 150), "HbA1c 7.2 <5.7 %")
path = root / "review_lab.pdf"
pdf.save(path)
width, height = page.rect.width, page.rect.height
tokens = [
    {
        "text": w[4],
        "bbox": [
            int(w[0] / width * 1000),
            int(w[1] / height * 1000),
            int(w[2] / width * 1000),
            int(w[3] / height * 1000),
        ],
    }
    for w in page.get_text("words")
]
full_text = page.get_text()
pdf.close()
source = {
    "document_id": "DOC-REVIEW",
    "document_title": "review_lab.pdf",
    "page_number": 1,
    "bbox": [95, 165, 300, 185],
    "snippet": "HbA1c 7.2 <5.7 %",
    "source_verified": True,
}
store.db.workspace_documents.insert_one(
    {
        "record_id": "DOC-REVIEW",
        "patient_id": "PRP-REVIEW",
        "filename": "review_lab.pdf",
        "source_path": str(path),
        "visit_date": "2025-01-01",
        "document_type": "lab",
        "page_count": 1,
        "status": "ready",
    }
)
store.db.patient_documents.insert_one(
    {
        "document_id": "DOC-REVIEW",
        "patient_id": "PRP-REVIEW",
        "source_file": "review_lab.pdf",
        "document_type": "lab",
        "visit_date": "2025-01-01",
        "stage_1_raw_ocr": {
            "pages": [{"page_number": 1, "full_text": full_text, "tokens": tokens}]
        },
    }
)
brief = ConsultationBrief(patient_id="PRP-REVIEW", patient_name="Review Patient").model_dump(
    mode="json"
)
brief.update(
    patient_id="PRP-REVIEW",
    patient_name="Review Patient",
    age_sex="45 years / Female",
    raw_evidence_count=1,
)
brief["trajectory"]["kpis"] = [
    {
        "name": "HbA1c",
        "value": "7.2",
        "unit": "%",
        "date_str": "2025-01-01",
        "trend_direction": "stable",
        "citation": source,
    }
]
brief["caregiver_prep"]["checklist"] = [
    {
        "id": "test-one",
        "text_en": "Bring the home log",
        "text_hi": "घर का रिकॉर्ड लाएँ",
        "text_ta": "வீட்டுப் பதிவைக் கொண்டு வாருங்கள்",
        "text_bn": "বাড়ির রেকর্ড আনুন",
        "text_or": "ଘରର ରେକର୍ଡ ଆଣନ୍ତୁ",
        "text_te": "ఇంటి రికార్డు తీసుకురండి",
    }
]
store.db.briefs.insert_one({"patient_id": "PRP-REVIEW", "brief": brief})
store.db.appointments.insert_one(
    {
        "appointment_id": "APT-REVIEW",
        "patient_id": "PRP-REVIEW",
        "doctor_id": "doctor",
        "date": local_day().isoformat(),
        "time": "10:30",
        "status": "scheduled",
        "reason": "Test follow-up",
    }
)


def fixture_translation(plan):
    import copy

    result = copy.deepcopy(plan)
    for item in result["items"]:
        item["texts"] = {
            lang: item.get("texts", {}).get(lang) or item["text"] for lang in care.LANGUAGES
        }
    result["notes_texts"] = {lang: result.get("doctor_notes", "") for lang in care.LANGUAGES}
    result["translation_status"] = "complete"
    return result


care.translate_plan = fixture_translation
