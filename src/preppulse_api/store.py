from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import uuid4

from pymongo import ASCENDING, MongoClient

from preppulse_api.config import MONGO_DB, MONGO_URI


def now() -> str:
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:16].upper()}"


class WorkspaceStore:
    def __init__(self, uri: str = MONGO_URI, db_name: str = MONGO_DB):
        self.client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        self.db = self.client[db_name]

    def ready(self) -> bool:
        self.client.admin.command("ping")
        return True

    def indexes(self) -> None:
        db = self.db
        db.users.create_index("username", unique=True)
        db.users.create_index("account_id", unique=True, sparse=True)
        db.staff_directory.create_index("user_id", unique=True)
        db.staff_directory.create_index("account_id", unique=True)
        db.patients.create_index("patient_id", unique=True)
        db.patient_aliases.create_index("alias", unique=True)
        db.patients.create_index("name_search")
        db.patient_access.create_index(
            [("patient_id", ASCENDING), ("doctor_id", ASCENDING)], unique=True
        )
        db.workspace_documents.create_index("record_id", unique=True)
        db.workspace_files.create_index("file_id", unique=True)
        db.workspace_files.create_index(
            [("patient_id", ASCENDING), ("relative_path", ASCENDING), ("sha256", ASCENDING)],
            unique=True,
        )
        db.appointments.create_index("appointment_id", unique=True)
        db.appointments.create_index([("doctor_id", ASCENDING), ("date", ASCENDING)])
        db.visits.create_index("visit_id", unique=True)
        db.review_decisions.create_index(
            [("visit_id", ASCENDING), ("finding_id", ASCENDING)], unique=True
        )
        db.pathways.create_index([("visit_id", ASCENDING), ("version", ASCENDING)], unique=True)
        db.pathway_items.create_index("item_id", unique=True)
        db.care_drafts.create_index("visit_id", unique=True)
        db.care_translations.create_index("pathway_id", unique=True)
        db.caregiver_access.create_index(
            [("patient_id", ASCENDING), ("caregiver_id", ASCENDING)], unique=True
        )
        db.care_reports.create_index(
            [("pathway_id", ASCENDING), ("task_id", ASCENDING)], unique=True
        )
        db.care_notes.create_index([("pathway_id", ASCENDING), ("created_at", ASCENDING)])
        db.jobs.create_index("job_id", unique=True)
        db.chat_sessions.create_index("session_id", unique=True)
        db.chat_sessions.create_index(
            [("user_id", ASCENDING), ("patient_id", ASCENDING), ("updated_at", ASCENDING)]
        )
        db.chat_messages.create_index("message_id", unique=True)
        db.chat_messages.create_index([("session_id", ASCENDING), ("created_at", ASCENDING)])
        db.chat_artifacts.create_index("artifact_id", unique=True)
        db.chat_turns.create_index("turn_id", unique=True)
        for account in db.users.find({}, {"_id": 0, "password_hash": 0}):
            self.account_identity(account)

    def account_identity(self, account: dict) -> dict:
        """Backfill public staff IDs without changing existing assignment/login keys."""
        kind = account.get("caregiver_type")
        if account["role"] == "caregiver" and not kind:
            professional = self.db.caregiver_access.find_one(
                {"caregiver_id": account["user_id"], "kind": "professional"}
            )
            kind = "professional" if professional else "family"
        prefix = {
            "doctor": "DOC",
            "admin": "ADM",
            "caregiver": "CGV" if kind == "professional" else "FAM",
        }[account["role"]]
        if not account.get("account_id"):
            self.db.users.update_one(
                {"user_id": account["user_id"], "account_id": {"$exists": False}},
                {"$set": {"account_id": new_id(prefix)}},
            )
        actual = (
            self.db.users.find_one({"user_id": account["user_id"]}, {"_id": 0, "password_hash": 0})
            or account
        )
        if actual["role"] == "caregiver":
            defaults = {
                "caregiver_type": kind or "family",
                "availability": actual.get("availability", "free"),
            }
            self.db.users.update_one({"user_id": actual["user_id"]}, {"$set": defaults})
            actual.update(defaults)
        fields = {
            k: actual.get(k)
            for k in (
                "user_id",
                "account_id",
                "name",
                "username",
                "role",
                "caregiver_type",
                "availability",
                "disabled",
            )
        }
        self.db.staff_directory.update_one(
            {"user_id": actual["user_id"]}, {"$set": fields}, upsert=True
        )
        return actual

    def patient(self, patient_id: str) -> dict | None:
        return self.db.patients.find_one({"patient_id": patient_id}, {"_id": 0})

    def allowed(self, user: dict, patient_id: str) -> bool:
        if user["role"] == "admin":
            return True
        if user["role"] == "caregiver":
            return (
                self.db.caregiver_access.find_one(
                    {"patient_id": patient_id, "caregiver_id": user["user_id"]}
                )
                is not None
            )
        return (
            self.db.patient_access.find_one(
                {"patient_id": patient_id, "doctor_id": user["user_id"]}
            )
            is not None
        )

    def search_patients(self, user: dict, query: str = "", limit: int = 30) -> list[dict]:
        q = query.strip()
        criteria: dict = {}
        if q:
            safe = re.escape(q)
            criteria["$or"] = [
                {"name": {"$regex": safe, "$options": "i"}},
                {"name_search": {"$regex": safe, "$options": "i"}},
                {"patient_id": {"$regex": safe, "$options": "i"}},
                {"external_aliases": {"$regex": safe, "$options": "i"}},
            ]
        if user["role"] in {"doctor", "caregiver"}:
            collection = (
                self.db.caregiver_access if user["role"] == "caregiver" else self.db.patient_access
            )
            key = "caregiver_id" if user["role"] == "caregiver" else "doctor_id"
            ids = [
                x["patient_id"] for x in collection.find({key: user["user_id"]}, {"patient_id": 1})
            ]
            criteria["patient_id"] = {"$in": ids}
        return list(self.db.patients.find(criteria, {"_id": 0, "source_root": 0}).limit(limit))

    def audit(
        self, user: dict, action: str, patient_id: str | None = None, extra: dict | None = None
    ) -> None:
        self.db.audit_events.insert_one(
            {
                "at": now(),
                "actor_id": user["user_id"],
                "action": action,
                "patient_id": patient_id,
                "extra": extra or {},
            }
        )
