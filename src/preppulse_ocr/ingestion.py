"""OCR ingestion into SQLite."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .manifest import ManifestDocument
from .pipeline import OcrPipeline
from .storage import SqliteStore


def selected_documents(selection_path: Path, cohort: str | None = None) -> list[ManifestDocument]:
    documents: list[ManifestDocument] = []
    for line in selection_path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if cohort is None or row.get("cohort") == cohort:
            documents.append(ManifestDocument.from_row(row))
    return documents


def patient_name(corpus_root: Path, patient_id: str) -> str | None:
    record = corpus_root / "records" / f"{patient_id}.json"
    if not record.exists():
        return None
    details = json.loads(record.read_text(encoding="utf-8"))
    return details.get("name")


def ingest_document(document: ManifestDocument, corpus_root: Path, output_root: Path, store: SqliteStore) -> None:
    source_path = corpus_root / document.file
    extraction_path = output_root / document.patient_id / f"{document.doc_id}.json"
    try:
        parsed = OcrPipeline().parse(source_path, document.metadata())
        parsed.write_json(extraction_path)
        store.save_document(parsed, source_path, extraction_path, document.mrn, patient_name(corpus_root, document.patient_id))
    except Exception as error:
        store.save_error(document.doc_id, document.patient_id, document.mrn, source_path, str(error))
        raise


def ingest_cohort(
    selection_path: Path, corpus_root: Path, output_root: Path, database_path: Path, cohort: str = "automatic",
) -> dict[str, int]:
    store = SqliteStore(database_path)
    counts = {"attempted": 0, "ingested": 0, "skipped": 0, "failed": 0}
    try:
        for document in selected_documents(selection_path, cohort):
            counts["attempted"] += 1
            if store.is_ingested(document.doc_id):
                counts["skipped"] += 1
                continue
            try:
                ingest_document(document, corpus_root, output_root, store)
                counts["ingested"] += 1
            except Exception:  # noqa: BLE001 - batch ingestion records a per-document failure and continues.
                counts["failed"] += 1
    finally:
        store.close()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a selected PrepPulse OCR cohort into SQLite.")
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--cohort", choices=["automatic", "manual"], default="automatic")
    args = parser.parse_args()
    print(json.dumps(
        ingest_cohort(
            selection_path=args.selection,
            corpus_root=args.corpus_root,
            output_root=args.output_root,
            database_path=args.database,
            cohort=args.cohort,
        ),
        indent=2,
    ))


if __name__ == "__main__":
    main()
