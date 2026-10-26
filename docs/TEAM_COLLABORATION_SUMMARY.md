# PrepPulse Team Collaboration Quick Summary

Hey team! Here is the quick breakdown of how we are collaborating on PrepPulse and who owns what.

---

### 1. The Big Picture
We are processing longitudinal medical records (lab reports, doctor prescriptions, consultation notes).
- **Core Team (Us):** Converts PDFs/scans into raw text & bounding boxes via OCR, and stores it in local MongoDB (**Stage 1**).
- **Teammate A (Chunker):** Reads raw OCR and splits it into clean, labeled sections with bounding boxes preserved.
- **Teammate B (Extractor):** Reads the chunks and uses a local LLM (Qwen) to separate clinical facts (labs, medications, diagnoses) from doctor notes/theory (**Stage 2**).

---

### 2. How to Set Up on Your Machine (Option 1: Git + Local Mongo)
Everyone runs their own MongoDB locally (`mongodb://localhost:27017/preppulse`). No cloud database needed.

1. **Pull the latest code:**
   ```bash
   git pull origin main
   ```
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Seed your local MongoDB with the 10 mock patients:**
   ```bash
   python ingest_mock_patients.py
   ```
   *(This populates your local `patient_documents` collection with `stage_1_raw_ocr` data).*

---

### 3. Clear Responsibilities

#### **Teammate A — Structural Chunker (`chunker.py`)**
* **Input:** Reads from `patient_documents` (field: `stage_1_raw_ocr`).
* **Task:** Detect section boundaries (`medications`, `labs`, `doctor_notes`, `plans`) and keep bounding boxes `[x0, y0, x1, y1]` intact.
* **Output:** Writes to MongoDB collection `document_chunks`.
  ```json
  {
    "document_id": "patient_01_doc_1",
    "patient_id": "patient_01",
    "section": "medications",
    "text": "Empagliflozin 10mg once daily",
    "source_page": 1,
    "source_bbox": [120, 340, 180, 360]
  }
  ```

#### **Teammate B — LLM Fact Extractor (`extractor.py`)**
* **Input:** Reads from `document_chunks`.
* **Task:** Run local Qwen (via Ollama) to extract concrete entities from messy doctor notes:
  - Labs ➔ test name, numerical value, unit, reference range
  - Meds ➔ drug name, dosage, frequency
  - Doctor's theory/instructions ➔ save under `advice` / `notes`
* **Output:** Updates `patient_documents` in MongoDB under `stage_2_structured_entities`.
  ```json
  {
    "stage_2_structured_entities": {
      "labs": [{ "test_name": "HbA1c", "value": 8.9, "unit": "%", "loinc_code": "4548-4" }],
      "medications": [{ "name": "Empagliflozin", "dosage": "10mg", "frequency": "once daily" }],
      "advice": "Strict carbohydrate restriction, 30 mins brisk walking daily."
    }
  }
  ```

---

### 4. Ground Truth Verification
In each patient folder (`data/active/v2_patients/patient_XX/`), there is a `ground_truth.json`.
Compare your extracted values against this file to verify extraction accuracy.
