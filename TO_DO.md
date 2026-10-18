# PrepPulse delivery tracker

This is the living implementation tracker. Update it with `README.md` whenever the project
state changes.

## Implemented

- [x] GitHub-connected Python repository and reproducible `uv` environment.
- [x] Typed Pydantic OCR output contract for documents, pages, tokens, lines, tables, and cells.
- [x] Required metadata fields: patient ID, document ID/name, document type, encounter date,
  page number, and source SHA-256 hash.
- [x] Normalized top-left-origin `[0,1000]` bounding boxes with original source coordinates.
- [x] Native digital-PDF extraction using PyMuPDF.
- [x] OCR route for PNG/JPG/JPEG and scanned PDF pages using local Tesseract.
- [x] First-pass line reconstruction and lab-table row/column reconstruction.
- [x] Command-line entry point for producing provenance-preserving JSON.
- [x] Initial tests for coordinate normalization, native-PDF extraction, metadata, and simple
  lab-table relationships.
- [x] Linting and test baseline: `pytest` and Ruff pass.

## Available but not yet integrated

- [ ] Synthetic dataset archives in `datasets/`.
- [ ] Dataset manifest, labels, and rendered-document corpus.

## To build — OCR foundation completion

- [ ] Unpack a safe sample of the synthetic corpus outside Git-tracked source files.
- [ ] Build a manifest loader for document metadata and routing ground truth.
- [ ] Build a batch runner for patient packs and document manifests.
- [ ] Evaluate router decisions against `text_extractable` and `requires_ocr` labels.
- [ ] Add hybrid-PDF support: retain native text and OCR embedded figures/regions when required.
- [ ] Improve table detection for multi-table, multi-page, degraded, and handwritten lab panels.
- [ ] Add OCR accuracy, table-cell integrity, rotation, low-resolution, and multi-column tests.
- [ ] Define clear acceptance thresholds for routing, OCR text quality, and table preservation.
- [ ] Confirm local Tesseract installation and run end-to-end scanned-document verification.

## To build — after the OCR/backend base is stable

These are major features and must be planned, approved, and built in separate repositories
before a reviewed merge into PrepPulse.

- [ ] Hybrid retrieval: vector index plus BM25 with provenance-carrying chunks.
- [ ] Longitudinal record-change detection.
- [ ] Medication and record-mismatch detection.
- [ ] Missing-task, unresolved-referral, and loop-closure detection.
- [ ] Validated agent outputs and safety guardrails.
- [ ] Consultation-brief API/backend.
- [ ] Dual-pane web UI with PDF.js source highlighting and audit controls.

## Known limitations

- Current table reconstruction is a conservative geometry heuristic, not a production-grade
  table-layout model.
- Hybrid PDFs are not yet processed as text-plus-embedded-figure inputs.
- No dataset manifest loader, RAG system, agents, API, or UI exists yet.
- The dataset zip archives are local and untracked; they have not been unpacked or processed.
