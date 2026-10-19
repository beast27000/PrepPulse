from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .engine import DocumentMetadata, DocumentType, OcrPipeline, ParsedDocument

# ---------- manifest models & loading ----------

KIND_TO_TYPE = {
    "clinic_note": DocumentType.OUTPATIENT_NOTE,
    "discharge_summary": DocumentType.DISCHARGE_SUMMARY,
    "lab_report": DocumentType.LAB_PANEL,
    "referral_letter": DocumentType.REFERRAL_ORDER,
}

REQUIRED_KINDS = tuple(KIND_TO_TYPE)


@dataclass(frozen=True)
class ManifestDocument:
    """Document reference from the synthetic dataset manifest."""
    doc_id: str
    patient_id: str
    mrn: str
    kind: str
    form: str
    doc_date: str | None
    file: str
    row: dict[str, Any]

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ManifestDocument:
        return cls(
            doc_id=row["doc_id"], patient_id=row["patient_id"], mrn=row["mrn"],
            kind=row["kind"], form=row["form"], doc_date=row.get("doc_date"), file=row["file"], row=row,
        )

    def metadata(self) -> DocumentMetadata:
        # /3 convert manifest record to typed document metadata
        parsed_date = date.fromisoformat(self.doc_date) if self.doc_date else None
        return DocumentMetadata(
            patient_id=self.patient_id,
            document_id=self.doc_id,
            document_name=Path(self.file).name,
            document_type=KIND_TO_TYPE[self.kind],
            encounter_date=parsed_date,
            encounter_date_raw=self.doc_date,
        )


def load_manifest(path: Path) -> list[ManifestDocument]:
    """Parse JSONL document manifest filtering for required kinds with existing source files."""
    documents: list[ManifestDocument] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("kind") in REQUIRED_KINDS and row.get("file"):
            documents.append(ManifestDocument.from_row(row))
    return documents


def select_complete_packs(documents: list[ManifestDocument]) -> dict[str, list[ManifestDocument]]:
    """Select the latest document of each required kind for each patient with a complete pack."""
    by_patient: dict[str, dict[str, list[ManifestDocument]]] = {}
    for doc in documents:
        by_patient.setdefault(doc.patient_id, {}).setdefault(doc.kind, []).append(doc)

    complete: dict[str, list[ManifestDocument]] = {}
    for patient_id, by_kind in by_patient.items():
        if not all(k in by_kind for k in REQUIRED_KINDS):
            continue
        chosen = [
            max(by_kind[k], key=lambda item: (item.doc_date or "", item.doc_id))
            for k in REQUIRED_KINDS
        ]
        complete[patient_id] = chosen
    return dict(sorted(complete.items()))


def write_manifest_rows(path: Path, documents: list[ManifestDocument], cohort: str) -> None:
    # /3 append document entries annotated with cohort label to manifest file
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as output:
        for doc in documents:
            row = dict(doc.row)
            row["cohort"] = cohort
            output.write(json.dumps(row, ensure_ascii=False) + "\n")


# ---------- sqlite storage ----------

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS patients (
  patient_id TEXT PRIMARY KEY, mrn TEXT NOT NULL, display_name TEXT
);
CREATE TABLE IF NOT EXISTS documents (
  document_id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(patient_id),
  document_name TEXT NOT NULL, document_type TEXT NOT NULL, encounter_date TEXT,
  source_path TEXT NOT NULL, source_sha256 TEXT, extraction_path TEXT, status TEXT NOT NULL,
  error_message TEXT
);
CREATE TABLE IF NOT EXISTS pages (
  document_id TEXT NOT NULL REFERENCES documents(document_id), page_number INTEGER NOT NULL,
  width REAL NOT NULL, height REAL NOT NULL, unit TEXT NOT NULL, extraction_method TEXT NOT NULL,
  PRIMARY KEY (document_id, page_number)
);
CREATE TABLE IF NOT EXISTS evidence_anchors (
  anchor_id INTEGER PRIMARY KEY AUTOINCREMENT, document_id TEXT NOT NULL,
  page_number INTEGER NOT NULL, anchor_type TEXT NOT NULL, source_id TEXT NOT NULL,
  text TEXT NOT NULL, bbox_json TEXT NOT NULL, source_bbox_json TEXT NOT NULL,
  confidence REAL, table_row INTEGER, table_column INTEGER,
  UNIQUE(document_id, page_number, anchor_type, source_id)
);
"""


class SqliteStore:
    """Relational store managing patient records, documents, pages, and OCR evidence anchors."""

    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)

    def close(self) -> None:
        self.connection.close()

    def is_ingested(self, document_id: str) -> bool:
        # /3 check if document has already been processed successfully
        row = self.connection.execute(
            "SELECT status FROM documents WHERE document_id = ?", (document_id,)
        ).fetchone()
        return row is not None and row["status"] == "ingested"

    def save_document(
        self, parsed: ParsedDocument, source_path: Path, extraction_path: Path, mrn: str, display_name: str | None,
    ) -> None:
        # /3 persist patient, document, page geometries, and evidence anchors in transaction
        metadata = parsed.metadata
        with self.connection:
            self.connection.execute(
                "INSERT INTO patients(patient_id, mrn, display_name) VALUES(?, ?, ?) "
                "ON CONFLICT(patient_id) DO UPDATE SET mrn=excluded.mrn, display_name=excluded.display_name",
                (metadata.patient_id, mrn, display_name),
            )
            self.connection.execute(
                "INSERT INTO documents(document_id, patient_id, document_name, document_type, encounter_date, "
                "source_path, source_sha256, extraction_path, status, error_message) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, 'ingested', NULL) "
                "ON CONFLICT(document_id) DO UPDATE SET source_path=excluded.source_path, "
                "source_sha256=excluded.source_sha256, extraction_path=excluded.extraction_path, status='ingested', error_message=NULL",
                (metadata.document_id, metadata.patient_id, metadata.document_name, metadata.document_type.value,
                 metadata.encounter_date.isoformat() if metadata.encounter_date else None, str(source_path),
                 metadata.source_sha256, str(extraction_path)),
            )
            self.connection.execute("DELETE FROM pages WHERE document_id = ?", (metadata.document_id,))
            self.connection.execute("DELETE FROM evidence_anchors WHERE document_id = ?", (metadata.document_id,))
            for page in parsed.pages:
                self.connection.execute(
                    "INSERT INTO pages VALUES (?, ?, ?, ?, ?, ?)",
                    (metadata.document_id, page.page_number, page.dimensions.width, page.dimensions.height,
                     page.dimensions.unit, page.extraction_method),
                )
                anchors = [("token", t.id, t.text, t.bbox, t.source_bbox, t.confidence, None, None)
                           for t in page.tokens]
                anchors += [("line", l.id, l.text, l.bbox, l.source_bbox, None, None, None)
                            for l in page.lines]
                for table in page.tables:
                    anchors += [
                        ("table_cell", f"{table.id}:{c.row_index}:{c.column_index}", c.text, c.bbox,
                         c.source_bbox, None, c.row_index, c.column_index)
                        for c in table.cells
                    ]
                self.connection.executemany(
                    "INSERT INTO evidence_anchors(document_id, page_number, anchor_type, source_id, text, bbox_json, "
                    "source_bbox_json, confidence, table_row, table_column) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [(metadata.document_id, page.page_number, anchor_type, source_id, text,
                      json.dumps(bbox.model_dump()), json.dumps(source_bbox.model_dump()), confidence, row, col)
                     for anchor_type, source_id, text, bbox, source_bbox, confidence, row, col in anchors],
                )

    def save_error(self, document_id: str, patient_id: str, mrn: str, source_path: Path, message: str) -> None:
        # /3 record ingestion error status for failed document
        with self.connection:
            self.connection.execute(
                "INSERT INTO patients(patient_id, mrn) VALUES(?, ?) ON CONFLICT(patient_id) DO NOTHING",
                (patient_id, mrn),
            )
            self.connection.execute(
                "INSERT INTO documents(document_id, patient_id, document_name, document_type, source_path, status, error_message) "
                "VALUES (?, ?, ?, 'unknown', ?, 'failed', ?) "
                "ON CONFLICT(document_id) DO UPDATE SET status='failed', error_message=excluded.error_message",
                (document_id, patient_id, source_path.name, str(source_path), message),
            )

    def documents_for_patient(self, patient_id: str) -> list[sqlite3.Row]:
        return self.connection.execute(
            "SELECT * FROM documents WHERE patient_id = ? ORDER BY document_type", (patient_id,)
        ).fetchall()

    def anchors_for_page(self, document_id: str, page_number: int) -> list[sqlite3.Row]:
        return self.connection.execute(
            "SELECT * FROM evidence_anchors WHERE document_id = ? AND page_number = ? "
            "ORDER BY CASE anchor_type WHEN 'line' THEN 0 WHEN 'table_cell' THEN 1 ELSE 2 END, anchor_id",
            (document_id, page_number),
        ).fetchall()


# ---------- pack builder & cohort ingestion ----------

ARCHIVE_BY_FORM = {
    "digital_pdf": "preppulse_docs_text_digital_pdf.zip",
    "scanned_pdf": "preppulse_docs_OCR_scanned_pdf.zip",
    "scanned_image": "preppulse_docs_OCR_scanned_images.zip",
    "hybrid_pdf": "preppulse_docs_hybrid_pdf.zip",
    "handwritten_note": "preppulse_docs_OCR_handwritten.zip",
}


def build_pack(
    manifest_path: Path, records_dir: Path, archives_dir: Path, output_root: Path, automatic_patients: int = 75,
) -> dict[str, int]:
    """Unpack four-document packs for all complete patients into a clean active folder."""
    all_documents = load_manifest(manifest_path)
    packs = select_complete_packs(all_documents)
    if len(packs) != 93:
        raise ValueError(f"Expected 93 complete packs, found {len(packs)}")

    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)
    selected_manifest = output_root / "selected_manifest.jsonl"
    selected_patient_ids = list(packs)
    automatic_ids = set(selected_patient_ids[:automatic_patients])

    archive_members: dict[str, set[str]] = {}
    archive_handles: dict[str, zipfile.ZipFile] = {}
    try:
        for form, filename in ARCHIVE_BY_FORM.items():
            archive_path = archives_dir / filename
            archive = zipfile.ZipFile(archive_path)
            archive_handles[form] = archive
            archive_members[form] = set(archive.namelist())

        for patient_id, documents in packs.items():
            cohort = "automatic" if patient_id in automatic_ids else "manual"
            write_manifest_rows(selected_manifest, documents, cohort)
            record_source = records_dir / f"{patient_id}.json"
            if record_source.is_file():
                record_target = output_root / "records" / record_source.name
                record_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(record_source, record_target)
            for document in documents:
                archive = archive_handles[document.form]
                if document.file not in archive_members[document.form]:
                    raise FileNotFoundError(f"{document.file} missing from {ARCHIVE_BY_FORM[document.form]}")
                target = output_root / document.file
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(document.file) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
    finally:
        for archive in archive_handles.values():
            archive.close()

    summary = {
        "complete_patients": len(packs),
        "documents": len(packs) * 4,
        "automatic_patients": len(automatic_ids),
        "manual_patients": len(packs) - len(automatic_ids),
    }
    (output_root / "selection_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def selected_documents(selection_path: Path, cohort: str | None = None) -> list[ManifestDocument]:
    # /3 load documents from selection manifest optionally filtered by cohort
    documents: list[ManifestDocument] = []
    for line in selection_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if cohort is None or row.get("cohort") == cohort:
            documents.append(ManifestDocument.from_row(row))
    return documents


def patient_name(corpus_root: Path, patient_id: str) -> str | None:
    # /3 retrieve patient display name from records json
    record = corpus_root / "records" / f"{patient_id}.json"
    if not record.exists():
        return None
    details = json.loads(record.read_text(encoding="utf-8"))
    return details.get("name")


def ingest_document(document: ManifestDocument, corpus_root: Path, output_root: Path, store: SqliteStore) -> None:
    # /3 parse single document and persist output to JSON and SQLite
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
    # /3 batch ingest all unparsed documents in a cohort
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


# ---------- CLI entry point ----------

def main() -> None:
    parser = argparse.ArgumentParser(description="PrepPulse OCR database and ingestion manager.")
    parser.add_argument("--selection", type=Path, default=Path("data/active/pack93/selected_manifest.jsonl"))
    parser.add_argument("--corpus-root", type=Path, default=Path("data/active/pack93"))
    parser.add_argument("--output-root", type=Path, default=Path("data/outputs/ocr_json"))
    parser.add_argument("--database", type=Path, default=Path("data/outputs/preppulse_ocr.sqlite"))
    parser.add_argument("--cohort", choices=["automatic", "manual"], default="automatic")
    args = parser.parse_args()

    results = ingest_cohort(
        selection_path=args.selection,
        corpus_root=args.corpus_root,
        output_root=args.output_root,
        database_path=args.database,
        cohort=args.cohort,
    )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
