from __future__ import annotations

import copy
import importlib
from datetime import timedelta

import fitz
import pytest
from fastapi.testclient import TestClient
from test_ui_api import login
from test_ui_api import workspace as workspace_fixture  # noqa: F401

from preppulse_api.app import app
from preppulse_api.care import end_date, local_day, pdf_bytes, tasks_for


@pytest.fixture
def workspace(workspace_fixture):  # noqa: F811
    return workspace_fixture


@pytest.fixture(autouse=True)
def isolated_jobs(monkeypatch, tmp_path):
    api = importlib.import_module("preppulse_api.app")
    care = importlib.import_module("preppulse_api.care")
    clinical = importlib.import_module("preppulse_api.clinical")
    folder = importlib.import_module("preppulse_api.folder_import")
    monkeypatch.setattr(api.workers, "submit", lambda *args, **kwargs: None)
    monkeypatch.setattr(care, "PRIVATE_ROOT", tmp_path)
    monkeypatch.setattr(clinical, "PRIVATE_ROOT", tmp_path)
    monkeypatch.setattr(folder, "PRIVATE_ROOT", tmp_path)


def setup_people(workspace):
    admin = TestClient(app)
    ah = login(admin, "admin", "correct-long-password")
    accounts = {}
    for role in ("doctor", "caregiver"):
        response = admin.post(
            "/api/admin/accounts",
            json={
                "name": role.title(),
                "username": role,
                "password": "test-long-password",
                "role": role,
                **({"caregiver_type": "family"} if role == "caregiver" else {}),
            },
            headers=ah,
        )
        assert response.status_code == 200, response.text
        accounts[role] = response.json()
    response = admin.post(
        "/api/patients",
        json={
            "name": "Test Patient",
            "age": 45,
            "sex": "Female",
            "doctor_id": accounts["doctor"]["user_id"],
        },
        headers=ah,
    )
    assert response.status_code == 200, response.text
    patient = response.json()
    assert patient["age"] == 45
    admin.post(
        "/api/admin/caregiver-assignments",
        json={
            "patient_id": patient["patient_id"],
            "caregiver_id": accounts["caregiver"]["user_id"],
            "kind": "family",
        },
        headers=ah,
    ).raise_for_status()
    doctor = TestClient(app)
    dh = login(doctor, "doctor", "test-long-password")
    caregiver = TestClient(app)
    ch = login(caregiver, "caregiver", "test-long-password")
    return admin, ah, doctor, dh, caregiver, ch, patient, accounts


def start_and_save(doctor, dh, patient):
    pid = patient["patient_id"]
    visit = doctor.post(f"/api/patients/{pid}/visits", json={}, headers=dh).json()
    data = doctor.get(f"/api/care/patients/{pid}").json()
    draft = data["draft"]
    draft.update(
        items=[
            {
                "item_id": "check-1",
                "text": "Bring the home log",
                "frequency": "daily",
                "source_language": "en",
            }
        ],
        doctor_notes="Review in 7 days",
        medications=[
            {
                "medication_id": "med-1",
                "name": "Prescribed medicine",
                "dose": "One tablet",
                "kind": "medicine",
                "start_date": local_day().isoformat(),
                "duration": 7,
                "duration_unit": "days",
                "times": ["morning", "evening"],
                "food": "after food",
            }
        ],
    )
    response = doctor.put(f"/api/care/visits/{visit['visit_id']}/draft", json=draft, headers=dh)
    assert response.status_code == 200, response.text
    return visit, response.json()


def test_caregiver_signoff_reports_notes_and_permissions(workspace):
    admin, ah, doctor, dh, caregiver, ch, patient, accounts = setup_people(workspace)
    pid = patient["patient_id"]
    workspace.db.briefs.insert_one(
        {"patient_id": pid, "brief": {"private_clinical_marker": "doctor only"}}
    )
    visit, draft = start_and_save(doctor, dh, patient)
    assert caregiver.get(f"/api/care/patients/{pid}").json()["draft"] is None
    assert (
        caregiver.put(
            f"/api/care/visits/{visit['visit_id']}/draft", json=draft, headers=ch
        ).status_code
        == 403
    )
    signed = doctor.post(f"/api/visits/{visit['visit_id']}/end", json={"confirm": True}, headers=dh)
    assert signed.status_code == 200, signed.text
    plan = signed.json()
    path_id = plan["pathway_id"]
    persisted = copy.deepcopy(workspace.db.pathways.find_one({"pathway_id": path_id}))
    data = caregiver.get(f"/api/care/patients/{pid}").json()
    assert len(data["plans"]) == 1
    assert "brief_snapshot" not in data["plans"][0]
    assert "document_ids" not in data["plans"][0]
    assert "patient_snapshot" not in data["plans"][0]
    tasks = data["followup"]["tasks"]
    assert len(tasks) == 3
    assert all(not x.get("report") for x in tasks)
    task = tasks[0]
    report = {"task_id": task["task_id"], "day": local_day().isoformat(), "completed": True}
    assert (
        caregiver.put(f"/api/care/pathways/{path_id}/report", json=report, headers=ch).status_code
        == 200
    )
    assert (
        doctor.put(f"/api/care/pathways/{path_id}/report", json=report, headers=dh).status_code
        == 403
    )
    assert (
        caregiver.post(
            f"/api/care/pathways/{path_id}/notes", json={"text": "Home log is ready."}, headers=ch
        ).status_code
        == 200
    )
    review = doctor.get(f"/api/care/pathways/{path_id}").json()
    assert review["tasks"][0]["report"]["completed"] is True
    assert review["notes"][0]["text"] == "Home log is ready."
    assert workspace.db.pathways.find_one({"pathway_id": path_id}) == persisted
    assert caregiver.get(f"/api/patients/{pid}/documents").status_code == 403
    assert caregiver.get(f"/api/patients/{pid}/brief").status_code == 403
    assert caregiver.get("/api/appointment-history").status_code == 403
    assert admin.get(f"/api/care/patients/{pid}").status_code == 403
    assert (
        caregiver.get(f"/api/care/pathways/{path_id}").json()["plan"].get("brief_snapshot") is None
    )
    other = {
        "patient_id": "PRP-OTHER",
        "name": "Other patient",
        "name_search": "other",
        "external_aliases": [],
    }
    workspace.db.patients.insert_one(other)
    assert caregiver.get(f"/api/care/patients/{other['patient_id']}").status_code == 403
    assert [x["patient_id"] for x in caregiver.get("/api/patients").json()] == [pid]
    assert caregiver.get(f"/api/care/pathways/{path_id}/pdf?language=en").content.startswith(
        b"%PDF"
    )
    assert caregiver.get(f"/api/care/pathways/{path_id}/pdf?language=hi").status_code == 409
    record = workspace.db.workspace_documents.find_one({"record_id": path_id})
    assert record and record["status"] == "ready"
    assert doctor.get(f"/api/patients/{pid}/documents/{path_id}/page/1").status_code == 200
    snapshot = doctor.get(f"/api/patients/{pid}/visit-records/{visit['visit_id']}").json()
    assert snapshot["snapshot_available"] is True
    assert snapshot["patient_snapshot"]["age"] == 45
    assert snapshot["brief_snapshot"]["private_clinical_marker"] == "doctor only"
    assert (
        doctor.post(
            f"/api/visits/{visit['visit_id']}/end", json={"confirm": True}, headers=dh
        ).status_code
        == 404
    )
    admin.delete(
        f"/api/admin/caregiver-assignments/{accounts['caregiver']['user_id']}/{pid}", headers=ah
    ).raise_for_status()
    assert caregiver.get(f"/api/care/pathways/{path_id}").status_code == 403


def test_daily_reset_overdue_and_future_reporting(workspace):
    _, _, doctor, dh, caregiver, ch, patient, _ = setup_people(workspace)
    visit, _ = start_and_save(doctor, dh, patient)
    plan = doctor.post(
        f"/api/visits/{visit['visit_id']}/end", json={"confirm": True}, headers=dh
    ).json()
    pid, path = patient["patient_id"], plan["pathway_id"]
    yesterday = local_day() - timedelta(days=1)
    workspace.db.pathways.update_one(
        {"pathway_id": path},
        {
            "$set": {
                "approved_day": yesterday.isoformat(),
                "medications.0.start_date": yesterday.isoformat(),
            }
        },
    )
    view = caregiver.get(f"/api/care/patients/{pid}").json()
    assert view["followup"]["past_due_unreported"] == 3
    prior = caregiver.get(f"/api/care/pathways/{path}?day={yesterday.isoformat()}").json()
    task = prior["tasks"][0]
    caregiver.put(
        f"/api/care/pathways/{path}/report",
        json={"task_id": task["task_id"], "day": yesterday.isoformat(), "completed": True},
        headers=ch,
    ).raise_for_status()
    view = caregiver.get(f"/api/care/patients/{pid}").json()
    assert view["followup"]["past_due_unreported"] == 2
    assert not any(x.get("report") for x in view["followup"]["tasks"])
    tomorrow = local_day() + timedelta(days=1)
    assert (
        caregiver.put(
            f"/api/care/pathways/{path}/report",
            json={
                "task_id": f"check-1:{tomorrow.isoformat()}",
                "day": tomorrow.isoformat(),
                "completed": True,
            },
            headers=ch,
        ).status_code
        == 400
    )
    assert (
        caregiver.put(
            f"/api/care/pathways/{path}/report",
            json={"task_id": "made-up", "day": local_day().isoformat(), "completed": True},
            headers=ch,
        ).status_code
        == 400
    )


def test_draft_conflicts_translation_invalidation_and_prescriptions(workspace):
    _, _, doctor, dh, _, _, patient, _ = setup_people(workspace)
    visit, draft = start_and_save(doctor, dh, patient)
    endpoint = f"/api/care/visits/{visit['visit_id']}/draft"
    stale = {**draft, "revision": 0}
    assert doctor.put(endpoint, json=stale, headers=dh).status_code == 409
    workspace.db.care_drafts.update_one(
        {"visit_id": visit["visit_id"]}, {"$set": {"items.0.texts.hi": "पुराना निर्देश"}}
    )
    draft["items"][0]["text"] = "Bring the new log"
    changed = doctor.put(endpoint, json=draft, headers=dh).json()
    assert changed["items"][0]["texts"] == {"en": "Bring the new log"}
    changed["medications"][0]["duration"] = 25
    changed["medications"][0]["duration_unit"] = "months"
    assert doctor.put(endpoint, json=changed, headers=dh).status_code == 400
    changed["medications"][0]["duration"] = 2
    changed["medications"][0]["times"] = []
    assert doctor.put(endpoint, json=changed, headers=dh).status_code == 422


def test_appointment_history_and_visit_link(workspace):
    admin, ah, doctor, dh, _, _, patient, accounts = setup_people(workspace)
    for day in (local_day() - timedelta(days=3), local_day()):
        response = admin.post(
            "/api/appointments",
            json={
                "patient_id": patient["patient_id"],
                "doctor_id": accounts["doctor"]["user_id"],
                "date": day.isoformat(),
                "time": "10:30",
            },
            headers=ah,
        )
        assert response.status_code == 200, response.text
    assert admin.get("/api/appointment-history").json()["total"] == 1
    assert (
        doctor.get(f"/api/appointment-history?scope=all&q={patient['patient_id']}").json()["total"]
        == 2
    )
    assert admin.get(f"/api/appointment-history?on={local_day().isoformat()}").json()["total"] == 1
    visit, _ = start_and_save(doctor, dh, patient)
    doctor.post(
        f"/api/visits/{visit['visit_id']}/end", json={"confirm": True}, headers=dh
    ).raise_for_status()
    row = doctor.get(f"/api/appointment-history?on={local_day().isoformat()}").json()[
        "appointments"
    ][0]
    assert row["visit_id"] == visit["visit_id"] and row["status"] == "completed"


def test_pdf_pagination_and_indic_text():
    from preppulse_api.care_labels import CARE_LABELS

    plan = {
        "pathway_id": "PATH-TEST",
        "patient_id": "PRP-TEST",
        "visit_id": "VIS-TEST",
        "approved_at": "2026-11-03T10:00:00",
        "approved_by": "doctor",
        "mode": "family",
        "doctor_notes": "",
        "medications": [],
        "items": [],
    }
    for i in range(80):
        plan["items"].append(
            {
                "item_id": str(i),
                "text": "Keep the home log. " * 8,
                "texts": {"hi": "घर पर अपना रिकॉर्ड रखें। " * 8},
                "frequency": "once",
            }
        )
    data = pdf_bytes(plan, {"name": "Test Patient", "patient_id": "PRP-TEST"}, "hi")
    doc = fitz.open(stream=data, filetype="pdf")
    assert len(doc) > 1
    text = "".join(p.get_text() for p in doc)
    assert "PrepPulse" in text and "घर" in text
    assert CARE_LABELS["hi"]["checklist"] in text
    doc.close()


def test_month_duration_and_dated_tasks():
    med = {
        "medication_id": "M",
        "name": "Test",
        "dose": "one",
        "start_date": "2026-01-31",
        "duration": 1,
        "duration_unit": "months",
        "times": ["morning"],
    }
    assert end_date(med).isoformat() == "2026-02-27"
    plan = {"approved_at": "2026-01-31T00:00:00", "items": [], "medications": [med]}
    from datetime import date

    assert len(tasks_for(plan, date(2026, 2, 27))) == 1
    assert tasks_for(plan, date(2026, 2, 28)) == []


def test_folder_upload_attaches_to_registered_patient_and_updates_demographics(workspace):
    admin, ah, _, _, _, _, patient, accounts = setup_people(workspace)
    pid = patient["patient_id"]
    data = {
        "doctor_id": accounts["doctor"]["user_id"],
        "patient_id": pid,
        "name": "Registered Patient",
        "age": "46",
        "sex": "Female",
        "paths": "PP009_Registered_Patient/note.pdf",
    }
    response = admin.post(
        "/api/admin/import-folder",
        data=data,
        files={"files": ("note.pdf", b"%PDF-test", "application/pdf")},
        headers=ah,
    )
    assert response.status_code == 200, response.text
    assert response.json()["patient_id"] == pid
    assert not response.json()["patient_created"]
    assert response.json()["files_saved"] == 1
    response = admin.post(
        "/api/admin/import-folder",
        data=data,
        files={"files": ("note.pdf", b"%PDF-test", "application/pdf")},
        headers=ah,
    )
    assert response.status_code == 200 and response.json()["files_unchanged"] == 1
    assert workspace.db.patients.count_documents({}) == 1
    assert workspace.patient(pid)["age"] == 46
    assert workspace.patient(pid)["name"] == "Registered Patient"
    assert admin.get("/api/patients?q=PP009").json()[0]["patient_id"] == pid
    data["age"] = "200"
    assert (
        admin.post(
            "/api/admin/import-folder",
            data=data,
            files={"files": ("note.pdf", b"%PDF-test", "application/pdf")},
            headers=ah,
        ).status_code
        == 400
    )


def test_translation_preserves_source_numbers_and_refreshes_other_languages(monkeypatch):
    from preppulse_api.care import translate_plan

    translation = importlib.import_module("preppulse_api.care_translation")
    messages = {
        "en": "Review in 7 days",
        "hi": "7 दिनों में समीक्षा करें",
        "ta": "7 நாட்களில் மதிப்பாய்வு",
        "bn": "7 দিনের মধ্যে পর্যালোচনা",
        "or": "7 ଦିନରେ ସମୀକ୍ଷା କରନ୍ତୁ",
        "te": "7 రోజులలో సమీక్షించండి",
    }
    monkeypatch.setattr(
        translation,
        "translate_batch",
        lambda batch, lang: {key: messages[lang] for key, _, _ in batch},
    )
    original = {
        "items": [
            {
                "item_id": "one",
                "text": "Review in 7 days",
                "source_language": "en",
                "texts": {"en": "Review in 7 days"},
            }
        ],
        "doctor_notes": "",
        "medications": [],
    }
    translated = translate_plan(original)
    assert translated["items"][0]["texts"]["hi"] == messages["hi"]
    assert translated["translation_status"] == "complete"
    assert "hi" not in original["items"][0]["texts"]

    monkeypatch.setattr(
        translation,
        "translate_batch",
        lambda batch, lang: {key: messages[lang].replace("7", "9") for key, _, _ in batch},
    )
    with pytest.raises(ValueError, match="number"):
        translate_plan(original)


def test_analysis_can_populate_untouched_draft_but_not_restore_deleted_items(workspace):
    _, _, doctor, dh, _, _, patient, _ = setup_people(workspace)
    pid = patient["patient_id"]
    visit = doctor.post(f"/api/patients/{pid}/visits", json={}, headers=dh).json()
    assert doctor.get(f"/api/care/patients/{pid}").json()["draft"]["items"] == []
    workspace.db.briefs.insert_one(
        {
            "patient_id": pid,
            "brief": {"caregiver_prep": {"checklist": [{"text_en": "Bring the home log"}]}},
        }
    )
    draft = doctor.get(f"/api/care/patients/{pid}").json()["draft"]
    assert len(draft["items"]) == 1
    draft["items"] = []
    assert (
        doctor.put(
            f"/api/care/visits/{visit['visit_id']}/draft", json=draft, headers=dh
        ).status_code
        == 200
    )
    assert doctor.get(f"/api/care/patients/{pid}").json()["draft"]["items"] == []
