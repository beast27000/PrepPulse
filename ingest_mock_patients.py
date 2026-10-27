from __future__ import annotations

import argparse
import sys
from pathlib import Path

from preppulse_db.ingest import ingest_patient_pack
from preppulse_db.mongo_store import MongoStore
from preppulse_ocr.engine import OcrPipeline

# ---------- cli runner ----------


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest mock patient dataset into local MongoDB (Stage 1)")
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=Path("data/active/v2_patients"),
        help="Path to unpacked v2 patients directory",
    )
    parser.add_argument(
        "--mongo-uri",
        type=str,
        default="mongodb://localhost:27017",
        help="MongoDB connection URI",
    )
    parser.add_argument(
        "--db-name",
        type=str,
        default="preppulse",
        help="Target database name",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of patients to ingest (0 = all)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear MongoDB collection before ingestion",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify stored documents and bounding-box geometry after ingest",
    )
    parser.add_argument(
        "--clean-after",
        action="store_true",
        help="Wipe all data from MongoDB after running tests/verification",
    )
    args = parser.parse_args()

    dataset_dir: Path = args.dataset_dir
    if not dataset_dir.is_dir():
        print(f"Error: Dataset directory '{dataset_dir}' does not exist.", file=sys.stderr)
        sys.exit(1)

    store = MongoStore(uri=args.mongo_uri, db_name=args.db_name)
    store.connect()

    if args.clear:
        print(f"Clearing collections in database '{args.db_name}'...")
        store.clear_database()

    patient_dirs = sorted([d for d in dataset_dir.iterdir() if d.is_dir()])
    if args.limit > 0:
        patient_dirs = patient_dirs[: args.limit]

    print(f"Ingesting {len(patient_dirs)} patient folders from {dataset_dir} into MongoDB '{args.db_name}'...")
    pipeline = OcrPipeline()
    total_docs = 0

    for idx, p_dir in enumerate(patient_dirs, start=1):
        count = ingest_patient_pack(
            patient_dir=p_dir,
            base_dir=dataset_dir,
            store=store,
            pipeline=pipeline,
        )
        total_docs += count
        print(f"[{idx}/{len(patient_dirs)}] {p_dir.name}: {count} documents ingested.")

    print(f"\nStage 1 Ingestion Complete: {total_docs} total documents written to 'patient_documents'.")

    # ---------- verification ----------
    if args.verify:
        print("\n--- Verifying MongoDB Stage 1 Persistence ---")
        docs = store.list_documents()
        assert len(docs) == total_docs, f"Count mismatch: expected {total_docs}, got {len(docs)}"
        print(f"[PASS] Total documents count verified: {len(docs)}")

        # Check sample doc
        sample = docs[0]
        assert "document_id" in sample and "stage_1_raw_ocr" in sample
        assert sample["status"] == "stage_1_complete"
        stage1 = sample["stage_1_raw_ocr"]
        assert stage1["page_count"] >= 1
        first_page = stage1["pages"][0]
        assert len(first_page["tokens"]) > 0
        first_token = first_page["tokens"][0]
        bbox = first_token["bbox"]
        assert len(bbox) == 4
        assert all(0 <= coord <= 1000 for coord in bbox)
        print(f"[PASS] Sample document '{sample['document_id']}' verified.")
        print(f"       Page count: {stage1['page_count']}, Tokens on p1: {len(first_page['tokens'])}")
        print(f"       Sample token: '{first_token['text']}' with bbox: {bbox}")

    if args.clean_after:
        print("\n--- Cleaning up MongoDB data as requested (--clean-after) ---")
        store.clear_database()
        print(f"[DONE] Collections in '{args.db_name}' dropped cleanly.")

    store.close()


if __name__ == "__main__":
    main()
