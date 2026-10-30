"""Shared test fixtures: a realistic Stage 1 document shaped per the spec."""
from __future__ import annotations

import pytest


def _tokens_from_text(full_text: str) -> list[dict]:
    tokens = []
    y = 100
    for line in full_text.split("\n"):
        x = 80
        for w in line.split():
            tokens.append({"text": w, "bbox": [x, y, x + len(w) * 8, y + 18],
                           "confidence": 1.0, "source": "native"})
            x += len(w) * 8 + 6
        y += 24
    return tokens


LAB_TEXT = """LABORATORY REPORT
Patient Name: Hassan Williams
MRN: 4177874
Specimen Date: 01/06/2024
Glycaemic Panel
Fasting Blood Glucose: 11.4 mmol/L (3.9 - 5.6) HIGH
HbA1c: 8.9 % (4.0 - 6.0) HIGH
Diagnosis: Type 2 Diabetes Mellitus
Rx Medications
Empagliflozin 10mg once daily
Advice: Strict diet compliance advised."""


@pytest.fixture
def lab_document() -> dict:
    return {
        "document_id": "b2b5967a_lab_report_visit1_20240601",
        "patient_id": "b2b5967a",
        "visit_date": "2024-06-01",
        "document_type": "lab_report",
        "stage_1_raw_ocr": {
            "page_count": 1,
            "pages": [{
                "page_number": 1,
                "extraction_method": "native_pdf",
                "full_text": LAB_TEXT,
                "tokens": _tokens_from_text(LAB_TEXT),
                "tables": [],
            }],
        },
    }
