"""Administrative edits and historical workspace adapters; source files remain immutable."""

from datetime import date
from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from preppulse_api.store import now

API_CONTRACT = "preppulse-ui-care-2"


def register_administration_routes(app, db, user, admin, clinician, patient_access):
    @app.get("/api/runtime")
    def runtime():
        return {
            "contract": API_CONTRACT,
            "roles": ["admin", "doctor", "caregiver"],
            "capabilities": [
                "care-plans",
                "appointment-history",
                "staff-directory",
                "historical-workspace",
            ],
        }

    class AvailabilityIn(BaseModel):
        availability: Literal["free", "active"]

    @app.patch("/api/admin/caregivers/{user_id}/availability")
    def availability(
        user_id: str, body: AvailabilityIn, current: dict = Depends(admin), store=Depends(db)
    ):
        account = store.db.users.find_one(
            {"user_id": user_id, "role": "caregiver"}, {"_id": 0, "password_hash": 0}
        )
        if not account:
            raise HTTPException(404, "Caregiver not found")
        store.db.users.update_one(
            {"user_id": user_id}, {"$set": {"availability": body.availability}}
        )
        account["availability"] = body.availability
        result = store.account_identity(account)
        store.audit(
            current,
            "caregiver_availability_changed",
            extra={"user_id": user_id, "availability": body.availability},
        )
        return result

    class RecordMetadata(BaseModel):
        display_name: str = Field(min_length=1, max_length=240)
        document_type: str = Field(min_length=1, max_length=40)
        visit_date: date | None = None

    @app.patch("/api/admin/patients/{patient_id}/documents/{record_id}")
    def edit_record(
        patient_id: str,
        record_id: str,
        body: RecordMetadata,
        current: dict = Depends(admin),
        store=Depends(db),
    ):
        patient_access(patient_id, current, store)
        record = store.db.workspace_documents.find_one(
            {"patient_id": patient_id, "record_id": record_id}
        )
        if not record:
            raise HTTPException(404, "Document not found")
        data = body.model_dump(mode="json")
        if record.get("document_type") == "care_pathway" and (
            data["document_type"] != "care_pathway"
            or data["visit_date"] != record.get("visit_date")
        ):
            raise HTTPException(
                400, "Signed pathway dates and type are immutable; edit the display title only"
            )
        if not data["display_name"].strip():
            raise HTTPException(400, "A record title is required")
        data["display_name"] = data["display_name"].strip()
        store.db.workspace_documents.update_one(
            {"patient_id": patient_id, "record_id": record_id},
            {"$set": {**data, "metadata_updated_at": now()}},
        )
        store.audit(
            current,
            "record_metadata_edited",
            patient_id,
            {"record_id": record_id, "previous": {k: record.get(k) for k in data}, "updated": data},
        )
        return {"ok": True}

    @app.get("/api/previous-patients")
    def previous_patients(
        q: str = "", on: date | None = None, current: dict = Depends(clinician), store=Depends(db)
    ):
        if not q.strip() and not on:
            return []
        results = []
        for patient in store.search_patients(current, q, limit=500):
            pid = patient["patient_id"]
            visits = list(
                store.db.visits.find({"patient_id": pid}, {"_id": 0, "doctor_notes": 0}).sort(
                    "started_at", -1
                )
            )
            appointments = list(
                store.db.appointments.find(
                    {"patient_id": pid, "doctor_id": current["user_id"]}, {"_id": 0}
                ).sort([("date", -1), ("time", -1)])
            )
            if on:
                visits = [v for v in visits if v.get("started_at", "")[:10] == on.isoformat()]
                appointments = [a for a in appointments if a["date"] == on.isoformat()]
                if not visits and not appointments:
                    continue
            results.append({"patient": patient, "visits": visits, "appointments": appointments})
        return results

    @app.get("/api/patients/{patient_id}/historical-workspace")
    def historical_workspace(
        patient_id: str,
        visit_id: str | None = None,
        current: dict = Depends(clinician),
        store=Depends(db),
    ):
        patient = patient_access(patient_id, current, store)
        visits = list(
            store.db.visits.find({"patient_id": patient_id}, {"_id": 0}).sort("started_at", -1)
        )
        visit = (
            next((v for v in visits if v["visit_id"] == visit_id), None)
            if visit_id
            else next((v for v in visits if v.get("status") == "ended"), None)
        )
        if visit_id and not visit:
            raise HTTPException(404, "Visit not found for this patient")
        plan = (
            store.db.pathways.find_one(
                {"patient_id": patient_id, "visit_id": visit["visit_id"]},
                {"_id": 0},
                sort=[("version", -1)],
            )
            if visit
            else None
        )
        snapshot = plan.get("brief_snapshot") if plan else None
        documents = list(
            store.db.workspace_documents.find(
                {"patient_id": patient_id}, {"_id": 0, "source_path": 0}
            ).sort("visit_date", -1)
        )
        if plan and "document_ids" in plan:
            allowed = set(plan["document_ids"]) | {plan["pathway_id"]}
            documents = [r for r in documents if r["record_id"] in allowed]
        latest = store.db.briefs.find_one({"patient_id": patient_id}, {"_id": 0}) or {}
        store.audit(
            current,
            "historical_workspace_opened",
            patient_id,
            {"visit_id": visit["visit_id"] if visit else None},
        )
        return {
            "patient": plan.get("patient_snapshot") or patient if plan else patient,
            "visit": visit,
            "visits": visits,
            "brief": snapshot or latest.get("brief"),
            "snapshot_available": bool(snapshot),
            "documents": documents,
        }
