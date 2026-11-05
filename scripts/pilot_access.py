"""Rotate the cloud admin password and create private pilot verification accounts.

Only run inside the cloud deployment. Credentials are never printed.
"""
import json
import secrets
from pathlib import Path

from pwdlib import PasswordHash

from preppulse_api.store import WorkspaceStore, new_id, now


def main():
    path = Path("/data/private/pilot_access.json")
    if path.exists():
        print("Pilot credentials already initialized")
        return
    store = WorkspaceStore()
    patient = store.db.patients.find_one({"external_aliases": "PP001"}) or store.db.patients.find_one({})
    if not patient:
        raise SystemExit("Import patients before initializing pilot access")
    credentials = {}
    for role, username in [("admin", "admin"), ("doctor", "pilot-review-doctor"), ("caregiver", "pilot-review-caregiver")]:
        password = secrets.token_urlsafe(24)
        existing = store.db.users.find_one({"username": username})
        uid = existing["user_id"] if existing else new_id("USR")
        row = {"user_id": uid, "username": username, "name": "PrepPulse Pilot " + role.title(),
               "role": role, "disabled": False, "password_hash": PasswordHash.recommended().hash(password),
               "created_at": now()}
        if role == "caregiver":
            row["caregiver_type"] = "family"
        store.db.users.update_one({"username": username}, {"$set": row}, upsert=True)
        if role == "doctor":
            for patient_row in store.db.patients.find({}):
                store.db.patient_access.update_one({"doctor_id": uid, "patient_id": patient_row["patient_id"]},
                    {"$setOnInsert": {"doctor_id": uid, "patient_id": patient_row["patient_id"]}}, upsert=True)
        elif role == "caregiver":
            store.db.caregiver_access.update_one({"caregiver_id": uid, "patient_id": patient["patient_id"]},
                {"$set": {"caregiver_id": uid, "patient_id": patient["patient_id"], "kind": "family"}}, upsert=True)
        credentials[role] = {"username": username, "password": password, "user_id": uid}
    store.indexes()
    path.write_text(json.dumps(credentials, indent=2))
    path.chmod(0o600)
    print("Cloud admin password rotated; pilot access saved privately")


if __name__ == "__main__":
    main()
