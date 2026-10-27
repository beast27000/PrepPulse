# PrepPulse: Stage 2 & Stage 3 Technical Specification

This document details the MongoDB data contracts, expected workflows, and output formats for the **Clinical Fact Extraction (Stage 2)** and **FHIR R4 Standardization (Stage 3)** pipeline.

---

## 1. System Overview & The 3 Stages

- **Stage 1 (Core Team / OCR):** The OCR engine parses patient documents (PDFs, scans, prescriptions) and stores full text, word tokens, normalized `[0, 1000]` bounding boxes, and tables as a JSON document in MongoDB (`patient_documents` collection).
- **Stage 2 (Your Scope - Clinical Fact Extraction):** Consume the Stage 1 OCR output, run your LLM extraction pipeline to separate actionable clinical facts from conversational doctor notes, and save structured entities back to MongoDB.
- **Stage 3 (Your Scope - FHIR R4 Standardization):** Map the extracted clinical facts from Stage 2 into standardized FHIR R4 transaction resources (`Observation`, `MedicationRequest`, `Condition`, `Patient`) and update the document in MongoDB.

---

## 2. Core Architectural Principles (Read Before Building)

### Principle A: Build a 100% Generic Pipeline (Mock Data is ONLY for Testing)
- The files provided in `data/active/v2_patients/` are **strictly synthetic mock test cases** to develop and benchmark against.
- **Do NOT hardcode** any patient names, document structures, regex shortcuts, or template assumptions based on these 10 mock patients.
- The pipeline you build must be fully generic. In production, documents will arrive from 100 different clinics and hospitals with random layouts, unformatted notes, and variable handwriting. The pipeline must take any arbitrary document's OCR output and extract facts cleanly.

### Principle B: Pluggable LLM Architecture (Decoupled Provider)
- While you develop Stage 2 using a local LLM (e.g., `qwen2.5:7b` via Ollama), you **must isolate the LLM calling logic** behind a clean interface or wrapper class (e.g. `LLMClient` or `get_llm_provider()`).
- Include all configuration files, environment variable hooks (e.g. `LLM_PROVIDER=ollama`, `OLLAMA_MODEL=qwen2.5:7b`, `LLM_BASE_URL=http://localhost:11434`), and provider wrappers.
- **Goal:** When this code is merged and someone wants to swap in another LLM down the line (e.g., Claude, OpenAI, DeepSeek, or another local engine), **they should only need to change one config setting or plug in a provider class**—zero changes to your extraction logic, schema validation, or database code.

---

## 3. Step 0: Seed Your Local MongoDB With Test Data

Since MongoDB runs locally on your machine (`localhost:27017`), your database starts empty when you pull the repo.

Before you can develop or test, run our ingestion script once:
```bash
python ingest_mock_patients.py
```
**What this script does:**
1. It reads the test patient files from `data/active/v2_patients/`.
2. It runs our frozen OCR engine over all PDFs, scans, and prescriptions.
3. It converts the extracted text and bounding boxes into JSON records and inserts them into your local MongoDB under the `patient_documents` collection.

Now your local MongoDB is populated with Stage 1 JSON documents and ready for your Stage 2/3 code.

---

## 3. What Exists in MongoDB (Stage 1 Input)

When querying MongoDB via `store.get_document(document_id)` or `store.list_documents(patient_id)`, each record in `patient_documents` has this exact JSON structure:

```json
{
  "_id": "671da8e1f0a2...",
  "document_id": "b2b5967a_lab_report_visit1_20240601",
  "patient_id": "b2b5967a",
  "visit_date": "2024-06-01",
  "document_type": "lab_report",
  "document_form": "digital_pdf",
  "source_file": "lab_report_visit1_20240601.pdf",
  "status": "stage_1_complete",
  "ingested_at": "2026-10-27T11:30:00Z",

  "stage_1_raw_ocr": {
    "engine_version": "1.0.0-frozen",
    "processed_at": "2026-10-27T11:30:00Z",
    "page_count": 1,
    "pages": [
      {
        "page_number": 1,
        "extraction_method": "native_pdf",
        "full_text": "LABORATORY REPORT\nPatient Name: Hassan Williams\nMRN: 4177874\nSpecimen Date: 01/06/2024\nGlycaemic Panel\nFasting Blood Glucose: 11.4 mmol/L (3.9 - 5.6) HIGH\nHbA1c: 8.9 % (4.0 - 6.0) HIGH",
        "tokens": [
          { "text": "HbA1c:", "bbox": [120, 340, 180, 360], "confidence": 1.0, "source": "native" },
          { "text": "8.9", "bbox": [190, 340, 220, 360], "confidence": 1.0, "source": "native" },
          { "text": "%", "bbox": [225, 340, 240, 360], "confidence": 1.0, "source": "native" }
        ],
        "tables": []
      }
    ]
  },

  "stage_2_structured_entities": null,
  "stage_3_fhir_output": null
}
```

---

## 4. What You Need to Output

### Stage 2: Clean Structured Clinical Facts
You take `stage_1_raw_ocr["pages"][i]["full_text"]` and `tokens`, run your LLM (e.g. local Qwen via Ollama), and extract clean clinical entities.

```json
{
  "stage_2_structured_entities": {
    "schema_version": "1.0",
    "compiled_at": "2026-10-27T14:00:00Z",
    "compiled_by": "llm_clinical_extractor_v1",
    "labs": [
      {
        "test_name": "HbA1c",
        "loinc_code": "4548-4",
        "value": 8.9,
        "unit": "%",
        "reference_range": "4.0 - 6.0",
        "flag": "HIGH",
        "visit_date": "2024-06-01",
        "source_page": 1,
        "source_bbox": [120, 340, 240, 360],
        "confidence": 0.98,
        "anchor_text": "HbA1c: 8.9 %"
      },
      {
        "test_name": "Fasting Blood Glucose",
        "loinc_code": "1558-6",
        "value": 11.4,
        "unit": "mmol/L",
        "reference_range": "3.9 - 5.6",
        "flag": "HIGH",
        "visit_date": "2024-06-01",
        "source_page": 1,
        "source_bbox": [120, 310, 280, 330],
        "confidence": 0.97,
        "anchor_text": "Fasting Blood Glucose: 11.4 mmol/L"
      }
    ],
    "medications": [
      {
        "name": "Empagliflozin",
        "rxnorm_code": "1656339",
        "dosage": "10mg",
        "frequency": "once daily",
        "route": "oral",
        "prescribed_date": "2024-06-01",
        "source_page": 1,
        "source_bbox": [80, 210, 400, 230],
        "confidence": 0.96,
        "anchor_text": "Empagliflozin 10mg once daily"
      }
    ],
    "diagnoses": [
      {
        "description": "Type 2 Diabetes Mellitus",
        "icd10_code": "E11.9",
        "recorded_date": "2024-06-01",
        "source_page": 1,
        "source_bbox": [80, 120, 350, 140],
        "confidence": 0.99
      }
    ],
    "advice": "Strict diet compliance advised. Home glucose log to be maintained.",
    "flags": []
  }
}
```

> **Dynamic Schema Support (`extra="allow"`):**  
> If the LLM identifies extra clinical concepts not covered above (e.g., `allergies: ["Penicillin"]`, `vitals: {"blood_pressure": "120/80"}`, `surgical_history: ["Appendectomy"]`), you can include them directly in the dictionary. MongoDB and Pydantic will accept and preserve them.

---

### Stage 3: Standardized FHIR R4 Bundle
Map the Stage 2 entities into an official FHIR R4 transaction bundle:

```json
{
  "stage_3_fhir_output": {
    "resourceType": "Bundle",
    "type": "transaction",
    "entry": [
      {
        "resource": {
          "resourceType": "Observation",
          "status": "final",
          "code": {
            "coding": [
              {
                "system": "http://loinc.org",
                "code": "4548-4",
                "display": "HbA1c"
              }
            ]
          },
          "subject": { "reference": "Patient/b2b5967a" },
          "effectiveDateTime": "2024-06-01",
          "valueQuantity": {
            "value": 8.9,
            "unit": "%",
            "system": "http://unitsofmeasure.org"
          }
        }
      },
      {
        "resource": {
          "resourceType": "MedicationRequest",
          "status": "active",
          "intent": "order",
          "medicationCodeableConcept": {
            "coding": [
              {
                "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                "code": "1656339",
                "display": "Empagliflozin"
              }
            ]
          },
          "subject": { "reference": "Patient/b2b5967a" },
          "dosageInstruction": [
            { "text": "10mg once daily oral" }
          ]
        }
      }
    ]
  }
}
```

---

## 5. Complete Runnable Python Test Script

Here is a complete, self-contained Python script to test your Stage 2 and Stage 3 pipeline against local MongoDB:

```python
from preppulse_db.mongo_store import MongoStore


def run_pipeline():
    # 1. Connect to local MongoDB
    store = MongoStore(uri="mongodb://localhost:27017", db_name="preppulse")
    store.connect()

    # 2. Check document count (seeded by ingest_mock_patients.py)
    total_docs = store.count_documents()
    print(f"Total Stage 1 documents available in MongoDB: {total_docs}")

    if total_docs == 0:
        print("Error: No documents in MongoDB. Run: python ingest_mock_patients.py")
        return

    # 3. Fetch one document to process
    documents = store.list_documents()
    target_doc = documents[0]
    doc_id = target_doc["document_id"]
    print(f"\nProcessing Document ID: {doc_id}")

    # Read the OCR text from Stage 1
    page_text = target_doc["stage_1_raw_ocr"]["pages"][0]["full_text"]
    print(f"--- Stage 1 OCR Text Snippet ---\n{page_text[:200]}...\n")

    # 4. Extract Stage 2 Facts (Your LLM logic goes here)
    stage_2_facts = {
        "compiled_by": "llm_extractor_test",
        "labs": [
            {
                "test_name": "HbA1c",
                "value": 8.9,
                "unit": "%",
                "flag": "HIGH",
                "loinc_code": "4548-4",
            }
        ],
        "medications": [
            {
                "name": "Empagliflozin",
                "dosage": "10mg",
                "frequency": "once daily",
                "rxnorm_code": "1656339",
            }
        ],
        "advice": "Strict dietary control and exercise advised.",
        "allergies": ["Penicillin"],  # Extra dynamic field accepted automatically
    }

    # Write Stage 2 back to MongoDB
    ok_stage2 = store.write_stage2(doc_id, stage_2_facts)
    print(f"Stage 2 Write Success: {ok_stage2}")

    # 5. Convert to FHIR R4 Bundle (Your FHIR mapping logic goes here)
    stage_3_fhir = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            {
                "resource": {
                    "resourceType": "Observation",
                    "status": "final",
                    "code": {
                        "coding": [{"system": "http://loinc.org", "code": "4548-4", "display": "HbA1c"}]
                    },
                    "valueQuantity": {"value": 8.9, "unit": "%"},
                }
            },
            {
                "resource": {
                    "resourceType": "MedicationRequest",
                    "status": "active",
                    "medicationCodeableConcept": {
                        "coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": "1656339", "display": "Empagliflozin"}]
                    },
                    "dosageInstruction": [{"text": "10mg once daily"}],
                }
            },
        ],
    }

    # Write Stage 3 back to MongoDB
    ok_stage3 = store.write_stage3(doc_id, stage_3_fhir)
    print(f"Stage 3 Write Success: {ok_stage3}")

    # 6. Verify complete updated record
    final_record = store.get_document(doc_id)
    print(f"\nFinal Document Status: {final_record['status']}")
    print(f"Stage 2 Medications: {final_record['stage_2_structured_entities']['medications']}")
    print(f"Stage 2 Allergies: {final_record['stage_2_structured_entities']['allergies']}")
    print(f"Stage 3 Bundle Type: {final_record['stage_3_fhir_output']['resourceType']}")

    store.close()


if __name__ == "__main__":
    run_pipeline()
```

---

## 6. Verification Against Ground Truth

Each patient directory in `data/active/v2_patients/` contains an authoritative `ground_truth.json`.
Compare your extracted values against this file to ensure accuracy:
- Extracted lab numbers (`hba1c`, `fasting_glucose`, `egfr`) should match within $\pm 0.1$.
- Prescribed drug names and dosages should match the active prescriptions list.
