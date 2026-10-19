# PrepPulse OCR

Sprint 1 foundation for extracting auditable clinical-document content from digital PDFs,
scanned PDFs, PNGs, and JPEGs.

## Teammate setup and verification

Use these commands from the repository root after cloning the project:

```powershell
git clone https://github.com/beast27000/PrepPulse.git
cd PrepPulse
uv sync --extra dev
uv run pytest
```

`uv sync --extra dev` creates or updates the project-local `.venv` and installs the locked
runtime and development dependencies. `uv run pytest` runs the OCR contract tests using that
environment, so manually activating a virtual environment is optional.

To activate it for an interactive shell on Windows, use:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the Tesseract desktop binary separately and ensure `tesseract` is available on your
`PATH`; it is required to process scanned PDFs and images. Digital PDFs can be tested without
Tesseract. This section is the canonical team setup guide and will be updated whenever a new
required prerequisite, command, or service is introduced.

On Windows, the pipeline also detects the standard installation at
`C:\Program Files\Tesseract-OCR\tesseract.exe` when a freshly installed binary has not yet
appeared in the current shell's `PATH`.

## Project status

The OCR foundation is implemented and tested. The LITE synthetic corpus is extracted locally
for testing but is not yet integrated with the OCR runner. RAG, agents, API, and UI are
intentionally out of scope until the OCR/backend base is stable. See [TO_DO.md](TO_DO.md) for
the live delivery tracker and [AGENTS.md](AGENTS.md) for the repository working agreement.

## Dataset handling

The delivered archives are local test assets, not source code. Track the delivery guide and
dataset context in Git, but do not commit ZIP archives or extracted documents. The first local
test corpus is extracted from `preppulse_synthetic_LITE.zip` into
`data/raw/preppulse_synthetic_lite/`.

LITE provides 720 synthetic patient records and 100 rendered sample documents. The full
documents manifest describes 4,156 rendered documents across 300 patients; 93 patients have
all four required core document types. The sample documents, their manifest, and the OCR output
are the first test path. See [`datasets/dataset_context.md`](datasets/dataset_context.md) for
the verified inventory.

## Guarantees

- Every token and reconstructed line has a normalized `[0, 1000]` bounding box.
- Source dimensions and original coordinates are retained for PDF.js overlays later.
- Lab panels retain table cells with explicit row/column relationships.
- Metadata is explicit and immutable in the output: patient ID, document ID/name, document
  type, encounter date, and page number.
- Native PDF text is preferred; image OCR is used only for scanned/low-text pages.

## Project layout

```text
src/preppulse_ocr/    Pipeline and output contract
tests/                Contract, coordinate, routing, and table tests
data/fixtures/        Safe, synthetic test inputs only
docs/                 Design and dataset contracts
TO_DO.md              Living delivery tracker
AGENTS.md             Planning and version-control agreement
```

## Environment details

```powershell
uv sync --extra dev
```

`uv sync` is the supported setup command; it creates `.venv` automatically. Run the tests with
`uv run pytest` after dependency changes or before sharing OCR changes.

## Run

```powershell
uv run preppulse-ocr path/to/document.pdf `
  --patient-id synth-001 `
  --document-type lab_panel `
  --encounter-date 2026-10-13 `
  --output data/outputs/lab-panel.json
```

The output JSON is the contract future RAG, agents, and the source-highlighting UI consume.

## Approved Sprint 1 local workflow

The active test corpus is deliberately separate from the delivered archives. Running the
following creates a Git-ignored `data/active/pack93/` containing exactly four selected source
documents for each of the 93 patients with complete packs. It labels the first 75 patients as
the automatic cohort and the remaining 18 as the manual-review cohort.

```powershell
uv run preppulse-pack `
  --manifest data/raw/preppulse_synthetic_lite/datasets/documents_manifest.jsonl `
  --records-dir data/raw/preppulse_synthetic_lite/records `
  --archives-dir datasets `
  --output data/active/pack93
```

Ingest the automatic 75-patient cohort (300 documents) into SQLite and write durable OCR JSON:

```powershell
uv run preppulse-ingest `
  --selection data/active/pack93/selected_manifest.jsonl `
  --corpus-root data/active/pack93 `
  --output-root data/outputs/ocr_json `
  --database data/outputs/preppulse_ocr.sqlite
```

Open the local Tkinter reviewer to inspect original source pages, OCR lines/table cells, and
their normalized-box highlights. It can process the reserved 18 manual patients one patient at
a time.

```powershell
uv run preppulse-review `
  --selection data/active/pack93/selected_manifest.jsonl `
  --corpus-root data/active/pack93 `
  --output-root data/outputs/ocr_json `
  --database data/outputs/preppulse_ocr.sqlite
```

The delivery ZIPs and original LITE extraction are retained as immutable local sources. Only
the active `pack93` folder is used for this Sprint 1 test; no raw archive is deleted or added to Git.

### Current local Sprint 1 result

The active pack has been built successfully: 93 patients, 372 selected source documents, and
exactly four document types per patient. The automatic cohort has completed: **75 patients / 300
documents** are persisted in `data/outputs/preppulse_ocr.sqlite`, with **34,797** token, line,
and table-cell evidence anchors. Their durable OCR JSON is in `data/outputs/ocr_json/`.

The 18 intentionally unprocessed manual-review patients are:

`b6d482911a`, `b7a53f9a59`, `b81a0d569a`, `c212fde59d`, `ca56ccbf0b`, `ca7c820419`, `cf3bb2a6f0`, `d123a26a0a`, `d16f595190`, `d4c966a125`, `d91b46cd87`, `d92e869072`, `dbaa5f2643`, `dc7b81b7c9`, `dc9ce68574`, `e9c0e51370`, `fa2cdb4535`, and `fda098fcfd`.

Start `preppulse-review` using the command above, select a `[MANUAL]` patient, and click
**Process selected patient**. Then select a document and an OCR evidence row to see its red
normalized-coordinate highlight over the source page.

## Target architecture

PrepPulse is deliberately layered so each stage preserves a direct path back to source evidence:

```text
Original PDF/image (local file storage)
            ↓
OCR/native-PDF extraction
            ↓
Normal database: patients, documents, pages, evidence anchors, findings, review actions
            ↓
RAG indexes: BM25 + dense-vector search over provenance-carrying chunks
            ↓
Validated agents: trajectory, care gaps, mismatches, caregiver handoff
            ↓
Source-proof UI: card click → document/page → highlighted evidence
```

### Normal database

The normal relational database is the system of record. Start with SQLite for local development;
move to PostgreSQL when the backend is multi-user or deployed. It will store patient/document
relationships, page metadata, OCR anchors, lab-table cells, validated findings, caregiver items,
and accept/edit/dismiss audit actions. Raw documents stay in local/object file storage and are
referenced by path and SHA-256 hash.

The future vector database is not the source of truth. It stores a searchable copy of text and
returns chunk IDs. The application then loads exact evidence, page metadata, and coordinates
from the normal database.

### Source-proof interaction

Every finding must link to one or more `evidence anchors`. An anchor identifies a document,
page, exact source text, anchor type, and normalized bounding box or list of boxes. The UI uses
PDF.js with an SVG/HTML overlay to open the cited page and highlight the evidence.

- token or table cell: exact number, dose, date, or lab value
- line: sentence-level claim
- list of line boxes: multi-line sentence or paragraph
- multiple anchors: cross-document mismatch or a care-gap explanation

OpenCV may support image preprocessing/table detection, but it is not needed to draw browser
highlights. The existing normalized `[0,1000]` coordinates make the overlay responsive at any
viewer size.

### RAG and LLM boundary

Use deterministic code for ingestion, manifest metadata, patient/document storage, coordinate
mapping, exact medication/numeric lookup, citations, and UI highlights. Hybrid RAG combines
BM25 for exact terms/numbers with dense retrieval for semantic questions. LLM-powered agents
are for evidence-grounded synthesis and caregiver wording only; their output must validate
against a schema and include existing evidence-anchor IDs. An LLM must never invent citations,
page numbers, or boxes.

### Four core document types

The Sprint 1 patient pack has four required types: outpatient clinic note, discharge summary,
lab panel, and referral/order form. The full synthetic corpus also has optional imaging reports,
medication lists, and handwritten notes. Not every corpus patient is guaranteed to have every
document type; pack-level validation will choose/build the required four-document test packs.
