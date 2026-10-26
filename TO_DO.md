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
- [x] Hybrid-PDF support: same-page extraction combining native digital text and embedded image region OCR.
- [x] Full test suite (6 passing tests) and Ruff linting passing cleanly.
- [x] OCR Foundation FROZEN: Native PDF, scanned OCR, table parsing, and same-page hybrid extraction locked.

## Active Roadmap (Updated Priorities)

### Phase 1: Scalable & Secure Database Architecture (Active Priority 1)
- [x] Received initial 10-patient longitudinal dataset (`Updated_Data_Set/PrepPulse_10_patients.zip`, 115 documents).
- [ ] Design and implement modernized, secure, and scalable database schema for structured text storage and high-performance retrieval.
- [ ] Ingest the 10 longitudinal patient packs into the new database using the frozen OCR engine.
- [ ] Verify Stage 1 data integrity and audit trails against `ground_truth.json`.

### Phase 2: Clinical Pre-Processing, Data Minimization & Confidentiality Layer (Active Priority 2)
- [ ] Relevance & Noise Reduction: Implement temporal filtering, encounter relevance scoring, and redundant/obsolete history pruning to prevent LLM hallucination from 10+ years of raw logs.
- [ ] Confidentiality & Privacy Guardrails: Implement secure medical data handling, PHI/PII redaction/masking, and strict access isolation prior to any downstream AI consumption.

### Phase 3: Hybrid RAG System (LangChain Ensemble: BM25 + Dense Vectors)
- [ ] Build provenance-preserving chunker linking chunks to exact evidence anchors and `[0, 1000]` bounding boxes.
- [ ] Build BM25 keyword index achieving 100% precision on exact drug names (e.g., 'Glargine', 'Metformin', 'Empagliflozin') and lab metrics.
- [ ] Build dense semantic vector index (Chroma / FAISS with dense embeddings).
- [ ] Implement LangChain `EnsembleRetriever` with Reciprocal Rank Fusion (RRF) achieving <500ms query latency per patient pack.
- [ ] Add automated retrieval test suite verifying exact precision, latency, and coordinate preservation.

### Phase 4: Streamlit v1 Mock Testing UI
- [ ] Define strict Pydantic output schemas for the 4 core categories:
  - `Metabolic Trajectory` (HbA1c, Fasting Glucose, eGFR trends)
  - `Care Gaps` (overdue screenings, missing follow-ups)
  - `Record Mismatches` (cross-document clinical conflicts)
  - `Caregiver Prep` (plain-language briefing, checklist with English & Hindi)
- [ ] Build lightweight Streamlit UI (`streamlit_app/`) rendering mock and live pipeline data.
- [ ] Display visual placement of KPIs (HbA1c, Fasting Glucose, eGFR) and patient trajectory cards.
- [ ] Validate schema compliance and raise explicit errors on malformed payloads.

### Phase 5: LangGraph Multi-Agent Orchestration & Interactive Source Proof
- [ ] Implement four specialized clinical review agents (Trajectory, Care Gaps, Mismatches, Caregiver) in a deterministic LangGraph state machine.
- [ ] Wire live agent outputs into the Streamlit UI with clickable citations.
- [ ] Interactive Source Proof panel: clicking any citation renders the source document/page and highlights the bounding box.
- [ ] Add dynamic toggleable English / Hindi (EN / हि) translations for caregiver handoff checklist.
