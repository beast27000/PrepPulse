# PrepPulse OCR

Auditable clinical document OCR and provenance extraction engine.

## Quickstart (Standard Python venv)

Clone and set up a standard Python virtual environment:

```powershell
git clone https://github.com/beast27000/PrepPulse.git
cd PrepPulse
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Run tests to verify setup:

```powershell
pytest
```

> **Note on Scanned OCR:** Install [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) for scanned documents/images. On Windows, the engine auto-detects `C:\Program Files\Tesseract-OCR\tesseract.exe`. Native digital PDFs work out of the box without Tesseract.

## Testing & Review UI

Launch the desktop review application:

```powershell
python temp_ui/mock_ui_ocr_testing.py
```

- **Left pane**: Lists all 93 patient packs (75 automatic + 18 manual).
- **Middle pane**: Shows documents for the selected patient and renders visual page previews.
- **Right pane**: Lists OCR evidence anchors (lines and table cells). Clicking an item renders a red bounding box highlight on the document canvas.
- **Processing**: Select any `[MANUAL]` patient and click **Process selected patient** to run OCR, persist records to SQLite, and view bounding boxes.

## Running the OCR Engine

### 1. Extract Single Document
```powershell
python -m preppulse_ocr path/to/document.pdf `
  --patient-id synth-001 `
  --document-type lab_panel `
  --encounter-date 2026-10-13 `
  --output data/outputs/lab-panel.json
```

### 2. Batch Cohort Ingestion
```powershell
python -m preppulse_ocr.database `
  --selection data/active/pack93/selected_manifest.jsonl `
  --corpus-root data/active/pack93 `
  --output-root data/outputs/ocr_json `
  --database data/outputs/preppulse_ocr.sqlite `
  --cohort automatic
```

## Repository Structure

```text
prompts/
  ├── agents/                   # External YAML agent prompts (classification, trajectory, gaps, caregiver, etc.)
  └── rag/                      # External YAML RAG prompts (query reformulation, clinical chatbot)
src/preppulse_ocr/
  ├── engine.py                 # Master OCR engine: models, geometry, table parser, router (FROZEN)
  ├── database.py               # Master data layer: SQLite store, manifest loader, pack builder, ingestion
  └── __init__.py               # Public package exports
src/preppulse_preprocessing/
  ├── chunk.py                  # Section-aware document chunking (Teammate A)
  ├── extract.py                # Fact extraction with terminology mapping (Teammate B)
  ├── ground.py                 # Fail-closed bounding box grounding and review queue
  ├── fhir.py                   # FHIR R4 Bundle conversion (Stage 3)
  ├── store.py                  # Store protocol & MongoStoreAdapter
  └── providers/                # Decoupled LLM providers (LMStudio, Ollama, Mock)
src/preppulse_db/
  ├── mongo_store.py            # Local MongoDB store (patient_documents, document_chunks)
  ├── schemas.py                # MongoDB patient document and chunk schemas
  └── __init__.py               # Public package exports
src/preppulse_rag/
  ├── chunker.py                # Provenance-preserving atomic table row and text chunker
  ├── retriever.py              # Hybrid BM25 + dense vector ensemble retriever with RRF
  ├── llm_provider.py           # Pluggable LLM factory (LM Studio, Ollama, Sarvam AI, OpenAI, Mock)
  └── __init__.py               # Public package exports
src/preppulse_agents/
  ├── schemas.py                # Pydantic brief schemas (Trajectory, Gaps, Mismatches, Caregiver 6-Lang)
  ├── graph.py                  # 8-node LangGraph multi-agent review state machine
  ├── prompt_loader.py          # Modular YAML prompt loader with template variable substitution
  ├── tools.py                  # Deterministic clinical extraction tools (e.g. timeseries extraction)
  └── __init__.py               # Public package exports
scripts/
  └── audit_dataset_pipeline.py # End-to-end audit harness running against 10-patient dataset
temp_ui/
  └── mock_ui_ocr_testing.py    # Desktop visual testing UI for OCR and bounding boxes
tests/                          # Pytest suite
requirements.txt                # Pinned pip dependencies
```

## Running Pipeline Audit & Tests

To execute the end-to-end 10-patient dataset audit against local LM Studio:

```powershell
python scripts/audit_dataset_pipeline.py PP001_Ananya_Baruah
```

To run the automated test suite:

```powershell
pytest tests/test_clinical_agents.py tests/test_hybrid_rag.py tests/test_mongo_store.py src/preppulse_preprocessing/tests -v
```

## Data Assets

- `data/outputs/preppulse_ocr.sqlite`: SQLite database containing ingested documents and 34,797 evidence anchors.
- `data/outputs/ocr_json/`: Durable extracted JSON files.
- `data/active/pack93/`: Active 93-patient 4-document packs.
- `datasets/PrepPulse Dataset/`: Multi-patient dataset batches (6 diabetics, 3 pre-diabetics, 1 non-diabetic).
