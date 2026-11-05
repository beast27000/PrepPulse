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
from preppulse_api.chat_service import make_chart_artifact, run_chat_turn
from preppulse_api.clinical import annotate_citations, grounded_priority_findings, validate_citation
from preppulse_api.evidence_catalog import build_catalog, enrich_history
from preppulse_api.folder_import import checked_paths
from preppulse_api.store import WorkspaceStore


@pytest.fixture
def workspace(monkeypatch, tmp_path):
    # No test worker or generated pathway may touch the live local workspace.
    api_module = importlib.import_module("preppulse_api.app")
    monkeypatch.setattr(api_module.workers, "submit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        importlib.import_module("preppulse_api.care_translation").executor,
        "submit",
        lambda *args, **kwargs: None,
    )
    for module_name in (
        "preppulse_api.app",
        "preppulse_api.care",
        "preppulse_api.clinical",
        "preppulse_api.folder_import",
    ):
        monkeypatch.setattr(importlib.import_module(module_name), "PRIVATE_ROOT", tmp_path)
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
    precise = annotate_citations(workspace, "PRP-1", citation)
    assert precise["source_verified"] is True
    assert precise["bbox"] == [100, 200, 175, 225]
    assert not validate_citation(workspace, "PRP-2", citation)
    assert not validate_citation(workspace, "PRP-1", {**citation, "bbox": [0, 0, 1000, 1000]})
    assert not validate_citation(workspace, "PRP-1", {**citation, "snippet": "insulin dose"})


def test_priority_findings_require_precise_source():
    verified = {
        "document_id": "DOC-1",
        "page_number": 1,
        "bbox": [10, 20, 30, 40],
        "source_verified": True,
        "extracted_text": "HbA1c 8.3 percent",
    }
    brief = {
        "priority_findings": [
            {"title": "Unverified claim", "citation": {"source_verified": False}},
            {
                "title": "Unsupported surgery",
                "citation": {**verified, "extracted_text": "HbA1c 8.3 percent"},
            },
        ],
        "trajectory": {
            "kpis": [
                {
                    "name": "HbA1c",
                    "value": "8.3",
                    "unit": "%",
                    "date_str": "2026-10-08",
                    "citation": verified,
                },
                {"name": "Other", "value": "99", "citation": {"source_verified": False}},
                {"name": "HbA1c", "value": "9.9", "citation": verified},
            ]
        },
    }
    findings = grounded_priority_findings(brief)
    assert len(findings) == 1
    assert findings[0]["title"] == "HbA1c: 8.3%"
    assert findings[0]["citation"]["source_verified"] is True


def test_record_search_is_patient_scoped(workspace):
    workspace.db.users.insert_one(
        {
            "user_id": "USR-DOC",
            "name": "Doctor",
            "username": "doctor",
            "role": "doctor",
            "password_hash": password_hash.hash("doctor-long-password"),
            "disabled": False,
        }
    )
    workspace.db.patients.insert_one({"patient_id": "PRP-1", "name": "Patient One"})
    workspace.db.patient_access.insert_one({"patient_id": "PRP-1", "doctor_id": "USR-DOC"})
    workspace.db.workspace_documents.insert_one(
        {"patient_id": "PRP-1", "record_id": "DOC-1", "filename": "labs.pdf"}
    )
    workspace.db.patient_documents.insert_one(
        {
            "patient_id": "PRP-1",
            "document_id": "DOC-1",
            "stage_1_raw_ocr": {
                "pages": [
                    {
                        "page_number": 1,
                        "full_text": "HbA1c 8.3 percent",
                        "tokens": [{"text": "HbA1c", "bbox": [10, 20, 40, 30]}],
                    }
                ]
            },
        }
    )
    with TestClient(app) as client:
        login(client, "doctor", "doctor-long-password")
        response = client.get("/api/patients/PRP-1/documents/search?q=HbA1c")
        assert response.status_code == 200
        assert response.json()[0]["document_id"] == "DOC-1"
        assert response.json()[0]["bbox"] == [10, 20, 40, 30]
        assert client.get("/api/patients/PRP-2/documents/search?q=HbA1c").status_code == 404
    with TestClient(app) as client:
        login(client, "admin", "correct-long-password")
        assert client.get("/api/patients/PRP-1/documents/search?q=HbA1c").status_code == 403


def seed_chat_patient(workspace):
    for username in ("first", "second"):
        workspace.db.users.insert_one(
            {
                "user_id": username,
                "name": username,
                "username": username,
                "role": "doctor",
                "password_hash": password_hash.hash("doctor-test-password"),
                "disabled": False,
            }
        )
        workspace.db.patient_access.insert_one({"doctor_id": username, "patient_id": "PRP-CHAT"})
    workspace.db.patients.insert_one({"patient_id": "PRP-CHAT", "name": "Chart Patient"})
    workspace.db.workspace_documents.insert_one(
        {
            "record_id": "DOC-CHAT",
            "patient_id": "PRP-CHAT",
            "filename": "2025_Labs.pdf",
            "visit_date": "2025-01-01",
            "document_type": "lab",
        }
    )
    workspace.db.patient_documents.insert_one(
        {
            "document_id": "DOC-CHAT",
            "patient_id": "PRP-CHAT",
            "stage_1_raw_ocr": {
                "pages": [
                    {
                        "page_number": 1,
                        "full_text": "HbA1c 7.2 <5.7 %",
                        "tokens": [
                            {"text": "HbA1c", "bbox": [100, 200, 170, 212]},
                            {"text": "7.2", "bbox": [400, 200, 430, 212]},
                            {"text": "<5.7", "bbox": [600, 200, 640, 212]},
                            {"text": "%", "bbox": [800, 200, 815, 212]},
                        ],
                    }
                ]
            },
        }
    )


def test_chart_tool_uses_ocr_values_and_new_artifact_ids(workspace):
    seed_chat_patient(workspace)
    catalog = build_catalog(workspace, "PRP-CHAT")
    assert catalog["metric_series"][0]["points"][0]["value"] == 7.2
    original_summary = catalog["record_summaries"][0]["summary"]
    assert enrich_history(catalog, None)["record_summaries"][0]["summary"] == original_summary
    first = make_chart_artifact(catalog, "Chart HbA1c", "CHAT-1", "PRP-CHAT")
    second = make_chart_artifact(catalog, "Chart HbA1c", "CHAT-1", "PRP-CHAT")
    assert first["artifact_id"] != second["artifact_id"]
    assert first["series"][0]["points"][0]["citation"]["bbox"] == [100, 200, 815, 212]
    assert make_chart_artifact(catalog, "Chart eGFR", "CHAT-1", "PRP-CHAT") is None
    assert make_chart_artifact(catalog, "Chart weight", "CHAT-1", "PRP-CHAT") is None
    assert make_chart_artifact(catalog, "Chart blood pressure", "CHAT-1", "PRP-CHAT") is None


def test_chart_request_never_waits_for_embedding_or_chat_model(workspace, monkeypatch):
    seed_chat_patient(workspace)
    module = importlib.import_module("preppulse_api.chat_service")

    def forbidden(*args, **kwargs):
        raise AssertionError("Chart generation must not call a model service")

    monkeypatch.setattr(module, "retriever_for_patient", forbidden)
    monkeypatch.setattr(module.LLMFactory, "get_chat_model", forbidden)
    result = run_chat_turn(
        workspace,
        {"patient_id": "PRP-CHAT", "session_id": "CHAT-1"},
        "Chart HbA1c",
        [],
        lambda *args: None,
    )
    assert result["artifacts"][0]["series"][0]["points"][0]["value"] == 7.2
    assert "cannot create" not in result["text"].lower()
    assert "| Measurement |" in result["text"]


@pytest.mark.parametrize(
    "question",
    ["Chart the heart disease journey", "Plot cardiac history", "Chart ejection fraction"],
)
def test_cardiac_chart_requests_explain_scope_without_unrelated_plot(workspace, question):
    seed_chat_patient(workspace)
    result = run_chat_turn(
        workspace,
        {"patient_id": "PRP-CHAT", "session_id": "CHAT-1"},
        question,
        [],
        lambda *args: None,
    )
    assert result["artifacts"] == []
    assert "Chart scope warning" in result["text"]
    assert "blood pressure" in result["text"]
    assert "outside the current diabetes agent's scope" in result["text"]


def test_chart_catalog_preserves_different_same_day_reports(workspace):
    seed_chat_patient(workspace)
    record = workspace.db.workspace_documents.find_one({}, {"_id": 0})
    workspace.db.workspace_documents.insert_one({**record, "record_id": "DOC-SECOND"})
    document = workspace.db.patient_documents.find_one({}, {"_id": 0})
    document["document_id"] = "DOC-SECOND"
    document["stage_1_raw_ocr"]["pages"][0]["tokens"][1]["text"] = "8.1"
    workspace.db.patient_documents.insert_one(document)
    points = build_catalog(workspace, "PRP-CHAT")["metric_series"][0]["points"]
    assert {point["value"] for point in points} == {7.2, 8.1}
    assert {point["citation"]["document_id"] for point in points} == {"DOC-CHAT", "DOC-SECOND"}


def test_interrupted_analysis_can_be_retried(workspace, monkeypatch):
    seed_chat_patient(workspace)
    api_module = importlib.import_module("preppulse_api.app")
    monkeypatch.setattr(api_module.workers, "submit", lambda *args: None)
    workspace.db.jobs.insert_one(
        {
            "job_id": "JOB-INTERRUPTED",
            "patient_id": "PRP-CHAT",
            "status": "running",
            "created_at": "2026-01-01T00:00:00Z",
        }
    )
    insert_job = workspace.db.jobs.insert_one

    def insert_and_poll(job):
        result = insert_job(job)
        assert api_module.recover_brief_job(workspace, job)["status"] == "queued"
        return result

    monkeypatch.setattr(workspace.db.jobs, "insert_one", insert_and_poll)
    with TestClient(app) as client:
        headers = login(client, "first", "doctor-test-password")
        assert client.get("/api/patients/PRP-CHAT/brief/jobs/latest").json()["status"] == "failed"
        new = client.post("/api/patients/PRP-CHAT/brief/jobs", json={}, headers=headers)
        assert new.status_code == 200, new.text
        assert new.json()["status"] == "queued"
        assert new.json()["job_id"] != "JOB-INTERRUPTED"


def test_chat_sessions_persist_messages_charts_and_enforce_owner(workspace, monkeypatch):
    seed_chat_patient(workspace)
    api_module = importlib.import_module("preppulse_api.app")
    contexts = []
    insert_turn = workspace.db.chat_turns.insert_one

    def insert_and_poll(turn):
        result = insert_turn(turn)
        if turn.get("status") == "queued":
            current = workspace.db.users.find_one({"user_id": "first"})
            session = api_module.owned_chat_session(turn["session_id"], current, workspace)
            assert session["active_turn_id"] == turn["turn_id"]
        return result

    monkeypatch.setattr(workspace.db.chat_turns, "insert_one", insert_and_poll)

    def fake_turn(store, session, question, previous, progress):
        contexts.append(len(previous))
        progress("RAG · retrieving evidence", "retrieval")
        artifact = make_chart_artifact(
            build_catalog(store, session["patient_id"]),
            question,
            session["session_id"],
            session["patient_id"],
        )
        return {
            "message_id": f"MSG-{len(contexts)}",
            "role": "assistant",
            "text": "### Recorded HbA1c\n\n**7.2%** [1]",
            "created_at": "2026-11-02T00:00:00Z",
            "citations": [artifact["series"][0]["points"][0]["citation"]],
            "artifact_ids": [artifact["artifact_id"]],
            "artifacts": [artifact],
            "presentation": {"show_chart": True, "show_source": False},
        }

    monkeypatch.setattr(api_module, "WorkspaceStore", lambda: workspace)
    monkeypatch.setattr(api_module, "run_chat_turn", fake_turn)
    monkeypatch.setattr(api_module.workers, "submit", lambda fn, *args: fn(*args))
    with TestClient(app) as client:
        headers = login(client, "first", "doctor-test-password")
        session = client.post(
            "/api/chat/sessions", json={"patient_id": "PRP-CHAT"}, headers=headers
        ).json()
        sid = session["session_id"]
        for _ in range(2):
            response = client.post(
                f"/api/chat/sessions/{sid}/turns", json={"query": "Chart HbA1c"}, headers=headers
            )
            assert response.status_code == 200, response.text
            assert (
                client.get(f"/api/chat/turns/{response.json()['turn_id']}").json()["status"]
                == "complete"
            )
        saved = client.get(f"/api/chat/sessions/{sid}").json()
        assert len(saved["messages"]) == 4
        assert len(saved["artifacts"]) == 2
        assert contexts == [0, 2]
        assert saved["artifacts"][0]["artifact_id"] != saved["artifacts"][1]["artifact_id"]
        assert client.get("/api/chat/sessions?patient_id=PRP-CHAT").json()[0]["session_id"] == sid
        workspace.db.chat_turns.insert_one(
            {
                "turn_id": "TURN-INTERRUPTED",
                "session_id": sid,
                "user_id": "first",
                "status": "running",
            }
        )
        workspace.db.chat_sessions.update_one(
            {"session_id": sid}, {"$set": {"active_turn_id": "TURN-INTERRUPTED"}}
        )
        assert client.get(f"/api/chat/sessions/{sid}").json()["active_turn"] is None
        assert client.get("/api/chat/turns/TURN-INTERRUPTED").json()["status"] == "failed"
    with TestClient(app) as client:
        login(client, "second", "doctor-test-password")
        assert client.get(f"/api/chat/sessions/{sid}").status_code == 404
        assert client.get("/api/chat/sessions?patient_id=PRP-CHAT").json() == []


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
