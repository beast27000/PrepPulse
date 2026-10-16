# PrepPulse OCR

Sprint 1 foundation for extracting auditable clinical-document content from digital PDFs,
scanned PDFs, PNGs, and JPEGs.

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
```

## Local setup

```powershell
uv venv
uv sync --extra dev
```

Install the Tesseract desktop binary separately and ensure `tesseract` is available on your
`PATH`; it is only required for scanned PDFs and images. Digital PDFs work without it.

## Run

```powershell
uv run preppulse-ocr path/to/document.pdf `
  --patient-id synth-001 `
  --document-type lab_panel `
  --encounter-date 2026-10-13 `
  --output data/outputs/lab-panel.json
```

The output JSON is the contract future RAG, agents, and the source-highlighting UI consume.
