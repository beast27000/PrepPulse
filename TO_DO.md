# PrepPulse Delivery Tracker

Implementation status and backlog.

## UI branch implementation (30 October 2026)

- [x] Created `UI` branch and removed the tracked Tkinter OCR test UI on that branch.
- [x] Added React/TypeScript browser workspace with screenshot-inspired Patients page, doctor/admin navigation, Today cards, Records, Care pathways, Source Proof, expandable chat, movable assistant bubble, login, intake, appointments, and accounts.
- [x] Added local FastAPI integration layer for admin-managed accounts, signed sessions with CSRF, doctor-to-patient assignments, permanent PrepPulse IDs and dataset aliases, document uploads, sample registry import, appointments, visit state, clinician review decisions, pathways, source page rendering, chat retrieval, and background brief jobs.
- [x] Added local faster-whisper dictation endpoint with transcript review in the UI. Added blank `PREPPULSE_TTS_MODEL_PATH` placeholder and disabled Read aloud control for the pending local GGUF runtime.
- [x] Rewrote `docs/FRONTEND_INTEGRATION_SPEC.md` as a handoff matching actual code contracts and known gaps.
- [ ] Validate the full doctor/admin flow against a running local MongoDB and real downloaded models. Static build and isolated tests are not a substitute for this live check.
- [ ] Resolve existing full-suite fixture assumptions: some legacy tests require a pre-seeded `PP001_Arvind_Narayanan` Mongo patient, and one agent expectation differs from the current mock-model output. The isolated UI/API suite passes without that seed.
- [x] Add a historical pathway browser for clinician-approved versions.
- [ ] Persist the sidebar checklist's temporary on-screen check marks. Finalized pathway items and doctor notes are persisted separately.
- [x] Added authenticated opt-in Read aloud API and browser playback, gated by a real WAV-audio probe of a configured local endpoint.
- [ ] Provide and test an audio-capable runtime for `mradermacher/Qwen3-1.7B-Multilingual-TTS-GGUF` and verify spoken languages. The reachable LM Studio server lists the model but returns `Unexpected endpoint or method` for `POST /v1/audio/speech`, so Read aloud remains disabled with that server.
- [ ] Add owner-approved Guidance library content when supplied.
- [ ] Complete a shared-deployment security review before exposing the app beyond local loopback.

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
- [x] Built the earlier desktop OCR test UI with document preview and bounding-box highlighting; removed it on `UI` after the browser workspace replaced it.
- [x] Hybrid-PDF support: same-page extraction combining native digital text and embedded image region OCR.
- [x] Earlier OCR foundation suite (6 tests) and Ruff linting passed at that milestone. Current full-suite status is tracked in the UI branch section.
- [x] OCR Foundation FROZEN: Native PDF, scanned OCR, table parsing, and same-page hybrid extraction locked.

## Active Roadmap (Updated Priorities)

### Phase 1: Local MongoDB & Mock Ingest Testing (COMPLETED)
- [x] Received initial 10-patient mock testing dataset (`data/active/v2_patients/`, 115 files) for pipeline validation.
- [x] Implement `src/preppulse_db/` (`mongo_store.py` and `schemas.py`) for local MongoDB (`mongodb://localhost:27017/preppulse`).
- [x] Create `ingest_mock_patients.py`: batch ingest mock patients via frozen OCR engine into `stage_1_raw_ocr`.
- [x] Verify Stage 1 persistence and `[0, 1000]` bounding-box preservation in local MongoDB.
- [x] Verified database teardown and data exclusion so no mock patient data is pushed.
- [x] Provide seed script and docs to teammates so they can run mock data locally (`docs/TEAMMATE_PREPROCESSING_GUIDE.md` and `docs/TEAM_COLLABORATION_SUMMARY.md`).

### Phase 2: Teammate Pre-Processing & Compilation Track (COMPLETED & INTEGRATED)
- [x] Integrated teammate preprocessing modules into `src/preppulse_preprocessing/` (`chunk.py`, `extract.py`, `ground.py`, `fhir.py`, `models.py`, `store.py`).
- [x] Section-aware chunking without fixed-size truncation (`chunk_document` -> `document_chunks`).
- [x] Pluggable LLM extraction with provider decoupling: added `LMStudioClient` in `src/preppulse_preprocessing/providers/lmstudio_provider.py`.
- [x] Grounding and verification pass enforcing fail-closed threshold validation and bounding box reattachment.
- [x] FHIR R4 Bundle conversion (Stage 3) and `MongoStoreAdapter` bridge with `preppulse_db.MongoStore`.
- [x] 5 of 5 preprocessing logic tests passing cleanly.

### Phase 3: Hybrid RAG System (LangChain Ensemble: BM25 + Dense Vectors) (COMPLETED)
- [x] Build provenance-preserving chunker (`ClinicalProvenanceChunker`) linking chunks to exact evidence anchors and `[0, 1000]` bounding boxes.
- [x] Build BM25 keyword index (`SparseBM25Index`) achieving 100% precision on exact drug names (e.g., 'Glargine', 'Metformin', 'Empagliflozin') and lab metrics.
- [x] Build dense semantic vector index (`DenseVectorIndex`) with in-memory cosine similarity and pluggable embeddings.
- [x] Implement `HybridEnsembleRetriever` with Reciprocal Rank Fusion (RRF) achieving <50ms query latency per patient pack.
- [x] Add plug-and-play `LLMFactory` supporting Ollama (`qwen2.5:7b`), Sarvam AI, OpenAI-compatible APIs, or offline mock providers via `.env`.
- [x] Add automated retrieval test suite (`tests/test_hybrid_rag.py`) verifying exact precision, latency, patient isolation, and coordinate preservation.

### Phase 4: Streamlit v1 Clinical Consultation UI
The owner approved a React browser UI on the `UI` branch in place of the earlier Streamlit proposal.
- [x] Build a screenshot-inspired consultation workspace in `web/` using the actual `ConsultationBrief` schema.
- [x] Display KPI and trajectory cards from available agent output.
- [x] Render source pages and normalized `[0, 1000]` highlights only when citation validation succeeds; unverified claims show a source-unavailable state.
- [x] Add six-language client-side checklist switching (English, Hindi, Tamil, Bengali, Odia, Telugu).

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

### Phase 6: 10-Year Longitudinal Multi-Condition Engine & UI Bindings (COMPLETED)
*(Detailed architectural specs documented in `priority_items.md` and `docs/FRONTEND_INTEGRATION_SPEC.md`)*
- [x] Ingested and validated real-world 10-year patient records (`PP001_Arvind_Narayanan`, 2016-2026, 13 multi-specialty PDFs) into local MongoDB `stage_1_raw_ocr` preserving normalized `[0, 1000]` bounding boxes.
- [x] Supported `record_index.json` and `ground_truth.json` manifests in `preppulse_db.ingest`.
- [x] Extended Pydantic schemas in `src/preppulse_agents/schemas.py`:
  - `PatientClassification` (dynamic classification across non-diabetic, pre-diabetic, diabetic spectrum).
  - `PriorityFindingItem` (reverse-chronological findings from recent to 10 years back with action hooks).
  - `TimeSeriesPoint`, `LongitudinalMetricSeries` (10-year tabular matrix and chart coordinates).
  - `SmartPromptBubble` (non-intrusive assistive prompt suggestions).
  - `CaregiverPrep` (dynamically switching between Caregiver Handoff and Caregiver Prep Sheet with `EN`, `हि`, `த` translations).
- [x] Configured pluggable `LLMFactory` with native local LM Studio inference (`qwen/qwen3-4b-2507` and `text-embedding-qwen3-embedding-0.6b` at `http://192.168.1.16:1234/v1`), VRAM safeguard for RTX 4060, Sarvam AI credit preservation (`SARVAM_AI_CREDITS`), and offline mock fallback.
- [x] Implemented 8-node LangGraph multi-agent review machine in `src/preppulse_agents/graph.py`:
  - Classification $\rightarrow$ Trajectory $\rightarrow$ Care Gaps $\rightarrow$ Mismatches $\rightarrow$ Comorbidities $\rightarrow$ Caregiver Prep $\rightarrow$ Assistive Bubbles $\rightarrow$ Brief Compiler.
- [x] **Refactored All Agents to LLM-Driven Dynamic Inference (Zero Hardcoding)**:
  - `comorbidities_agent`: Replaced all hardcoded keyword branches with dynamic Qwen3-4B inference to identify any clinical admission, surgery, or specialist consult across a patient's entire decade-long record.
  - `mismatches_agent`: Replaced hardcoded drug queries with broad reconciliation retrieval and LLM discovery of conflicting doses, frequencies, or unconfirmed discontinuations.
  - `caregiver_prep_agent`: Dynamic contextual generation of actionable family caregiver checklist items with English, Hindi (`हि`), and Tamil (`த`) translations.
  - `trajectory_agent`: Added open-ended LLM discovery pass extracting any documented numeric lab biomarkers into `LongitudinalMetricSeries`.
  - `assistive_bubbles_agent`: Dynamic bubble synthesis reflecting the actual clinical events and longitudinal series present in the patient's state.
  - Robust `_parse_llm_json_array` utility ensuring fail-safe JSON parsing across diverse LLM markdown outputs.
- [x] Built and verified full end-to-end integration test suite (`tests/test_end_to_end_pipeline.py`) validating raw PDF $\rightarrow$ Stage 1 OCR $\rightarrow$ Chunker $\rightarrow$ Hybrid RAG $\rightarrow$ LangGraph Swarm $\rightarrow$ Unified Brief.
- [x] 19 of 19 tests passing across full repository test suite with zero linter errors.

### Phase 7: External YAML Prompt Engine & 6-Language Multi-Lingual Support (COMPLETED)
- [x] Externalized all agent and RAG prompts into modular YAML configurations (`prompts/agents/` and `prompts/rag/`):
  - `prompts/agents/classification_agent.yaml`
  - `prompts/agents/trajectory_agent.yaml`
  - `prompts/agents/lab_discovery_agent.yaml`
  - `prompts/agents/care_gaps_agent.yaml`
  - `prompts/agents/mismatches_agent.yaml`
  - `prompts/agents/comorbidities_agent.yaml`
  - `prompts/agents/caregiver_prep_agent.yaml`
  - `prompts/agents/assistive_bubbles_agent.yaml`
  - `prompts/rag/hybrid_query_reformulation.yaml`
  - `prompts/rag/clinical_chatbot.yaml`
- [x] Implemented `src/preppulse_agents/prompt_loader.py` with caching and safe string substitution preserving literal JSON formatting.
- [x] Implemented `src/preppulse_agents/tools.py` with deterministic `extract_metric_timeseries` tool for multi-year clinical trajectory extraction.
- [x] Expanded multi-lingual caregiver checklist support across 6 languages: English (`en`), Hindi (`hi`), Tamil (`ta`), Bengali (`bn`), Odia (`or`), and Telugu (`te`).
- [x] Updated `docs/FRONTEND_INTEGRATION_SPEC.md` documenting the 6-language toggle bar, dynamic brief bindings, and full-page expandable chatbot view.

### Phase 8: 10-Patient Dataset Verification & Pipeline Audit (COMPLETED)
- [x] Received and verified 10-patient dataset in `datasets/PrepPulse Dataset/` (6 diabetics, 3 pre-diabetics, 1 non-diabetic).
- [x] Implemented `scripts/audit_dataset_pipeline.py` verifying full end-to-end pipeline against live local LM Studio Qwen3-4B:
  - Stage 1 OCR PDF extraction (15 PDFs).
  - Section-aware preprocessing chunking (58 section chunks + 237 RAG chunks).
  - Hybrid BM25 + Qwen dense vector retrieval (<50ms latency).
  - 8-node LangGraph review workflow (Classification, Trajectory, Gaps, Conflicts, Timeline, 6-Language Checklist, Bubbles).
- [x] Verified zero database leakage: automated teardown wipes all MongoDB test data immediately upon audit completion (`count == 0`).
- [x] Full test suite (15 tests) passing cleanly with zero Ruff linting errors.

## Clinical & Architectural Decision Log

### 1. High-Priority Directives (See `priority_items.md`)
- **Strictly Assistive (Non-Diagnostic)**: Never assert autonomous diagnoses or treatment advice; present objective metrics, trends, and factual excerpts with clinical humility.
- **Smart UI Assistive Bubbles**: Offer non-intrusive prompt bubbles (e.g. *"10-year lab history detected: Would you like to view the patient's glycemic trajectory?"*) instead of unsolicited clinical assertions.
- **Multi-Condition & 10-Year Depth**: Track all conditions (cardiovascular/stents, surgeries, childhood conditions, renal) across a 10-year timeline for non-diabetic, pre-diabetic, and all diabetic stages.
- **Retrospective Briefs with Lab Linking**: Reconstruct past consultations faithfully, using dates, years, and semantics to correlate separated lab reports to clinician encounter notes.
- **Dual Presentation Contract**: Feed both direct UI data cards on top and granular drill-downs with Stage 1 bounding box highlights underneath, alongside fast hybrid RAG chat.

### 2. Diabetes Clinical Track & Agent Specialization
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
