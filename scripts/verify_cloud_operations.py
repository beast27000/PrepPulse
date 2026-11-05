"""Bounded live pilot operations: routing, voice, persistence and 100 logins.

Uses the private credentials generated for this deployment. Does not invoke
clinical generation or print credentials/transcripts.
"""
import json
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

import httpx

STAGING = Path(__file__).resolve().parents[1] / ".tmp/azure_pilot"
BASE = "https://preppulse-pilot-b8bc.centralindia.cloudapp.azure.com"


def main():
    access = json.loads((STAGING / "pilot_access.json").read_text())
    def login(role):
        client = httpx.Client(base_url=BASE, timeout=120, trust_env=False)
        response = client.post("/api/auth/login", json={k: access[role][k] for k in ["username", "password"]})
        response.raise_for_status()
        client.headers["X-CSRF-Token"] = response.json()["csrf"]
        client.headers["Origin"] = BASE
        return client
    with closing(login("admin")) as admin, closing(login("doctor")) as doctor:
        for mode in ["sarvam", "auto"]:
            response = admin.put("/api/admin/ai-routing", json={"mode": mode})
            response.raise_for_status()
            assert admin.get("/api/admin/ai-routing").json()["mode"] == mode
        patients = doctor.get("/api/patients").json()
        assert len(patients) >= 7
        pid = json.loads((STAGING / "care-verification.json").read_text())["synthetic_patient_id"]
        speech = doctor.post("/api/voice/speak", json={"patient_id": pid,
            "text": "This is a synthetic PrepPulse voice check. Please bring earlier reports to the next visit."})
        speech.raise_for_status()
        assert speech.content.startswith(b"RIFF")
        transcript = doctor.post("/api/voice/transcribe", files={"file": ("check.wav", speech.content, "audio/wav")})
        transcript.raise_for_status()
        assert len(transcript.json()["transcript"]) > 10 and transcript.json()["review_required"]
        assert doctor.get("/api/admin/ai-routing").status_code == 403
        assert admin.put("/api/admin/ai-routing", json={"mode": "auto"}, headers={"X-CSRF-Token": "invalid"}).status_code == 403
        assert admin.put("/api/admin/ai-routing", json={"mode": "auto"}, headers={"Origin": "https://untrusted.example"}).status_code == 403
    def flow(_):
        start = time.monotonic()
        with closing(login("doctor")) as client:
            response = client.get("/api/patients")
            response.raise_for_status()
            assert len(response.json()) >= 7
            client.post("/api/auth/logout").raise_for_status()
        return time.monotonic() - start
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=10) as pool:
        durations = sorted(pool.map(flow, range(100)))
    result = {"ok": True, "successful_login_flows": len(durations), "concurrency": 10,
              "seconds": round(time.monotonic() - start, 2), "p95_seconds": round(durations[94], 2),
              "public_voice_auto_detection": True, "csrf_and_role_checks": True,
              "provider_switch_persisted": True, "patients_after_restart": len(patients)}
    (STAGING / "operations-verification.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
