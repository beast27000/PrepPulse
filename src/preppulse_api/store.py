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
        db.patients.create_index("patient_id", unique=True)
        db.patient_aliases.create_index("alias", unique=True)
        db.patients.create_index("name_search")
        db.patient_access.create_index(
            [("patient_id", ASCENDING), ("doctor_id", ASCENDING)], unique=True
        )
        db.workspace_documents.create_index("record_id", unique=True)
        db.appointments.create_index("appointment_id", unique=True)
        db.appointments.create_index([("doctor_id", ASCENDING), ("date", ASCENDING)])
        db.visits.create_index("visit_id", unique=True)
        db.review_decisions.create_index(
            [("visit_id", ASCENDING), ("finding_id", ASCENDING)], unique=True
        )
        db.pathways.create_index([("visit_id", ASCENDING), ("version", ASCENDING)], unique=True)
        db.pathway_items.create_index("item_id", unique=True)
        db.jobs.create_index("job_id", unique=True)

    def patient(self, patient_id: str) -> dict | None:
        return self.db.patients.find_one({"patient_id": patient_id}, {"_id": 0})

    def allowed(self, user: dict, patient_id: str) -> bool:
        if user["role"] == "admin":
            return True
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
                {"name_search": {"$regex": safe, "$options": "i"}},
                {"patient_id": {"$regex": safe, "$options": "i"}},
                {"external_aliases": {"$regex": safe, "$options": "i"}},
            ]
        if user["role"] == "doctor":
            ids = [
                x["patient_id"]
                for x in self.db.patient_access.find(
                    {"doctor_id": user["user_id"]}, {"patient_id": 1}
                )
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
