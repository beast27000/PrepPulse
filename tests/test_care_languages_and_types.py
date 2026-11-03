from __future__ import annotations

import copy
import importlib

import pytest
from test_caregiver_workflow import setup_people
from test_ui_api import workspace as workspace_fixture  # noqa: F401

from preppulse_api.care_translation import overlay, request_language, run_language_job, usable


@pytest.fixture
def workspace(workspace_fixture):  # noqa: F811
    return workspace_fixture


def sample_plan():
    return {
        "pathway_id": "P-LANGUAGE",
        "visit_id": "V-LANGUAGE",
        "revision": 2,
        "items": [
            {
                "item_id": "one",
                "text": "Bring earlier reports.",
                "source_language": "en",
                "texts": {"ta": "Bring earlier reports."},
            },
            {"item_id": "two", "text": "Record readings for 3 days.", "source_language": "en"},
        ],
        "doctor_notes": "Review after 7 days.",
        "notes_language": "en",
        "medications": [{"medication_id": "m", "dose": "1 tablet after food."}],
    }


def test_caregiver_type_required_change_preserves_keys_and_revokes_old_access(workspace):
    admin, ah, _, _, caregiver, _, patient, accounts = setup_people(workspace)
    response = admin.post(
        "/api/admin/accounts",
        json={
            "name": "Unspecified",
            "username": "unspecified",
            "password": "a-unique-long-password",
            "role": "caregiver",
        },
        headers=ah,
    )
    assert response.status_code == 400
    before = accounts["caregiver"]
    assert caregiver.get(f"/api/care/patients/{patient['patient_id']}").status_code == 200
    changed = admin.patch(
        f"/api/admin/accounts/{before['user_id']}/caregiver-type",
        json={"caregiver_type": "professional"},
        headers=ah,
    )
    assert changed.status_code == 200, changed.text
    after = changed.json()
    assert after["user_id"] == before["user_id"]
    assert after["account_id"].startswith("HCW-")
    assert before["account_id"] in after["account_aliases"]
    assert caregiver.get(f"/api/care/patients/{patient['patient_id']}").status_code == 403
    assert (
        admin.get(f"/api/admin/accounts?q={before['account_id']}").json()[0]["user_id"]
        == before["user_id"]
    )
    assert (
        workspace.db.staff_directory.find_one({"user_id": before["user_id"]})["account_id"]
        == after["account_id"]
    )


def test_caregiver_cannot_read_other_type_even_for_same_patient(workspace):
    admin, ah, _, _, caregiver, ch, patient, accounts = setup_people(workspace)
    for mode in ("family", "caregiver"):
        workspace.db.pathways.insert_one(
            {
                "pathway_id": mode,
                "visit_id": "visit-" + mode,
                "patient_id": patient["patient_id"],
                "mode": mode,
                "items": [],
                "medications": [],
                "approved_at": "2026-11-01T10:00:00+00:00",
                "approved_by": "doctor",
            }
        )
    assert [
        x["mode"]
        for x in caregiver.get(f"/api/care/patients/{patient['patient_id']}").json()["plans"]
    ] == ["family"]
    for suffix in ("", "/pdf"):
        assert caregiver.get("/api/care/pathways/caregiver" + suffix).status_code == 403
    assert (
        caregiver.post(
            "/api/care/pathways/caregiver/translate?language=ta", json={}, headers=ch
        ).status_code
        == 403
    )
    assert (
        caregiver.post(
            "/api/care/pathways/caregiver/notes", json={"text": "denied"}, headers=ch
        ).status_code
        == 403
    )
    uid = accounts["caregiver"]["user_id"]
    admin.patch(
        f"/api/admin/accounts/{uid}/caregiver-type",
        json={"caregiver_type": "professional"},
        headers=ah,
    ).raise_for_status()
    admin.post(
        "/api/admin/caregiver-assignments",
        json={"caregiver_id": uid, "patient_id": patient["patient_id"], "kind": "professional"},
        headers=ah,
    ).raise_for_status()
    assert [
        x["mode"]
        for x in caregiver.get(f"/api/care/patients/{patient['patient_id']}").json()["plans"]
    ] == ["caregiver"]
    assert caregiver.get("/api/care/pathways/family").status_code == 403


def test_translation_rejects_english_copies_and_changed_numbers():
    assert not usable("Bring earlier reports.", "Bring earlier reports.", "ta")
    assert usable("3 நாட்களுக்கு அளவுகளைப் பதிவு செய்யவும்.", "Record readings for 3 days.", "ta")
    assert not usable("4 நாட்களுக்கு அளவுகளைப் பதிவு செய்யவும்.", "Record readings for 3 days.", "ta")
    assert not usable("அளவு 8", "8 mg", "ta")
    assert usable("8 mg", "8 mg", "ta")


def test_preview_translation_is_doctor_only_and_does_not_start_a_visit(workspace):
    _, _, doctor, dh, caregiver, ch, patient, _ = setup_people(workspace)
    pid = patient["patient_id"]
    workspace.db.briefs.insert_one(
        {
            "patient_id": pid,
            "brief": {"caregiver_prep": {"checklist": [{"text_en": "Bring earlier reports."}]}},
        }
    )
    bundle = doctor.get(f"/api/care/patients/{pid}").json()
    assert bundle["suggestions"][0]["text"] == "Bring earlier reports."
    assert bundle["suggestion_revision"] > 0
    result = doctor.post(
        f"/api/care/patients/{pid}/translate-preview?language=ta", json={}, headers=dh
    )
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "queued"
    assert workspace.db.visits.count_documents({}) == 0
    assert workspace.db.care_drafts.count_documents({}) == 0
    assert (
        caregiver.post(
            f"/api/care/patients/{pid}/translate-preview?language=ta", json={}, headers=ch
        ).status_code
        == 403
    )
    assert caregiver.get(f"/api/care/patients/{pid}").json()["suggestions"] == []


def test_per_language_cache_deduplicates_and_preserves_partial_results(workspace, monkeypatch):
    translation = importlib.import_module("preppulse_api.care_translation")
    plan = sample_plan()
    original = copy.deepcopy(plan)
    workspace.db.pathways.insert_one(copy.deepcopy(plan))
    calls = []
    monkeypatch.setattr(translation.executor, "submit", lambda *args: calls.append(args))
    assert (
        request_language(workspace, plan, "signed", plan["pathway_id"], 2, "ta")["status"]
        == "queued"
    )
    request_language(workspace, plan, "signed", plan["pathway_id"], 2, "ta")
    assert len(calls) == 1
    # A local API restart can resume a queued translation from its former worker.
    workspace.db.care_language_cache.update_one(
        {"identity": plan["pathway_id"]}, {"$set": {"worker_instance": "previous-process"}}
    )
    request_language(workspace, plan, "signed", plan["pathway_id"], 2, "ta")
    assert len(calls) == 2
    monkeypatch.setattr(
        importlib.import_module("preppulse_api.store"), "WorkspaceStore", lambda: workspace
    )

    def partial(batch, language):
        return {
            "item:one": "முந்தைய அறிக்கைகளைக் கொண்டு வரவும்.",
            "item:two": "3 நாட்களுக்கு அளவுகளைப் பதிவு செய்யவும்.",
            "notes": "7 நாட்களுக்குப் பிறகு மதிப்பாய்வு செய்யவும்.",
        }

    monkeypatch.setattr(translation, "translate_batch", partial)
    run_language_job("signed", plan["pathway_id"], 2, "ta")
    derived = overlay(workspace, plan, "signed", plan["pathway_id"], 2)
    assert derived["language_status"]["ta"]["status"] == "partial"
    assert derived["language_status"]["ta"]["completed"] == 3
    assert derived["items"][0]["texts"]["ta"].startswith("முந்தைய")
    assert derived["notes_texts"]["ta"].startswith("7")
    assert plan == original
    assert (
        workspace.db.pathways.find_one({"pathway_id": plan["pathway_id"]})["doctor_notes"]
        == original["doctor_notes"]
    )
    # A failed dose segment is retried without discarding the other three.
    monkeypatch.setattr(
        translation,
        "translate_batch",
        lambda batch, language: {"dose:m": "உணவுக்குப் பிறகு 1 மாத்திரை."},
    )
    request_language(workspace, derived, "signed", plan["pathway_id"], 2, "ta")
    run_language_job("signed", plan["pathway_id"], 2, "ta")
    result = overlay(workspace, plan, "signed", plan["pathway_id"], 2)
    assert result["language_status"]["ta"]["status"] == "complete"
    assert result["medications"][0]["dose_texts"]["ta"].endswith("மாத்திரை.")


def test_stale_draft_translation_does_not_appear_in_new_revision(workspace, monkeypatch):
    plan = sample_plan()
    workspace.db.care_drafts.insert_one(copy.deepcopy(plan))
    translation = importlib.import_module("preppulse_api.care_translation")
    monkeypatch.setattr(
        importlib.import_module("preppulse_api.store"), "WorkspaceStore", lambda: workspace
    )

    def changed(batch, language):
        workspace.db.care_drafts.update_one(
            {"visit_id": plan["visit_id"]}, {"$set": {"revision": 3}}
        )
        return {"item:one": "முந்தைய அறிக்கைகளைக் கொண்டு வரவும்."}

    monkeypatch.setattr(translation, "translate_batch", changed)
    run_language_job("draft", plan["visit_id"], 2, "ta")
    current = workspace.db.care_drafts.find_one({"visit_id": plan["visit_id"]})
    assert (
        "ta" not in overlay(workspace, current, "draft", plan["visit_id"], 3)["items"][0]["texts"]
    )
