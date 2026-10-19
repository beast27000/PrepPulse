"""Authoritative manifest handling for the synthetic PrepPulse corpus."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .models import DocumentMetadata, DocumentType

KIND_TO_TYPE = {
    "clinic_note": DocumentType.OUTPATIENT_NOTE,
    "discharge_summary": DocumentType.DISCHARGE_SUMMARY,
    "lab_report": DocumentType.LAB_PANEL,
    "referral_letter": DocumentType.REFERRAL_ORDER,
}

REQUIRED_KINDS = tuple(KIND_TO_TYPE)


@dataclass(frozen=True)
class ManifestDocument:
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
    """Load only OCR-rendered documents with one source file per row."""
    documents: list[ManifestDocument] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("kind") in REQUIRED_KINDS and row.get("file"):
            documents.append(ManifestDocument.from_row(row))
    return documents


def select_complete_packs(documents: list[ManifestDocument]) -> dict[str, list[ManifestDocument]]:
    """Choose one latest document per required kind for each complete patient pack.

    Keeping exactly four files per selected patient makes the Sprint 1 corpus predictable,
    while the original full manifest remains untouched as the source of truth.
    """
    by_patient: dict[str, dict[str, list[ManifestDocument]]] = {}
    for document in documents:
        by_patient.setdefault(document.patient_id, {}).setdefault(document.kind, []).append(document)

    complete: dict[str, list[ManifestDocument]] = {}
    for patient_id, by_kind in by_patient.items():
        if not all(kind in by_kind for kind in REQUIRED_KINDS):
            continue
        chosen = [
            max(by_kind[kind], key=lambda item: (item.doc_date or "", item.doc_id))
            for kind in REQUIRED_KINDS
        ]
        complete[patient_id] = chosen
    return dict(sorted(complete.items()))


def write_manifest_rows(path: Path, documents: list[ManifestDocument], cohort: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as output:
        for document in documents:
            row = dict(document.row)
            row["cohort"] = cohort
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
