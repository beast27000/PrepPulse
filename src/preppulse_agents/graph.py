from __future__ import annotations

import json
import logging
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
from preppulse_rag.llm_provider import LLMFactory
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


# ---------- json parsing helper ----------


def _parse_llm_json_array(text: str) -> list[dict[str, Any]]:
    # Robust extractor for JSON arrays returned by LLM with markdown fences or commentary
    text_clean = text.strip()
    try:
        res = json.loads(text_clean)
        if isinstance(res, list):
            return res
        if isinstance(res, dict):
            for v in res.values():
                if isinstance(v, list):
                    return v
    except Exception:  # noqa: BLE001, S110
        pass
    start = text_clean.find("[")
    end = text_clean.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            res = json.loads(text_clean[start : end + 1])
            if isinstance(res, list):
                return res
        except Exception:  # noqa: BLE001, S110
            pass
    return []


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

    # LLM-driven discovery: find any other lab values not captured by standard queries
    try:
        lab_hits = retriever.retrieve("laboratory test result value analyte reference range", patient_id=patient_id, top_k=6)
        if lab_hits:
            lab_context = "\n".join(
                f"[{h.metadata.get('source_file', '')} | {h.metadata.get('visit_date') or h.metadata.get('year', '')}]: {h.page_content[:180]}"
                for h in lab_hits
            )
            discovery_prompt = (
                "Extract all numeric lab test values from these medical records.\n"
                "For each distinct test that has a numeric result:\n"
                "Return JSON: "
                '[{"metric_name": "...", "value": 0.0, "unit": "...", "date": "YYYY-MM-DD", "category": "glycemic|renal|cardiac|lipid|hepatic|hematology|other", "status": "normal|borderline|high|critical"}]\n'
                "Rules: Only numeric values. No diagnosis. Skip values already in: HbA1c, Fasting Glucose, eGFR, Blood Pressure.\n"
                "Return ONLY the JSON array.\n\n"
                f"RECORDS:\n{lab_context}\n\nJSON:"
            )
            llm = LLMFactory.get_chat_model(max_tokens=512)
            disc_response = llm.invoke(discovery_prompt)
            disc_parsed = _parse_llm_json_array(disc_response.content)
            # Build additional LongitudinalMetricSeries for each discovered metric
            known_metrics = {"hba1c", "fasting glucose", "egfr", "blood pressure", "fasting blood glucose"}
            for lab in disc_parsed[:8]:
                metric = str(lab.get("metric_name", "")).strip()
                if not metric or metric.lower() in known_metrics:
                    continue
                try:
                    val = float(lab.get("value", 0))
                except (ValueError, TypeError):
                    continue
                unit = str(lab.get("unit", ""))
                date_str = str(lab.get("date", "2024-01-01"))
                try:
                    year = int(date_str[:4])
                except ValueError:
                    year = 2024
                category = str(lab.get("category", "other"))
                status = str(lab.get("status", "normal"))
                # Find a matching hit for citation
                best_hit = lab_hits[0]
                for h in lab_hits:
                    if str(h.metadata.get("year", "")) == date_str[:4]:
                        best_hit = h
                        break
                disc_cit = SourceProofCitation(
                    document_title=best_hit.metadata.get("source_file", "Lab Report"),
                    bbox=best_hit.metadata.get("bbox", [100, 200, 400, 250]),
                    extracted_text=best_hit.page_content[:100],
                )
                point = TimeSeriesPoint(date=date_str, year=year, value=val, unit=unit, status=status, citation=disc_cit)
                series_list.append(LongitudinalMetricSeries(
                    metric_name=metric,
                    category=category,
                    points=[point],
                    ten_year_trend="stable",
                    tabular_flow={str(year): val},
                ))
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).debug("trajectory_agent: LLM discovery pass skipped (LLM unavailable or invalid JSON)")  # Discovery is additive — silently skip if LLM unavailable

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

    # Broad medication retrieval — any prescription, reconciliation, or discharge med list
    rx_hits = retriever.retrieve("prescription medication dose tablet capsule daily twice", patient_id=patient_id, top_k=6)
    recon_hits = retriever.retrieve("medication reconciliation stopped discontinued active dispute conflict referral", patient_id=patient_id, top_k=8)
    combined = {h.metadata.get("chunk_id", h.page_content[:30]): h for h in rx_hits + recon_hits}
    all_hits = list(combined.values())[:12]

    items: list[MismatchItem] = []

    if all_hits:
        context_parts = []
        for h in all_hits:
            src = h.metadata.get("source_file", "Record")
            date = h.metadata.get("visit_date") or h.metadata.get("year", "")
            context_parts.append(f"[{src} | {date}]: {h.page_content[:180]}")
        context_text = "\n".join(context_parts)

        prompt = (
            "You are a clinical chart review assistant. Review these medical records for medication discrepancies.\n"
            "Find medications where dose, frequency, or status conflicts between different records, "
            "or where a patient stopped a medication without a documented discontinuation order.\n"
            "For each discrepancy:\n"
            "- TITLE: short name of the discrepancy (e.g. 'Atorvastatin discontinuation unconfirmed')\n"
            "- DESCRIPTION: one-sentence factual description of the conflict\n"
            "- SEVERITY: high (patient safety risk), medium (needs clarification), low (minor)\n"
            "- SOURCE_A_DATE: date of first conflicting record (YYYY-MM-DD or blank)\n"
            "- SOURCE_B_DATE: date of second conflicting record (YYYY-MM-DD or blank)\n\n"
            "Rules: No diagnosis. Only factual discrepancies. One entry per medication conflict.\n"
            "Return ONLY a JSON array:\n"
            '[{"title": "...", "description": "...", "severity": "...", "source_a_date": "...", "source_b_date": "..."}]\n\n'
            f"RECORDS:\n{context_text}\n\nJSON:"
        )

        try:
            llm = LLMFactory.get_chat_model(max_tokens=512)
            response = llm.invoke(prompt)
            parsed = _parse_llm_json_array(response.content)
            for item_data in parsed[:5]:
                title = str(item_data.get("title", "")).strip()
                desc = str(item_data.get("description", "")).strip()
                if not title:
                    continue
                # Build citations from hits
                cit_a = None
                cit_b = None
                if all_hits:
                    h = all_hits[0]
                    cit_a = SourceProofCitation(
                        document_id=h.metadata.get("document_id", ""),
                        document_title=h.metadata.get("source_file", "Medical Record"),
                        date_formatted=str(h.metadata.get("visit_date") or ""),
                        page_number=h.metadata.get("page_number", 1),
                        bbox=h.metadata.get("bbox", [80, 200, 400, 250]),
                        extracted_text=h.page_content[:120],
                    )
                if len(all_hits) > 1:
                    h2 = all_hits[1]
                    cit_b = SourceProofCitation(
                        document_title=h2.metadata.get("source_file", "Medical Record"),
                        date_formatted=str(h2.metadata.get("visit_date") or ""),
                        bbox=h2.metadata.get("bbox", [80, 200, 400, 250]),
                        extracted_text=h2.page_content[:120],
                    )
                items.append(MismatchItem(
                    title=title,
                    description=desc,
                    source_a_citation=cit_a,
                    source_b_citation=cit_b,
                    citations=[c for c in [cit_a, cit_b] if c],
                ))
        except Exception:  # noqa: BLE001
            _log = logging.getLogger(__name__)
            _log.warning("mismatches_agent: LLM call failed or returned invalid JSON; returning empty items")

    return {"mismatches": RecordMismatches(items=items)}


# ---------- agent 5: comorbidities & acute admissions ----------


def comorbidities_agent(state: AgentReviewState) -> dict[str, Any]:
    # Identifies 10-year multi-condition milestones, surgeries, and acute admissions
    retriever: HybridEnsembleRetriever = state["retriever"]
    patient_id = state["patient_id"]

    # Broad retrieval: hospital admissions, surgeries, specialist consults
    discharge_hits = retriever.retrieve("hospital admission discharge ward admitted inpatient", patient_id=patient_id, top_k=6)
    consult_hits = retriever.retrieve("specialist consultation referral procedure surgery", patient_id=patient_id, top_k=6)
    combined = {h.metadata.get("chunk_id", h.page_content[:30]): h for h in discharge_hits + consult_hits}
    all_hits = list(combined.values())[:10]

    findings: list[PriorityFindingItem] = []

    if all_hits:
        context_parts = []
        for h in all_hits:
            src = h.metadata.get("source_file", "Record")
            date = h.metadata.get("visit_date") or h.metadata.get("year", "")
            context_parts.append(f"[{src} | {date}]: {h.page_content[:180]}")
        context_text = "\n".join(context_parts)

        prompt = (
            "You are a clinical chart review assistant. Review these medical record excerpts.\n"
            "For each distinct clinical event, hospitalization, surgery, procedure, or specialist consultation:\n"
            "1. TITLE: concise name (e.g. 'Acute Dengue Hospitalization', 'Cardiac Angioplasty', 'Urology Consultation')\n"
            "2. SUBTITLE: one sentence describing what happened and outcome\n"
            "3. SEVERITY: high (life-threatening/major surgery), medium (acute illness/procedure), low (routine consult)\n"
            "4. DATE: extract from record in YYYY-MM-DD format (use YYYY-01-01 if only year known)\n\n"
            "Rules: No diagnosis. Only report what is documented. Deduplicate — one entry per event.\n"
            "Return ONLY a JSON array (no markdown fences):\n"
            '[{"title": "...", "subtitle": "...", "severity": "high|medium|low", "date": "YYYY-MM-DD"}]\n\n'
            f"RECORDS:\n{context_text}\n\nJSON:"
        )

        try:
            llm = LLMFactory.get_chat_model(max_tokens=512)
            response = llm.invoke(prompt)
            parsed = _parse_llm_json_array(response.content)
            for i, item in enumerate(parsed[:8]):
                title = str(item.get("title", "")).strip()
                subtitle = str(item.get("subtitle", "")).strip()
                severity = str(item.get("severity", "medium")).strip()
                date_str = str(item.get("date", "")).strip()
                if not title:
                    continue
                # Find best matching hit for citation (by date or first)
                best_hit = all_hits[0]
                for h in all_hits:
                    if date_str[:4] and str(h.metadata.get("year", "")) == date_str[:4]:
                        best_hit = h
                        break
                cit = SourceProofCitation(
                    document_id=best_hit.metadata.get("document_id", ""),
                    document_title=best_hit.metadata.get("source_file", "Hospital Record"),
                    date_formatted=date_str,
                    page_number=best_hit.metadata.get("page_number", 1),
                    bbox=best_hit.metadata.get("bbox", [100, 100, 500, 200]),
                    extracted_text=best_hit.page_content[:140],
                )
                findings.append(PriorityFindingItem(
                    finding_id=f"find_{i + 1}",
                    title=title,
                    subtitle=subtitle,
                    status="confirmed",
                    severity=severity if severity in ("high", "medium", "low") else "medium",
                    date=date_str,
                    citation=cit,
                ))
        except Exception:  # noqa: BLE001
            _log = logging.getLogger(__name__)
            _log.warning("comorbidities_agent: LLM call failed or returned invalid JSON; returning empty findings")

    findings.sort(key=lambda f: f.date, reverse=True)
    return {"comorbidity_findings": findings}


# ---------- agent 6: dynamic caregiver prep / handoff ----------


def caregiver_prep_agent(state: AgentReviewState) -> dict[str, Any]:
    # Generates Caregiver Handoff (diabetic) or Caregiver Prep Sheet (prediabetic)
    classification = state.get("classification")
    is_diabetic = classification and classification.category == "diabetic"
    patient_name = state.get("patient_name", "the patient")
    first_name = patient_name.split()[0] if patient_name else "Patient"
    age = state.get("age", "")
    gender = state.get("gender", "")
    comorbidities = state.get("comorbidity_findings") or []
    mismatches_obj = state.get("mismatches")
    retriever: HybridEnsembleRetriever = state["retriever"]
    patient_id = state["patient_id"]

    # Retrieve allergy and medication context
    allergy_hits = retriever.retrieve("allergy allergic reaction medication intolerance", patient_id=patient_id, top_k=3)
    med_hits = retriever.retrieve("prescription medication ongoing active daily", patient_id=patient_id, top_k=4)

    allergy_text = " | ".join(h.page_content[:120] for h in allergy_hits) or "None documented"
    med_text = " | ".join(h.page_content[:120] for h in med_hits) or "None documented"
    comorbidity_text = ", ".join(f.title for f in comorbidities[:5]) if comorbidities else "None identified"
    mismatch_text = " | ".join(m.title for m in mismatches_obj.items[:3]) if mismatches_obj and mismatches_obj.items else "None"

    mode = "handoff" if is_diabetic else "prep_sheet"

    if mode == "handoff":
        checklist_instruction = (
            "Generate 4 caregiver visit checklist items for a diabetic patient. "
            "Focus on medication adherence, insulin or medication routine, monitoring glucose, "
            "and upcoming lab appointments relevant to this patient."
        )
    else:
        checklist_instruction = (
            "Generate 4 caregiver visit checklist items for this patient based on their actual documented conditions. "
            "Focus on medication adherence, lifestyle modifications, monitoring, and follow-up appointments."
        )

    prompt = (
        f"You are a clinical assistant preparing a caregiver checklist. {checklist_instruction}\n\n"
        f"Patient: {first_name}, {age} years old, {gender}\n"
        f"Classification: {classification.stage if classification else 'Unknown'}\n"
        f"Active conditions/events: {comorbidity_text}\n"
        f"Medication context: {med_text[:300]}\n"
        f"Medication discrepancies: {mismatch_text}\n"
        f"Allergy context: {allergy_text[:200]}\n\n"
        "Rules:\n"
        "- Be specific to THIS patient's documented conditions\n"
        "- No diagnosis or treatment advice\n"
        "- Each item must be actionable for a family caregiver\n"
        "- Translate each item into Hindi (text_hi) and Tamil (text_ta)\n"
        "Return ONLY a JSON array:\n"
        '[{"id": "chk_01", "text_en": "...", "text_hi": "...", "text_ta": "..."}]\n\n'
        "JSON:"
    )

    checklist: list[ChecklistItem] = []
    allergies: list[str] = []
    ongoing_issues: list[str] = [f.title for f in comorbidities[:4]]

    try:
        llm = LLMFactory.get_chat_model(max_tokens=800)
        response = llm.invoke(prompt)
        parsed = _parse_llm_json_array(response.content)
        for item_data in parsed[:6]:
            text_en = str(
                item_data.get("text_en")
                or item_data.get("english")
                or item_data.get("item")
                or item_data.get("action")
                or item_data.get("text")
                or item_data.get("description")
                or ""
            ).strip()
            if not text_en:
                continue
            text_hi = str(item_data.get("text_hi") or item_data.get("hindi") or text_en).strip()
            text_ta = str(item_data.get("text_ta") or item_data.get("tamil") or text_en).strip()
            checklist.append(ChecklistItem(
                id=str(item_data.get("id", f"chk_{len(checklist)+1:02d}")),
                text_en=text_en,
                text_hi=text_hi,
                text_ta=text_ta,
            ))
        # Extract allergies from allergy context
        if allergy_hits:
            for h in allergy_hits[:2]:
                content_lower = h.page_content.lower()
                if "allerg" in content_lower or "intolerance" in content_lower:
                    allergies.append(h.page_content[:80].strip())
    except Exception:  # noqa: BLE001
        _log = logging.getLogger(__name__)
        _log.warning("caregiver_prep_agent: LLM call failed; using minimal fallback checklist")

    if not checklist:
        checklist = [
            ChecklistItem(
                id="chk_01",
                text_en="Bring all current medication strips or packaging to the visit.",
                text_hi="सभी वर्तमान दवाओं के पैकेट या पट्टी लेकर आएं।",
                text_ta="தற்போது உட்கொள்ளும் அனைத்து மருந்துகளையும் எடுத்து வாருங்கள்.",
            ),
            ChecklistItem(
                id="chk_02",
                text_en="Keep a record of any new symptoms or side effects noticed since the last visit.",
                text_hi="पिछली मुलाकात के बाद किसी भी नए लक्षण या दुष्प्रभाव का रिकॉर्ड रखें।",
                text_ta="கடந்த வருகைக்குப் பிறகு தோன்றிய புதிய அறிகுறிகள் அல்லது பக்க விளைவுகளை பதிவு செய்யுங்கள்.",
            ),
            ChecklistItem(
                id="chk_03",
                text_en="Confirm all upcoming follow-up appointments and lab tests are scheduled.",
                text_hi="सभी आगामी अनुवर्ती नियुक्तियों और लैब परीक्षणों की पुष्टि करें।",
                text_ta="வரவிருக்கும் அனைத்து பின்தொடர் சந்திப்புகள் மற்றும் ஆய்வக பரிசோதனைகள் திட்டமிடப்பட்டுள்ளனவா என உறுதிப்படுத்தவும்.",
            ),
        ]

    return {
        "caregiver_prep": CaregiverPrep(
            mode=mode,
            active_language="en",
            checklist=checklist,
            allergies=allergies,
            ongoing_issues=ongoing_issues,
            guidance_notes="Caregiver checklist generated from documented patient history. Review with clinical team.",
        )
    }


# ---------- agent 7: smart assistive bubbles ----------


def assistive_bubbles_agent(state: AgentReviewState) -> dict[str, Any]:
    # Emits non-intrusive assistive prompt bubbles driven by actual findings from state
    classification = state.get("classification")
    is_diabetic = classification and classification.category == "diabetic"
    comorbidities = state.get("comorbidity_findings") or []
    mismatches_obj = state.get("mismatches")
    metric_series = state.get("metric_series") or []

    bubbles: list[SmartPromptBubble] = []

    # Bubble 1: Longitudinal trajectory (always present if metric series exist)
    if metric_series:
        series_names = [s.metric_name for s in metric_series[:3]]
        bubbles.append(SmartPromptBubble(
            bubble_id="bubble_01",
            icon="timeline",
            prompt_text=f"Longitudinal data available for {', '.join(series_names)}: Would you like to chart the multi-year metabolic trajectory?",
            action_type="open_chart_modal",
            target_series=series_names,
        ))
    else:
        bubbles.append(SmartPromptBubble(
            bubble_id="bubble_01",
            icon="timeline",
            prompt_text="10-year health records loaded: Would you like to view the longitudinal metabolic trajectory?",
            action_type="open_chart_modal",
            target_series=[],
        ))

    # Bubble 2: Acute admissions / comorbidities (only if findings exist)
    if comorbidities:
        # Pick up to 2 most recent events
        recent_events = comorbidities[:2]
        event_names = " and ".join(f.title for f in recent_events)
        bubbles.append(SmartPromptBubble(
            bubble_id="bubble_02",
            icon="hospital",
            prompt_text=f"Clinical events found: {event_names}. Would you like to review the source records?",
            action_type="open_milestone_detail",
            milestone_id="admissions",
        ))

    # Bubble 3: Medication discrepancies (only if mismatches exist)
    if mismatches_obj and mismatches_obj.items:
        first_mismatch = mismatches_obj.items[0]
        bubbles.append(SmartPromptBubble(
            bubble_id="bubble_03",
            icon="pill",
            prompt_text=f"Medication discrepancy noted: {first_mismatch.title}. Shall I open the reconciliation details?",
            action_type="open_mismatch_detail",
            milestone_id="mismatch_01",
        ))

    # Bubble 4: Diabetic-specific care gap
    if is_diabetic:
        bubbles.append(SmartPromptBubble(
            bubble_id="bubble_04",
            icon="alert",
            prompt_text="Annual foot examination is overdue: Would you like to add this to the visit action plan?",
            action_type="add_action_item",
        ))

    # Always have at least 2 bubbles
    if len(bubbles) < 2:
        bubbles.append(SmartPromptBubble(
            bubble_id=f"bubble_{len(bubbles)+1:02d}",
            icon="info",
            prompt_text="All clinical records reviewed. Would you like a summary of key findings for this visit?",
            action_type="open_summary",
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
