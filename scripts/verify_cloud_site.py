"""Exercise the actual HTTPS deployment using private pilot credentials.

Only synthetic imported records and explicitly labelled verification visits are used.
"""
import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / ".tmp/azure_pilot"
BASE = "https://preppulse-pilot-b8bc.centralindia.cloudapp.azure.com"


def main():
    credentials = json.loads((STAGING / "pilot_access.json").read_text())
    result = {}

    def record(name, value):
        result[name] = value
        (STAGING / "site-verification.json").write_text(json.dumps(result, indent=2))
        print(json.dumps({name: value}), flush=True)

    def login(role):
        client = httpx.Client(base_url=BASE, timeout=120, trust_env=False)
        response = client.post("/api/auth/login", json={key: credentials[role][key] for key in ["username", "password"]})
        response.raise_for_status()
        client.headers["X-CSRF-Token"] = response.json()["csrf"]
        client.headers["Origin"] = BASE
        assert "secure" in response.headers["set-cookie"].lower() and "httponly" in response.headers["set-cookie"].lower()
        return client

    def get(client, path):
        response = client.get("/api" + path)
        response.raise_for_status()
        return response.json()

    def post(client, path, body=None):
        response = client.post("/api" + path, json=body or {})
        response.raise_for_status()
        return response.json()

    anon = httpx.Client(base_url=BASE, timeout=30, trust_env=False)
    assert anon.get("/").status_code == 200
    assert anon.get("/api/health").json()["status"] == "ready"
    assert anon.get("/api/patients").status_code == 401
    admin, doctor, caregiver = [login(role) for role in ["admin", "doctor", "caregiver"]]
    patients = get(doctor, "/patients")
    assert len(patients) >= 6
    selected = next(p for p in patients if "PP001" in p.get("external_aliases", []))
    pid = selected["patient_id"]
    documents = get(doctor, f"/patients/{pid}/documents")
    record("https_login_and_data", {"ok": True, "patients": len(patients), "selected_records": len(documents)})
    checks = ["/admin/accounts", "/appointment-history", f"/admin/patients/{pid}/overview", "/admin/caregiver-assignments", "/admin/ai-routing"]
    for path in checks:
        get(admin, path)
    for path in ["/appointments", "/appointment-history", f"/patients/{pid}/visits", f"/care/patients/{pid}", "/voice/capabilities"]:
        get(doctor, path)
    get(caregiver, f"/care/patients/{pid}")
    assert caregiver.get(f"/api/patients/{pid}/brief").status_code == 403
    assert admin.get(f"/api/patients/{pid}/brief").status_code == 403
    assert doctor.get("/api/admin/accounts").status_code == 403
    for doc in documents:
        response = doctor.get(f"/api/patients/{pid}/documents/{doc['record_id']}/page/1")
        assert response.status_code == 200 and response.content.startswith(b"\x89PNG")
    record("routes_roles_and_source_pages", {"ok": True, "original_pages_verified": len(documents)})

    # Start the full real pipeline through the same durable queue used by the browser.
    started = time.monotonic()
    job = post(doctor, f"/patients/{pid}/brief/jobs")
    record("analysis_started", {"job_id": job["job_id"]})
    previous = None
    while time.monotonic() - started < 1800:
        status = get(doctor, f"/patients/{pid}/brief/jobs/latest")
        state = (status.get("status"), status.get("stage"))
        if state != previous:
            print(json.dumps({"analysis_progress": state}), flush=True)
            previous = state
        if status["status"] in {"complete", "failed"}:
            record("analysis", {"ok": status["status"] == "complete", "status": status,
                "seconds": round(time.monotonic() - started, 2)})
            break
        time.sleep(4)
    else:
        raise RuntimeError("Cloud analysis exceeded 30 minutes")
    assert status["status"] == "complete", status.get("error")
    brief = get(doctor, f"/patients/{pid}/brief")["brief"]
    for doc in documents:
        response = doctor.get(f"/api/patients/{pid}/documents/{doc['record_id']}/fhir")
        response.raise_for_status()
        assert response.json()["resourceType"] == "Bundle"
    record("fhir_and_findings", {"ok": True, "fhir_bundles": len(documents),
        "findings": len(brief["priority_findings"]), "metric_series": len(brief["metric_series"])})

    chat = post(doctor, "/chat/sessions", {"patient_id": pid})
    for index, question in enumerate([
        "Summarize the documented diabetes journey and HbA1c changes, with source citations.",
        "Which other conditions and hospital admissions are documented? Cite the records.",
        "Plot HbA1c and fasting glucose for the last 3 years.",
        "Plot it for the past 10 years.",
        "Plot a chart of this patient's heart disease."]):
        turn = post(doctor, f"/chat/sessions/{chat['session_id']}/turns", {"query": question})
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            turn = get(doctor, "/chat/turns/" + turn["turn_id"])
            if turn["status"] in {"complete", "failed"}:
                break
            time.sleep(2)
        assert turn["status"] == "complete", turn
        snapshot = get(doctor, "/chat/sessions/" + chat["session_id"])
        last = snapshot["messages"][-1]
        assert last.get("text")
        if index in {0, 1}:
            assert last.get("citations")
        if index in {2, 3}:
            assert snapshot["artifacts"]
        record("chat_" + str(index + 1), {"ok": True, "citations": len(last.get("citations", [])),
            "session_artifacts": len(snapshot["artifacts"])})
    record("complete", {"ok": True})


if __name__ == "__main__":
    main()
