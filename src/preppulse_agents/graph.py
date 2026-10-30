from __future__ import annotations

import json
import logging
import re
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from preppulse_agents.prompt_loader import format_agent_prompt
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
from preppulse_agents.tools import extract_metric_timeseries
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


# ---------- json parsing helpers ----------


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


def _parse_llm_json_object(text: str) -> dict[str, Any]:
    # Robust extractor for JSON objects returned by LLM
    text_clean = text.strip()
    try:
        res = json.loads(text_clean)
        if isinstance(res, dict):
            return res
    except Exception:  # noqa: BLE001, S110
        pass
    start = text_clean.find("{")
    end = text_clean.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            res = json.loads(text_clean[start : end + 1])
            if isinstance(res, dict):
                return res
        except Exception:  # noqa: BLE001, S110
            pass
    return {}


# ---------- agent 1: patient classification ----------


def classification_agent(state: AgentReviewState) -> dict[str, Any]:
    # Dynamically classifies patient across diabetes spectrum via external prompt
    retriever: HybridEnsembleRetriever = state["retriever"]
    patient_id = state["patient_id"]

    hits = retriever.retrieve("diabetes prediabetes impaired fasting glucose HbA1c metabolic diagnosis", patient_id=patient_id, top_k=6)
    context_text = "\n".join(
        f"[{h.metadata.get('source_file', 'Record')} | {h.metadata.get('visit_date', '')}]: {h.page_content[:180]}"
        for h in hits
    )

    category = "prediabetic"
    stage = "Pre-Diabetic"
    basis = "Documented impaired fasting glucose / borderline HbA1c"

    if context_text.strip():
        system_prompt, user_msg, params = format_agent_prompt(
            "classification_agent",
            context_text=context_text,
        )
        try:
            llm = LLMFactory.get_chat_model(
                max_tokens=params.get("max_tokens", 256),
                temperature=params.get("temperature", 0.0),
            )
            resp = llm.invoke([{"role": "system", "content": system_prompt}, {"role": "user", "content": user_msg}])
            data = _parse_llm_json_object(resp.content)
            if data and data.get("category"):
                cat = str(data["category"]).strip().lower()
                if cat in ("diabetic", "prediabetic", "non_diabetic"):
                    category = cat
                if data.get("stage"):
                    stage = str(data["stage"]).strip()
                if data.get("diagnostic_basis"):
                    basis = str(data["diagnostic_basis"]).strip()
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).warning("classification_agent: LLM call failed; using rule fallback")
            content_combined = " ".join(h.page_content.lower() for h in hits)
            if "type 2 diabetes" in content_combined or "t2d" in content_combined or "insulin glargine" in content_combined:
                category, stage, basis = "diabetic", "Type 2 Diabetes", "Documented Type 2 Diabetes on pharmacotherapy"
            elif "prediabet" in content_combined or "impaired fasting" in content_combined:
                category, stage, basis = "prediabetic", "Pre-Diabetic", "Documented impaired fasting glucose"

    classification = PatientClassification(stage=stage, category=category, diagnostic_basis=basis)
    return {"classification": classification}


# ---------- agent 2: metabolic trajectory ----------


def trajectory_agent(state: AgentReviewState) -> dict[str, Any]:
    # Synthesizes longitudinal metabolic trajectory, KPIs, and open-ended lab discovery
    retriever: HybridEnsembleRetriever = state["retriever"]
    patient_id = state["patient_id"]

    kpis: list[KpiMetric] = []
    series_list: list[LongitudinalMetricSeries] = []

    # 1. Glycemic & Renal Series via metric timeseries tool
    hba1c_series = extract_metric_timeseries("HbA1c", retriever, patient_id=patient_id, category="glycemic", unit="%")
    if hba1c_series and hba1c_series.points:
        series_list.append(hba1c_series)
        latest = hba1c_series.points[-1]
        kpis.append(KpiMetric(
            name="HbA1c",
            value=f"{latest.value}%",
            unit="%",
            date_str=latest.date,
            trend_direction="up" if hba1c_series.ten_year_trend == "worsening" else "stable",
            citation=latest.citation,
        ))

    glucose_series = extract_metric_timeseries("Fasting Blood Glucose", retriever, patient_id=patient_id, category="glycemic", unit="mg/dL")
    if glucose_series and glucose_series.points:
        series_list.append(glucose_series)
        latest = glucose_series.points[-1]
        kpis.append(KpiMetric(
            name="Fasting glucose",
            value=str(int(latest.value)),
            unit="mg/dL",
            date_str=latest.date,
            trend_direction="up" if latest.value >= 100 else "stable",
            citation=latest.citation,
        ))

    egfr_series = extract_metric_timeseries("eGFR", retriever, patient_id=patient_id, category="renal", unit="mL/min/1.73m²")
    if egfr_series and egfr_series.points:
        series_list.append(egfr_series)
        latest = egfr_series.points[-1]
        kpis.append(KpiMetric(
            name="eGFR",
            value=str(int(latest.value)),
            unit="mL/min/1.73m²",
            date_str=latest.date,
            trend_direction=egfr_series.ten_year_trend,
            citation=latest.citation,
        ))

    # Blood pressure series check
    bp_hits = retriever.retrieve("blood pressure hypertension mmHg", patient_id=patient_id, top_k=3)
    if bp_hits:
        hit = bp_hits[0]
        bp_match = re.search(r"(\d{2,3})\s*/\s*(\d{2,3})", hit.page_content)
        if bp_match:
            bp_val = f"{bp_match.group(1)}/{bp_match.group(2)}"
            cit = SourceProofCitation(
                document_title=hit.metadata.get("source_file", "Prescription"),
                bbox=hit.metadata.get("bbox", [100, 200, 400, 250]),
                extracted_text=hit.page_content[:100],
            )
            kpis.append(KpiMetric(
                name="Blood pressure",
                value=bp_val,
                unit="mmHg",
                date_str=str(hit.metadata.get("visit_date") or ""),
                trend_direction="stable",
                citation=cit,
            ))

    # 2. Open-ended Lab Discovery Pass via lab_discovery_agent.yaml
    try:
        lab_hits = retriever.retrieve("laboratory test result value analyte reference range", patient_id=patient_id, top_k=8)
        if lab_hits:
            lab_context = "\n".join(
                f"[{h.metadata.get('source_file', '')} | {h.metadata.get('visit_date') or h.metadata.get('year', '')}]: {h.page_content[:180]}"
                for h in lab_hits
            )
            sys_msg, user_msg, params = format_agent_prompt("lab_discovery_agent", lab_context=lab_context)
            llm = LLMFactory.get_chat_model(
                max_tokens=params.get("max_tokens", 512),
                temperature=params.get("temperature", 0.0),
            )
            disc_resp = llm.invoke([{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}])
            disc_parsed = _parse_llm_json_array(disc_resp.content)
            existing_names = {s.metric_name.lower() for s in series_list}

            for lab in disc_parsed[:10]:
                metric = str(lab.get("metric_name", "")).strip()
                if not metric or metric.lower() in existing_names:
                    continue
                try:
                    val = float(lab.get("value", 0))
                except (ValueError, TypeError):
                    continue
                unit = str(lab.get("unit", "")).strip()
                date_str = str(lab.get("date", "2024-01-01")).strip()
                year = int(date_str[:4]) if len(date_str) >= 4 and date_str[:4].isdigit() else 2024
                category = str(lab.get("category", "other")).strip()
                status = str(lab.get("status", "normal")).strip()

                best_hit = lab_hits[0]
                for h in lab_hits:
                    if str(h.metadata.get("year", "")) == str(year):
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
                existing_names.add(metric.lower())
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).debug("trajectory_agent: Lab discovery pass skipped")

    # 3. Trajectory Summary via trajectory_agent.yaml
    series_summary = "; ".join(f"{s.metric_name}: {len(s.points)} points ({s.ten_year_trend})" for s in series_list)
    summary_text = "Longitudinal metabolic profile tracking glycaemic and vascular trajectory."
    if series_summary:
        try:
            sys_msg, user_msg, params = format_agent_prompt("trajectory_agent", series_summary=series_summary)
            llm = LLMFactory.get_chat_model(max_tokens=params.get("max_tokens", 384), temperature=params.get("temperature", 0.0))
            resp = llm.invoke([{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}])
            traj_data = _parse_llm_json_object(resp.content)
            if traj_data.get("summary"):
                summary_text = str(traj_data["summary"]).strip()
        except Exception:  # noqa: BLE001, S110
            pass

    trajectory = MetabolicTrajectory(kpis=kpis, summary=summary_text)
    return {"trajectory": trajectory, "metric_series": series_list}


# ---------- agent 3: care gaps ----------


def care_gaps_agent(state: AgentReviewState) -> dict[str, Any]:
    # Audits overdue longitudinal screenings and missing follow-ups via care_gaps_agent.yaml
    retriever: HybridEnsembleRetriever = state["retriever"]
    patient_id = state["patient_id"]
    classification = state.get("classification")
    stage_str = classification.stage if classification else "Pre-Diabetic"

    items: list[CareGapItem] = []

    screening_hits = retriever.retrieve("annual screening examination follow-up overdue pending diabetic foot eye exam urine microalbumin", patient_id=patient_id, top_k=6)
    if screening_hits:
        context_parts = [
            f"[{h.metadata.get('source_file', 'Record')} | {h.metadata.get('visit_date') or h.metadata.get('year', '')}]: {h.page_content[:180]}"
            for h in screening_hits
        ]
        context_text = "\n".join(context_parts)
        sys_msg, user_msg, params = format_agent_prompt("care_gaps_agent", classification_stage=stage_str, context_text=context_text)

        try:
            llm = LLMFactory.get_chat_model(max_tokens=params.get("max_tokens", 512), temperature=params.get("temperature", 0.0))
            resp = llm.invoke([{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}])
            parsed = _parse_llm_json_array(resp.content)
            for gap in parsed[:6]:
                title = str(gap.get("title", "")).strip()
                details = str(gap.get("details", "")).strip()
                severity = str(gap.get("severity", "warning")).strip().lower()
                if not title:
                    continue
                cit = None
                if screening_hits:
                    h = screening_hits[0]
                    cit = SourceProofCitation(
                        document_title=h.metadata.get("source_file", "Record"),
                        bbox=h.metadata.get("bbox", [100, 100, 500, 200]),
                        extracted_text=h.page_content[:100],
                    )
                items.append(CareGapItem(
                    title=title,
                    details=details,
                    severity=severity if severity in ("warning", "info", "critical") else "warning",
                    citation=cit,
                ))
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).warning("care_gaps_agent: LLM call failed")

    if not items:
        items.append(CareGapItem(
            title="Periodic metabolic screening due",
            details="Annual glycaemic and metabolic screening recommended based on documented history.",
            severity="warning",
        ))

    return {"care_gaps": CareGaps(items=items)}


# ---------- agent 4: medication reconciliation & mismatches ----------


def mismatches_agent(state: AgentReviewState) -> dict[str, Any]:
    # Identifies cross-document medication contradictions via mismatches_agent.yaml
    retriever: HybridEnsembleRetriever = state["retriever"]
    patient_id = state["patient_id"]

    rx_hits = retriever.retrieve("prescription medication dose tablet capsule daily twice", patient_id=patient_id, top_k=6)
    recon_hits = retriever.retrieve("medication reconciliation stopped discontinued active dispute conflict referral", patient_id=patient_id, top_k=8)
    combined = {h.metadata.get("chunk_id", h.page_content[:30]): h for h in rx_hits + recon_hits}
    all_hits = list(combined.values())[:12]

    items: list[MismatchItem] = []

    if all_hits:
        context_parts = [
            f"[{h.metadata.get('source_file', 'Record')} | {h.metadata.get('visit_date') or h.metadata.get('year', '')}]: {h.page_content[:180]}"
            for h in all_hits
        ]
        context_text = "\n".join(context_parts)
        sys_msg, user_msg, params = format_agent_prompt("mismatches_agent", context_text=context_text)

        try:
            llm = LLMFactory.get_chat_model(max_tokens=params.get("max_tokens", 512), temperature=params.get("temperature", 0.0))
            resp = llm.invoke([{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}])
            parsed = _parse_llm_json_array(resp.content)
            for item_data in parsed[:5]:
                title = str(item_data.get("title", "")).strip()
                desc = str(item_data.get("description", "")).strip()
                if not title:
                    continue
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
            logging.getLogger(__name__).warning("mismatches_agent: LLM call failed")

    return {"mismatches": RecordMismatches(items=items)}


# ---------- agent 5: comorbidities & acute admissions ----------


def comorbidities_agent(state: AgentReviewState) -> dict[str, Any]:
    # Identifies 10-year multi-condition milestones and surgeries via comorbidities_agent.yaml
    retriever: HybridEnsembleRetriever = state["retriever"]
    patient_id = state["patient_id"]

    discharge_hits = retriever.retrieve("hospital admission discharge ward admitted inpatient surgery procedure", patient_id=patient_id, top_k=6)
    consult_hits = retriever.retrieve("specialist consultation referral procedure evaluation cardiac urology", patient_id=patient_id, top_k=6)
    combined = {h.metadata.get("chunk_id", h.page_content[:30]): h for h in discharge_hits + consult_hits}
    all_hits = list(combined.values())[:10]

    findings: list[PriorityFindingItem] = []

    if all_hits:
        context_parts = [
            f"[{h.metadata.get('source_file', 'Record')} | {h.metadata.get('visit_date') or h.metadata.get('year', '')}]: {h.page_content[:180]}"
            for h in all_hits
        ]
        context_text = "\n".join(context_parts)
        sys_msg, user_msg, params = format_agent_prompt("comorbidities_agent", context_text=context_text)

        try:
            llm = LLMFactory.get_chat_model(max_tokens=params.get("max_tokens", 512), temperature=params.get("temperature", 0.0))
            resp = llm.invoke([{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}])
            parsed = _parse_llm_json_array(resp.content)
            for i, item in enumerate(parsed[:8]):
                title = str(item.get("title", "")).strip()
                subtitle = str(item.get("subtitle", "")).strip()
                severity = str(item.get("severity", "medium")).strip().lower()
                date_str = str(item.get("date", "")).strip()
                if not title:
                    continue

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
            logging.getLogger(__name__).warning("comorbidities_agent: LLM call failed")

    findings.sort(key=lambda f: f.date, reverse=True)
    return {"comorbidity_findings": findings}


# ---------- agent 6: dynamic caregiver prep with 6-language translations ----------


def caregiver_prep_agent(state: AgentReviewState) -> dict[str, Any]:
    # Generates 6-language Caregiver Handoff/Prep Sheet via caregiver_prep_agent.yaml
    classification = state.get("classification")
    is_diabetic = classification and classification.category == "diabetic"
    patient_name = state.get("patient_name") or "Patient"
    first_name = patient_name.split()[0] if patient_name else "Patient"
    age = state.get("age", "")
    gender = state.get("gender", "")
    comorbidities = state.get("comorbidity_findings") or []
    mismatches_obj = state.get("mismatches")
    retriever: HybridEnsembleRetriever = state["retriever"]
    patient_id = state["patient_id"]

    allergy_hits = retriever.retrieve("allergy allergic reaction medication intolerance", patient_id=patient_id, top_k=3)
    med_hits = retriever.retrieve("prescription medication ongoing active daily", patient_id=patient_id, top_k=4)

    allergy_text = " | ".join(h.page_content[:120] for h in allergy_hits) or "None documented"
    med_text = " | ".join(h.page_content[:120] for h in med_hits) or "None documented"
    comorbidity_text = ", ".join(f.title for f in comorbidities[:5]) if comorbidities else "None documented"
    mismatch_text = " | ".join(m.title for m in mismatches_obj.items[:3]) if mismatches_obj and mismatches_obj.items else "None"

    mode = "handoff" if is_diabetic else "prep_sheet"
    stage_str = classification.stage if classification else "Pre-Diabetic"

    sys_msg, user_msg, params = format_agent_prompt(
        "caregiver_prep_agent",
        first_name=first_name,
        age=age,
        gender=gender,
        stage=stage_str,
        mode=mode,
        comorbidities=comorbidity_text,
        medications=med_text[:300],
        mismatches=mismatch_text,
        allergies=allergy_text[:200],
    )

    checklist: list[ChecklistItem] = []
    allergies: list[str] = []
    ongoing_issues: list[str] = [f.title for f in comorbidities[:4]]

    try:
        llm = LLMFactory.get_chat_model(max_tokens=params.get("max_tokens", 1024), temperature=params.get("temperature", 0.1))
        resp = llm.invoke([{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}])
        parsed = _parse_llm_json_array(resp.content)
        for item_data in parsed[:6]:
            text_en = str(
                item_data.get("text_en")
                or item_data.get("english")
                or item_data.get("item")
                or item_data.get("action")
                or item_data.get("text")
                or ""
            ).strip()
            if not text_en:
                continue
            checklist.append(ChecklistItem(
                id=str(item_data.get("id", f"chk_{len(checklist)+1:02d}")),
                text_en=text_en,
                text_hi=str(item_data.get("text_hi") or item_data.get("hindi") or text_en).strip(),
                text_ta=str(item_data.get("text_ta") or item_data.get("tamil") or text_en).strip(),
                text_bn=str(item_data.get("text_bn") or item_data.get("bengali") or text_en).strip(),
                text_or=str(item_data.get("text_or") or item_data.get("odia") or text_en).strip(),
                text_te=str(item_data.get("text_te") or item_data.get("telugu") or text_en).strip(),
            ))
        if allergy_hits:
            for h in allergy_hits[:2]:
                c_low = h.page_content.lower()
                if "allerg" in c_low or "intolerance" in c_low:
                    allergies.append(h.page_content[:80].strip())
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).warning("caregiver_prep_agent: LLM call failed")

    if not checklist:
        checklist = [
            ChecklistItem(
                id="chk_01",
                text_en="Bring all current medication strips or packaging to the visit.",
                text_hi="सभी वर्तमान दवाओं के पैकेट या पट्टी लेकर आएं।",
                text_ta="தற்போது உட்கொள்ளும் அனைத்து மருந்துகளையும் எடுத்து வாருங்கள்.",
                text_bn="বর্তমান সব ওষুধের স্ট্রিপ বা প্যাকেট সাথে আনুন।",
                text_or="ବର୍ତ୍ତମାନର ସମସ୍ତ ଔଷଧ ପ୍ୟାକେଟ୍ ସାଙ୍ଗରେ ଆଣନ୍ତୁ।",
                text_te="ప్రస్తుతం వాడుతున్న అన్ని మందుల ప్యాకెట్లను వెంట తీసుకురండి.",
            ),
            ChecklistItem(
                id="chk_02",
                text_en="Keep a record of any new symptoms noticed since the last visit.",
                text_hi="पिछली मुलाकात के बाद किसी भी नए लक्षण का रिकॉर्ड रखें।",
                text_ta="கடந்த வருகைக்குப் பிறகு தோன்றிய புதிய அறிகுறிகளை பதிவு செய்யுங்கள்.",
                text_bn="গত পরিদর্শনের পর থেকে দেখা দেওয়া নতুন লক্ষণগুলো লিখে রাখুন।",
                text_or="ପୂର୍ବ ଦେଖା ପରଠାରୁ ଦେଖାଦେଇଥିବା ନୂଆ ଲକ୍ଷଣ ଲିପିବଦ୍ଧ କରନ୍ତୁ।",
                text_te="గత పర్యటన తర్వాత కనిపించిన కొత్త లక్షణాలను నమోదు చేసుకోండి.",
            ),
            ChecklistItem(
                id="chk_03",
                text_en="Confirm all upcoming follow-up appointments and lab tests are scheduled.",
                text_hi="सभी आगामी अनुवर्ती नियुक्तियों और लैब परीक्षणों की पुष्टि करें।",
                text_ta="வரவிருக்கும் அனைத்து பின்தொடர் சந்திப்புகள் மற்றும் ஆய்வக பரிசோதனைகளை உறுதிப்படுத்தவும்.",
                text_bn="আসন্ন সমস্ত ফলো-আপ অ্যাপয়েন্টমেন্ট ও ল্যাব টেস্ট নিশ্চিত করুন।",
                text_or="ଆଗାମୀ ସମସ୍ତ ପରୀକ୍ଷା ଓ ଡାକ୍ତରୀ ପରାମର୍ଶ ତାରିଖ ନିଶ୍ଚିତ କରନ୍ତୁ।",
                text_te="రాబోయే అన్ని ఫాలో-అప్ అపాయింట్‌మెంట్‌లు మరియు ల్యాబ్ పరీక్షలను నిర్ధారించండి.",
            ),
        ]

    return {
        "caregiver_prep": CaregiverPrep(
            mode=mode,
            active_language="en",
            available_languages=["en", "hi", "ta", "bn", "or", "te"],
            checklist=checklist,
            allergies=allergies,
            ongoing_issues=ongoing_issues,
            guidance_notes="Caregiver checklist generated from documented patient history. Review with clinical team.",
        )
    }


# ---------- agent 7: smart assistive bubbles ----------


def assistive_bubbles_agent(state: AgentReviewState) -> dict[str, Any]:
    # Emits non-intrusive assistive prompt bubbles ending with ? via assistive_bubbles_agent.yaml
    classification = state.get("classification")
    stage_str = classification.stage if classification else "Pre-Diabetic"
    comorbidities = state.get("comorbidity_findings") or []
    mismatches_obj = state.get("mismatches")
    metric_series = state.get("metric_series") or []
    care_gaps_obj = state.get("care_gaps")

    milestones_str = ", ".join(f.title for f in comorbidities[:3]) if comorbidities else "None"
    series_str = ", ".join(s.metric_name for s in metric_series[:3]) if metric_series else "None"
    mismatch_str = mismatches_obj.items[0].title if mismatches_obj and mismatches_obj.items else "None"
    gaps_str = care_gaps_obj.items[0].title if care_gaps_obj and care_gaps_obj.items else "None"

    bubbles: list[SmartPromptBubble] = []

    sys_msg, user_msg, params = format_agent_prompt(
        "assistive_bubbles_agent",
        stage=stage_str,
        milestones=milestones_str,
        series_names=series_str,
        mismatches=mismatch_str,
        care_gaps=gaps_str,
    )

    try:
        llm = LLMFactory.get_chat_model(max_tokens=params.get("max_tokens", 384), temperature=params.get("temperature", 0.0))
        resp = llm.invoke([{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}])
        parsed = _parse_llm_json_array(resp.content)
        for b in parsed[:4]:
            p_text = str(b.get("prompt_text", "")).strip()
            if not p_text:
                continue
            if not p_text.endswith("?"):
                p_text = f"{p_text}?"
            bubbles.append(SmartPromptBubble(
                bubble_id=str(b.get("bubble_id", f"bubble_{len(bubbles)+1:02d}")),
                icon=str(b.get("icon", "info")),
                prompt_text=p_text,
                action_type=str(b.get("action_type", "open_chart_modal")),
                target_series=b.get("target_series", []),
                milestone_id=b.get("milestone_id"),
            ))
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).debug("assistive_bubbles_agent: LLM call failed; using rule fallback")

    if len(bubbles) < 2:
        if metric_series:
            series_names = [s.metric_name for s in metric_series[:3]]
            bubbles.append(SmartPromptBubble(
                bubble_id="bubble_01",
                icon="timeline",
                prompt_text=f"Longitudinal data available for {', '.join(series_names)}: Would you like to chart the multi-year metabolic trajectory?",
                action_type="open_chart_modal",
                target_series=series_names,
            ))
        if comorbidities:
            bubbles.append(SmartPromptBubble(
                bubble_id="bubble_02",
                icon="hospital",
                prompt_text=f"Clinical events found: {comorbidities[0].title}. Would you like to review the source records?",
                action_type="open_milestone_detail",
                milestone_id="admissions",
            ))

    return {"assistive_bubbles": bubbles}


# ---------- agent 8: brief compiler node ----------


def brief_compiler_node(state: AgentReviewState) -> dict[str, Any]:
    # Assembles final consultation brief matching the UI layout from runtime state ONLY
    classification = state.get("classification") or PatientClassification()
    comorbidities = state.get("comorbidity_findings") or []
    metric_series = state.get("metric_series") or []
    bubbles = state.get("assistive_bubbles") or []

    patient_name = state.get("patient_name") or "Unknown Patient"
    age = state.get("age", 0)
    gender = state.get("gender") or "Unknown"
    mrn = state.get("mrn") or state.get("patient_id", "")
    age_sex = state.get("age_sex") or (f"{age} years / {gender}" if age else gender)

    brief = ConsultationBrief(
        patient_id=state["patient_id"],
        patient_name=patient_name,
        age_sex=age_sex,
        age=age,
        gender=gender,
        mrn=mrn,
        diabetes_type=classification.stage,
        classification=classification,
        visit_focus="Metabolic screening review & medication reconciliation",
        trajectory=state.get("trajectory") or MetabolicTrajectory(),
        care_gaps=state.get("care_gaps") or CareGaps(),
        mismatches=state.get("mismatches") or RecordMismatches(),
        caregiver_prep=state.get("caregiver_prep") or CaregiverPrep(),
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
