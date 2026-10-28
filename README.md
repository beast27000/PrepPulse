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
src/preppulse_ocr/
  ├── engine.py                 # Master OCR engine: models, geometry, table parser, router (FROZEN)
  ├── database.py               # Master data layer: SQLite store, manifest loader, pack builder, ingestion
  └── __init__.py               # Public package exports
src/preppulse_db/
  ├── mongo_store.py            # Local MongoDB store (stage_1_raw_ocr, patient isolation)
  ├── schemas.py                # MongoDB patient document schemas
  └── __init__.py               # Public package exports
src/preppulse_rag/
  ├── chunker.py                # Provenance-preserving atomic table row and text chunker
  ├── retriever.py              # Hybrid BM25 + dense vector ensemble retriever with RRF
  ├── llm_provider.py           # Pluggable LLM factory (Ollama, Sarvam AI, OpenAI, Mock)
  └── __init__.py               # Public package exports
src/preppulse_agents/
  ├── schemas.py                # Pydantic brief schemas (Trajectory, Gaps, Mismatches, Caregiver)
  ├── graph.py                  # LangGraph multi-agent review state machine
  └── __init__.py               # Public package exports
temp_ui/
  └── mock_ui_ocr_testing.py    # Desktop visual testing UI for OCR and bounding boxes
tests/                          # Pytest suite
requirements.txt                # Pinned pip dependencies
```

## Data Assets

- `data/outputs/preppulse_ocr.sqlite`: SQLite database containing ingested documents and 34,797 evidence anchors.
- `data/outputs/ocr_json/`: Durable extracted JSON files.
- `data/active/pack93/`: Active 93-patient 4-document packs.
