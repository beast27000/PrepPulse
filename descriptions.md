# PrepPulse: Master Project Architecture, Implementation State & Execution Handover (`descriptions.md`)

> **Document Purpose**: Complete, uncompromised, zero-loss handover and technical blueprint for PrepPulse. This document captures every architectural decision, data contract, teammate boundary, prompt strategy, RAG design, agent swarm configuration, and UI requirement so any developer or AI agent can immediately pick up and execute the project with 100% precision and zero hardcoded fallbacks.

---

## 1. Project Vision & Core Directive

### 1.1 What PrepPulse Is
PrepPulse is an **assistive longitudinal clinical chart-review workspace** designed for clinicians (specifically targeting endocrinologists, primary care physicians, and care teams managing complex patients over up to 10 years of multi-facility medical history).

### 1.2 Clinical Scope & Strict Directives
- **Assistive, Non-Autonomous**: PrepPulse **never** acts as an autonomous diagnostic authority or treatment prescriber. It surfaces factual provenance, trends, discrepancies, and care gaps from documents to augment the doctor's review.
- **Strict Provenance Guarantee**: Every single extracted fact, metric, milestone, medication contradiction, or care gap must be tied back to an exact normalized `[0, 1000]` bounding box (`[ymin, xmin, ymax, xmax]` or `[x0, y0, x1, y1]`) on a specific document page, so clicking any UI card or tile highlights the original source document in the viewer.
- **Dynamic for Any Patient & Any Condition**: The system is **NOT** a one-off demo for a single patient. While diabetes (Type 1, Type 2, Pre-diabetes, Impaired Fasting Glucose, Gestational) is the primary metabolic tracking journey, patients have multi-morbidities (cardiovascular stents, CABG, COVID-19, Dengue, urology procedures, orthopaedic consults, dental history, renal decline). **No condition, medication name, lab name, or date may EVER be hardcoded in application logic.** Everything must be dynamically discovered via Hybrid RAG + LLM inference.

---

## 2. Team Split & Architecture Boundaries

The PrepPulse project is split across specialized modules:

```mermaid
flowchart TD
    subgraph Teammate OCR & Ingestion (Foundation - FROZEN)
        PDF[Patient Records Multi-Year PDFs] --> OCR[preppulse_ocr Engine]
        OCR --> MONGODB[(MongoDB: stage_1_raw_ocr)]
    end

    subgraph Teammate Pre-Processing Pipeline (Parallel Workstream)
        MONGODB --> CHUNKER_TEAM[Teammate A: Section & Chunking Engine]
        CHUNKER_TEAM --> CHUNKS_DB[(document_chunks Collection)]
        CHUNKS_DB --> LLM_EXTRACT[Teammate B: Entity Extraction & Ontology Mapping]
        LLM_EXTRACT --> STAGE_2_DB[(stage_2_structured_entities: LOINC / RxNorm / ICD-10)]
    end

    subgraph RAG & Agentic Swarm (Our Workstream)
        MONGODB --> LOCAL_CHUNKER[ClinicalProvenanceChunker]
        LOCAL_CHUNKER --> RETRIEVER[HybridEnsembleRetriever: BM25 + Dense Qwen Embeddings + RRF]
        RETRIEVER --> SWARM[LangGraph 8-Agent Swarm]
        PROMPT_FILES[External Prompts: prompts/agents/*.txt] --> SWARM
        LLM_QWEN[Local Qwen3-4B / Sarvam AI Credits] --> SWARM
        SWARM --> BRIEF[ConsultationBrief JSON]
    end

    subgraph Interactive Clinical UI
        BRIEF --> DASHBOARD[Live Doctor Pre-Consultation Workspace]
        MONGODB --> VIEWER[Source Proof Document Viewer with BBox Highlights]
        RETRIEVER --> CHATBOT[Sidecar Doctor Assistant Chatbot]
    end
```

### 2.1 The Two Ingestion / Storage Contracts
1. **Stage 1 (`stage_1_raw_ocr`)**:
   - Stores raw OCR/digital text extractions per document: `document_id`, `patient_id`, `source_file`, `status: stage_1_complete`.
   - Contains pages, tokens, lines, tables, cells, each with coordinates normalized to `[0, 1000]`.
2. **What Other Teammates Are Providing (Parallel Track)**:
   - **Teammate A**: Reading `stage_1_raw_ocr`, applying clinical section detection (Subjective, Objective, Assessment, Plan, Discharge Meds, Lab Tables), writing clean chunk documents to MongoDB `document_chunks`.
   - **Teammate B**: Ingesting `document_chunks`, running LLM extraction to produce structured entities with standard clinical ontology codes (LOINC for labs, RxNorm for drugs, ICD-10 for diagnoses) into `stage_2_structured_entities`.
3. **Our System's Isolation & Independence**:
   - Because teammate modules run in parallel, our RAG and LangGraph engine can run **directly from `stage_1_raw_ocr`** using our internal `ClinicalProvenanceChunker`, or plug into `stage_2_structured_entities` once delivered.

---

## 3. Local Model & Compute Constraints

- **Host Machine**: RTX 4060 GPU (8 GB VRAM).
- **Primary LLM**: Local LM Studio running at `http://192.168.1.16:1234/v1`
  - Model: `qwen/qwen3-4b-2507` (Q4_K_M GGUF, 2.5 GB, context window up to 28,858 tokens).
  - Embeddings: `text-embedding-qwen3-embedding-0.6b` (1024-dim, OpenAI-compatible endpoint).
  - VRAM Rule: Prompts must remain concise (under ~3,500 characters of context, chunks trimmed to ~180-200 characters) to prevent VRAM spikes or OOM crashes on the 8 GB card.
- **Secondary / Fallback LLM**: Sarvam AI API
  - Env Var: `SARVAM_AI_CREDITS` in `.env`.
  - Preserve credits: only use if local server is down or explicitly toggled.
- **Offline / CI Fallback**: `MockClinicalChatModel` and `MockEmbeddings` in `llm_provider.py` for headless unit tests.

---

## 4. The 8-Node LangGraph Agent Swarm

The clinical review workflow must run as an orchestrated LangGraph state machine:

### 4.1 Agent 1: Dynamic Patient Classification (`classification_agent`)
- **Objective**: Determine whether the patient is `non_diabetic`, `prediabetic`, or `diabetic` (Type 1, Type 2, Gestational, Impaired Fasting Glucose).
- **Mechanism**:
  - Retrieves diagnostic statements, doctor impression notes, and recent HbA1c/glucose tests.
  - Dynamically classifies based on clinical consensus (e.g., ADA criteria: HbA1c <5.7% Normal, 5.7–6.4% Pre-diabetic, $\ge$6.5% Diabetic) or documented clinical diagnosis.
  - Stores `PatientClassification(stage, category, diagnostic_basis)`.

### 4.2 Agent 2: Metabolic & Lab Trajectory (`trajectory_agent`)
- **Objective**: Construct 10-year multi-year longitudinal timelines and KPI cards.
- **Mechanism**:
  - Extracts standard metabolic series (HbA1c %, Fasting/Random Blood Glucose mg/dL, eGFR mL/min/1.73m², Urine ACR, Blood Pressure).
  - **Open-Ended Lab Discovery Pass**: Prompts the LLM with all laboratory chunks to extract *any other* numeric lab tests present in the patient's records (Lipid profile, Total Cholesterol, LDL, HDL, Triglycerides, Serum Creatinine, Liver enzymes ALT/AST, CBC/Platelets, Cardiac Troponins).
  - Calculates trends (`worsening`, `improving`, `stable`, `elevated`) and tabulates a 10-year matrix `{ "2016": val, "2018": val, ... }`.

### 4.3 Agent 3: Longitudinal Care Gaps (`care_gaps_agent`)
- **Objective**: Surface clinical screenings and follow-ups that are overdue or missing from the record.
- **Mechanism**:
  - Gathers annual screening history and orders.
  - Diabetic track checks: annual dilated eye exam, annual diabetic comprehensive foot exam, annual urine microalbumin/ACR spot check, periodic HbA1c recheck.
  - General / Pre-diabetic track checks: periodic metabolic screening, lifestyle follow-up, blood pressure logs, pending specialist consultations.
  - LLM extracts findings into `CareGapItem(title, details, severity: warning|info|critical, citation)`.

### 4.4 Agent 4: Medication Reconciliation & Mismatches (`mismatches_agent`)
- **Objective**: Compare active prescriptions, discharge medication orders, and patient reports across visits to detect conflicting doses, duplicate therapies, or unconfirmed discontinuations.
- **Mechanism**:
  - Retrieves all prescription slips, transfer summaries, and reconciliation logs.
  - Prompts LLM to identify contradictions (e.g. Doc A says 14U insulin vs Doc B says 20U; or patient reports stopping a statin without a physician order).
  - Emits `MismatchItem(title, description, source_a_citation, source_b_citation, citations)`.

### 4.5 Agent 5: Comorbidities, Milestones & Acute Admissions (`comorbidities_agent`)
- **Objective**: Build the reverse-chronological "Priority Findings" timeline spanning 10 years back (surgeries, hospitalizations, procedures, specialist consultations).
- **Mechanism**:
  - Broad retrieval across discharge summaries, procedural notes, operative reports, specialist consults (cardiology, urology, orthopaedics, dental, ophthalmology, infectious disease).
  - LLM extracts distinct events: Title, Subtitle, Severity (`high`, `medium`, `low`), Date (`YYYY-MM-DD`).
  - Attaches source proof bounding-box citations to each milestone.

### 4.6 Agent 6: Dynamic Caregiver Prep Sheet / Handoff (`caregiver_prep_agent`)
- **Objective**: Generate actionable, low-health-literacy visit prep checklists for family care partners.
- **Dynamic Mode Switch**:
  - If patient is **Diabetic** $\rightarrow$ `mode: "handoff"` (focus on insulin administration demonstration, hypoglycemia protocols, evening meal carbs, upcoming ACR/eye exams).
  - If patient is **Pre-diabetic / Non-diabetic** $\rightarrow$ `mode: "prep_sheet"` (focus on lifestyle modifications, meal timing, physical routine, medication compliance, annual rescreening).
- **Multi-Lingual Requirement**:
  - Checklist items must be provided in English (`text_en`), Hindi (`text_hi`), and Tamil (`text_ta`) for Indian clinical care settings.

### 4.7 Agent 7: Non-Intrusive Smart Prompt Bubbles (`assistive_bubbles_agent`)
- **Objective**: Suggest context-aware exploratory actions without making unsolicited clinical assertions.
- **Mechanism**:
  - Dynamically inspects the state. If multi-year labs exist $\rightarrow$ prompts doctor to view trajectory modal. If acute admissions exist $\rightarrow$ prompts to review discharge summaries. If medication discrepancies exist $\rightarrow$ prompts to open reconciliation.
  - Formats prompts as questions ending with `?` (e.g. *"Longitudinal data available for HbA1c and eGFR: Would you like to chart the 10-year metabolic trajectory?"*).

### 4.8 Agent 8: Brief Compiler Node (`brief_compiler_node`)
- **Objective**: Assemble all agent outputs into a unified, strict Pydantic `ConsultationBrief` schema ready for immediate UI consumption.

---

## 5. Architectural Mandate: Externalized Prompts & Zero Hardcoding

### 5.1 The Root Cause of User Frustration
In earlier revisions, agent logic used Python keyword checks (`if "covid" in content ... elif "dengue" ... elif "atorvastatin"`) or hardcoded fallback values (`"138/86"`, `"107 mg/dL"`, `"68"`, `"Arvind Narayanan"`). **This completely violates the universal architecture of PrepPulse.**

### 5.2 Mandatory Directory Layout for Prompts
All LLM prompts must live in external text/jinja templates in a dedicated `prompts/` directory so they can be iteratively refined without touching Python application code:

```
c:\All_My_Personal_Projects\PrepPulse\
├── prompts\
│   ├── agents\
│   │   ├── classification_agent.txt
│   │   ├── trajectory_agent.txt
│   │   ├── lab_discovery_agent.txt
│   │   ├── care_gaps_agent.txt
│   │   ├── mismatches_agent.txt
│   │   ├── comorbidities_agent.txt
│   │   ├── caregiver_prep_agent.txt
│   │   └── assistive_bubbles_agent.txt
│   └── rag\
│       ├── hybrid_query_reformulation.txt
│       └── chatbot_doctor_assistant.txt
```

### 5.3 Strict JSON Extraction Rule
Every agent calling the LLM must utilize a centralized, fail-safe JSON array parser (`_parse_llm_json_array`) that:
- Trims markdown backticks (````json ... ````).
- Extracts innermost bracket ranges `[...]` if the model adds conversational pleasantries.
- Safely handles alternative key names (e.g. `text_en` vs `english` vs `description`).
- Never throws unhandled exceptions that break the workflow.

---

## 6. Hybrid RAG Engine (`preppulse_rag`)

The RAG layer combines lexical and dense semantic search with Reciprocal Rank Fusion (RRF):

1. **`SparseBM25Index`**: Exact keyword matching for drug names (Amlodipine, Glargine, Metformin, Atorvastatin), lab acronyms (HbA1c, eGFR, ACR), and procedural terms.
2. **`DenseVectorIndex`**: Cosine similarity using 1024-dimensional Qwen embeddings (`text-embedding-qwen3-embedding-0.6b`), applying a 90% relative threshold against max score to prevent multi-patient semantic drift.
3. **`HybridEnsembleRetriever`**:
   - Merges results via RRF: $\text{RRF Score} = \sum \frac{1}{60 + \text{rank}}$.
   - Supports metadata filtering: `patient_id`, `year_start`, `year_end`, `category`.
   - Returns chunks with full provenance metadata (`source_file`, `page_number`, `bbox: [ymin, xmin, ymax, xmax]`, `visit_date`).
   - Query execution target: `<50ms` per query.

---

## 7. Mock Interactive UI & Final Testing Specification

To test the entire pipeline end-to-end visually, an interactive application (Streamlit or lightweight web UI) must be provided:

### 7.1 Key UI Elements
1. **Patient Selector Bar**:
   - Dropdown to select a patient (e.g. `PP001_Arvind_Narayanan` or any newly ingested patient).
   - "Run Live Clinical Analysis" button: triggers live ingestion $\rightarrow$ chunking $\rightarrow$ Hybrid RAG $\rightarrow$ 8-node LangGraph swarm in real time.
2. **Doctor Pre-Consultation Workspace (Top & Center)**:
   - **Header Card**: Greeting, patient name, age/sex, MRN, dynamically inferred classification badge (`Pre-Diabetic`, `Type 2 Diabetes`, `Non-Diabetic`).
   - **Metabolic Trajectory Card**: KPI values with trend arrows ($\nearrow, \searrow, \rightarrow$), sparklines, and 10-year tabular flow.
   - **Care Gaps Card**: Overdue items with severity tags (`warning`, `info`, `critical`).
   - **Record Mismatches Card**: Contradiction items showing side-by-side conflicting sources.
   - **Family Caregiver Prep Card**: Toggle between English (`EN`), Hindi (`हि`), and Tamil (`த`) checklist items.
   - **10-Year Priority Findings Timeline**: Reverse-chronological tiles from most recent down to 10 years ago.
   - **Smart Prompt Bubbles**: Floating suggestion pills at top or bottom (clickable to open specific modals).
3. **Source Proof Side Viewer (Side / Drawer)**:
   - When any KPI, mismatch, finding, or care gap is clicked, the side viewer displays the original document page with the bounding box highlighted.
4. **Interactive Doctor Chatbot Bar (Side / Full-Page Expandable)**:
   - Dedicated chat drawer connected directly to `HybridEnsembleRetriever`.
   - Doctor can ask free-form clinical questions (e.g. *"What was his eGFR baseline in 2016?"*, *"Why was Atorvastatin disputed?"*).
   - Expandable into a full-page split view.

---

## 8. Current Implementation State & File Manifest

| File Path | Status | Description |
|---|---|---|
| `src/preppulse_ocr/engine.py` | **FROZEN** | Core OCR engine (PyMuPDF + Tesseract hybrid same-page extraction, lab-table parsing, `[0, 1000]` bboxes). |
| `src/preppulse_db/mongo_store.py` | Complete | MongoDB store connecting to `mongodb://localhost:27017/preppulse` (`stage_1_raw_ocr`). |
| `src/preppulse_db/schemas.py` | Complete | MongoDB Pydantic documents for raw OCR pages, tokens, and evidence anchors. |
| `src/preppulse_rag/chunker.py` | Complete | `ClinicalProvenanceChunker` preserving line tokens and normalized bounding boxes. |
| `src/preppulse_rag/retriever.py` | Complete | BM25 + Dense Qwen vector hybrid ensemble retriever with RRF and temporal filters. |
| `src/preppulse_rag/llm_provider.py` | Complete | Auto-detects local LM Studio Qwen server, Sarvam fallback, or deterministic mock. |
| `src/preppulse_agents/schemas.py` | Complete | Strict Pydantic contracts for all agent outputs and the unified `ConsultationBrief`. |
| `src/preppulse_agents/graph.py` | In Progress / Refactoring | 8-node LangGraph workflow. Must migrate inline prompts to external template files and purge all hardcoded defaults. |
| `tests/test_end_to_end_pipeline.py` | Passing | End-to-end integration test validating 13 real-world PDFs of PP001 Arvind Narayanan. |
| `TO_DO.md` | Active | Living source of truth tracking completed and planned milestones. |

---

## 9. Next Steps for Immediate Execution

1. **Extract All Prompts to `prompts/agents/*.txt`**:
   - Create the `prompts/` directory tree.
   - Externalize all prompts for classification, trajectory, lab discovery, care gaps, mismatches, comorbidities, caregiver prep, and assistive bubbles.
2. **Purge Any Lingering Hardcoded Defaults**:
   - Replace any remaining default fallback strings in `graph.py` (e.g. fallback patient names, dummy lab strings) with generic placeholder indicators or explicit `None`.
3. **Build the Live Interactive Consultation UI**:
   - Implement `temp_ui/clinical_workspace_app.py` (Streamlit) matching the visual layout of the reference designs:
     - Real-time patient selection and dynamic swarm execution.
     - Priority finding tiles with reverse-chronological sorting.
     - Dual-view Source Proof bounding-box inspector.
     - Multi-lingual caregiver checklist (`EN` / `हि` / `த`).
     - Expandable sidecar doctor chatbot backed by Hybrid RAG.

