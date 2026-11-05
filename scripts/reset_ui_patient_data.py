"""Clear local PrepPulse patient/workflow data while preserving login accounts.

Run without flags to inspect counts. Applying requires an explicit database name.
Stop the API first so background workers cannot repopulate the collections.
"""

from __future__ import annotations

import argparse

from preppulse_api.config import MONGO_DB
from preppulse_api.store import WorkspaceStore

PATIENT_COLLECTIONS = (
    "patients",
    "patient_aliases",
    "patient_access",
    "workspace_files",
    "workspace_documents",
    "patient_documents",
    "document_chunks",
    "briefs",
    "jobs",
    "appointments",
    "visits",
    "pathways",
    "pathway_items",
    "care_drafts",
    "care_visit_checks",
    "care_translations",
    "care_language_cache",
    "care_segment_cache",
    "caregiver_access",
    "care_reports",
    "care_notes",
    "review_decisions",
    "audit_events",
    "chat_sessions",
    "chat_messages",
    "chat_turns",
    "chat_artifacts",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Delete the listed records")
    parser.add_argument("--confirm", default="", help="Exact database name for apply mode")
    args = parser.parse_args()
    store = WorkspaceStore()
    try:
        store.ready()
        counts = {name: store.db[name].count_documents({}) for name in PATIENT_COLLECTIONS}
        print(f"Database: {store.db.name}")
        for name, count in counts.items():
            if count:
                print(f"{name}: {count}")
        print(f"users preserved: {store.db.users.count_documents({})}")
        if not args.apply:
            print("Preview only. Nothing deleted.")
            return
        if MONGO_DB != "preppulse" or args.confirm != MONGO_DB:
            parser.error("Apply requires --confirm preppulse and the default preppulse database")
        if store.db.jobs.count_documents({"status": {"$in": ["queued", "running"]}}):
            parser.error("Processing jobs are active; stop the API and wait before clearing data")
        for name in PATIENT_COLLECTIONS:
            store.db[name].delete_many({})
        print("Patient and workflow records cleared. User accounts and indexes retained.")
    finally:
        store.client.close()


if __name__ == "__main__":
    main()
