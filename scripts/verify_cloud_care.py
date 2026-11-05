"""Real cloud clinician→signed pathway→caregiver→records verification."""
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fitz
import httpx

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / ".tmp/azure_pilot"
BASE = "https://preppulse-pilot-b8bc.centralindia.cloudapp.azure.com"


def main():
    credentials = json.loads((STAGING / "pilot_access.json").read_text())
    clients = {}
    for role in ["admin", "doctor", "caregiver"]:
        client = httpx.Client(base_url=BASE + "/api/", timeout=90, trust_env=False)
        response = client.post("auth/login", json={k: credentials[role][k] for k in ["username", "password"]})
        response.raise_for_status()
        client.headers["X-CSRF-Token"] = response.json()["csrf"]
        client.headers["Origin"] = BASE
        clients[role] = client

    def call(role, method, path, body=None):
        response = clients[role].request(method, path, json=body)
        response.raise_for_status()
        return response.json()

    result = {}
    existing = call("admin", "GET", "patients?q=Deployment%20verification")
    patient = existing[0] if existing else call("admin", "POST", "patients", {"name": "Deployment verification (synthetic)", "age": 45,
        "sex": "Female", "doctor_id": credentials["doctor"]["user_id"]})
    pid = patient["patient_id"]
    result["synthetic_patient_id"] = pid
    call("admin", "POST", "admin/caregiver-assignments", {"patient_id": pid,
        "caregiver_id": credentials["caregiver"]["user_id"], "kind": "family"})
    day = datetime.now(timezone(timedelta(hours=5, minutes=30))).date().isoformat()
    appointment = call("admin", "POST", "appointments", {"patient_id": pid,
        "doctor_id": credentials["doctor"]["user_id"], "date": day, "time": "16:30", "reason": "Synthetic deployment workflow verification"})
    visit = call("doctor", "POST", f"patients/{pid}/visits")
    care = call("doctor", "GET", f"care/patients/{pid}")
    draft = care["draft"]
    saved = call("doctor", "PUT", f"care/visits/{visit['visit_id']}/draft", {
        "revision": draft["revision"], "items": [
            {"text": "Bring earlier reports and prescriptions to the next visit.", "source": "doctor", "frequency": "once"},
            {"text": "Write down new symptoms and questions for the doctor.", "source": "doctor", "frequency": "daily"}],
        "doctor_notes": "Synthetic deployment verification only. Follow the instructions reviewed with the doctor.",
        "medications": [{"name": "Synthetic schedule test (not a prescription)", "dose": "10 mg verification value",
            "kind": "treatment", "start_date": day, "duration": 3, "duration_unit": "days",
            "times": ["morning", "evening"], "food": "after food"}]})
    signed = call("doctor", "POST", f"visits/{visit['visit_id']}/end", {"confirm": True,
        "confirm_evidence_only": True, "draft_revision": saved["revision"]})
    pathway = signed["pathway_id"]
    result["pathway_id"] = pathway
    for language in ["hi", "ta", "bn", "or", "te"]:
        call("caregiver", "POST", f"care/pathways/{pathway}/translate?language={language}")
        start = time.monotonic()
        while time.monotonic() - start < 90:
            view = call("caregiver", "GET", f"care/pathways/{pathway}")
            if view["plan"].get("language_status", {}).get(language, {}).get("status") == "complete":
                break
            time.sleep(1)
        else:
            raise RuntimeError("Translation did not complete: " + language)
        assert all(language in item["texts"] for item in view["plan"]["items"])
        assert "10 mg" in view["plan"]["medications"][0]["dose_texts"][language]
        pdf = clients["caregiver"].get(f"care/pathways/{pathway}/pdf?language={language}")
        pdf.raise_for_status()
        with fitz.open(stream=pdf.content, filetype="pdf") as document:
            assert len(document) >= 1
            text = "".join(page.get_text() for page in document)
            assert "10" in text
        result["translation_" + language] = {"ok": True, "seconds": round(time.monotonic() - start, 2), "pdf_bytes": len(pdf.content)}
        print(json.dumps({language: result["translation_" + language]}), flush=True)
    view = call("caregiver", "GET", f"care/pathways/{pathway}")
    task = view["tasks"][0]
    call("caregiver", "PUT", f"care/pathways/{pathway}/report", {"task_id": task["task_id"], "day": day, "completed": True})
    call("caregiver", "POST", f"care/pathways/{pathway}/notes", {"text": "Synthetic verification: caregiver note saved for clinician review."})
    read_back = call("doctor", "GET", f"care/pathways/{pathway}")
    assert any(row["completed"] for row in read_back["reports"])
    assert read_back["notes"]
    docs = call("admin", "GET", f"patients/{pid}/documents")
    assert any(doc["record_id"] == pathway and doc.get("language") == "en" for doc in docs)
    call("admin", "GET", f"appointment-history?patient_id={pid}&scope=all")
    result.update(ok=True, caregiver_completion_visible_to_doctor=True, caregiver_notes_saved=True,
        english_archive_preserved=True, daily_tasks=len(view["tasks"]), appointment_id=appointment["appointment_id"])
    (STAGING / "care-verification.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({"care_workflow_complete": True, "daily_tasks": len(view["tasks"])}), flush=True)


if __name__ == "__main__":
    main()
