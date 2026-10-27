from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from preppulse_db.mongo_store import MongoStore
from preppulse_db.schemas import (
    PageRecord,
    PatientDocument,
    Stage1RawOcr,
    TableRecord,
    TokenRecord,
)
from preppulse_ocr.engine import DocumentMetadata, DocumentType, OcrPipeline, ParsedDocument

# ---------- helpers ----------

DOC_TYPE_MAPPING = {
    "patient_record": DocumentType.OUTPATIENT_NOTE,
    "lab_report": DocumentType.LAB_PANEL,
    "doctor_prescription": DocumentType.REFERRAL_ORDER,
    "handwritten_prescription": DocumentType.REFERRAL_ORDER,
    "discharge_summary": DocumentType.DISCHARGE_SUMMARY,
}


def _parse_date(date_str: str | None) -> date | None:
    # Parses dates in DD/MM/YYYY or YYYY-MM-DD formats
    if not date_str:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def map_parsed_doc_to_mongo(
    parsed: ParsedDocument,
    patient_id: str,
    visit_date: str | None,
    raw_doc_type: str,
    doc_form: str | None,
    source_file: str,
    requires_ocr: bool = False,
    degradation: str | None = None,
) -> PatientDocument:
    # Transforms OCR engine ParsedDocument into MongoDB PatientDocument
    pages: list[PageRecord] = []
    for page in parsed.pages:
        tokens: list[TokenRecord] = [
            TokenRecord(
                text=t.text,
                bbox=[t.bbox.x0, t.bbox.y0, t.bbox.x1, t.bbox.y1],
                confidence=t.confidence if t.confidence is not None else 1.0,
                source="ocr" if page.extraction_method == "ocr" else "native",
            )
            for t in page.tokens
        ]

        tables: list[TableRecord] = []
        for idx, table in enumerate(page.tables):
            grid: dict[int, dict[int, str]] = {}
            for cell in table.cells:
                grid.setdefault(cell.row_index, {})[cell.column_index] = cell.text
            rows: list[list[str]] = [
                [row_dict.get(c, "") for c in range(max(row_dict.keys(), default=-1) + 1)]
                for r, row_dict in sorted(grid.items())
            ]
            tables.append(
                TableRecord(
                    table_id=idx,
                    rows=rows,
                    bbox=[table.bbox.x0, table.bbox.y0, table.bbox.x1, table.bbox.y1],
                )
            )

        full_text = "\n".join(line.text for line in page.lines)
        pages.append(
            PageRecord(
                page_number=page.page_number,
                extraction_method=page.extraction_method,
                full_text=full_text,
                tokens=tokens,
                tables=tables,
            )
        )

    return PatientDocument(
        document_id=parsed.metadata.document_id,
        patient_id=patient_id,
        visit_date=visit_date,
        document_type=raw_doc_type,
        document_form=doc_form,
        source_file=source_file,
        requires_ocr=requires_ocr,
        degradation=degradation,
        status="stage_1_complete",
        stage_1_raw_ocr=Stage1RawOcr(page_count=len(pages), pages=pages),
    )


# ---------- batch ingest flow ----------


def ingest_patient_pack(
    patient_dir: Path,
    base_dir: Path,
    store: MongoStore,
    pipeline: OcrPipeline | None = None,
) -> int:
    # Ingests all documents for a single patient directory using ground_truth manifest
    pipeline = pipeline or OcrPipeline()
    gt_path = patient_dir / "ground_truth.json"
    if not gt_path.is_file():
        return 0

    with gt_path.open("r", encoding="utf-8") as f:
        gt_data: dict[str, Any] = json.load(f)

    patient_id = gt_data.get("patient_id", patient_dir.name)
    documents = gt_data.get("documents", [])
    count = 0

    for doc_meta in documents:
        rel_file = doc_meta.get("file")
        if not rel_file:
            continue
        file_path = base_dir / rel_file
        if not file_path.is_file():
            continue

        raw_type = doc_meta.get("type", "patient_record")
        doc_type = DOC_TYPE_MAPPING.get(raw_type, DocumentType.OUTPATIENT_NOTE)
        visit_date_raw = doc_meta.get("visit_date") or doc_meta.get("admit_date")
        parsed_date = _parse_date(visit_date_raw)
        doc_id = f"{patient_id}_{file_path.stem}"

        engine_meta = DocumentMetadata(
            patient_id=patient_id,
            document_id=doc_id,
            document_name=file_path.name,
            document_type=doc_type,
            encounter_date=parsed_date,
            encounter_date_raw=visit_date_raw,
        )

        parsed_doc = pipeline.parse(file_path, engine_meta)
        mongo_doc = map_parsed_doc_to_mongo(
            parsed=parsed_doc,
            patient_id=patient_id,
            visit_date=str(parsed_date) if parsed_date else visit_date_raw,
            raw_doc_type=raw_type,
            doc_form=doc_meta.get("form"),
            source_file=file_path.name,
            requires_ocr=doc_meta.get("requires_ocr", False),
            degradation=doc_meta.get("degradation"),
        )
        store.write_stage1(mongo_doc)
        count += 1

    return count
