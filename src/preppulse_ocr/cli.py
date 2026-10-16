from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from .models import DocumentMetadata, DocumentType
from .pipeline import OcrPipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract provenance-preserving PrepPulse OCR JSON.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--patient-id", required=True)
    parser.add_argument("--document-id")
    parser.add_argument("--document-type", required=True, choices=[item.value for item in DocumentType])
    parser.add_argument("--encounter-date", type=date.fromisoformat)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    metadata = DocumentMetadata(
        patient_id=args.patient_id, document_id=args.document_id or args.input.stem,
        document_name=args.input.name, document_type=DocumentType(args.document_type),
        encounter_date=args.encounter_date,
    )
    result = OcrPipeline().parse(args.input, metadata)
    result.write_json(args.output)


if __name__ == "__main__":
    main()
