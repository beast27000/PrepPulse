# PrepPulse Database & Collaboration Architecture

This document describes the local MongoDB architecture, the mock testing pipeline, and how the team collaborates via Git.

---

## 1. Collaboration Workflow (Option 1: Git-Based)

Everyone runs their own local instance of MongoDB (`localhost:27017`). There is no cloud database or shared network port.

```
                  ┌──────────────────────────────┐
                  │          Git Repo            │
                  │  (Code + Mock 10 Patients)   │
                  └──────────────┬───────────────┘
                                 │ git pull
         ┌───────────────────────┼───────────────────────┐
         ▼                       ▼                       ▼
    Core Team               Teammate A              Teammate B
 ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
 │ Local Mongo  │        │ Local Mongo  │        │ Local Mongo  │
 │ (port 27017) │        │ (port 27017) │        │ (port 27017) │
 └──────────────┘        └──────────────┘        └──────────────┘
```

1. **Core Team** sets up the local MongoDB store and writes the mock ingestion script `ingest_mock_patients.py`.
2. **Teammates** pull the Git repository onto their machines.
3. Teammates run `python ingest_mock_patients.py` once.
   - This runs the frozen OCR engine over the 10 mock patients.
   - It populates their local MongoDB (`patient_documents` collection) with `stage_1_raw_ocr`.
4. **Teammate A** writes `chunker.py` and pushes their code to Git.
5. **Teammate B** writes `extractor.py` and pushes their code to Git.
6. Everyone pulls and can run the entire pipeline locally on their own laptop.

---

## 2. Who Builds What

| Team Member | Responsibility | Inputs | Outputs |
|---|---|---|---|
| **Core Team (Us)** | Local MongoDB Store (`src/preppulse_db/`), schemas, and mock ingest script (`ingest_mock_patients.py`). | 10 Mock Patient Files in `data/active/v2_patients/` | Populates `patient_documents` with `stage_1_raw_ocr`. |
| **Teammate A** | Structural Chunker (`chunker.py`). Splits OCR text into sections with bounding boxes. | Reads `patient_documents` from local Mongo. | Writes clean chunks to `document_chunks` collection. |
| **Teammate B** | LLM Fact Extractor (`extractor.py`). Runs local Qwen via Ollama, maps medical codes. | Reads `document_chunks` from local Mongo. | Updates `patient_documents` with `stage_2_structured_entities`. |

---

## 3. MongoDB Collections Structure

Database Name: `preppulse` (local at `mongodb://localhost:27017`)

### 1. `patient_documents` (Compound Record)
```json
{
  "_id": "<ObjectId>",
  "document_id": "patient_01_lab_visit1",
  "patient_id": "patient_01",
  "visit_date": "2024-03-15",
  "document_type": "lab_report",
  "source_file": "lab_report_visit1.pdf",
  
  "stage_1_raw_ocr": {
    "engine": "preppulse-ocr-v1",
    "pages": [
      {
        "page_number": 1,
        "full_text": "HbA1c: 7.2 % ...",
        "tokens": [
          { "text": "HbA1c:", "bbox": [120, 340, 180, 360], "confidence": 1.0 }
        ],
        "tables": []
      }
    ]
  },

  "stage_2_structured_entities": null
}
```

### 2. `document_chunks` (Intermediate Bridge)
```json
{
  "_id": "<ObjectId>",
  "chunk_id": "CHK_01_LAB1_P1_C0",
  "document_id": "patient_01_lab_visit1",
  "patient_id": "patient_01",
  "section": "laboratory_results",
  "chunk_text": "HbA1c: 7.2 %",
  "source_page": 1,
  "source_bbox": [120, 340, 180, 360]
}
```

---

## 4. Current Status: Mock Dataset Testing

* The real dataset will be delivered later.
* Current development and testing use the **10-patient mock pack** (`data/active/v2_patients/`) containing 115 files (PDFs, scans, handwritten prescriptions).
* Testing the pipeline against this mock pack ensures that the database, OCR, chunker, and extractor are working before the real patient dataset arrives.
