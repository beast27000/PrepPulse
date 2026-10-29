# PrepPulse: Frontend Integration & Agent UI Contract Specification

This document provides the complete technical specification for the **Frontend Engineering Team** to bind UI components to the PrepPulse RAG & Multi-Agent backend.

---

## 1. High-Level Architecture & Page Layout Contract

The application interface follows a **3-Column / Dual-Pane Layout** as depicted in the clinical reference designs:

```
+---------------------------------------------------------------------------------------------------------+
|                                    PREPPULSE TOP BAR & PATIENT SELECTOR                                 |
+---------------------------------------------------------------------------------------------------------+
| [NAV SIDEBAR] |                  MAIN CONSULTATION WORKSPACE                   |     RIGHT SIDEBAR      |
|               |                                                                |                        |
| • Today       |  Greeting Banner & Patient Header                              |  [ SOURCE PROOF PANEL ]|
| • Patients    |  (Name, Age, Disease Stage, Visit Focus, Sync Status)           |                        |
| • Records     |  ------------------------------------------------------------  |  Document Title & Date |
| • Care paths  |  [ TOP 4 DYNAMIC CARDS ]                                       |  Page Preview Canvas   |
| • Guidance    |   01. Metabolic Trajectory   |   02. Care Gaps                 |  Visual Bounding Box   |
|               |   03. Record Mismatches      |   04. Caregiver Handoff/Prep    |  Highlight ([0, 1000]) |
| [LANGUAGE]    |  ------------------------------------------------------------  |                        |
| [EN|हि|த|తె]   |  [ PRIORITY FINDINGS TILES (Chronological 10-Yr Flow) ]        |  Snippet Extraction    |
|               |   • Finding 1 (Recent - Confirmed / Accept / Reject)           |                        |
|               |   • Finding 2 (Pending Review / Direct Proof Link)             |  --------------------  |
|               |  ------------------------------------------------------------  |  [ SMART CHAT DOCK ]   |
|               |  [ SMART ASSISTIVE PROMPT BUBBLES ]                            |  Ad-hoc Doctor Q&A     |
|               |   (e.g., "Shall I chart patient's 10-yr diabetic journey?")    |  Sub-50ms Hybrid RAG   |
+---------------------------------------------------------------------------------------------------------+
```

---

## 2. API Payloads & Pydantic Schema Contracts

The backend returns a unified `DecadeConsultationBrief` JSON payload structured specifically for zero-parsing direct UI rendering.

### A. Patient Header & Dynamic Classification
```json
{
  "patient_id": "patient_08_4091",
  "patient_name": "Meera Joshi",
  "age": 62,
  "gender": "Female",
  "classification": {
    "stage": "Type 2 Diabetes", 
    "category": "diabetic",
    "diagnostic_basis": "HbA1c 8.4% (elevated from 7.8% in Jan), on dual oral therapy + basal insulin"
  },
  "visit_focus": "Improve glycemic control",
  "last_reviewed_days_ago": 21,
  "open_items_count": 4,
  "needs_confirmation_count": 2,
  "freshness": {
    "score_percent": 72,
    "label": "Brief is clinically fresh",
    "sources_count": 6,
    "last_sync": "Today 08:42"
  }
}
```
*Note on Dynamic Classification:*
- `category: "non_diabetic"` $\rightarrow$ Card 04 renders as **"Caregiver Prep Sheet"** (Lifestyle, Allergies, Vitals).
- `category: "pre_diabetic"` $\rightarrow$ Card 04 renders as **"Caregiver Prep Sheet"** (Dietary Steps, Activity, HbA1c Monitoring).
- `category: "diabetic"` $\rightarrow$ Card 04 renders as **"Caregiver Handoff"** (Insulin Schedule, Hypoglycemia Precautions, Medication Strip Verification).

---

### B. Top 4 Dynamic Consultation Cards (`cards[0..3]`)

#### Card 01: `WHAT CHANGED - Metabolic Trajectory`
```json
{
  "card_id": "card_01_trajectory",
  "title": "Metabolic trajectory",
  "badge": "WHAT CHANGED",
  "kpis": [
    {
      "name": "HbA1c",
      "value": "8.4",
      "unit": "%",
      "date": "03/14",
      "trend": "up",
      "status": "warning",
      "citation": { "document_id": "doc_lab_2024", "page": 2, "bbox": [100, 200, 150, 220] }
    },
    {
      "name": "Fasting glucose",
      "value": "142",
      "unit": "mg/dL",
      "date": "03/14",
      "trend": "up",
      "status": "warning",
      "citation": { "document_id": "doc_lab_2024", "page": 2, "bbox": [100, 240, 150, 260] }
    },
    {
      "name": "eGFR",
      "value": "68",
      "unit": "mL/min/1.73m²",
      "date": "03/14",
      "trend": "down",
      "status": "alert",
      "citation": { "document_id": "doc_lab_2024", "page": 2, "bbox": [100, 280, 150, 300] }
    }
  ]
}
```

#### Card 02: `STILL TO CLOSE - Care Gaps`
```json
{
  "card_id": "card_02_care_gaps",
  "title": "Care gaps",
  "badge": "STILL TO CLOSE",
  "items": [
    {
      "id": "gap_01",
      "severity": "high",
      "title": "Annual diabetic foot exam is overdue",
      "detail": "No completed foot exam report found in the last 12 months.",
      "citation": null
    },
    {
      "id": "gap_02",
      "severity": "medium",
      "title": "Urine microalbumin result is missing",
      "detail": "Order is present in clinic note (14 Mar), but no lab result is attached.",
      "citation": { "document_id": "doc_clinic_2024", "page": 1, "bbox": [120, 500, 600, 530] }
    }
  ]
}
```

#### Card 03: `RESOLVE BEFORE PLAN - Record Mismatches`
```json
{
  "card_id": "card_03_mismatches",
  "title": "Record mismatches",
  "badge": "RESOLVE BEFORE PLAN",
  "items": [
    {
      "id": "mismatch_01",
      "severity": "critical",
      "title": "Conflicting insulin dose",
      "detail": "Clinic slip states Glargine 14U; hospital discharge states Glargine 20U.",
      "citations": [
        { "document_id": "doc_slip_mar", "page": 1, "bbox": [80, 320, 400, 340], "label": "Clinic slip" },
        { "document_id": "doc_discharge_feb", "page": 3, "bbox": [90, 410, 420, 435], "label": "Discharge summary" }
      ]
    },
    {
      "id": "mismatch_02",
      "severity": "medium",
      "title": "Metformin dose needs reconciliation",
      "detail": "Medication list says 500mg twice daily; pharmacy history shows 1000mg.",
      "citations": [
        { "document_id": "doc_rx_jan", "page": 1, "bbox": [110, 210, 380, 230], "label": "Med list" }
      ]
    }
  ]
}
```

#### Card 04: `FAMILY HANDOFF - Caregiver Prep Sheet / Checklist`
```json
{
  "card_id": "card_04_caregiver",
  "title": "Caregiver prep sheet",
  "badge": "FAMILY HANDOFF",
  "mode": "handoff",
  "checklist": [
    {
      "id": "chk_01",
      "text_en": "Bring every current medicine strip or photo to the visit.",
      "text_hi": "मुलाकात में वर्तमान दवाओं के सभी स्ट्रिप या तस्वीरें साथ लाएं।",
      "text_ta": "தற்போது உட்கொள்ளும் அனைத்து மருந்து அட்டைகள் அல்லது புகைப்படங்களை எடுத்து வாருங்கள்.",
      "completed": false
    },
    {
      "id": "chk_02",
      "text_en": "Ask patient to demonstrate evening insulin injection routine.",
      "text_hi": "मरीज से शाम के इंसुलिन इंजेक्शन की प्रक्रिया दिखाने को कहें।",
      "text_ta": "மாலை நேர இன்சுலின் ஊசி செலுத்தும் முறையை செய்து காட்டச் சொல்லுங்கள்.",
      "completed": false
    },
    {
      "id": "chk_03",
      "text_en": "Keep the next urine ACR and dilated eye exam appointments on calendar.",
      "text_hi": "अगली यूरिन ACR और आंखों की जांच का अपॉइंटमेंट कैलेंडर पर नोट रखें।",
      "text_ta": "அடுத்த சிறுநீர் ACR மற்றும் கண் பரிசோதனைக்கான தேதியை குறித்து வையுங்கள்.",
      "completed": false
    }
  ]
}
```

---

## 3. Priority Findings Tiles (Reverse Chronological 10-Year Flow)

Each finding represents a clinically validated signal over the patient's 10-year history:

```json
{
  "priority_findings": [
    {
      "finding_id": "find_01",
      "title": "Glycemic control above target",
      "subtitle": "HbA1c 8.4% — up from 7.8% in Jan. Reports afternoon fatigue and missed evening doses twice weekly.",
      "status": "confirmed",
      "severity": "high",
      "date": "2024-03-14",
      "citation": {
        "document_id": "lab_report_20240314",
        "document_title": "Lab report",
        "date_formatted": "14 Mar 2024",
        "page_number": 2,
        "bbox": [590, 94, 656, 906],
        "extracted_text": "HbA1c: 8.4% (High). Previous: 7.8% (Jan 2024)"
      },
      "actions": ["accept", "edit", "reject"]
    },
    {
      "finding_id": "find_02",
      "title": "Early renal risk signal",
      "subtitle": "Urine ACR 42 mg/g with stable eGFR 68. Consider repeat ACR and medication review.",
      "status": "pending_review",
      "severity": "medium",
      "date": "2024-03-14",
      "citation": {
        "document_id": "lab_report_20240314",
        "document_title": "Lab report",
        "date_formatted": "14 Mar 2024",
        "page_number": 2,
        "bbox": [680, 110, 720, 890],
        "extracted_text": "Microalbumin / Creatinine Ratio: 42 mg/g (Ref: <30)"
      },
      "actions": ["accept", "edit", "reject"]
    },
    {
      "finding_id": "find_03",
      "title": "Cardiovascular Stent Placement (LAD)",
      "subtitle": "Percutaneous Coronary Intervention with Drug-Eluting Stent placed following acute NSTEMI.",
      "status": "confirmed",
      "severity": "high",
      "date": "2022-06-18",
      "citation": {
        "document_id": "cardiology_discharge_2022",
        "document_title": "Hospital discharge summary",
        "date_formatted": "18 Jun 2022",
        "page_number": 1,
        "bbox": [250, 80, 310, 920],
        "extracted_text": "Procedure: PCI with 1x DES to mid-LAD. Cardiologist: Dr. Rao. LVEF 45%."
      },
      "actions": ["accept", "edit", "reject"]
    }
  ]
}
```

---

## 4. Source Proof Interaction & Highlighting Contract

When a doctor clicks **any** KPI, finding tile, mismatch link, or chart coordinate:

1. **Trigger:** Frontend emits `onSelectCitation(citation)`.
2. **Right Pane Action:**
   - Loads the source document image / PDF page referenced by `citation.document_id` and `citation.page_number`.
   - Normalizes the `citation.bbox` array `[x0, y0, x1, y1]` against canvas dimensions:
     $$\text{pixel\_x0} = \frac{x_0}{1000} \times \text{canvas\_width}, \quad \text{pixel\_y0} = \frac{y_0}{1000} \times \text{canvas\_height}$$
     $$\text{pixel\_width} = \frac{x_1 - x_0}{1000} \times \text{canvas\_width}, \quad \text{pixel\_height} = \frac{y_1 - y_0}{1000} \times \text{canvas\_height}$$
   - Renders a semi-transparent golden/yellow bounding highlight with a smooth focus scroll.
   - Displays the extracted raw snippet text in the `SOURCE PROOF` sidebar card.

---

## 5. Multi-Lingual Localization Contract

PrepPulse supports live localization across Indian languages (**English, Hindi, Tamil, Telugu**):
- **UI System Strings:** Static dictionary (headings, buttons, status pills).
- **Clinical Content Localization:** Generated by the AI layer in parallel:
  - `text_en`, `text_hi`, `text_ta`, `text_te`.
  - When the doctor toggles language `EN | हि | த`:
    - The UI switches the rendered key dynamically without re-invoking the backend.

---

## 6. Smart Assistive Prompt Bubbles (Non-Diagnostic)

Displayed at the bottom of the workspace or docked to the chat:
```json
{
  "assistive_bubbles": [
    {
      "bubble_id": "bubble_01",
      "icon": "timeline",
      "prompt_text": "10-year lab history available: Shall I chart patient's diabetic journey over 10 years?",
      "action_type": "open_chart_modal",
      "target_series": ["HbA1c", "eGFR", "Fasting Glucose"]
    },
    {
      "bubble_id": "bubble_02",
      "icon": "heart",
      "prompt_text": "LAD Stent placement in 2022: Would you like to view the cardiology consultation remarks?",
      "action_type": "open_milestone_detail",
      "milestone_id": "find_03"
    }
  ]
}
```
*Doctor Experience:* A single click opens the relevant visual modal or sends the prompt directly into the interactive chat dock.

---

## 7. Interactive Clinical Chat Dock API

- **Endpoint:** `POST /api/chat/query`
- **Payload:**
  ```json
  {
    "patient_id": "patient_08_4091",
    "query": "Show me the HbA1c values and Dr. Mehta's remarks from 2022",
    "language": "en"
  }
  ```
- **Response:**
  ```json
  {
    "answer_markdown": "In **March 2022**, Dr. Mehta reviewed the patient following lab testing:\n- **HbA1c:** 7.2% (elevated from 6.5% in 2019)\n- **Dr. Mehta's Remarks:** Patient reported dietary challenges. Metformin titrated to 1000mg twice daily with evening meal.\n- **Linked Lab:** Lab panel from 12 Mar 2022 confirmed eGFR was 78 mL/min/1.73m².",
    "citations": [
      { "document_id": "clinic_note_2022", "page": 1, "bbox": [150, 100, 220, 900] }
    ],
    "suggested_followups": [
      "Show medication titration timeline from 2020 to 2024",
      "Compare eGFR trend before and after 2022"
    ]
  }
  ```
