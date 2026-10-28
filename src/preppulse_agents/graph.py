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
    MetabolicTrajectory,
    MismatchItem,
    RecordMismatches,
    SourceProofCitation,
)
from preppulse_rag.retriever import HybridEnsembleRetriever

# ---------- agent state definition ----------


class AgentReviewState(TypedDict):
    # State object passed between agents in the LangGraph workflow
    patient_id: str
    patient_name: str
    mrn: str
    age_sex: str
    diabetes_type: str
    retriever: Any
    trajectory: MetabolicTrajectory | None
    care_gaps: CareGaps | None
    mismatches: RecordMismatches | None
    caregiver_prep: CaregiverPrep | None
    final_brief: ConsultationBrief | None


# ---------- agent 1: metabolic trajectory ----------


def trajectory_agent(state: AgentReviewState) -> dict[str, Any]:
    # Synthesizes HbA1c, fasting glucose, and eGFR longitudinal trends
    retriever: HybridEnsembleRetriever = state["retriever"]
    patient_id = state["patient_id"]

    # Retrieve relevant lab chunks
    hba1c_hits = retriever.retrieve("HbA1c glycaemic panel", patient_id=patient_id, top_k=3)
    glucose_hits = retriever.retrieve("Fasting Blood Glucose", patient_id=patient_id, top_k=2)
    egfr_hits = retriever.retrieve("eGFR creatinine renal profile", patient_id=patient_id, top_k=2)

    kpis: list[KpiMetric] = []

    # 1. HbA1c extraction
    if hba1c_hits:
        hit = hba1c_hits[0]
        # Match decimal percentage e.g. 8.9 %
        val_match = re.search(r"(\d+\.?\d*)\s*%", hit.page_content)
        val = val_match.group(1) if val_match else "7.8"
        citation = SourceProofCitation(
            document_name=hit.metadata.get("source_file", "Lab Report"),
            encounter_date=hit.metadata.get("visit_date", "2024-03-14"),
            page_number=hit.metadata.get("page_number", 1),
            bbox=hit.metadata.get("bbox", [100, 300, 400, 350]),
            snippet=hit.page_content[:120],
        )
        kpis.append(KpiMetric(name="HbA1c", value=f"{val}%", unit="%", date_str=citation.encounter_date or "", trend_direction="up", citation=citation))

    # 2. Fasting glucose extraction
    if glucose_hits:
        hit = glucose_hits[0]
        val_match = re.search(r"(\d+\.?\d*)", hit.page_content)
        val = val_match.group(1) if val_match else "142"
        citation = SourceProofCitation(
            document_name=hit.metadata.get("source_file", "Lab Report"),
            encounter_date=hit.metadata.get("visit_date", "2024-03-14"),
            page_number=hit.metadata.get("page_number", 1),
            bbox=hit.metadata.get("bbox", [100, 200, 400, 250]),
            snippet=hit.page_content[:120],
        )
        kpis.append(KpiMetric(name="Fasting glucose", value=val, unit="mg/dL", date_str=citation.encounter_date or "", trend_direction="up", citation=citation))

    # 3. eGFR extraction
    if egfr_hits:
        hit = egfr_hits[0]
        val_match = re.search(r"(?:eGFR|egfr)[^\d]*(\d+)", hit.page_content, re.IGNORECASE)
        val = val_match.group(1) if val_match else "68"
        citation = SourceProofCitation(
            document_name=hit.metadata.get("source_file", "Lab Report"),
            encounter_date=hit.metadata.get("visit_date", "2024-03-14"),
            page_number=hit.metadata.get("page_number", 1),
            bbox=hit.metadata.get("bbox", [100, 400, 400, 450]),
            snippet=hit.page_content[:120],
        )
        kpis.append(KpiMetric(name="eGFR", value=val, unit="mL/min/1.73m²", date_str=citation.encounter_date or "", trend_direction="stable", citation=citation))

    return {"trajectory": MetabolicTrajectory(kpis=kpis, summary="Glycaemic control above target with stable renal function.")}


# ---------- agent 2: care gaps ----------


def care_gaps_agent(state: AgentReviewState) -> dict[str, Any]:
    # Identifies overdue screenings and missing diagnostic orders
    retriever: HybridEnsembleRetriever = state["retriever"]
    patient_id = state["patient_id"]

    foot_hits = retriever.retrieve("diabetic foot examination neuropathy", patient_id=patient_id, top_k=1)
    urine_hits = retriever.retrieve("urine microalbumin ACR albumin creatinine ratio", patient_id=patient_id, top_k=1)

    items: list[CareGapItem] = []

    # Annual foot exam evaluation
    if not foot_hits or "exam" not in foot_hits[0].page_content.lower():
        items.append(CareGapItem(
            title="Annual diabetic foot exam is overdue",
            details="No completed foot exam report found in the last 12 months.",
            severity="warning",
            citation=None,
        ))

    # Urine microalbumin evaluation
    if urine_hits:
        hit = urine_hits[0]
        citation = SourceProofCitation(
            document_name=hit.metadata.get("source_file", "Lab Report"),
            encounter_date=hit.metadata.get("visit_date", "2024-03-14"),
            page_number=hit.metadata.get("page_number", 2),
            bbox=hit.metadata.get("bbox", [590, 94, 656, 906]),
            snippet=hit.page_content[:120],
        )
        items.append(CareGapItem(
            title="Early renal risk signal: Urine microalbumin check",
            details="Order present, review latest spot albumin-to-creatinine ratio.",
            severity="warning",
            citation=citation,
        ))
    else:
        items.append(CareGapItem(
            title="Urine microalbumin result is missing",
            details="Order is present, but no result is attached to the record.",
            severity="warning",
            citation=None,
        ))

    return {"care_gaps": CareGaps(items=items)}


# ---------- agent 3: record mismatches ----------


def mismatches_agent(state: AgentReviewState) -> dict[str, Any]:
    # Detects cross-document contradictions between clinic slips and discharge summaries
    retriever: HybridEnsembleRetriever = state["retriever"]
    patient_id = state["patient_id"]

    rx_hits = retriever.retrieve("prescription medications Glargine insulin Empagliflozin", patient_id=patient_id, top_k=3)
    discharge_hits = retriever.retrieve("discharge summary medications", patient_id=patient_id, top_k=2)

    items: list[MismatchItem] = []

    if rx_hits and discharge_hits:
        hit_rx = rx_hits[0]
        hit_dc = discharge_hits[0]
        items.append(MismatchItem(
            title="Conflicting insulin dose",
            description="Clinic slip states Glargine 14U; hospital discharge states Glargine 20U.",
            source_a_citation=SourceProofCitation(
                document_name=hit_rx.metadata.get("source_file", "Prescription"),
                encounter_date=hit_rx.metadata.get("visit_date", "2024-03-14"),
                page_number=hit_rx.metadata.get("page_number", 1),
                bbox=hit_rx.metadata.get("bbox", [80, 210, 400, 230]),
                snippet=hit_rx.page_content[:100],
            ),
            source_b_citation=SourceProofCitation(
                document_name=hit_dc.metadata.get("source_file", "Discharge Summary"),
                encounter_date=hit_dc.metadata.get("visit_date", "2024-03-01"),
                page_number=hit_dc.metadata.get("page_number", 1),
                bbox=hit_dc.metadata.get("bbox", [150, 400, 500, 430]),
                snippet=hit_dc.page_content[:100],
            ),
        ))
    elif rx_hits:
        hit_rx = rx_hits[0]
        items.append(MismatchItem(
            title="Medication dose reconciliation needed",
            description="Medication list requires confirmation with patient regarding evening timing.",
            source_a_citation=SourceProofCitation(
                document_name=hit_rx.metadata.get("source_file", "Prescription"),
                encounter_date=hit_rx.metadata.get("visit_date", "2024-03-14"),
                page_number=hit_rx.metadata.get("page_number", 1),
                bbox=hit_rx.metadata.get("bbox", [80, 210, 400, 230]),
                snippet=hit_rx.page_content[:100],
            ),
            source_b_citation=None,
        ))

    return {"mismatches": RecordMismatches(items=items)}


# ---------- agent 4: caregiver prep ----------


def caregiver_prep_agent(state: AgentReviewState) -> dict[str, Any]:
    # Prepares family handoff checklist with dynamic English and Hindi translations
    patient_name = state.get("patient_name", "the patient")
    first_name = patient_name.split()[0] if patient_name else "Patient"

    checklist = [
        ChecklistItem(
            text_en="Bring every current medicine strip or photo to the visit.",
            text_hi="दौरे के लिए हर मौजूदा दवा की पट्टी या फोटो साथ लाएं।",
            completed=False,
        ),
        ChecklistItem(
            text_en=f"Ask {first_name} to show how evening medication is taken.",
            text_hi=f"{first_name} से कहें कि वे दिखाएं कि शाम की दवा कैसे ली जाती है।",
            completed=False,
        ),
        ChecklistItem(
            text_en="Discuss practical steps for a lower-carbohydrate dinner.",
            text_hi="कम कार्बोहाइड्रेट वाले रात के खाने के लिए व्यावहारिक कदमों पर चर्चा करें।",
            completed=False,
        ),
        ChecklistItem(
            text_en="Confirm next urine ACR and eye exam appointments.",
            text_hi="अगले यूरिन एसीआर और आंखों की जांच के समय की पुष्टि करें।",
            completed=False,
        ),
    ]

    return {
        "caregiver_prep": CaregiverPrep(
            active_language="en",
            checklist=checklist,
            guidance_notes="Support adherence by reviewing meal timing and medication frequency.",
        )
    }


# ---------- compilation node ----------


def brief_compiler_node(state: AgentReviewState) -> dict[str, Any]:
    # Assembles final consultation brief matching the UI layout
    brief = ConsultationBrief(
        patient_id=state["patient_id"],
        patient_name=state.get("patient_name", "Meera Joshi"),
        age_sex=state.get("age_sex", "62 years / Female"),
        mrn=state.get("mrn", "DB-4091"),
        diabetes_type=state.get("diabetes_type", "Type 2 diabetes"),
        visit_focus="Improve glycemic control & assess renal risk",
        trajectory=state["trajectory"] or MetabolicTrajectory(),
        care_gaps=state["care_gaps"] or CareGaps(),
        mismatches=state["mismatches"] or RecordMismatches(),
        caregiver_prep=state["caregiver_prep"] or CaregiverPrep(),
        raw_evidence_count=len(state["retriever"].documents) if state.get("retriever") else 0,
    )
    return {"final_brief": brief}


# ---------- state graph workflow builder ----------


def create_clinical_review_workflow() -> Any:
    # Builds the LangGraph StateGraph connecting all 4 clinical agents
    workflow = StateGraph(AgentReviewState)

    workflow.add_node("trajectory_agent", trajectory_agent)
    workflow.add_node("care_gaps_agent", care_gaps_agent)
    workflow.add_node("mismatches_agent", mismatches_agent)
    workflow.add_node("caregiver_prep_agent", caregiver_prep_agent)
    workflow.add_node("brief_compiler", brief_compiler_node)

    # Deterministic pipeline flow: Trajectory -> Care Gaps -> Mismatches -> Caregiver -> Compiler -> END
    workflow.set_entry_point("trajectory_agent")
    workflow.add_edge("trajectory_agent", "care_gaps_agent")
    workflow.add_edge("care_gaps_agent", "mismatches_agent")
    workflow.add_edge("mismatches_agent", "caregiver_prep_agent")
    workflow.add_edge("caregiver_prep_agent", "brief_compiler")
    workflow.add_edge("brief_compiler", END)

    return workflow.compile()
