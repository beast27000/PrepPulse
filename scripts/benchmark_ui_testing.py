"""Synthetic 100-patient/100-user API rehearsal; no cloud calls or real patient writes."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from bson import BSON


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-template", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.environ.update({"PREPPULSE_MONGO_DB": "preppulse_ui_testing_load",
                       "PREPPULSE_SESSION_SECRET": "synthetic-load-session-secret-more-than-32-characters",
                       "PREPPULSE_PRIVATE_ROOT": str(root / ".tmp/ui_testing/private_data"),
                       "PREPPULSE_AI_PROVIDER": "mock", "PREPPULSE_EMBED_PROVIDER": "mock"})
    from preppulse_api.app import password_hash
    from preppulse_api.store import WorkspaceStore, now
    from preppulse_preprocessing.fhir import to_fhir_bundle
    store = WorkspaceStore()
    store.indexes()
    source = store.client["preppulse_ui_testing"]
    pid = source.patient_aliases.find_one({"alias": "PP001"})["patient_id"]
    template = list(source.patient_documents.find({"patient_id": pid}))
    password = "synthetic-load-password-2026"
    hashed = password_hash.hash(password)
    original_bytes = sum(len(BSON.encode(row)) for row in template)
    for i in range(100):
        user_id, patient_id = f"LOAD-DOC-{i:03}", f"PRP-LOAD-{i:03}"
        store.db.users.update_one({"user_id": user_id}, {"$setOnInsert": {
            "user_id": user_id, "username": f"load{i:03}", "name": f"Synthetic Doctor {i}",
            "role": "doctor", "disabled": False, "password_hash": hashed}}, upsert=True)
        store.db.patients.update_one({"patient_id": patient_id}, {"$setOnInsert": {
            "patient_id": patient_id, "name": f"Synthetic Patient {i}",
            "name_search": f"synthetic patient {i}", "created_at": now()}}, upsert=True)
        store.db.patient_access.update_one({"patient_id": patient_id, "doctor_id": user_id},
                                          {"$setOnInsert": {"patient_id": patient_id, "doctor_id": user_id}}, upsert=True)
        for j, original in enumerate(template):
            if not args.refresh_template and store.db.patient_documents.find_one({"document_id": f"LOAD-DOC-{i:03}-{j:03}"}, {"_id": 1}):
                continue
            row = copy.deepcopy(original)
            row.pop("_id", None)
            row["patient_id"], row["document_id"] = patient_id, f"LOAD-DOC-{i:03}-{j:03}"
            entities = row.get("stage_2_structured_entities")
            if entities:
                entities["patient"] = {"name": f"Synthetic Patient {i}"}
                row["stage_3_fhir_output"] = to_fhir_bundle(entities, patient_id, row["document_id"])
            store.db.patient_documents.update_one({"document_id": row["document_id"]},
                                                 {"$set" if args.refresh_template else "$setOnInsert": row}, upsert=True)
    log_path = root / ".tmp/ui_testing/load-server.log"
    log = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "preppulse_api.app:app",
                                "--host", "127.0.0.1", "--port", "8002"],
                               stdout=log, stderr=log, cwd=root, env=os.environ.copy(),
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    for _ in range(40):
        try:
            if httpx.get("http://127.0.0.1:8002/api/health", timeout=2, trust_env=False).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(.5)
    else:
        process.terminate()
        raise RuntimeError("Isolated load server did not start")
    def user_flow(i):
        started = time.monotonic()
        with httpx.Client(base_url="http://127.0.0.1:8002", timeout=60, trust_env=False) as client:
            login = client.post("/api/auth/login", json={"username": f"load{i:03}", "password": password})
            listing = client.get("/api/patients")
            rows = listing.json() if listing.status_code == 200 else []
            expected = f"PRP-LOAD-{i:03}"
            owned = len(rows) == 1 and rows[0]["patient_id"] == expected
            forbidden = client.get(f"/api/patients/PRP-LOAD-{(i+1)%100:03}/brief")
            return {"ok": login.status_code == 200 and owned and forbidden.status_code == 403,
                    "seconds": time.monotonic() - started}
    started = time.monotonic()
    try:
        with ThreadPoolExecutor(max_workers=10) as pool:
            outcomes = list(pool.map(user_flow, range(100)))
    finally:
        process.terminate()
        process.wait(timeout=15)
        log.close()
    elapsed = time.monotonic() - started
    collections = [name for name in store.db.list_collection_names() if not name.startswith("system.")]
    snapshot = {name: list(store.db[name].find({})) for name in collections}
    def digest(rows):
        return hashlib.sha256(b"".join(sorted(BSON.encode(row) for row in rows))).hexdigest()
    restore = store.client["preppulse_ui_testing_restore_" + str(int(time.time()))]
    if restore.list_collection_names():
        raise RuntimeError("Restore database already exists; refusing to overwrite it")
    restored = {}
    for name, rows in snapshot.items():
        if rows:
            restore[name].insert_many(copy.deepcopy(rows))
        restored[name] = digest(list(restore[name].find({}))) == digest(rows)
    stats = store.db.command("dbStats")
    latencies = sorted(row["seconds"] for row in outcomes)
    report = {"synthetic_patients": 100, "documents": len(template)*100,
              "users": 100, "concurrent_user_flows": 10,
              "passed_user_flows": sum(row["ok"] for row in outcomes),
              "total_seconds": round(elapsed, 2), "flow_p50_seconds": round(statistics.median(latencies), 3),
              "flow_p95_seconds": round(latencies[94], 3),
              "data_MiB": round(stats["dataSize"]/1048576, 2),
              "indexes_MiB": round(stats["indexSize"]/1048576, 2),
              "source_template_MiB": round(original_bytes/1048576, 2),
              "restore_matches": all(restored.values()),
              "limitations": ["Local HTTP/uvicorn transport, not an internet or Oracle benchmark",
                              "10 active flows serving 100 distinct users, not 100 simultaneous AI jobs",
                              "Replicated synthetic records; not 100 independently reviewed clinical charts",
                              "No five-day soak or cloud quota extrapolation from this short test"]}
    output = root / ".tmp/ui_testing/results/load.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    store.client.close()


if __name__ == "__main__":
    main()
