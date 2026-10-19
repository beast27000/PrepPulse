# PrepPulse Delivery Tracker

Implementation status and backlog.

## Implemented

- [x] Streamlined architecture: consolidated into master modules (`engine.py` and `database.py`).
- [x] Standard `venv` support with root `requirements.txt`.
- [x] Provenance OCR data contract: documents, pages, tokens, lines, tables, and cells.
- [x] Normalized `[0, 1000]` bounding boxes with original source dimensions.
- [x] Native PDF extraction (PyMuPDF) and scanned PDF/image OCR (Tesseract).
- [x] Lab-table row and column reconstruction.
- [x] SQLite store (`patients`, `documents`, `pages`, `evidence_anchors`).
- [x] Pack builder creating active 93-patient 4-document packs.
- [x] Batch ingestion pipeline: 75 patients (300 documents, 34,797 anchors) ingested into SQLite.
- [x] Desktop test UI in `temp_ui/mock_ui_ocr_testing.py` with document preview and bounding-box highlighting.
- [x] Full test suite (5 passing tests) and Ruff linting passing cleanly.

## Active Backlog

- [ ] Use `temp_ui/mock_ui_ocr_testing.py` to process the remaining 18 manual patients.
- [ ] Evaluate routing decisions against `text_extractable` and `requires_ocr` ground-truth labels.
- [ ] Add hybrid-PDF support (retaining native text while running OCR on embedded image regions).
- [ ] Enhance table detection for degraded and multi-page lab reports.

## Post-OCR Foundation (Future Sprints)

- [ ] Hybrid RAG (BM25 + dense vector retrieval).
- [ ] Clinical agents (trajectory, care gaps, medication mismatches, caregiver handoff).
- [ ] Production dual-pane web UI with PDF.js source highlighting.
