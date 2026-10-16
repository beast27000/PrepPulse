from pathlib import Path

import fitz

from preppulse_ocr.models import DocumentMetadata, DocumentType
from preppulse_ocr.pipeline import OcrPipeline


def test_digital_pdf_tokens_lines_and_required_metadata(tmp_path: Path) -> None:
    input_pdf = tmp_path / "clinic-note.pdf"
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "Patient synth-001 takes Glargine 14 U every evening.")
    pdf.save(input_pdf)
    pdf.close()

    metadata = DocumentMetadata(
        patient_id="synth-001", document_id="clinic-001", document_name=input_pdf.name,
        document_type=DocumentType.OUTPATIENT_NOTE,
    )
    result = OcrPipeline().parse(input_pdf, metadata)
    assert result.metadata.patient_id == "synth-001"
    assert result.metadata.source_sha256
    assert result.pages[0].page_number == 1
    assert result.pages[0].tokens
    assert result.pages[0].lines
    assert all(0 <= token.bbox.x0 <= 1000 for token in result.pages[0].tokens)
