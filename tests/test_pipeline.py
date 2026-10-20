import io
from pathlib import Path

import fitz
from PIL import Image, ImageDraw

from preppulse_ocr.engine import DocumentMetadata, DocumentType, OcrPipeline


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


def test_hybrid_pdf_extracts_both_native_and_ocr_tokens(tmp_path: Path) -> None:
    img = Image.new("RGB", (400, 120), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((30, 40), "GLUCOSE 110", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    input_pdf = tmp_path / "hybrid-note.pdf"
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((72, 72), "Patient Maria Clinical Header Note")
    page.insert_image(fitz.Rect(72, 200, 472, 320), stream=buf.getvalue())
    doc.save(input_pdf)
    doc.close()

    metadata = DocumentMetadata(
        patient_id="patient-hybrid", document_id="hybrid-001", document_name=input_pdf.name,
        document_type=DocumentType.OUTPATIENT_NOTE,
    )
    result = OcrPipeline().parse(input_pdf, metadata)
    assert result.pages[0].extraction_method == "hybrid"
    token_texts = [token.text for token in result.pages[0].tokens]
    assert any(text == "Maria" for text in token_texts)
    assert any(text in {"GLUCOSE", "110"} for text in token_texts)
    assert all(0 <= token.bbox.x0 <= 1000 for token in result.pages[0].tokens)
