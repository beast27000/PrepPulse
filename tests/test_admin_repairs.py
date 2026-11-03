from __future__ import annotations

import copy
from datetime import timedelta

import pytest
from test_caregiver_workflow import setup_people, start_and_save
from test_ui_api import workspace as workspace_fixture  # noqa: F401

from preppulse_api.care import ensure_draft, local_day


@pytest.fixture
def workspace(workspace_fixture):  # noqa: F811
    return workspace_fixture


def test_runtime_and_public_account_ids_are_searchable_and_preserve_keys(workspace):
    admin, ah, doctor, _, _, _, _, accounts = setup_people(workspace)
    assert admin.get("/api/runtime").json()["contract"] == "preppulse-ui-care-2"
    assert (
        "caregiver"
        in admin.get("/openapi.json").json()["components"]["schemas"]["AccountIn"]["properties"][
            "role"
        ]["enum"]
    )
    first = admin.get("/api/admin/accounts").json()
    ids = {a["user_id"]: a["account_id"] for a in first}
    assert ids[accounts["doctor"]["user_id"]].startswith("DOC-")
    assert ids[accounts["caregiver"]["user_id"]].startswith("FAM-")
    assert ids["USR-ADMIN"].startswith("ADM-")
    workspace.indexes()
    assert ids == {a["user_id"]: a["account_id"] for a in admin.get("/api/admin/accounts").json()}
    assert workspace.db.staff_directory.count_documents({}) == len(first)
    assert (
        admin.get(f"/api/admin/accounts?q={ids[accounts['doctor']['user_id']]}").json()[0][
            "user_id"
        ]
        == accounts["doctor"]["user_id"]
    )
    assert doctor.get("/api/admin/accounts").status_code == 403
    created = admin.post(
        "/api/admin/accounts",
        json={
            "name": "Professional Nurse",
            "username": "nurse",
            "password": "long-test-password",
            "role": "caregiver",
            "caregiver_type": "professional",
        },
        headers=ah,
    )
    assert created.status_code == 200, created.text
    assert created.json()["account_id"].startswith("CGV-")
    assert "password_hash" not in created.json()


def test_caregiver_availability_and_type_match(workspace):
    admin, ah, doctor, dh, _, _, patient, accounts = setup_people(workspace)
    caregiver_id = accounts["caregiver"]["user_id"]
    path = f"/api/admin/caregivers/{caregiver_id}/availability"
    assert (
        admin.patch(path, json={"availability": "active"}, headers=ah).json()["availability"]
        == "active"
    )
    assert (
        workspace.db.staff_directory.find_one({"user_id": caregiver_id})["availability"] == "active"
    )
    assert doctor.patch(path, json={"availability": "free"}, headers=dh).status_code == 403
    assert (
        admin.post(
            "/api/admin/caregiver-assignments",
            json={
                "patient_id": patient["patient_id"],
                "caregiver_id": caregiver_id,
                "kind": "professional",
            },
            headers=ah,
        ).status_code
        == 400
    )


def test_directory_record_edits_preserve_original_source_and_signed_dates(workspace):
    admin, ah, doctor, dh, _, _, patient, _ = setup_people(workspace)
    pid = patient["patient_id"]
    record = {
        "record_id": "DOC-META",
        "patient_id": pid,
        "filename": "original.pdf",
        "source_path": "private/original.pdf",
        "visit_date": "2026-01-01",
        "document_type": "consult",
        "status": "ready",
    }
    workspace.db.workspace_documents.insert_one(copy.deepcopy(record))
    response = admin.patch(
        f"/api/admin/patients/{pid}/documents/DOC-META",
        json={
            "display_name": "Corrected display title",
            "document_type": "lab",
            "visit_date": "2026-01-02",
        },
        headers=ah,
    )
    assert response.status_code == 200
    saved = workspace.db.workspace_documents.find_one({"record_id": "DOC-META"})
    assert saved["filename"] == record["filename"] and saved["source_path"] == record["source_path"]
    assert saved["display_name"] == "Corrected display title"
    assert (
        doctor.patch(
            f"/api/admin/patients/{pid}/documents/DOC-META",
            json={"display_name": "X", "document_type": "lab"},
            headers=dh,
        ).status_code
        == 403
    )
    workspace.db.workspace_documents.update_one(
        {"record_id": "DOC-META"}, {"$set": {"document_type": "care_pathway"}}
    )
    assert (
        admin.patch(
            f"/api/admin/patients/{pid}/documents/DOC-META",
            json={"display_name": "Signed", "document_type": "consult", "visit_date": "2026-01-02"},
            headers=ah,
        ).status_code
        == 400
    )
    assert (
        admin.get(f"/api/admin/patients/{pid}/overview").json()["documents"][0]["display_name"]
        == "Corrected display title"
    )


def test_unsigned_checklist_suggestions_remain_doctor_only(workspace):
    _, _, doctor, _, caregiver, _, patient, _ = setup_people(workspace)
    pid = patient["patient_id"]
    workspace.db.briefs.insert_one(
        {
            "patient_id": pid,
            "brief": {"caregiver_prep": {"checklist": [{"text_en": "Private review prompt"}]}},
        }
    )
    assert doctor.get(f"/api/care/patients/{pid}").json()["suggestions"]
    assert caregiver.get(f"/api/care/patients/{pid}").json()["suggestions"] == []


def test_previous_patients_snapshot_isolation_and_checklist_regeneration(workspace):
    admin, _, doctor, dh, _, _, patient, _ = setup_people(workspace)
    pid = patient["patient_id"]
    assert doctor.get("/api/previous-patients").json() == []
    assert admin.get("/api/previous-patients?q=Test").status_code == 403
    visit, _ = start_and_save(doctor, dh, patient)
    assert doctor.get("/api/previous-patients?q=Test").json()[0]["patient"]["patient_id"] == pid
    ended = doctor.post(f"/api/visits/{visit['visit_id']}/end", json={"confirm": True}, headers=dh)
    assert ended.status_code == 200, ended.text
    history = doctor.get(
        f"/api/patients/{pid}/historical-workspace?visit_id={visit['visit_id']}"
    ).json()
    assert history["visit"]["visit_id"] == visit["visit_id"]
    assert history["patient"]["name"] == patient["name"]
    assert (
        doctor.get(f"/api/patients/{pid}/historical-workspace?visit_id=VIS-WRONG").status_code
        == 404
    )
    # Reanalysis must not recreate completed/signed instructions in a subsequent draft.
    workspace.db.briefs.insert_one(
        {
            "patient_id": pid,
            "brief": {"caregiver_prep": {"checklist": [{"text_en": "A new agent suggestion"}]}},
        }
    )
    next_visit = doctor.post(f"/api/patients/{pid}/visits", json={}, headers=dh).json()
    draft = ensure_draft(workspace, next_visit)
    assert draft["items"] == []
    assert draft["previous_pathway_id"] == ended.json()["pathway_id"]
    assert (
        doctor.get(
            f"/api/previous-patients?on={(local_day() - timedelta(days=100)).isoformat()}"
        ).json()
        == []
    )
