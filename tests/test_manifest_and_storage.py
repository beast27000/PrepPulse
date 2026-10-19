from datetime import date
from pathlib import Path

import fitz

from preppulse_ocr.manifest import ManifestDocument, select_complete_packs
from preppulse_ocr.models import DocumentMetadata, DocumentType
from preppulse_ocr.pipeline import OcrPipeline
from preppulse_ocr.storage import SqliteStore


def manifest_document(patient_id: str, kind: str, doc_id: str, doc_date: str) -> ManifestDocument:
    return ManifestDocument.from_row({
        "doc_id": doc_id, "patient_id": patient_id, "mrn": "MRN-1", "kind": kind,
        "form": "digital_pdf", "doc_date": doc_date, "file": f"documents/{patient_id}/{doc_id}.pdf",
    })


def test_complete_pack_selects_one_latest_document_per_required_kind() -> None:
    kinds = ["clinic_note", "discharge_summary", "lab_report", "referral_letter"]
    complete = [manifest_document("patient-a", kind, f"{kind}-old", "2024-01-01") for kind in kinds]
    complete.append(manifest_document("patient-a", "lab_report", "lab-new", "2024-03-01"))
    incomplete = [manifest_document("patient-b", "lab_report", "only-lab", "2024-01-01")]

    packs = select_complete_packs(complete + incomplete)

    assert list(packs) == ["patient-a"]
    assert len(packs["patient-a"]) == 4
    assert any(document.doc_id == "lab-new" for document in packs["patient-a"])


def test_sqlite_store_preserves_line_evidence(tmp_path: Path) -> None:
    source = tmp_path / "note.pdf"
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "Patient takes Glargine 14 U every evening with dinner today.")
    pdf.save(source)
    pdf.close()
    parsed = OcrPipeline().parse(source, DocumentMetadata(
        patient_id="patient-a", document_id="note-a", document_name="note.pdf",
        document_type=DocumentType.OUTPATIENT_NOTE, encounter_date=date(2024, 1, 1),
    ))
    output = tmp_path / "note.json"
    parsed.write_json(output)
    store = SqliteStore(tmp_path / "ocr.sqlite")
    try:
        store.save_document(parsed, source, output, "MRN-1", "Synthetic Patient")
        assert store.is_ingested("note-a")
        anchors = store.anchors_for_page("note-a", 1)
        assert any(row["anchor_type"] == "line" for row in anchors)
        assert any(row["anchor_type"] == "token" for row in anchors)
    finally:
        store.close()
