# PrepPulse Clinical Pre-Processing Track: Developer Handoff Guide

This repository guide details the architecture, input/output data contracts, and implementation steps for building the **PrepPulse Clinical Pre-Processing and Compilation Layer**.

---

## 1. System Overview

PrepPulse processes multi-document patient records (PDFs, scans, handwritten notes). The OCR layer extracts tokens, lines, and bounding boxes. To prevent LLM hallucinations during downstream RAG and agent reasoning, this pre-processing layer transforms unstructured OCR text into structured, source-verified clinical facts.

```
                    ┌─────────────────────────┐
                    │   PrepPulse OCR Engine  │
                    └────────────┬────────────┘
                                 │ writes
                                 ▼
                     MongoDB: patient_documents
                        (stage_1_raw_ocr)
                                 │
                                 │ reads
                                 ▼
                    ┌─────────────────────────┐
                    │       TEAMMATE A        │
                    │   Structural Chunker    │
                    └────────────┬────────────┘
                                 │ writes
                                 ▼
                     MongoDB: document_chunks
                                 │
                                 │ reads
                                 ▼
                    ┌─────────────────────────┐
                    │       TEAMMATE B        │
                    │ LLM Fact & Code Mapper  │
                    └────────────┬────────────┘
                                 │ updates
                                 ▼
                     MongoDB: patient_documents
                    (stage_2_structured_entities)
```

---

## 2. Environment & Prerequisites

* **Python:** 3.11+
* **Database:** Local MongoDB instance running at `mongodb://localhost:27017`
* **Database Name:** `preppulse`
* **Dependencies:**
  ```bash
  pip install pymongo pydantic rapidfuzz langchain-ollama
  ```
* **Local LLM Engine (for Teammate B):**
  Install [Ollama](https://ollama.ai) and pull Qwen 2.5:
  ```bash
  ollama pull qwen2.5:7b
  # or lighter version:
  ollama pull qwen2.5:3b
  ```

---

## 3. Teammate A: Document Sectioning & Structural Chunker

### 3.1 Responsibility
Convert noisy raw OCR documents into isolated, semantically grouped sections (Medications, Labs, Notes) while **preserving exact bounding-box coordinates** so the UI can later highlight citations.

### 3.2 Input Contract
* **Collection:** `patient_documents`
* **Field:** `stage_1_raw_ocr`
* **Sample Input Structure:**
```json
{
  "_id": "671da...",
  "document_id": "PP-PATIENT-02-LAB-VISIT2",
  "patient_id": "PP-PATIENT-02",
  "visit_date": "2024-03-15",
  "document_type": "lab_report",
  "stage_1_raw_ocr": {
    "page_count": 1,
    "pages": [
      {
        "page_number": 1,
        "full_text": "METABOLIC LAB REPORT\nPatient: J. Williams\nHbA1c: 7.2 %\nFasting Blood Sugar: 142 mg/dL",
        "tokens": [
          {"text": "HbA1c:", "bbox": [120, 340, 180, 360], "confidence": 1.0},
          {"text": "7.2", "bbox": [190, 340, 220, 360], "confidence": 1.0},
          {"text": "%", "bbox": [225, 340, 240, 360], "confidence": 1.0}
        ],
        "tables": []
      }
    ]
  }
}
```

### 3.3 Core Processing Logic
1. **Section Detection:** Use regex to identify boundary markers:
   - `laboratory_results`: Matches "Lab Results", "Metabolic Panel", "Test", "HbA1c", "Glucose".
   - `medications`: Matches "Rx", "Medications", "Current Meds", "Prescriptions".
   - `assessment`: Matches "Assessment", "Impression", "Diagnosis".
   - `instructions`: Matches "Plan", "Advice", "Follow-up".
2. **Table Preservation:** If `pages[].tables` exists, treat each table row as a single atomic chunk. Do not split rows.
3. **Bounding Box Preservation:** For each chunk, calculate the enclosing bounding box `[x0, y0, x1, y1]` in normalized `[0, 1000]` coordinate space using the tokens that form that chunk.

### 3.4 Output Contract
* **Collection:** `document_chunks`
* **Document Schema:**
```json
{
  "chunk_id": "CHK_PATIENT02_DOC1_P1_C0",
  "document_id": "PP-PATIENT-02-LAB-VISIT2",
  "patient_id": "PP-PATIENT-02",
  "visit_date": "2024-03-15",
  "document_type": "lab_report",
  "section_type": "laboratory_results",
  "chunk_text": "HbA1c: 7.2 % (Ref: 4.0 - 5.6) High",
  "source_page": 1,
  "source_bbox": [120, 340, 240, 360],
  "created_at": "2026-10-27T01:30:00Z"
}
```

### 3.5 Deliverable Checklist
- [ ] Script or module `chunker.py` that processes documents from `patient_documents`.
- [ ] Keeps medication names grouped with their dosage and frequency.
- [ ] Populates `document_chunks` with normalized `[0, 1000]` coordinates.

---

## 4. Teammate B: LLM Fact Extraction & Terminology Normalizer

### 4.1 Responsibility
Read chunk text, run local Qwen extraction with strict Pydantic schemas, attach standardized medical codes (LOINC, RxNorm, ICD-10) using local dictionary CSVs, and update `stage_2_structured_entities` in MongoDB.

### 4.2 Input Contract
* **Collection:** `document_chunks` (generated by Teammate A)

### 4.3 Extraction Schemas (Pydantic Models)

```python
from pydantic import BaseModel, Field
from typing import List, Optional

class LabEntity(BaseModel):
    test_name: str
    loinc_code: Optional[str] = None
    value: float
    unit: Optional[str] = None
    reference_range: Optional[str] = None
    flag: Optional[str] = None  # "H", "L", "N"
    visit_date: str
    source_page: int
    source_bbox: List[int]
    confidence: float
    anchor_text: str

class MedicationEntity(BaseModel):
    name: str
    rxnorm_code: Optional[str] = None
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    route: Optional[str] = "oral"
    prescribed_date: Optional[str] = None
    source_page: int
    source_bbox: List[int]
    confidence: float
    anchor_text: str

class DiagnosisEntity(BaseModel):
    description: str
    icd10_code: Optional[str] = None
    recorded_date: Optional[str] = None
    source_page: int
    source_bbox: List[int]
    confidence: float
```

### 4.4 Local Medical Code Lookup
Do not make live network API calls. Use offline CSV tables with `rapidfuzz`:
* **Labs (LOINC):** `loinc_common.csv` (e.g., `HbA1c` ➔ `4548-4`, `Fasting Glucose` ➔ `1558-6`, `eGFR` ➔ `33914-3`)
* **Medications (RxNorm):** `rxnorm_common.csv` (e.g., `Metformin` ➔ `6809`, `Empagliflozin` ➔ `1656339`, `Glargine` ➔ `274783`)
* **Diagnoses (ICD-10):** `icd10_common.csv` (e.g., `Type 2 Diabetes Mellitus` ➔ `E11.9`)

Matching rule: If string match score is $\ge 85\%$, map the code; otherwise leave `null` and set a flag.

### 4.5 Output Contract
* **Collection:** `patient_documents`
* **Target Field:** Update `stage_2_structured_entities`
```json
{
  "stage_2_structured_entities": {
    "schema_version": "1.0",
    "patient_id": "PP-PATIENT-02",
    "compiled_by": "qwen2.5-extractor-v1",
    "labs": [
      {
        "test_name": "HbA1c",
        "loinc_code": "4548-4",
        "value": 7.2,
        "unit": "%",
        "reference_range": "4.0 - 5.6",
        "flag": "H",
        "visit_date": "2024-03-15",
        "source_page": 1,
        "source_bbox": [120, 340, 240, 360],
        "confidence": 0.98,
        "anchor_text": "HbA1c: 7.2 %"
      }
    ],
    "medications": [
      {
        "name": "Empagliflozin",
        "rxnorm_code": "1656339",
        "dosage": "10mg",
        "frequency": "once daily",
        "route": "oral",
        "prescribed_date": "2024-03-15",
        "source_page": 1,
        "source_bbox": [80, 210, 400, 230],
        "confidence": 0.96,
        "anchor_text": "Empagliflozin 10mg once daily"
      }
    ],
    "diagnoses": [],
    "advice": "Low carbohydrate diet recommended."
  }
}
```

### 4.6 Deliverable Checklist
- [ ] Script or module `extractor.py` that queries `document_chunks` and invokes Ollama Qwen.
- [ ] Module `code_mapper.py` with CSV dictionary lookup functions.
- [ ] Updates the corresponding `patient_documents` entry under `stage_2_structured_entities`.

---

## 5. Verification Against Ground Truth

Each patient in `data/active/v2_patients/` has a `ground_truth.json` file.
After running your pipeline:
1. Verify that extracted lab values (`hba1c`, `fasting_glucose`, `egfr`) match `ground_truth.json` within $\pm 0.1$.
2. Verify that extracted medication names match the active prescription list in `ground_truth.json`.

