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

### Phase 1: Local MongoDB & Mock Ingest Testing (COMPLETED)
- [x] Received initial 10-patient mock testing dataset (`data/active/v2_patients/`, 115 files) for pipeline validation.
- [x] Implement `src/preppulse_db/` (`mongo_store.py` and `schemas.py`) for local MongoDB (`mongodb://localhost:27017/preppulse`).
- [x] Create `ingest_mock_patients.py`: batch ingest mock patients via frozen OCR engine into `stage_1_raw_ocr`.
- [x] Verify Stage 1 persistence and `[0, 1000]` bounding-box preservation in local MongoDB.
- [x] Verified database teardown and data exclusion so no mock patient data is pushed.
- [x] Provide seed script and docs to teammates so they can run mock data locally (`docs/TEAMMATE_PREPROCESSING_GUIDE.md` and `docs/TEAM_COLLABORATION_SUMMARY.md`).

### Phase 2: Teammate Pre-Processing & Compilation Track (Parallel)
- [ ] **Teammate A (Chunking):** Ingest `stage_1_raw_ocr` -> section detection -> write to `document_chunks` collection with normalized bboxes.
- [ ] **Teammate B (Extraction):** Ingest `document_chunks` -> local Qwen LLM fact extraction -> LOINC/RxNorm/ICD-10 mapping -> write back to `stage_2_structured_entities`.

### Phase 3: Hybrid RAG System (LangChain Ensemble: BM25 + Dense Vectors) (COMPLETED)
- [x] Build provenance-preserving chunker (`ClinicalProvenanceChunker`) linking chunks to exact evidence anchors and `[0, 1000]` bounding boxes.
- [x] Build BM25 keyword index (`SparseBM25Index`) achieving 100% precision on exact drug names (e.g., 'Glargine', 'Metformin', 'Empagliflozin') and lab metrics.
- [x] Build dense semantic vector index (`DenseVectorIndex`) with in-memory cosine similarity and pluggable embeddings.
- [x] Implement `HybridEnsembleRetriever` with Reciprocal Rank Fusion (RRF) achieving <50ms query latency per patient pack.
- [x] Add plug-and-play `LLMFactory` supporting Ollama (`qwen2.5:7b`), Sarvam AI, OpenAI-compatible APIs, or offline mock providers via `.env`.
- [x] Add automated retrieval test suite (`tests/test_hybrid_rag.py`) verifying exact precision, latency, patient isolation, and coordinate preservation.

### Phase 4: Streamlit v1 Clinical Consultation UI
- [ ] Build lightweight Streamlit UI (`streamlit_app/`) rendering consultation brief matching Figma/Replit prototype.
- [ ] Display visual placement of KPIs (HbA1c, Fasting Glucose, eGFR) and patient trajectory cards.
- [ ] Interactive Source Proof panel: clicking any citation renders the source document/page and highlights the normalized `[0, 1000]` bounding box.
- [ ] Add dynamic toggleable English / Hindi (EN / हि) translations for caregiver handoff checklist.

### Phase 5: LangGraph Multi-Agent Orchestration & Clinical Brief (COMPLETED)
- [x] Define strict Pydantic schemas (`src/preppulse_agents/schemas.py`) for:
  - `MetabolicTrajectory` (HbA1c, Fasting Glucose, eGFR trends + direction)
  - `CareGaps` (overdue foot exam, missing microalbumin/ACR)
  - `RecordMismatches` (conflicting insulin doses, metformin reconciliation)
  - `CaregiverPrep` (plain-language caregiver handoff with English + Hindi checklist)
  - `SourceProofCitation` (`[0, 1000]` bbox, document ID, page, text preview)
  - `ConsultationBrief` (unified doctor view)
- [x] Implement four specialized clinical review agents in a deterministic LangGraph state machine (`src/preppulse_agents/graph.py`):
  - Trajectory Agent -> Care Gaps Agent -> Mismatches Agent -> Caregiver Prep Agent -> Brief Compiler.
- [x] Expose hybrid retriever as a standard LangChain Tool (`retriever.as_tool()`) for agent state queries.
- [x] Add agent unit test suite (`tests/test_clinical_agents.py`) verifying compilation, schema compliance, and citation preservation.
