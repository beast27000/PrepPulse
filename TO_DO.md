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

- [x] Dataset delivery guide and verified dataset context tracked in Git.
- [x] LITE synthetic corpus extracted locally under `data/raw/preppulse_synthetic_lite/`
  (720 patient records, 100 sample documents, and sample manifest; never committed).
- [x] Dataset manifest, labels, and the selected rendered-document corpus integrated with the OCR runner.

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

## Active build — local data + OCR backend

This scope is approved: build a clean 93-patient/four-document active corpus, automatically
ingest 75 patients, and manually review the remaining 18 through a local-only Tkinter tool.

- [x] Define a manifest-to-four-document-pack selection strategy (one latest document per kind).
- [x] Run the pack builder to create the Git-ignored active 93-patient corpus (372 selected files).
- [x] Run automatic ingestion of 75 selected patients (300 documents) into SQLite (34,797 evidence anchors).
- [ ] Use the Tkinter local reviewer to ingest and inspect the remaining 18 patients.
- [ ] Verify scanned-document OCR using local Tesseract and record environment prerequisites.
- [ ] Produce a routing/evaluation report against `text_extractable` and `requires_ocr`.

## Planned backend data model

- [ ] `patients`: patient identity and synthetic demographic references.
- [ ] `documents`: source path, type, date, hash, patient relationship, and ingestion status.
- [ ] `pages`: document page geometry and extraction method.
- [ ] `evidence_anchors`: tokens, lines, table cells, and later paragraph/multi-box regions.
- [ ] `chunks`: RAG-ready text with evidence-anchor references.
- [ ] `findings` and `finding_evidence`: validated future outputs and their citations.
- [ ] `review_actions`: accept/edit/dismiss audit trail.
- [ ] `caregiver_items`: English/Hindi text and checklist state.

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

## Planned test UI

After the local OCR/database path is stable and an implementation plan is approved:

- [ ] Build a local-only mock source-proof UI against a small LITE sample.
- [ ] List patients/documents and show OCR-derived evidence records.
- [ ] Select a finding/evidence item and open the correct document/page.
- [ ] Draw token, line, table-cell, and multi-line highlight overlays from normalized boxes.
- [ ] Use it as an OCR/provenance test harness before building the production UI.

## Known limitations

- Current table reconstruction is a conservative geometry heuristic, not a production-grade
  table-layout model.
- Hybrid PDFs are not yet processed as text-plus-embedded-figure inputs.
- No dataset manifest loader, RAG system, agents, API, or UI exists yet.
- Raw dataset ZIP archives are local and untracked. Only the LITE archive has been extracted;
  its records and documents have not yet been processed by the OCR pipeline.
- No database, RAG index, agent service, API, or mock UI has been implemented yet.
