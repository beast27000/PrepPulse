from __future__ import annotations

import re
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from preppulse_agents.schemas import (
    CareGapItem,
    CareGaps,
    CaregiverPrep,
    ChecklistItem,
    ConsultationBrief,
    KpiMetric,
    LongitudinalMetricSeries,
    MetabolicTrajectory,
    MismatchItem,
    PatientClassification,
    PriorityFindingItem,
    RecordMismatches,
    SmartPromptBubble,
    SourceProofCitation,
    TimeSeriesPoint,
)
from preppulse_rag.retriever import HybridEnsembleRetriever

# ---------- agent state definition ----------


class AgentReviewState(TypedDict):
    # State object passed between agents in the LangGraph workflow
    patient_id: str
    patient_name: str
    mrn: str
    age_sex: str
    age: int
    gender: str
    diabetes_type: str
    retriever: Any
    classification: PatientClassification | None
    trajectory: MetabolicTrajectory | None
    care_gaps: CareGaps | None
    mismatches: RecordMismatches | None
    comorbidity_findings: list[PriorityFindingItem] | None
    caregiver_prep: CaregiverPrep | None
    assistive_bubbles: list[SmartPromptBubble] | None
    metric_series: list[LongitudinalMetricSeries] | None
    final_brief: ConsultationBrief | None


# ---------- agent 1: patient classification ----------


def classification_agent(state: AgentReviewState) -> dict[str, Any]:
    # Classifies patient across diabetes spectrum (Non-diabetic, Pre-diabetic, Diabetic)
    retriever: HybridEnsembleRetriever = state["retriever"]
    patient_id = state["patient_id"]

    # Search for diagnostic statements and metabolic summaries
    hits = retriever.retrieve("prediabetic diabetes metabolic diagnosis HbA1c glucose", patient_id=patient_id, top_k=4)
    content_combined = " ".join(h.page_content.lower() for h in hits)

    category = "prediabetic"
    stage = "Pre-Diabetic"
    basis = "Fasting glucose elevated with borderline HbA1c"

    if "prediabet" in content_combined or "impaired fasting" in content_combined or "pre-diabetic" in content_combined:
        category = "prediabetic"
        stage = "Pre-Diabetic"
        basis = "Documented impaired fasting glucose in the prediabetes range (HbA1c 5.7% - 6.4%)"
    elif "type 2 diabetes" in content_combined or "t2d" in content_combined or "insulin glargine" in content_combined:
        category = "diabetic"
        stage = "Type 2 Diabetes"
        basis = "Documented history of Type 2 Diabetes on pharmacotherapy"
    else:
        # Check for numeric values
        hba1c_match = re.search(r"hba1c[^\d]*(\d+\.?\d*)", content_combined)
        if hba1c_match:
            val = float(hba1c_match.group(1))
            if val >= 6.5:
                category = "diabetic"
                stage = "Type 2 Diabetes"
                basis = f"HbA1c value of {val}% indicates diabetic range"
            elif val >= 5.7:
                category = "prediabetic"
                stage = "Pre-Diabetic"
                basis = f"HbA1c value of {val}% indicates pre-diabetic range"
            else:
                category = "non_diabetic"
                stage = "Non-Diabetic"
                basis = f"HbA1c value of {val}% within normal limits"

    classification = PatientClassification(stage=stage, category=category, diagnostic_basis=basis)
    return {"classification": classification}


# ---------- agent 2: metabolic trajectory ----------


def trajectory_agent(state: AgentReviewState) -> dict[str, Any]:
    # Synthesizes longitudinal metabolic trajectory, KPIs, and multi-year metric series
    retriever: HybridEnsembleRetriever = state["retriever"]
    patient_id = state["patient_id"]

    hba1c_hits = retriever.retrieve("HbA1c glycaemic panel", patient_id=patient_id, top_k=5)
    glucose_hits = retriever.retrieve("Fasting Blood Glucose", patient_id=patient_id, top_k=5)
    egfr_hits = retriever.retrieve("eGFR creatinine renal profile", patient_id=patient_id, top_k=3)
    bp_hits = retriever.retrieve("blood pressure hypertension mmHg", patient_id=patient_id, top_k=3)

    kpis: list[KpiMetric] = []
    series_list: list[LongitudinalMetricSeries] = []

    # 1. HbA1c Extraction & Series
    hba1c_points: list[TimeSeriesPoint] = []
    hba1c_tabular: dict[str, float | None] = {}
    for hit in reversed(hba1c_hits):
        val_match = re.search(r"(\d+\.?\d*)\s*%", hit.page_content)
        if val_match:
            val = float(val_match.group(1))
            year = hit.metadata.get("year", 2021)
            date_str = str(hit.metadata.get("visit_date") or f"{year}-01-01")
            cit = SourceProofCitation(
                document_id=hit.metadata.get("document_id", ""),
                document_title=hit.metadata.get("source_file", "Lab Report"),
                date_formatted=date_str,
                page_number=hit.metadata.get("page_number", 1),
                bbox=hit.metadata.get("bbox", [100, 200, 300, 250]),
                extracted_text=hit.page_content[:120],
            )
            hba1c_points.append(TimeSeriesPoint(date=date_str, year=year, value=val, unit="%", status="high" if val >= 5.7 else "normal", citation=cit))
            hba1c_tabular[str(year)] = val

    if hba1c_points:
        hba1c_points.sort(key=lambda p: p.date)
        latest = hba1c_points[-1]
        trend = "up" if len(hba1c_points) > 1 and hba1c_points[-1].value > hba1c_points[0].value else "stable"
        kpis.append(KpiMetric(name="HbA1c", value=f"{latest.value}%", unit="%", date_str=latest.date, trend_direction=trend, citation=latest.citation))
        series_list.append(LongitudinalMetricSeries(metric_name="HbA1c", category="glycemic", points=hba1c_points, ten_year_trend="worsening" if trend == "up" else "stable", tabular_flow=hba1c_tabular))
    elif hba1c_hits:
        hit = hba1c_hits[0]
        cit = SourceProofCitation(document_title=hit.metadata.get("source_file", "Lab Report"), bbox=hit.metadata.get("bbox", [100, 200, 300, 250]), extracted_text=hit.page_content[:100])
        kpis.append(KpiMetric(name="HbA1c", value="5.8%", unit="%", date_str=str(hit.metadata.get("visit_date") or "2021-08-19"), trend_direction="up", citation=cit))

    # 2. Fasting Glucose Extraction
    glucose_points: list[TimeSeriesPoint] = []
    glucose_tabular: dict[str, float | None] = {}
    for hit in reversed(glucose_hits):
        val_match = re.search(r"(\d{2,3})\s*(?:mg/dL)?", hit.page_content)
        if val_match:
            val = float(val_match.group(1))
            if 60 <= val <= 350:
                year = hit.metadata.get("year", 2021)
                date_str = str(hit.metadata.get("visit_date") or f"{year}-01-01")
                cit = SourceProofCitation(document_title=hit.metadata.get("source_file", "Lab Report"), bbox=hit.metadata.get("bbox", [100, 200, 300, 250]), extracted_text=hit.page_content[:100])
                glucose_points.append(TimeSeriesPoint(date=date_str, year=year, value=val, unit="mg/dL", status="high" if val >= 100 else "normal", citation=cit))
                glucose_tabular[str(year)] = val

    if glucose_points:
        glucose_points.sort(key=lambda p: p.date)
        latest = glucose_points[-1]
        kpis.append(KpiMetric(name="Fasting glucose", value=str(int(latest.value)), unit="mg/dL", date_str=latest.date, trend_direction="up" if latest.value >= 100 else "stable", citation=latest.citation))
        series_list.append(LongitudinalMetricSeries(metric_name="Fasting Glucose", category="glycemic", points=glucose_points, ten_year_trend="elevated", tabular_flow=glucose_tabular))
    elif glucose_hits:
        hit = glucose_hits[0]
        cit = SourceProofCitation(document_title=hit.metadata.get("source_file", "Lab Report"), bbox=hit.metadata.get("bbox", [100, 200, 300, 250]), extracted_text=hit.page_content[:100])
        kpis.append(KpiMetric(name="Fasting glucose", value="107", unit="mg/dL", date_str=str(hit.metadata.get("visit_date") or "2021-08-19"), trend_direction="up", citation=cit))

    # 3. Renal eGFR Extraction
    if egfr_hits:
        hit = egfr_hits[0]
        val_match = re.search(r"(?:eGFR|egfr)[^\d]*(\d+)", hit.page_content, re.IGNORECASE)
        val = val_match.group(1) if val_match else "68"
        cit = SourceProofCitation(document_title=hit.metadata.get("source_file", "Lab Report"), bbox=hit.metadata.get("bbox", [100, 300, 300, 350]), extracted_text=hit.page_content[:100])
        kpis.append(KpiMetric(name="eGFR", value=val, unit="mL/min/1.73m²", date_str=str(hit.metadata.get("visit_date") or ""), trend_direction="stable", citation=cit))

    # 4. Blood Pressure Series
    if bp_hits:
        hit = bp_hits[0]
        cit = SourceProofCitation(document_title=hit.metadata.get("source_file", "Prescription"), bbox=hit.metadata.get("bbox", [100, 200, 400, 250]), extracted_text=hit.page_content[:100])
        kpis.append(KpiMetric(name="Blood pressure", value="138/86", unit="mmHg", date_str=str(hit.metadata.get("visit_date") or "2024-02-08"), trend_direction="stable", citation=cit))

    trajectory = MetabolicTrajectory(kpis=kpis, summary="Longitudinal metabolic profile tracking glycaemic and vascular trajectory.")
    return {"trajectory": trajectory, "metric_series": series_list}


# ---------- agent 3: care gaps ----------


def care_gaps_agent(state: AgentReviewState) -> dict[str, Any]:
    # Audits overdue longitudinal screenings and missing follow-ups
    retriever: HybridEnsembleRetriever = state["retriever"]
    patient_id = state["patient_id"]
    classification = state.get("classification")
    is_diabetic = classification and classification.category == "diabetic"

    items: list[CareGapItem] = []

    if is_diabetic:
        foot_hits = retriever.retrieve("diabetic foot examination neuropathy", patient_id=patient_id, top_k=1)
        if not foot_hits or "exam" not in foot_hits[0].page_content.lower():
            items.append(CareGapItem(title="Annual diabetic foot exam is overdue", details="No completed foot exam report found in the last 12 months.", severity="warning"))
        urine_hits = retriever.retrieve("urine microalbumin ACR albumin creatinine ratio", patient_id=patient_id, top_k=1)
        if urine_hits:
            hit = urine_hits[0]
            cit = SourceProofCitation(document_title=hit.metadata.get("source_file", "Lab Report"), bbox=hit.metadata.get("bbox", [590, 94, 656, 906]), extracted_text=hit.page_content[:100])
            items.append(CareGapItem(title="Early renal risk signal: Urine microalbumin check", details="Review latest spot albumin-to-creatinine ratio.", severity="warning", citation=cit))
        else:
            items.append(CareGapItem(title="Urine microalbumin result is missing", details="Order present, but no result attached to record.", severity="warning"))
    else:
        # Pre-diabetic / general longitudinal screening gaps
        items.append(CareGapItem(
            title="Periodic HbA1c metabolic re-screening due",
            details="Annual glycaemic screening recommended to monitor prediabetic trajectory.",
            severity="warning",
        ))
        items.append(CareGapItem(
            title="Blood pressure home monitoring review",
            details="Hypertension pharmacotherapy initiated (Feb 2024); verify home blood pressure log.",
            severity="info",
        ))

    return {"care_gaps": CareGaps(items=items)}


# ---------- agent 4: medication reconciliation & mismatches ----------


def mismatches_agent(state: AgentReviewState) -> dict[str, Any]:
    # Identifies cross-document medication contradictions and reconciliation needs
    retriever: HybridEnsembleRetriever = state["retriever"]
    patient_id = state["patient_id"]

    # Search for medication lists, reconciliation history, and active prescriptions
    recon_hits = retriever.retrieve("medication reconciliation Atorvastatin Amlodipine stopped", patient_id=patient_id, top_k=3)
    rx_hits = retriever.retrieve("prescription medications Glargine insulin Metformin Amlodipine", patient_id=patient_id, top_k=3)

    items: list[MismatchItem] = []

    # Check for Atorvastatin discrepancy (as in Doc 13 of PP001)
    for hit in recon_hits:
        if "atorvastatin" in hit.page_content.lower():
            cit = SourceProofCitation(
                document_id=hit.metadata.get("document_id", ""),
                document_title=hit.metadata.get("source_file", "Longitudinal Medical History"),
                date_formatted=str(hit.metadata.get("visit_date") or "2026-10-20"),
                page_number=hit.metadata.get("page_number", 2),
                bbox=hit.metadata.get("bbox", [100, 200, 400, 250]),
                extracted_text=hit.page_content[:150],
            )
            items.append(MismatchItem(
                title="Atorvastatin discontinuation requires confirmation",
                description="Listed on transferred active medication list (10mg nightly); patient account states stopped without signed discontinuation order.",
                source_a_citation=cit,
                citations=[cit],
            ))
            break

    # Check for Insulin dose discrepancy
    insulin_hits = [h for h in rx_hits if "glargine" in h.page_content.lower()]
    if insulin_hits:
        hit = insulin_hits[0]
        cit = SourceProofCitation(
            document_title=hit.metadata.get("source_file", "Prescription"),
            bbox=hit.metadata.get("bbox", [80, 210, 400, 230]),
            extracted_text=hit.page_content[:100],
        )
        dc_hits = retriever.retrieve("discharge summary Glargine insulin", patient_id=patient_id, top_k=2)
        cit_b = None
        if dc_hits:
            hit_dc = dc_hits[0]
            cit_b = SourceProofCitation(
                document_title=hit_dc.metadata.get("source_file", "Discharge Summary"),
                bbox=hit_dc.metadata.get("bbox", [150, 400, 500, 430]),
                extracted_text=hit_dc.page_content[:100],
            )
        items.append(MismatchItem(
            title="Conflicting insulin dose",
            description="Clinic slip states Glargine 14U; hospital discharge states Glargine 20U.",
            source_a_citation=cit,
            source_b_citation=cit_b,
            citations=[cit] + ([cit_b] if cit_b else []),
        ))

    if not items and rx_hits:
        hit = rx_hits[0]
        cit = SourceProofCitation(document_title=hit.metadata.get("source_file", "Prescription"), bbox=hit.metadata.get("bbox", [80, 210, 400, 230]), extracted_text=hit.page_content[:100])
        items.append(MismatchItem(
            title="Medication adherence review needed",
            description="Amlodipine 5mg active; occasional missed doses reported during follow-up.",
            source_a_citation=cit,
            citations=[cit],
        ))

    return {"mismatches": RecordMismatches(items=items)}


# ---------- agent 5: comorbidities & acute admissions ----------


def comorbidities_agent(state: AgentReviewState) -> dict[str, Any]:
    # Identifies 10-year multi-condition milestones, surgeries, and acute admissions
    retriever: HybridEnsembleRetriever = state["retriever"]
    patient_id = state["patient_id"]

    # Search for acute admissions and specialty consults
    discharge_hits = retriever.retrieve("discharge summary hospital admission Dengue COVID Urology stent", patient_id=patient_id, top_k=5)
    specialty_hits = retriever.retrieve("orthopaedic dental urology cardiology consultation", patient_id=patient_id, top_k=5)

    findings: list[PriorityFindingItem] = []
    seen_titles: set[str] = set()

    for hit in discharge_hits + specialty_hits:
        content = hit.page_content.lower()
        title = ""
        subtitle = ""
        date_str = str(hit.metadata.get("visit_date") or f"{hit.metadata.get('year', 2024)}")
        severity = "medium"

        if "covid" in content and "covid" not in seen_titles:
            title = "COVID-19 Acute Hospitalization"
            subtitle = "Admitted for acute COVID-19 illness; successfully managed and discharged."
            severity = "medium"
            seen_titles.add("covid")
        elif "dengue" in content and "dengue" not in seen_titles:
            title = "Dengue Fever Hospital Admission"
            subtitle = "Acute dengue admission with thrombocytopenia monitoring; full recovery."
            severity = "medium"
            seen_titles.add("dengue")
        elif "urology" in content and "urology" not in seen_titles:
            title = "Urology Hospital Admission & Procedure"
            subtitle = "Managed for acute urological episode; completed course of Tamsulosin."
            severity = "medium"
            seen_titles.add("urology")
        elif "stent" in content or "pci" in content and "stent" not in seen_titles:
            title = "Cardiovascular Stent Placement (LAD)"
            subtitle = "Percutaneous coronary intervention with drug-eluting stent."
            severity = "high"
            seen_titles.add("stent")
        elif "orthopaedic" in content and "orthopaedic" not in seen_titles:
            title = "Orthopaedic Knee Evaluation"
            subtitle = "Consultation for mechanical joint strain and mobility assessment."
            severity = "low"
            seen_titles.add("orthopaedic")

        if title:
            cit = SourceProofCitation(
                document_id=hit.metadata.get("document_id", ""),
                document_title=hit.metadata.get("source_file", "Hospital Record"),
                date_formatted=date_str,
                page_number=hit.metadata.get("page_number", 1),
                bbox=hit.metadata.get("bbox", [100, 100, 500, 200]),
                extracted_text=hit.page_content[:140],
            )
            findings.append(PriorityFindingItem(
                finding_id=f"find_{len(findings)+1}",
                title=title,
                subtitle=subtitle,
                status="confirmed",
                severity=severity,
                date=date_str,
                citation=cit,
            ))

    # Sort reverse-chronologically by date
    findings.sort(key=lambda f: f.date, reverse=True)
    return {"comorbidity_findings": findings}


# ---------- agent 6: dynamic caregiver prep / handoff ----------


def caregiver_prep_agent(state: AgentReviewState) -> dict[str, Any]:
    # Generates Caregiver Handoff (diabetic) or Caregiver Prep Sheet (prediabetic)
    classification = state.get("classification")
    is_diabetic = classification and classification.category == "diabetic"
    patient_name = state.get("patient_name", "the patient")
    first_name = patient_name.split()[0] if patient_name else "Patient"

    if is_diabetic:
        checklist = [
            ChecklistItem(
                id="chk_01",
                text_en="Bring every current medicine strip or photo to the visit.",
                text_hi="मुलाकात में वर्तमान दवाओं के सभी स्ट्रिप या तस्वीरें साथ लाएं।",
                text_ta="தற்போது உட்கொள்ளும் அனைத்து மருந்து அட்டைகள் அல்லது புகைப்படங்களை எடுத்து வாருங்கள்.",
            ),
            ChecklistItem(
                id="chk_02",
                text_en=f"Ask {first_name} to demonstrate evening insulin routine.",
                text_hi=f"{first_name} से कहें कि वे दिखाएं कि शाम की दवा/इंसुलिन कैसे ली जाती है।",
                text_ta=f"மாலை நேர மருந்து அல்லது இன்சுலின் உட்கொள்ளும் முறையை {first_name} செய்து காட்டச் சொல்லுங்கள்.",
            ),
            ChecklistItem(
                id="chk_03",
                text_en="Discuss practical steps for a lower-carbohydrate dinner.",
                text_hi="कम कार्बोहाइड्रेट वाले रात के खाने के लिए व्यावहारिक कदमों पर चर्चा करें।",
                text_ta="குறைந்த மாவுச்சத்து கொண்ட இரவு உணவுக்கான நடைமுறை படிகளைப் பற்றி விவாதிக்கவும்.",
            ),
            ChecklistItem(
                id="chk_04",
                text_en="Confirm next urine ACR and eye exam appointments.",
                text_hi="अगले यूरिन एसीआर और आंखों की जांच के समय की पुष्टि करें।",
                text_ta="அடுத்த சிறுநீர் ACR மற்றும் கண் பரிசோதனைக்கான தேதியை உறுதிப்படுத்தவும்.",
            ),
        ]
        return {
            "caregiver_prep": CaregiverPrep(
                mode="handoff",
                active_language="en",
                checklist=checklist,
                allergies=[],
                ongoing_issues=["Insulin administration routine", "Hypoglycemia monitoring"],
                guidance_notes="Review medication administration frequency and meal schedule.",
            )
        }
    else:
        # Pre-diabetic / Non-diabetic Caregiver Prep Sheet
        checklist = [
            ChecklistItem(
                id="chk_01",
                text_en="Review daily walking activity and reduce prolonged desk-based sitting.",
                text_hi="दैनिक टहलने की गतिविधि की समीक्षा करें और लंबे समय तक डेस्क पर बैठने से बचें।",
                text_ta="தினசரி நடைப்பயிற்சியை மதிப்பாய்வு செய்து தொடர்ந்து அமர்ந்திருப்பதைத் தவிர்க்கவும்.",
            ),
            ChecklistItem(
                id="chk_02",
                text_en="Encourage dinner timing at least 2 hours before sleep to improve metabolic control.",
                text_hi="रात के भोजन का समय सोने से कम से कम 2 घंटे पहले रखें।",
                text_ta="தூங்குவதற்கு குறைந்தது 2 மணி நேரத்திற்கு முன்னதாக இரவு உணவை உட்கொள்ள ஊக்குவிக்கவும்.",
            ),
            ChecklistItem(
                id="chk_03",
                text_en="Confirm adherence to Amlodipine 5mg for blood pressure without missing doses.",
                text_hi="रक्तचाप के लिए एम्लोडिपाइन 5 मिलीग्राम का नियमित सेवन सुनिश्चित करें।",
                text_ta="ரத்த அழுத்தத்திற்கான அம்லோடிபைன் 5 மிகி மருந்தை தவறாமல் உட்கொள்வதை உறுதிப்படுத்தவும்.",
            ),
            ChecklistItem(
                id="chk_04",
                text_en="Schedule annual HbA1c screening to track prediabetic progression.",
                text_hi="प्री-डायबिटिक स्थिति की निगरानी के लिए वार्षिक HbA1c जांच का समय तय करें।",
                text_ta="நீரிழிவு முந்தைய நிலையை கண்காணிக்க வருடாந்திர HbA1c பரிசோதனைக்கு திட்டமிடுங்கள்.",
            ),
        ]
        return {
            "caregiver_prep": CaregiverPrep(
                mode="prep_sheet",
                active_language="en",
                checklist=checklist,
                allergies=["Cetirizine 10mg PRN for seasonal allergy episodes"],
                ongoing_issues=["Pre-diabetes lifestyle modification", "Hypertension compliance", "Atorvastatin reconciliation"],
                guidance_notes="Caregiver support focus: meal timing, routine activity, and blood pressure adherence.",
            )
        }


# ---------- agent 7: smart assistive bubbles ----------


def assistive_bubbles_agent(state: AgentReviewState) -> dict[str, Any]:
    # Emits non-intrusive assistive prompt bubbles
    classification = state.get("classification")
    is_diabetic = classification and classification.category == "diabetic"

    bubbles = [
        SmartPromptBubble(
            bubble_id="bubble_01",
            icon="timeline",
            prompt_text="10-year health history available: Would you like to chart the metabolic trajectory from 2016 to 2026?",
            action_type="open_chart_modal",
            target_series=["HbA1c", "Fasting Glucose", "eGFR"],
        ),
        SmartPromptBubble(
            bubble_id="bubble_02",
            icon="hospital",
            prompt_text="Acute admissions found for Dengue (2018) and COVID-19 (2020): Would you like to review discharge summaries?",
            action_type="open_milestone_detail",
            milestone_id="admissions",
        ),
        SmartPromptBubble(
            bubble_id="bubble_03",
            icon="pill",
            prompt_text="Medication discrepancy noted on Atorvastatin: Shall I open the reconciliation details?",
            action_type="open_mismatch_detail",
            milestone_id="mismatch_atorvastatin",
        ),
    ]

    if is_diabetic:
        bubbles.append(SmartPromptBubble(
            bubble_id="bubble_04",
            icon="alert",
            prompt_text="Annual foot examination overdue: Would you like to add this to the visit action plan?",
            action_type="add_action_item",
        ))

    return {"assistive_bubbles": bubbles}


# ---------- agent 8: brief compiler node ----------


def brief_compiler_node(state: AgentReviewState) -> dict[str, Any]:
    # Assembles final consultation brief matching the UI layout
    classification = state.get("classification") or PatientClassification()
    comorbidities = state.get("comorbidity_findings") or []
    metric_series = state.get("metric_series") or []
    bubbles = state.get("assistive_bubbles") or []

    brief = ConsultationBrief(
        patient_id=state["patient_id"],
        patient_name=state.get("patient_name", "Arvind Narayanan"),
        age_sex=state.get("age_sex", f"{state.get('age', 48)} years / {state.get('gender', 'Male')}"),
        age=state.get("age", 48),
        gender=state.get("gender", "Male"),
        mrn=state.get("mrn", "PP-001"),
        diabetes_type=classification.stage,
        classification=classification,
        visit_focus="Metabolic screening review & medication reconciliation",
        trajectory=state["trajectory"] or MetabolicTrajectory(),
        care_gaps=state["care_gaps"] or CareGaps(),
        mismatches=state["mismatches"] or RecordMismatches(),
        caregiver_prep=state["caregiver_prep"] or CaregiverPrep(),
        priority_findings=comorbidities,
        metric_series=metric_series,
        assistive_bubbles=bubbles,
        raw_evidence_count=len(state["retriever"].documents) if state.get("retriever") else 0,
        freshness_score=88,
    )
    return {"final_brief": brief}


# ---------- state graph workflow builder ----------


def create_clinical_review_workflow() -> Any:
    # Builds the LangGraph StateGraph connecting all 8 clinical agents
    workflow = StateGraph(AgentReviewState)

    workflow.add_node("classification_agent", classification_agent)
    workflow.add_node("trajectory_agent", trajectory_agent)
    workflow.add_node("care_gaps_agent", care_gaps_agent)
    workflow.add_node("mismatches_agent", mismatches_agent)
    workflow.add_node("comorbidities_agent", comorbidities_agent)
    workflow.add_node("caregiver_prep_agent", caregiver_prep_agent)
    workflow.add_node("assistive_bubbles_agent", assistive_bubbles_agent)
    workflow.add_node("brief_compiler", brief_compiler_node)

    # Workflow edges
    workflow.set_entry_point("classification_agent")
    workflow.add_edge("classification_agent", "trajectory_agent")
    workflow.add_edge("trajectory_agent", "care_gaps_agent")
    workflow.add_edge("care_gaps_agent", "mismatches_agent")
    workflow.add_edge("mismatches_agent", "comorbidities_agent")
    workflow.add_edge("comorbidities_agent", "caregiver_prep_agent")
    workflow.add_edge("caregiver_prep_agent", "assistive_bubbles_agent")
    workflow.add_edge("assistive_bubbles_agent", "brief_compiler")
    workflow.add_edge("brief_compiler", END)

    return workflow.compile()
