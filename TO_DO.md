# PrepPulse Delivery Tracker

Implementation status and backlog.

## Processing recovery and administration update (6 November 2026)

Implemented accurate waiting states, queue observations, unchanged upload status, administrator retry, pulsing ingestion progress, bounded transient provider retries, staff provider tests, doctor Upcoming appointments, server date restrictions, inline suggestions and administrator patient/source deletion with confirmations and worker fencing.

Verification in progress: focused API/provider/deletion/caregiver regressions and frontend build passed. Browser and live PP006 verification, cleanup and publication are pending. Azure model deployment remains unavailable and cannot be repaired by application fallback logic alone.

## Composite measurement extraction recovery (6 November 2026)

- [x] Quarantined nonnumeric or combined lab values in the source-linked review queue so a malformed blood-pressure/pulse reading does not fail the rest of the document's valid facts.
- [x] Clarified the extraction prompt that blood pressure and pulse belong in vitals, and validated a mixed valid/composite example through the Stage 2 model.
- [ ] Retry the affected patient's failed document in the application and confirm it completes; the code change does not start a patient job automatically.

## Patient search and navigation controls (6 November 2026)

- [x] Added API-backed name, PrepPulse ID and folder-alias search to the admin patient directory and new-appointment patient selector; ambiguous appointment matches require an explicit choice.
- [x] Added name/ID search to assigned caregiver care-plan cards, with localized search labels.
- [x] Removed the inactive notification bell and aligned the top appointment panels after adding the search field.

## Repository documentation cleanup (6 November 2026)

- [x] Removed obsolete frontend handoff and Stage 2/3 specification documents, replacing their current guidance with the focused product documentation.
- [x] Removed user-facing links to the delivery tracker, agent prompt source and API implementation; these remain project maintenance or runtime files, not product guides.
- [x] Removed an unused Sarvam setup prompt file that contained a credential. Deleting it does not remove the value from earlier Git history; rotate the credential.
- [x] Retained all 18 focused test files because they cover distinct application behaviors; no generated installer or test output files were found in the tracked source tree.

## Product documentation restructure (6 November 2026)

- [x] Reworked the local implementation README into a concise physician assistance product overview, architecture summary, technology stack, AI component summaries, chart scope and documentation map.
- [x] Preserved detailed frontend, backend and data, AI and RAG, architecture, and setup content in separate guides under `docs/product/`.
- [x] Added focused frontend, backend and evidence flow diagrams. Wrapped long labels in the overall architecture diagram and retained the consultation pipeline diagram.
- [x] Documented local model and Sarvam API configuration as implemented, including the current embedding limitation when Sarvam is selected.
- [x] Updated UI with the latest reviewed main changes before the documentation work. Main promotion and deployment documentation remain separately tracked below.
- [ ] Create the deployment product overview and deployment specific guides on the deployment branch. Do not describe local setup as the deployed product.

## Logout navigation access (6 November 2026)

- [x] Added a Logout menu action after Settings for doctor/admin navigation and after My care plans for caregiver navigation; it calls the existing logout flow and preserves the bottom sign-out button.
- [x] Verified the action at desktop and phone portrait sizes with mocked API responses; existing desktop sign-out remains visible.
- [x] Applied the same minimal navigation change to the deployment branch and verified its production build plus mocked desktop/phone-portrait sign-out flows.
- [ ] Landscape phone layout remains separate follow-up work.

## Model-provider documentation and branch promotion (6 November 2026)

- [x] Documented the implemented chat/agent choices: local LM Studio or Sarvam API, selected by `LLM_PROVIDER`; provider changes take effect after restarting the API.
- [x] Added safe PowerShell setup examples and clarified that credentials must stay server-side and outside Git.
- [x] Documented the current boundary: Gemini, Azure routing, automatic failover/key rotation, and Sarvam embeddings are not implemented in this UI release. When `LLM_PROVIDER=sarvam`, chat uses Sarvam while the current embedding factory returns deterministic mock embeddings; lexical retrieval remains available, but this is not full semantic hybrid retrieval.
- [x] Merged the reviewed UI release and this provider documentation into `main` after branch verification.

## Appointment view update (5 November 2026)

- [x] Added admin Today / Upcoming appointments tabs and optional future-date filtering.
- [x] Removed browser Read aloud controls while retaining microphone dictation.
- [x] Owner approved applying the reviewed changes to UI and deployment.

## Local IndicTrans2 integration — UI (4 November 2026)

- [x] Owner approved the scoped implementation and a local WSL2 worker alongside LM Studio. The UI branch remains the local implementation; hosted translation is deferred.
- [x] Dedicated offline IndicTrans2 worker with pinned official English→Indic / Indic→English model revisions, local process pipes, isolated dependencies, CPU default and optional CUDA setup. Downloaded weights/configuration stay ignored by Git.
- [x] Downloaded and SHA-256 verified both official 1B checkpoints on the owner's machine; configured the isolated Ubuntu WSL2 environment. The caregiver agent now requests English source instructions only instead of spending chat-model generation on display translations.
- [x] Replaced care translation chat-model calls; complete model-versioned snapshots prevent partial English/target-language rendering and stale revision reuse. Per-patient segment caching reuses unchanged translations after edits.
- [x] Shared care-card/checklist/editor language selection, localized caregiver portal controls, protected numbers/units, input splitting without silent truncation, pending/failure/retry states and selected-language downloads.
- [x] English patient-record PDF archive waits for a complete English derivative for non-English sources; immutable signed source text, source citations, schedules and completion reports stay stored independently.
- [x] Verification: 76 focused care/API/cache/OCR/RAG/chart/geometry/presentation tests, three Edge browser workflows (all five target languages plus partial-state suppression), frontend production build and targeted lint passed. English archiving covers both cold and prewarmed translation caches.
- [x] Live synthetic IndicTrans2 checks passed for Hindi, Tamil, Bengali, Odia and Telugu, including multiline notes, compact `10U`/`8mg` values, glucose/BP units, rendered PDFs and Tamil→English. Outputs are in ignored `.tmp/translation-smoke/`; these checks verify mechanics and protected values, not fluent clinical meaning.
- [x] The existing `test_clinical_agents.py` foot-exam assertion still fails; reproduced the same failure on unmodified commit `0a784d4` in a detached worktree and removed that temporary worktree. It is outside this translation change.
- [ ] Fluent clinical review remains required before relying on translated instructions. Automated number/script checks cannot establish semantic accuracy.

## Caregiver types, assignment search and language switching — UI review (3 November 2026)

- [x] Accounts requires an explicit family/in-hospital choice when creating a caregiver. New hospital IDs use `HCW-`; families use `FAM-`; existing identities remain valid.
- [x] Admins can correct a caregiver's type in Accounts; internal identity/history stay intact, the former public ID remains searchable, and old assignments are revoked before reassignment.
- [x] Assignment search resolves unique names/usernames/IDs/aliases and synchronizes with dropdowns; ambiguous names require selection. Roster search stays independent.
- [x] Server checks caregiver account type, patient assignment and signed pathway mode for list/view/translation/download/report/note access.
- [x] Language selection automatically requests the selected language, reuses independent revision/source-hash caches, retains successful segments on partial failures, and exposes progress/retry states. Doctor card/checklist/editor language remains synchronized.
- [x] Localized care controls/headings/status captions; separate derived doctor-note/checklist/dose text leaves signed source instructions and completion reports unchanged.
- [x] Pre-visit suggestions use the same language cache without starting a visit; incomplete translations from a previous local API process can resume on the next request.
- [x] Modestly enlarged only admin patient IDs/account details and doctor finding/citation text. OCR, RAG, chart routing and chat synthesis are unchanged.
- [x] Verification: 71 focused API/care/chart/RAG/geometry/table tests, three Edge browser flows including Tamil/Hindi switching and downloads, TypeScript/production build, and targeted lint passed. Synthetic browser translations test mechanics, not clinical meaning.
- [ ] Review semantic translation quality and multilingual PDFs with the configured model and a fluent clinical reviewer; target-script/number validation is not proof of correct meaning. A synthetic live Tamil request exposed wording limitations.

## Final chart routing, voice feedback and documentation — UI review (3 November 2026)

- [x] Fixed the plural `charts` request falling into text-only synthesis. Added deterministic chart/graph/plot/visualization routing, generic patient-chart selection, topic inheritance for follow-ups and explicit date-window filtering for 1–10 years, including number words.
- [x] Preserved per-request artifacts, original OCR values and source-linked chart interaction. Unsupported targets do not silently plot glucose; supported targets with no data report a gap.
- [x] Added cited patient-owned OCR occurrence tables for unsupported chart topics; a 200-row display cap is disclosed. Non-chart diabetes/measurement answers offer a chart; explicit no-chart requests remain text-only.
- [x] Caregiver prompt balances 2–3 generic reminders with supported specific values/dates/other-condition context; no invented diagnoses, thresholds or new monitoring schedules.
- [x] Added listening/transcribing animated status to dictation, with transcript correction still required before sending; enlarged only the previous-visit link text.
- [x] Rewrote README as comprehensive theory, clinical boundaries, individual agents, page-by-page workflows, architecture, persistence, models, setup, verification and troubleshooting documentation.
- [x] Verification: 69 focused tests, three Edge browser flows, frontend build and targeted lint passed. Browser voice uses synthetic audio; actual microphone/transcription and live multilingual quality still require owner review.
- [ ] Existing live-model foot-exam assertion remains a known limitation from the previous release; unrelated care-gap/classification behavior was not changed.

## Care checklist simplification — UI review (3 November 2026)

- [x] Patients: checkbox-only care panel with small Edit pathway link and signed-plan download; all text/add/delete/frequency/prescription editing stays on Care pathways.
- [x] Pathway items default to checkboxes with per-item Edit / Done editing controls. Existing new-item entry, autosave, notes, prescriptions and sign-off remain.
- [x] Shared language selection and persisted clinician preparation ticks between card, lower panel and editor; caregiver-reported completion remains separate and read-only for doctors.
- [x] Family / caregiver pathway card shows three items with clinician-authored/edited items first.
- [x] Plain-language caregiver prompt includes dated measurement context, avoids unrequested monitoring/treatment, and replaces raw clinical-value fallback tasks with general preparation reminders. Signed text remains immutable.
- [x] Removed the separate Previous patients screen/nav; Records functionality retained, with spacing changes only around visit/record disclosures and links.
- [x] Created and pushed `old-ui` from the existing `origin/main`; main remains untouched. This release is for UI branch review.
- [ ] Live-model wording and multilingual meaning still require clinician/owner review.
- [x] Verification: 47 focused API/OCR/RAG/prompt tests and two Edge browser flows passed; frontend production build and targeted lint passed. Browser mutations use only synthetic/in-memory data.
- [ ] Existing live-model `test_langgraph_clinical_review_workflow` assertion failed because its care-gap output did not contain the expected foot-exam title (47 other tests passed in that run). The care-gap implementation and its test were left unchanged; this is not a claim of fully validated live clinical output.

## Admin and continuity repairs — UI review (3 November 2026)

- [x] Diagnosed the running port-8000 API as an older release lacking caregiver roles, care routes and appointment history. Replaced it after checking no analysis/chat jobs were active; retained all patients, accounts and sources.
- [x] Added `/api/runtime`, a UI compatibility banner and `scripts/start_ui_api.ps1` for recognized-service restart/reload and a private persistent session secret.
- [x] Centralized account creation in Accounts, including family/professional caregivers. Added searchable stable public IDs for existing/new accounts and a non-secret `staff_directory` mirror without changing original user IDs.
- [x] Caregivers page: patient assignment left, searchable roster and free/active status right; server checks registered caregiver type.
- [x] Restored the original appointment first row; separate matching search/history panels below; newest-first vertical history, completed-today inclusion and separate expanded workspace.
- [x] Enhanced admin directory with editable demographics, preserved doctor assignments, all-records default, visit/date filters, metadata-only record edits, source preview, and visit-linked uploads with live refresh.
- [x] Added doctor's Previous patients search and full historical review layout; saved snapshot vs current-reference distinction, original chat/source access, no active care editor or new-visit actions there.
- [x] Shared handoff-card/checklist data, filtered generic preparation templates, visible first-visit editor entry and preserved signed completion. Reanalysis does not overwrite clinician drafts or regenerate signed checklists.
- [x] Removed the inline assistant button's negative overlap margin. OCR, RAG, agent graph, chart generation and source-rendering implementations remain unchanged.
- [x] Verification: 44 focused API/OCR/RAG regression tests, two combined Edge browser flows, production frontend build and targeted Ruff checks passed. Browser data/translations are synthetic; no live patient data was used for browser mutation tests.
- [ ] Owner verification with the actual patient/LM Studio setup and clinical translation review. Synthetic browser translations do not establish live-model quality.

## Caregiver and continuity release — UI review (3 November 2026)

- [x] Main Patients rail: chat first, Source Proof second, editable checklist third; independent and whole-rail collapses preserve dedicated workspace expansion.
- [x] Unified demographics, existing-patient selection, record/folder uploads and processing progress. Recorded age does not invent a DOB; folder aliases map to permanent PrepPulse IDs.
- [x] Shared autosaved, revision-checked care draft; editable checklist, doctor notes and prescription controls for doses, timings, food and duration.
- [x] Six-language translation invalidation/retry, number preservation, source/pending states and fixed localized schedule labels. Medication names/doses bypass the LLM.
- [x] Admin caregiver registration, professional/family assignment/revocation and one-page caregiver portal; server-enforced patient access and withheld briefs/raw records/unsigned drafts.
- [x] Immutable signed plans, patient/brief snapshots, paginated multilingual PDFs and source PDF patient records; separate persisted caregiver completion/notes.
- [x] Dated daily tasks, past-due unreported counts, future-completion rejection and next-plan supersession. Completion is caregiver-reported, not verified administration.
- [x] Expandable appointment history by date/name/either ID; appointment/visit links; Records opens saved visits and the full document workspace.
- [x] Removed Guidance library. README explains actual classifier inputs, fallback limitations and supported diabetes-related chart measures.
- [x] Verification: 37 focused API/OCR/RAG/pipeline tests and 2 Edge browser flows pass; frontend production build and targeted Ruff pass. Browser fixtures are synthetic/in-memory with deterministic translations.
- [ ] Owner review with the actual LLM, including translation meaning and PDF wording across all six languages. Fixture tests do not establish live-model translation quality.
- [x] The reviewed UI release was promoted to `main`; subsequent UI review changes require a separate merge.

- [x] Changed full chat to a left/right layout with independently collapsible chat and chart views; the remaining panel fills the available width. Source Proof continues to open from selected citations in the right panel.
- [x] Added an explicit diabetes-agent scope warning for heart-disease chart requests, listing supported OCR measurements and offering cited cardiac text summaries.

## UI branch implementation (30 October 2026)

- [x] Created `UI` branch and removed the tracked Tkinter OCR test UI on that branch.
- [x] Added React/TypeScript browser workspace with screenshot-inspired Patients page, doctor/admin navigation, Today cards, Records, Care pathways, Source Proof, expandable chat, movable assistant bubble, login, intake, appointments, and accounts.
- [x] Added local FastAPI integration layer for admin-managed accounts, signed sessions with CSRF, doctor-to-patient assignments, permanent PrepPulse IDs and folder aliases, document uploads, one-folder intake, appointments, visit state, clinician review decisions, pathways, source page rendering, chat retrieval, and background brief jobs.
- [x] Changed the UI tagline to “Diabetes Clinical Intelligence”; replaced global sample import with one-folder upload and background processing; added admin patient overview with visits, appointments, documents, and assigned doctors.
- [x] Cleared local patient, alias, document, appointment, visit, job, pathway, review, and audit records on 2 November 2026; verified both login accounts remain. The local API was stopped for the reset and must be restarted.
- [x] Added per-account browser Settings for Light/Dark/System appearance, text size, contrast, dictation language, opt-in Read aloud visibility, and admin appointment defaults. Preferences are local to one browser.
- [x] Added a top-level Analyze records action, clearer job progress, a full patient record workspace with page controls and searchable file tiles, tight OCR citation highlights, and source-backed metric findings. Verified the imported patient's 15 processed documents, 422 evidence chunks, eight source-backed priority observations and earlier events, and a multi-year chat answer against the local model.
- [x] Replaced plain-text chat with safe Markdown/GFM rendering, real tables, emphasized values, inline citation links, and saved doctor/patient chat sessions in MongoDB.
- [x] Added real chart artifacts per request using dated OCR values, saved chart links/session library, collapsible charts above chat, and an optional Source Proof dock that opens from a citation or explicit source request. Removed the permanently displayed chat source/context/chart column.
- [x] Added actual stage bubbles for review agents, retrieval, chart generation, and response synthesis; added retry states for interrupted sessions and analysis jobs.
- [x] Added diabetes journey and other-history tiles across the uploaded records, narrative history synthesis, previous-measurement source links, and a collapsible navigation rail for both roles.
- [x] Corrected the local inference default to loopback, bounded model/embedding timeouts, preserved BM25 after embedding failure, and made chart creation independent of inference availability.
- [x] Completed browser regression checks in headless Edge against an isolated copy of the imported patient. Verified two independent charts, native reply tables, chart point/inline source links, OCR overlays with automatic source-span centering, full record expansion, panel collapse/reopen, session reload/new chat, and 1000px responsive width. Captured review screenshots outside version control.
- [ ] Extend deterministic chart extraction to additional analytes and document layouts as needed; unsupported requests currently show a data gap instead of generated measurements.
- [x] Added local faster-whisper dictation endpoint with transcript review in the UI. Added blank `PREPPULSE_TTS_MODEL_PATH` placeholder and disabled Read aloud control for the pending local GGUF runtime.
- [x] Replaced the previous frontend handoff with focused product documentation matching actual code contracts and known gaps.
- [ ] Validate the full doctor/admin flow against a running local MongoDB and real downloaded models. Static build and isolated tests are not a substitute for this live check.
- [ ] Resolve existing full-suite fixture assumptions: some legacy tests require a pre-seeded `PP001_Arvind_Narayanan` Mongo patient, and one agent expectation differs from the current mock-model output. The isolated UI/API suite passes without that seed.
- [x] Add a historical pathway browser for clinician-approved versions.
- [x] Replaced temporary sidebar marks with the shared draft and persistent caregiver reports (3 November release).
- [x] Added authenticated opt-in Read aloud API and browser playback, gated by a real WAV-audio probe of a configured local endpoint.
- [ ] Provide and test an audio-capable runtime for `mradermacher/Qwen3-1.7B-Multilingual-TTS-GGUF` and verify spoken languages. The reachable LM Studio server lists the model but returns `Unexpected endpoint or method` for `POST /v1/audio/speech`, so Read aloud remains disabled with that server.
- [x] Removed Guidance library at the owner's request (3 November release).
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

### Phase 4: React browser consultation UI
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
*(Current architecture and interface documentation is maintained in `docs/product/ARCHITECTURE.md`, `docs/product/FRONTEND.md`, and `docs/product/AI_AND_RAG.md`.)*
- [x] Ingested and validated real-world 10-year patient records (`PP001_Arvind_Narayanan`, 2016-2026, 13 multi-specialty PDFs) into local MongoDB `stage_1_raw_ocr` preserving normalized `[0, 1000]` bounding boxes.
- [x] Supported `record_index.json` and `ground_truth.json` manifests in `preppulse_db.ingest`.
- [x] Extended Pydantic schemas in `src/preppulse_agents/schemas.py`:
  - `PatientClassification` (dynamic classification across non-diabetic, pre-diabetic, diabetic spectrum).
  - `PriorityFindingItem` (reverse-chronological findings from recent to 10 years back with action hooks).
  - `TimeSeriesPoint`, `LongitudinalMetricSeries` (10-year tabular matrix and chart coordinates).
  - `SmartPromptBubble` (non-intrusive assistive prompt suggestions).
  - `CaregiverPrep` (dynamically switching between Caregiver Handoff and Caregiver Prep Sheet with `EN`, `हि`, `த` translations).
- [x] Configured pluggable `LLMFactory` with native local LM Studio inference (`qwen/qwen3-4b-2507` and `text-embedding-qwen3-embedding-0.6b`), defaulting to loopback `http://127.0.0.1:1234/v1` and allowing `LOCAL_LLM_BASE_URL` overrides; retained the RTX 4060 safeguard, Sarvam fallback, and offline mock provider.
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
- [x] Focused UI/API, RAG, pipeline, and browser regression checks pass; legacy full-suite fixtures that require a pre-seeded patient remain documented below.

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
- [x] Updated frontend documentation to describe language selection, dynamic brief bindings, and the full-page expandable chatbot view.

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
