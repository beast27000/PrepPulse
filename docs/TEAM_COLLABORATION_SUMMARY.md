# PrepPulse: 3-Stage Pipeline Breakdown & Team Collaboration

PrepPulse uses a **3-Stage Pipeline** stored in MongoDB to process patient medical records. Here is what happens in each stage and who owns it:

---

```
┌────────────────────────────────────────────────────────┐
│ STAGE 1: Raw OCR & Spatial Ingestion (CORE TEAM / US)  │
│ - Scans & PDFs ➔ OCR Engine                            │
│ - Outputs full text, word tokens, bboxes [0, 1000]     │
│ - Populates: patient_documents.stage_1_raw_ocr         │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ STAGE 2: Pre-Processing & Fact Extraction (TEAMMATES)  │
│                                                        │
│ • Teammate A (Chunker):                                │
│   - Splits stage_1 text into clinical sections         │
│   - Writes to: document_chunks                         │
│                                                        │
│ • Teammate B (Extractor):                              │
│   - Consumes document_chunks                           │
│   - Runs local Qwen LLM to extract facts vs notes      │
│   - Maps LOINC / RxNorm / ICD-10 codes                 │
│   - Populates: patient_documents.stage_2_structured_   │
│                entities                                │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ STAGE 3: FHIR R4 Standard Output (CORE TEAM / US)      │
│ - Reads stage_2 structured facts                       │
│ - Maps to standard FHIR R4 resources:                  │
│   - Labs ➔ Observation                                 │
│   - Meds ➔ MedicationRequest                           │
│   - Diagnoses ➔ Condition                              │
│   - Patient Info ➔ Patient                             │
│ - Populates: patient_documents.stage_3_fhir_output     │
└────────────────────────────────────────────────────────┘
```

---

## Stage-by-Stage Breakdown

### STAGE 1 (Owned by Core Team / Us)
* **What happens:** We run our frozen OCR engine over all patient files (PDFs, scans, handwritten notes).
* **What it produces:** Text, tokens, normalized bounding boxes `[0, 1000]`, and table grids.
* **Where it is stored:** MongoDB `patient_documents` collection under `stage_1_raw_ocr`.
* **State of Stage 2 & 3 at this point:** Initialized as `null`.

---

### STAGE 2 (Owned by Teammates A & B)
* **What happens:** Transform raw, noisy OCR text and doctor consultation notes into clean clinical facts.
* **Teammate A:**
  - Reads `stage_1_raw_ocr`.
  - Splits text by clinical sections (`medications`, `labs`, `doctor_notes`, `plans`).
  - Preserves exact bounding boxes.
  - Writes records to `document_chunks`.
* **Teammate B:**
  - Reads `document_chunks`.
  - Runs local Qwen LLM (Ollama) to extract concrete entities (test names, results, dosages) and separates out doctor theory/advice.
  - Maps to LOINC (labs), RxNorm (drugs), and ICD-10 (diagnoses).
  - Writes the final structured JSON back to `stage_2_structured_entities`.

---

### STAGE 3 (Owned by Core Team / Us)
* **What happens:** Standardize the extracted clinical facts into FHIR R4 format for hospital EHR compatibility.
* **What it produces:** An official FHIR R4 Transaction Bundle.
  - Maps `stage_2.labs` ➔ FHIR `Observation`
  - Maps `stage_2.medications` ➔ FHIR `MedicationRequest`
  - Maps `stage_2.diagnoses` ➔ FHIR `Condition`
  - Maps `stage_2.patient` ➔ FHIR `Patient`
* **Where it is stored:** MongoDB `patient_documents` collection under `stage_3_fhir_output`.

---

## How to Set Up & Run (Option 1: Local Mongo via Git)

1. **Pull the code:**
   ```bash
   git pull origin main
   ```
2. **Install requirements:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Run Stage 1 seed script on your machine:**
   ```bash
   python ingest_mock_patients.py
   ```
   This populates your local MongoDB with all 10 mock patients in **Stage 1**, ready for your **Stage 2** scripts to consume.
