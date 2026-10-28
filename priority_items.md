# PrepPulse: High-Priority Requirements & Architectural Directives

This document tracks the core requirements, clinical boundaries, and design directives for the PrepPulse Longitudinal RAG & Multi-Agent Engine.

---

## 1. Non-Negotiable Core Principle: Assistive Scope (Strictly Non-Diagnostic)

- **Assistive Partner Only**: PrepPulse is an assistive clinical chart-review engine designed to eliminate doctor fatigue when reviewing years of medical history. It is **never** an autonomous diagnostic or treatment engine.
- **No Autonomous Diagnosis**: The system must never assert clinical diagnoses (e.g., never say *"Patient has diabetic nephropathy"*). It presents factual, objective observations (e.g., *"eGFR declined from 92 to 68 mL/min/1.73m² over 3 years; urine ACR is 42 mg/g"*).
- **No Superiority Framing**: The system must never tell the doctor it "knows better". It respects the clinical authority of the treating physician and faithfully presents what is documented in the chart.

---

## 2. Smart UI Assistive Prompt Bubbles (Interactive Guidance)

Instead of unsolicited diagnostic claims, the system generates subtle, smart prompt bubbles at the bottom of the UI or chat interface to offer relevant historical context:
- *"10-year lab history detected: Would you like to view the patient's glycemic trajectory over 10 years?"*
- *"Patient noted to have chronic history dating back to childhood: Would you like to pull up relevant records over this period?"*
- *"Cardiology consultation notes found from 2022: Would you like to inspect the cardiovascular timeline and stent history?"*
- *"Lab panel ordered near the 14 March 2024 consult: Would you like to review linked values alongside the doctor's remarks?"*

These bubbles give the doctor instant one-click drill-downs without cluttering the screen or making unsolicited assertions.

---

## 3. 10-Year Longitudinal Scope & Full Spectrum Coverage

- **Spectrum Coverage**:
  - **Non-Diabetic** (Normal glycemic range, monitoring general metabolic health).
  - **Pre-Diabetic** (Impaired fasting glucose, borderline HbA1c 5.7% - 6.4%, lifestyle intervention phase).
  - **All Diabetic Stages** (Stage 1 diet/monotherapy, progressive dual/triple oral therapy, advanced insulin-dependent, complicated T2D with end-organ involvement).
- **Decade-Scale Health History**:
  - Longitudinal coverage spanning up to 10 years of patient records.
  - Encompasses all hospitalizations, surgical procedures, specialty consultations (cardiology, nephrology, ophthalmology, podiatry), and episodic clinic visits.
- **Multi-Condition Comorbidity Timelines**:
  - Seamless tracking of non-diabetic conditions (e.g., coronary artery disease, angioplasty/stents 4 years ago, hypertension, acute admissions).

---

## 4. Multi-Modal Visualizations: Numerical Tables & Graphical Charts

- **10-Year Tabular Flow**:
  - Annualized comparative matrix displaying core biomarkers across years (e.g., 2015, 2018, 2021, 2024, 2026).
  - Displays dates, numbers, units, reference ranges, and directional trends.
- **Graphical Chart Series**:
  - Formatted numerical datasets ready for direct binding to UI chart widgets (Streamlit, Plotly, Altair).
  - Multi-year line charts (e.g., HbA1c trajectory vs. eGFR decline).
  - Bar charts (e.g., medication dose progression, annual screening frequency).
- **100% Provenance Preservation**:
  - Every single cell in the table and every coordinate on the chart links directly to its Stage 1 OCR source proof with normalized `[0, 1000]` bounding boxes (`[x0, y0, x1, y1]`) for click-to-highlight review.

---

## 5. Retrospective Consultation Briefs & Temporal-Semantic Lab Linking

- **Historical Consultation Reconstruction**:
  - When the doctor requests past consultation history (e.g., *"What was discussed in Dr. Mehta's visit in 2022?"*), the system reconstructs a specialized historical consultation brief.
  - Faithful extraction and concise summarization of the original doctor's clinical notes, reasoning, and specialist remarks.
- **Temporal-Semantic Lab Linking**:
  - Often, lab reports are physically separate documents from the consultation slip.
  - The engine links disparate lab panels to consultation notes using dates, calendar years, clinical entities, and semantic references within the notes.
  - Preserves the treating clinician's original clinical framework while enriching it with corresponding objective lab data.

---

## 6. Dual Presentation Contract: Chat Interface + Direct UI Element Binding

- **Top-Level High-Level Data Cards**:
  - Prominent summary cards bound directly to frontend components when the doctor opens the patient file:
    - *Glycemic Status & Trajectory Card* (Non-diabetic / Pre-diabetic / Diabetic).
    - *Comorbidity Timeline Card* (Key milestones, cardiac interventions, surgeries).
    - *Immediate Action & Mismatch Cards* (Overdue screenings, medication discrepancies).
- **Interactive Chat Interface**:
  - Powered by sub-50ms hybrid RAG (BM25 + dense vectors) for rapid ad-hoc doctor queries and drill-downs.
- **Full Provenance Underneath**:
  - Behind every high-level card and chat response lies the granular Stage 1 OCR token/line data and visual bounding box overlays.
