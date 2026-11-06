from datetime import timedelta
import importlib

import pytest
from test_ui_api import workspace as workspace_fixture
from test_caregiver_workflow import setup_people
from preppulse_api.care import local_day
from preppulse_api.operations import linked_queries, job_status


@pytest.fixture
def workspace(workspace_fixture, monkeypatch, tmp_path):
    monkeypatch.setattr(importlib.import_module("preppulse_api.operations"), "PRIVATE_ROOT", tmp_path)
    return workspace_fixture


def test_future_visit_lock_allows_review_and_today_start(workspace):
    admin, ah, doctor, dh, _, _, patient, accounts = setup_people(workspace)
    pid = patient["patient_id"]
    future = (local_day() + timedelta(days=2)).isoformat()
    row = admin.post("/api/appointments", headers=ah, json={"patient_id": pid,
        "doctor_id": accounts["doctor"]["user_id"], "date": future, "time": "10:30"})
    assert row.status_code == 200
    blocked = doctor.post(f"/api/patients/{pid}/visits", headers=dh, json={})
    assert blocked.status_code == 409 and future in blocked.json()["detail"]
    assert doctor.get(f"/api/patients/{pid}/documents").status_code == 200
    assert doctor.get("/api/appointments?scope=all").json()[0]["date"] == future
    workspace.db.appointments.update_one({"patient_id": pid}, {"$set": {"date": local_day().isoformat()}})
    assert doctor.post(f"/api/patients/{pid}/visits", headers=dh, json={}).status_code == 200


def test_deletion_fences_workers_preserves_other_patients_and_original_dataset(workspace, tmp_path):
    admin, ah, doctor, dh, _, _, patient, _ = setup_people(workspace)
    pid = patient["patient_id"]
    root = tmp_path / pid
    root.mkdir()
    (root / "record.pdf").write_bytes(b"original")
    outside = tmp_path / "dataset.pdf"
    outside.write_bytes(b"keep")
    workspace.db.workspace_documents.insert_one({"record_id": "DOC-X", "patient_id": pid, "source_path": str(root / "record.pdf")})
    workspace.db.workspace_documents.insert_one({"record_id": "DOC-OTHER", "patient_id": "PRP-OTHER"})
    workspace.db.patient_aliases.insert_one({"alias": "PP006", "patient_id": pid})
    workspace.db.chat_sessions.insert_one({"session_id": "SES-X", "patient_id": pid})
    workspace.db.chat_messages.insert_one({"session_id": "SES-X", "message_id": "MSG-X", "text": "private"})
    workspace.db.pathways.insert_one({"pathway_id": "PATH-X", "patient_id": pid})
    workspace.db.care_reports.insert_one({"pathway_id": "PATH-X", "task_id": "task"})
    path = f"/api/admin/patients/{pid}"
    assert doctor.request("DELETE", path, json={"confirm_id": pid}, headers=dh).status_code == 403
    assert admin.request("DELETE", path, json={"confirm_id": "wrong"}, headers=ah).status_code == 400
    workspace.db.jobs.insert_one({"job_id": "JOB-X", "patient_id": pid, "status": "running"})
    assert admin.request("DELETE", path, json={"confirm_id": pid}, headers=ah).status_code == 409
    assert doctor.post(f"/api/patients/{pid}/brief/jobs", json={}, headers=dh).status_code == 409
    workspace.db.jobs.update_one({"job_id": "JOB-X"}, {"$set": {"status": "failed"}})
    response = admin.request("DELETE", path, json={"confirm_id": pid}, headers=ah)
    assert response.status_code == 200, response.text
    assert not root.exists() and outside.exists()
    assert not workspace.patient(pid)
    assert workspace.db.workspace_documents.count_documents({}) == 1
    assert not workspace.db.chat_messages.count_documents({})
    assert not workspace.db.care_reports.count_documents({})
    assert not workspace.db.patient_aliases.count_documents({"alias": "PP006"})
    assert admin.request("DELETE", path, json={"confirm_id": pid}, headers=ah).status_code == 200


def test_record_removal_invalidates_mutable_outputs_and_protects_signed_plans(workspace, tmp_path):
    admin, ah, _, _, _, _, patient, _ = setup_people(workspace)
    pid = patient["patient_id"]
    root = tmp_path / pid
    root.mkdir()
    source = root / "upload.pdf"
    source.write_bytes(b"source")
    workspace.db.workspace_documents.insert_one({"record_id": "DOC-X", "patient_id": pid,
        "source_path": str(source), "file_id": "FILE-X", "document_type": "lab"})
    workspace.db.workspace_files.insert_one({"file_id": "FILE-X", "patient_id": pid})
    for name in ("patient_documents", "document_chunks", "fhir_versions"):
        workspace.db[name].insert_one({"patient_id": pid, "document_id": "DOC-X"})
    workspace.db.briefs.insert_one({"patient_id": pid, "brief": {"sensitive": "source"}})
    workspace.db.workspace_documents.insert_one({"record_id": "PATH-X", "patient_id": pid,
        "document_type": "care_pathway"})
    path = f"/api/admin/patients/{pid}/documents/"
    assert admin.request("DELETE", path + "PATH-X", json={"confirm_id": "PATH-X"}, headers=ah).status_code == 409
    result = admin.request("DELETE", path + "DOC-X", json={"confirm_id": "DOC-X"}, headers=ah)
    assert result.status_code == 200, result.text
    assert not source.exists() and not workspace.db.briefs.count_documents({})
    assert workspace.patient(pid) and not workspace.patient(pid).get("maintenance")
    assert workspace.db.workspace_documents.find_one({"record_id": "PATH-X"})
    assert not workspace.db.patient_documents.count_documents({"document_id": "DOC-X"})


def test_full_cleanup_can_resume_after_storage_failure(workspace, monkeypatch, tmp_path):
    admin, ah, _, _, _, _, patient, _ = setup_people(workspace)
    pid = patient["patient_id"]
    root = tmp_path / pid
    root.mkdir()
    (root / "private.pdf").write_bytes(b"private")
    operations = importlib.import_module("preppulse_api.operations")
    actual = operations.shutil.rmtree
    monkeypatch.setattr(operations.shutil, "rmtree", lambda *args: (_ for _ in ()).throw(OSError("Storage temporarily unavailable")))
    with pytest.raises(OSError):
        admin.request("DELETE", f"/api/admin/patients/{pid}", headers=ah, json={"confirm_id": pid})
    assert workspace.patient(pid)["maintenance"]
    assert workspace.db.patient_deletions.find_one({"patient_id": pid})
    assert admin.get(f"/api/admin/patients/{pid}/overview").status_code == 200
    monkeypatch.setattr(operations.shutil, "rmtree", actual)
    result = admin.request("DELETE", f"/api/admin/patients/{pid}", headers=ah, json={"confirm_id": pid})
    assert result.status_code == 200 and not root.exists() and not workspace.patient(pid)


def test_queue_reports_waiting_and_position(workspace, monkeypatch):
    monkeypatch.setenv("PREPPULSE_DURABLE_JOBS", "1")
    workspace.db.worker_tasks.insert_one({"function": "_job", "status": "running", "created_at": "2026-01-01"})
    value = job_status(workspace, {"status": "queued", "created_at": "2026-01-02"})
    assert value["stage"] == "Waiting for processing" and value["queue_position"] == 2


def test_provider_probe_is_staff_only_and_contains_no_patient_data(workspace, monkeypatch):
    admin, ah, doctor, dh, caregiver, ch, _, _ = setup_people(workspace)
    calls = []
    monkeypatch.setattr("preppulse_api.operations.local_probe", lambda: calls.append("nonclinical probe"))
    assert doctor.get("/api/ai/status").status_code == 200
    result = doctor.post("/api/ai/test", headers=dh)
    assert result.status_code == 200, result.text
    assert result.json()["providers"][0]["status"] == "healthy"
    assert calls == ["nonclinical probe"]
    assert caregiver.post("/api/ai/test", headers=ch).status_code == 403
    assert admin.post("/api/ai/test").status_code == 403


def test_durable_recovery_uses_queue_even_if_api_has_stale_local_tracking(workspace, monkeypatch):
    api = importlib.import_module("preppulse_api.app")
    if not hasattr(api, "durable_jobs"):
        pytest.skip("Local UI uses its in-process executor")
    monkeypatch.setenv("PREPPULSE_DURABLE_JOBS", "1")
    job = {"job_id": "JOB-STOPPED", "patient_id": "PRP-TEST", "status": "running"}
    workspace.db.jobs.insert_one(dict(job))
    api.active_brief_jobs.add(job["job_id"])
    try:
        recovered = api.recover_brief_job(workspace, job)
        assert recovered["status"] == "failed"
    finally:
        api.active_brief_jobs.discard(job["job_id"])
