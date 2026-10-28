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

## Clinical & Architectural Decision Log

### 1. Diabetes Clinical Track & Agent Specialization
- **Pathophysiology & Risks**: Type 2 diabetes complications stem from chronic hyperglycemia inducing microvascular damage (diabetic nephropathy, retinopathy, peripheral neuropathy) and macrovascular risks (atherosclerosis, CAD).
- **Agent Roles**:
  - **Trajectory Agent**: Tracks longitudinal metabolic biomarkers (HbA1c %, fasting/random glucose mg/dL, eGFR mL/min/1.73m², urine ACR mg/g) and computes directional vectors (`worsening`, `improving`, `stable`).
  - **Care Gaps Agent**: Audits annual ADA/ICMR standard of care checklists: identifies missing or overdue annual diabetic foot exams (ulcer/neuropathy risk), annual dilated eye exams (retinopathy), and annual microalbumin/ACR.
  - **Record Mismatches Agent**: Resolves cross-encounter contradictions (e.g., clinic slip stating Glargine 14U vs. discharge summary stating 20U; unverified Metformin or Sulfonylurea titration).
  - **Caregiver Prep Agent**: Converts complex clinical metrics into accessible family handoff checklists with bilingual English and Hindi (`EN` / `हि`) items for low-health-literacy care partners.

### 2. Architecture Boundary: Direct RAG vs. Specialized Agents
- **Ad-Hoc Doctor Q&A & Document Summarization (Direct RAG)**:
  - Quick doctor queries (e.g., *"Show me the latest lab values"*, *"Summarize discharge notes from May"*) are routed directly to `HybridEnsembleRetriever`.
  - Sub-50ms execution; retrieves exact text snippets with normalized `[0, 1000]` bounding boxes for instant UI highlight without agent orchestration overhead.
- **Pre-Consultation Synthesis (LangGraph Agents)**:
  - Multi-document reasoning, timeline reconciliation, gap auditing, and family checklist generation are executed by the specialized agent workflow.
- **Elimination of Middleman Verifier Agent (Latency Optimization)**:
  - Adding a secondary LLM reflection/verifier hop introduces prohibitive 2–4s latency per query.
  - Instead of a middleman agent, verification is enforced deterministically via Pydantic schema validation and immutable `SourceProofCitation` bounding boxes tied directly to Stage 1 OCR ground truth.
