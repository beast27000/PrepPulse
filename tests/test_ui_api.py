from __future__ import annotations

import importlib
import json
import os

import mongomock
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

os.environ.setdefault("PREPPULSE_SESSION_SECRET", "test-session-secret-with-more-than-32-chars")

from preppulse_api.app import app, db, password_hash
from preppulse_api.clinical import validate_citation
from preppulse_api.folder_import import checked_paths
from preppulse_api.store import WorkspaceStore


@pytest.fixture
def workspace():
    client = mongomock.MongoClient()
    store = WorkspaceStore.__new__(WorkspaceStore)
    store.client = client
    store.db = client["preppulse_test"]
    store.indexes()
    store.db.users.insert_one(
        {
            "user_id": "USR-ADMIN",
            "name": "PrepPulse Admin",
            "username": "admin",
            "role": "admin",
            "password_hash": password_hash.hash("correct-long-password"),
            "disabled": False,
        }
    )

    def override():
        yield store

    app.dependency_overrides[db] = override
    yield store
    app.dependency_overrides.clear()
    client.close()


def login(client: TestClient, username: str, password: str) -> dict:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf"]}


def test_roles_registry_search_and_appointments(workspace):
    with TestClient(app) as admin_client:
        admin_headers = login(admin_client, "admin", "correct-long-password")
        doctor = admin_client.post(
            "/api/admin/accounts",
            json={
                "name": "Dr Anika",
                "username": "anika",
                "password": "doctor-long-password",
                "role": "doctor",
            },
            headers=admin_headers,
        ).json()
        admin_client.post(
            "/api/admin/accounts",
            json={
                "name": "Dr Other",
                "username": "other",
                "password": "doctor-other-password",
                "role": "doctor",
            },
            headers=admin_headers,
        ).json()
        response = admin_client.post(
            "/api/patients",
            json={
                "name": "Sample Patient",
                "dob": "1980-05-01",
                "sex": "Female",
                "doctor_id": doctor["user_id"],
            },
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        patient_id = response.json()["patient_id"]
        assert patient_id.startswith("PRP-")
        workspace.db.patients.update_one(
            {"patient_id": patient_id},
            {"$set": {"external_aliases": ["PP001", "PP001_Sample_Patient"]}},
        )
        workspace.db.patient_aliases.insert_many(
            [
                {"alias": "PP001", "patient_id": patient_id},
                {"alias": "PP001_Sample_Patient", "patient_id": patient_id},
            ]
        )
        appointment = admin_client.post(
            "/api/appointments",
            json={
                "patient_id": patient_id,
                "doctor_id": doctor["user_id"],
                "date": "2026-10-30",
                "time": "10:30",
                "reason": "Follow-up",
            },
            headers=admin_headers,
        )
        assert appointment.status_code == 200, appointment.text
        assert admin_client.get(f"/api/patients/{patient_id}/brief").status_code == 403

    with TestClient(app) as doctor_client:
        doc_headers = login(doctor_client, "anika", "doctor-long-password")
        assert [p["patient_id"] for p in doctor_client.get("/api/patients?q=PP001").json()] == [
            patient_id
        ]
        assert len(doctor_client.get("/api/appointments?date_filter=2026-10-30").json()) == 1
        assert doctor_client.post("/api/patients", json={}, headers=doc_headers).status_code == 403
        assert doctor_client.post(f"/api/patients/{patient_id}/visits", json={}).status_code == 403
        visit = doctor_client.post(
            f"/api/patients/{patient_id}/visits", json={}, headers=doc_headers
        )
        assert visit.status_code == 200, visit.text
        visit_id = visit.json()["visit_id"]
        assert (
            doctor_client.post(
                f"/api/visits/{visit_id}/end", json={"confirm": True}, headers=doc_headers
            ).status_code
            == 400
        )
        assert (
            doctor_client.post(
                f"/api/visits/{visit_id}/notes",
                json={"notes": "Discussed follow-up with patient."},
                headers=doc_headers,
            ).status_code
            == 200
        )
        item = doctor_client.post(
            f"/api/visits/{visit_id}/pathway/items",
            json={"text": "Bring the home log to review."},
            headers=doc_headers,
        )
        assert item.status_code == 200, item.text
        assert (
            doctor_client.patch(
                f"/api/visits/{visit_id}/pathway/items/{item.json()['item_id']}",
                json={"completed": True},
                headers=doc_headers,
            ).status_code
            == 200
        )
        ended = doctor_client.post(
            f"/api/visits/{visit_id}/end", json={"confirm": True}, headers=doc_headers
        )
        assert ended.status_code == 200, ended.text
        assert ended.json()["items"][0]["completed"] is True

    with TestClient(app) as other_client:
        other_headers = login(other_client, "other", "doctor-other-password")
        assert other_client.get("/api/patients?q=PP001").json() == []
        assert other_client.get(f"/api/patients/{patient_id}").status_code == 403
        assert (
            other_client.post(
                "/api/chat/query",
                json={"patient_id": patient_id, "query": "labs?"},
                headers=other_headers,
            ).status_code
            == 403
        )


def test_citation_requires_matching_ocr_span(workspace):
    workspace.db.workspace_documents.insert_one({"record_id": "DOC-1", "patient_id": "PRP-1"})
    workspace.db.patient_documents.insert_one(
        {
            "document_id": "DOC-1",
            "patient_id": "PRP-1",
            "stage_1_raw_ocr": {
                "pages": [
                    {
                        "page_number": 2,
                        "tokens": [
                            {"text": "HbA1c", "bbox": [100, 200, 145, 225]},
                            {"text": "8.4", "bbox": [150, 200, 175, 225]},
                        ],
                    }
                ]
            },
        }
    )
    citation = {
        "document_id": "DOC-1",
        "page_number": 2,
        "bbox": [95, 195, 180, 230],
        "snippet": "HbA1c 8.4",
    }
    assert validate_citation(workspace, "PRP-1", citation)
    assert not validate_citation(workspace, "PRP-2", citation)
    assert not validate_citation(workspace, "PRP-1", {**citation, "bbox": [0, 0, 1000, 1000]})
    assert not validate_citation(workspace, "PRP-1", {**citation, "snippet": "insulin dose"})


def test_one_folder_import_preserves_files_ids_and_admin_overview(workspace, tmp_path, monkeypatch):
    api_module = importlib.import_module("preppulse_api.app")
    folder_module = importlib.import_module("preppulse_api.folder_import")
    private = tmp_path / "private"
    monkeypatch.setattr(folder_module, "PRIVATE_ROOT", private)
    monkeypatch.setattr(api_module.workers, "submit", lambda *args: None)
    manifest = json.dumps(
        {
            "patient_folder": "PP002_Ananya_Baruah",
            "name": "Wrong Manifest Name",
            "records": [{"file": "record.pdf", "date": "2026-10-30", "type": "lab"}],
        }
    ).encode()
    paths = [
        "PP001_Ananya_Baruah/record.pdf",
        "PP001_Ananya_Baruah/manifest.json",
        "PP001_Ananya_Baruah/RECORD_INDEX.txt",
    ]

    def upload_files():
        return [
            ("files", ("record.pdf", b"%PDF-1.4\n", "application/pdf")),
            ("files", ("manifest.json", manifest, "application/json")),
            ("files", ("RECORD_INDEX.txt", b"One record", "text/plain")),
        ]

    with TestClient(app) as client:
        headers = login(client, "admin", "correct-long-password")
        doctor = client.post(
            "/api/admin/accounts",
            json={
                "name": "Dr Anika",
                "username": "anika",
                "password": "doctor-long-password",
                "role": "doctor",
            },
            headers=headers,
        ).json()
        patient_id = None
        for saved in (3, 0):
            response = client.post(
                "/api/admin/import-folder",
                data={"doctor_id": doctor["user_id"], "paths": paths},
                files=upload_files(),
                headers=headers,
            )
            assert response.status_code == 200, response.text
            assert response.json()["files_saved"] == saved
            if patient_id:
                assert response.json()["patient_id"] == patient_id
            patient_id = response.json()["patient_id"]
        assert workspace.db.patients.count_documents({}) == 1
        assert workspace.db.workspace_documents.count_documents({}) == 1
        assert workspace.db.workspace_files.count_documents({}) == 3
        patient = workspace.db.patients.find_one()
        assert patient["name"] == "Ananya Baruah"
        assert "PP001" in patient["external_aliases"]
        assert "PP002" not in patient["external_aliases"]
        assert list(private.rglob("record.pdf"))
        doc = workspace.db.workspace_documents.find_one()
        assert doc["source_path"].startswith(str(private))
        overview = client.get(f"/api/admin/patients/{patient_id}/overview")
        assert overview.status_code == 200
        assert overview.json()["stored_files"] == 3
        assert len(overview.json()["documents"]) == 1
        assert "source_path" not in overview.text
        assert "password_hash" not in overview.text
        assert (
            client.post(
                "/api/admin/import-folder",
                data={"doctor_id": doctor["user_id"], "paths": ["PP001_Other_Name/record.pdf"]},
                files=[upload_files()[0]],
                headers=headers,
            ).status_code
            == 409
        )
    with TestClient(app) as doctor_client:
        doctor_headers = login(doctor_client, "anika", "doctor-long-password")
        assert doctor_client.get(f"/api/admin/patients/{patient_id}/overview").status_code == 403
        assert (
            doctor_client.post(
                "/api/admin/import-folder",
                data={"doctor_id": doctor["user_id"], "paths": paths},
                files=upload_files(),
                headers=doctor_headers,
            ).status_code
            == 403
        )


def test_read_aloud_requires_assigned_doctor_and_audio_runtime(workspace, monkeypatch):
    api_module = importlib.import_module("preppulse_api.app")
    monkeypatch.setattr(api_module, "tts_ready", lambda: False)
    with TestClient(app) as client:
        headers = login(client, "admin", "correct-long-password")
        doctor = client.post(
            "/api/admin/accounts",
            json={
                "name": "Dr Anika",
                "username": "anika",
                "password": "doctor-long-password",
                "role": "doctor",
            },
            headers=headers,
        ).json()
        patient = client.post(
            "/api/patients",
            json={"name": "Sample Patient", "doctor_id": doctor["user_id"]},
            headers=headers,
        ).json()
        payload = {"patient_id": patient["patient_id"], "text": "Voice check."}
        assert client.post("/api/voice/speak", json=payload, headers=headers).status_code == 403
    with TestClient(app) as client:
        headers = login(client, "anika", "doctor-long-password")
        assert client.get("/api/voice/capabilities").json()["tts_ready"] is False
        assert client.post("/api/voice/speak", json=payload, headers=headers).status_code == 503
        monkeypatch.setattr(api_module, "tts_ready", lambda: True)
        monkeypatch.setattr(api_module, "synthesize", lambda text: b"RIFF" + b"\0" * 36 + b"WAVE")
        response = client.post("/api/voice/speak", json=payload, headers=headers)
        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/wav"
        assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "paths",
    [
        ["PP001_Ananya_Baruah/record.pdf", "PP002_Other_Patient/other.pdf"],
        ["PP001_Ananya_Baruah/../escape.pdf"],
        ["PP001_Ananya_Baruah/record.pdf", "PP001_Ananya_Baruah/RECORD.pdf"],
        ["invalid-folder/record.pdf"],
    ],
)
def test_folder_selection_rejects_unsafe_or_ambiguous_paths(paths):
    with pytest.raises(HTTPException):
        checked_paths(paths)
