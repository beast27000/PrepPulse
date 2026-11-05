from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import fitz
from langchain_core.messages import HumanMessage, SystemMessage

from preppulse_agents.graph import create_clinical_review_workflow
from preppulse_agents.prompt_loader import format_rag_prompt
from preppulse_agents.schemas import ConsultationBrief
from preppulse_api.config import DATASET_ROOT, MONGO_URI, PRIVATE_ROOT
from preppulse_api.evidence_catalog import build_catalog, enrich_history
from preppulse_api.store import WorkspaceStore, now
from preppulse_db.ingest import map_parsed_doc_to_mongo
from preppulse_db.mongo_store import MongoStore
from preppulse_ocr.engine import DocumentMetadata, DocumentType, OcrPipeline
from preppulse_rag.chunker import ClinicalProvenanceChunker
from preppulse_rag.llm_provider import LLMFactory, MockClinicalChatModel
from preppulse_rag.retriever import HybridEnsembleRetriever

TYPE_MAP = {
    "lab": DocumentType.LAB_PANEL,
    "lab_report": DocumentType.LAB_PANEL,
    "discharge": DocumentType.DISCHARGE_SUMMARY,
    "discharge_summary": DocumentType.DISCHARGE_SUMMARY,
    "rx": DocumentType.REFERRAL_ORDER,
    "prescription": DocumentType.REFERRAL_ORDER,
    "consult": DocumentType.OUTPATIENT_NOTE,
}


def source_path(record: dict) -> Path:
    path = Path(record["source_path"]).resolve()
    if not any(path.is_relative_to(root) for root in (DATASET_ROOT, PRIVATE_ROOT)):
        raise ValueError("Source path outside authorized storage")
    if not path.is_file():
        raise FileNotFoundError("Source document unavailable")
    return path


def render_page(record: dict, page_number: int) -> bytes:
    path = source_path(record)
    if page_number < 1:
        raise ValueError("Invalid page number")
    if path.suffix.lower() == ".pdf":
        with fitz.open(path) as pdf:
            if page_number > len(pdf):
                raise ValueError("Invalid page number")
            return (
                pdf[page_number - 1]
                .get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False)
                .tobytes("png")
            )
    if page_number != 1:
        raise ValueError("Invalid page number")
    with fitz.open(path) as image_doc:
        return image_doc[0].get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False).tobytes("png")


def process_patient(
    store: WorkspaceStore, patient_id: str, progress: Callable[[str], None] | None = None
) -> dict:
    patient = store.patient(patient_id)
    if not patient:
        raise ValueError("Patient not found")
    mongo = MongoStore(uri=MONGO_URI, db_name=store.db.name)
    try:
        for rec in store.db.workspace_documents.find({"patient_id": patient_id}):
            if mongo.get_document(rec["record_id"]):
                continue
            path = source_path(rec)
            visit_date = rec.get("visit_date")
            try:
                parsed_date = date.fromisoformat(visit_date) if visit_date else None
            except ValueError:
                parsed_date = None
            meta = DocumentMetadata(
                patient_id=patient_id,
                document_id=rec["record_id"],
                document_name=rec["filename"],
                document_type=TYPE_MAP.get(
                    rec.get("document_type", ""), DocumentType.OUTPATIENT_NOTE
                ),
                encounter_date=parsed_date,
            )
            try:
                parsed = OcrPipeline().parse(path, meta)
                mongo_doc = map_parsed_doc_to_mongo(
                    parsed,
                    patient_id,
                    visit_date,
                    rec.get("document_type", "consult"),
                    None,
                    rec["filename"],
                )
                mongo.write_stage1(mongo_doc)
                store.db.workspace_documents.update_one(
                    {"record_id": rec["record_id"]},
                    {"$set": {"status": "ready", "page_count": len(parsed.pages), "error": None}},
                )
            except Exception as exc:
                store.db.workspace_documents.update_one(
                    {"record_id": rec["record_id"]},
                    {"$set": {"status": "failed", "error": str(exc)[:300]}},
                )
            if progress:
                progress("ocr")
        docs = mongo.get_patient_documents(patient_id)
        if not docs:
            raise ValueError("No processed patient documents")
        if progress:
            progress("analysis")
        chunker = ClinicalProvenanceChunker()
        chunks = [chunk for doc in docs for chunk in chunker.chunk_mongo_document(doc)]
        retriever = HybridEnsembleRetriever(chunks)
        dob = patient.get("dob")
        age = date.today().year - int(dob[:4]) if dob and len(dob) >= 4 and dob[:4].isdigit() else patient.get("age") or 0
        initial = {
            "patient_id": patient_id,
            "patient_name": patient["name"],
            "mrn": patient_id,
            "age_sex": f"{age} years / {patient.get('sex') or 'Unknown'}",
            "age": age,
            "gender": patient.get("sex") or "Unknown",
            "diabetes_type": "",
            "retriever": retriever,
            "classification": None,
            "trajectory": None,
            "care_gaps": None,
            "mismatches": None,
            "comorbidity_findings": None,
            "caregiver_prep": None,
            "assistive_bubbles": None,
            "metric_series": None,
            "final_brief": None,
        }
        state = dict(initial)
        workflow = create_clinical_review_workflow()
        agent_names = [
            "classification_agent",
            "trajectory_agent",
            "care_gaps_agent",
            "mismatches_agent",
            "comorbidities_agent",
            "caregiver_prep_agent",
            "assistive_bubbles_agent",
            "brief_compiler",
        ]
        if progress:
            progress(agent_names[0])
        for update in workflow.stream(initial, stream_mode="updates"):
            for node, values in update.items():
                if values:
                    state.update(values)
                if (
                    progress
                    and node in agent_names
                    and agent_names.index(node) + 1 < len(agent_names)
                ):
                    progress(agent_names[agent_names.index(node) + 1])
        brief: ConsultationBrief = state["final_brief"]
        raw = brief.model_dump(mode="json")
        checked = annotate_citations(store, patient_id, raw)
        if progress:
            progress("history_synthesis_agent")
        catalog = build_catalog(store, patient_id)
        model = LLMFactory.get_chat_model(max_tokens=2600)
        if not isinstance(model, MockClinicalChatModel):
            enrich_history(catalog, model, progress=progress)
        checked["record_summaries"] = catalog["record_summaries"]
        checked["metric_series"] = catalog["metric_series"]
        glycemic = next(
            (series for series in catalog["metric_series"] if series["metric_name"] == "HbA1c"),
            None,
        )
        dates = [record["date"] for record in catalog["record_summaries"] if record["date"]]
        history_text = (
            f"{len(dates)} source records cover {min(dates)[:4]}–{max(dates)[:4]}."
            if dates
            else "No dated source history is available."
        )
        if glycemic and glycemic["points"]:
            first, last = glycemic["points"][0], glycemic["points"][-1]
            history_text += f" Recorded HbA1c: {first['value']:g}% ({first['date']}) → {last['value']:g}% ({last['date']})."
        diagnosis = next(
            (
                record
                for record in catalog["record_summaries"]
                if any(
                    re.search(r"new diagnosis of type 2 diabetes", item["text"], re.IGNORECASE)
                    for item in record["evidence"]
                )
            ),
            None,
        )
        if diagnosis:
            history_text = (
                f"Type 2 diabetes is documented in the {diagnosis['date']} consultation. "
                + history_text
            )
        checked["diabetes_history"] = {
            "summary": history_text,
            "start_date": min(dates) if dates else None,
            "end_date": max(dates) if dates else None,
            "diagnosis_date": diagnosis["date"] if diagnosis else None,
            "diagnosis_citation": diagnosis.get("citation") if diagnosis else None,
            "records": [
                record
                for record in catalog["record_summaries"]
                if record["category"] == "diabetes_history"
            ],
        }
        checked["history_synthesis"] = catalog.get("history_synthesis", "source_excerpts")
        checked["care_gaps"]["items"] = [
            item
            for item in checked["care_gaps"]["items"]
            if (item.get("citation") or {}).get("source_verified")
        ]
        checked["visit_focus"] = "Diabetes history, current results, and relevant clinical events"
        checked["trajectory"]["summary"] = history_text
        kpis = []
        for name in ("HbA1c", "Fasting glucose", "eGFR"):
            series = next(
                (item for item in catalog["metric_series"] if item["metric_name"] == name), None
            )
            if not series or not series["points"]:
                continue
            point = series["points"][-1]
            earlier = series["points"][-2] if len(series["points"]) > 1 else point
            kpis.append(
                {
                    "name": name,
                    "value": f"{point['value']:g}",
                    "unit": point["unit"],
                    "date_str": point["date"],
                    "trend_direction": "up"
                    if point["value"] > earlier["value"]
                    else "down"
                    if point["value"] < earlier["value"]
                    else "stable",
                    "citation": point["citation"],
                }
            )
        checked["trajectory"]["kpis"] = kpis
        if not patient.get("sex"):
            text = " ".join(
                page.get("full_text", "")[:600]
                for doc in docs
                for page in doc.get("stage_1_raw_ocr", {}).get("pages", [])[:1]
            )
            sex = re.search(r"\bSex:\s*(Female|Male|Other)\b", text, re.IGNORECASE)
            checked["gender"] = sex[1] if sex else "Not recorded"
            checked["age_sex"] = f"{age} years / {checked['gender']}" if age else checked["gender"]
        checked["priority_findings"] = grounded_priority_findings(checked)
        for record in catalog["record_summaries"]:
            if record["category"] == "other_history" and record.get("citation"):
                checked["priority_findings"].append(
                    {
                        "finding_id": f"history_{record['record_id']}",
                        "title": record["title"],
                        "subtitle": record["summary"],
                        "date": record["date"],
                        "severity": "medium",
                        "status": "pending_review",
                        "citation": record["citation"],
                    }
                )
        store.db.briefs.update_one(
            {"patient_id": patient_id},
            {"$set": {"patient_id": patient_id, "brief": checked, "generated_at": now()}},
            upsert=True,
        )
        return checked
    finally:
        mongo.close()


def _tokens(text: str) -> set[str]:
    return {
        t
        for t in re.findall(r"[a-z0-9]{3,}", text.lower())
        if t not in {"the", "and", "from", "with", "report"}
    }


def locate_citation(store: WorkspaceStore, patient_id: str, citation: dict) -> list[int] | None:
    doc_id = citation.get("document_id")
    bbox = citation.get("bbox")
    page_no = citation.get("page_number")
    snippet = citation.get("snippet") or citation.get("extracted_text") or ""
    if not doc_id or not isinstance(page_no, int) or not isinstance(bbox, list) or len(bbox) != 4:
        return None
    if bbox == [0, 0, 1000, 1000] or not all(isinstance(v, int) and 0 <= v <= 1000 for v in bbox):
        return None
    if bbox[0] >= bbox[2] or bbox[1] >= bbox[3]:
        return None
    rec = store.db.workspace_documents.find_one({"record_id": doc_id, "patient_id": patient_id})
    doc = store.db.patient_documents.find_one(
        {"document_id": doc_id, "patient_id": patient_id}, {"stage_1_raw_ocr.pages": 1}
    )
    if not rec or not doc:
        return None
    page = next(
        (p for p in doc.get("stage_1_raw_ocr", {}).get("pages", []) if p["page_number"] == page_no),
        None,
    )
    if not page or not snippet:
        return None
    overlapping = [
        t
        for t in page.get("tokens", [])
        if t["bbox"][0] <= bbox[2]
        and t["bbox"][2] >= bbox[0]
        and t["bbox"][1] <= bbox[3]
        and t["bbox"][3] >= bbox[1]
    ]
    words = [
        re.sub(r"[^a-z0-9]", "", word.lower())
        for word in re.findall(r"[a-zA-Z0-9]+(?:\.[0-9]+)?", snippet)
    ]
    words = [word for word in words if word]
    token_words = [re.sub(r"[^a-z0-9]", "", t["text"].lower()) for t in overlapping]
    # A retrieval chunk can cover a whole page. Require a contiguous OCR phrase
    # and return its tight token box, never the chunk's broad bounding box.
    for length in range(min(7, len(words)), 1, -1):
        for start in range(len(words) - length + 1):
            phrase = words[start : start + length]
            for offset in range(len(token_words) - length + 1):
                if token_words[offset : offset + length] != phrase:
                    continue
                boxes = [t["bbox"] for t in overlapping[offset : offset + length]]
                result = [
                    min(b[0] for b in boxes),
                    min(b[1] for b in boxes),
                    max(b[2] for b in boxes),
                    max(b[3] for b in boxes),
                ]
                if (result[2] - result[0]) * (result[3] - result[1]) <= 100_000:
                    return result
    return None


def validate_citation(store: WorkspaceStore, patient_id: str, citation: dict) -> bool:
    return locate_citation(store, patient_id, citation) is not None


def annotate_citations(store: WorkspaceStore, patient_id: str, value: Any) -> Any:
    if isinstance(value, list):
        return [annotate_citations(store, patient_id, v) for v in value]
    if isinstance(value, dict):
        result = {k: annotate_citations(store, patient_id, v) for k, v in value.items()}
        if "bbox" in result and "page_number" in result:
            precise = locate_citation(store, patient_id, result)
            result["source_verified"] = precise is not None
            if precise:
                result["bbox"] = precise
        return result
    return value


def grounded_priority_findings(brief: dict) -> list[dict]:
    """Show reviewable, source-linked observations already present in the brief."""
    findings = [
        finding
        for finding in brief.get("priority_findings", [])
        if (finding.get("citation") or {}).get("source_verified")
        and len(
            _tokens(finding.get("title") or "")
            & _tokens(
                (finding.get("citation") or {}).get("snippet")
                or (finding.get("citation") or {}).get("extracted_text")
                or ""
            )
        )
        >= min(2, len(_tokens(finding.get("title") or "")))
        and bool(_tokens(finding.get("title") or ""))
    ]
    seen = {((f.get("citation") or {}).get("document_id"), f.get("title")) for f in findings}
    for index, metric in enumerate(brief.get("trajectory", {}).get("kpis", [])):
        citation = metric.get("citation") or {}
        if not citation.get("source_verified") or not metric.get("value"):
            continue
        source_text = citation.get("snippet") or citation.get("extracted_text") or ""
        metric_terms = _tokens(metric.get("name") or "")
        source_numbers = set(re.findall(r"\d+(?:\.\d+)?", source_text))
        value_numbers = set(re.findall(r"\d+(?:\.\d+)?", str(metric["value"])))
        if (metric_terms and not metric_terms & _tokens(source_text)) or (
            value_numbers and not value_numbers & source_numbers
        ):
            continue
        value = str(metric["value"])
        unit = metric.get("unit") or ""
        rendered = (
            value if not unit or unit in value else f"{value}{'' if unit == '%' else ' '}{unit}"
        )
        title = f"{metric.get('name', 'Recorded metric')}: {rendered}"
        key = (citation.get("document_id"), title)
        if key in seen:
            continue
        seen.add(key)
        series = next(
            (
                item
                for item in brief.get("metric_series", [])
                if item.get("metric_name", "").lower() == str(metric.get("name", "")).lower()
            ),
            None,
        )
        previous = series["points"][-2] if series and len(series.get("points", [])) > 1 else None
        subtitle = f"Recorded on {metric.get('date_str') or 'the source date'}."
        if previous:
            previous_value = f"{previous['value']:g}{'' if unit == '%' else ' '}{unit}"
            subtitle = f"Previous recorded value: {previous_value} on {previous['date']}. Latest result: {metric.get('date_str') or 'source date'}."
        findings.append(
            {
                "finding_id": f"metric_{index + 1}",
                "title": title,
                "subtitle": subtitle,
                "date": metric.get("date_str") or "",
                "severity": "low",
                "status": "pending_review",
                "citation": citation,
                "related_citations": [previous["citation"]]
                if previous and previous.get("citation")
                else [],
            }
        )
    return findings[:12]


def retriever_for_patient(store: WorkspaceStore, patient_id: str) -> HybridEnsembleRetriever:
    docs = list(store.db.patient_documents.find({"patient_id": patient_id}, {"_id": 0}))
    chunker = ClinicalProvenanceChunker()
    return HybridEnsembleRetriever([c for d in docs for c in chunker.chunk_mongo_document(d)])


def answer_chat(store: WorkspaceStore, patient_id: str, question: str) -> dict:
    retriever = retriever_for_patient(store, patient_id)
    hits = retriever.retrieve(question, patient_id=patient_id, top_k=6)
    longitudinal = bool(
        re.search(
            r"\b(history|years?|decade|timeline|earlier|since|over time|trend|previous)\b",
            question,
            re.IGNORECASE,
        )
    )
    if longitudinal:
        # A single top-k search overweights recent similar lab reports. Include
        # documented years across the chart before asking for a timeline answer.
        terms = _tokens(question)
        by_year: dict[str, Any] = {}
        for chunk in retriever.get_patient_documents(patient_id):
            year = str(chunk.metadata.get("visit_date") or chunk.metadata.get("year") or "")[:4]
            if not year.isdigit():
                continue
            score = len(terms & _tokens(chunk.page_content))
            if year not in by_year or score > by_year[year][0]:
                by_year[year] = (score, chunk)
        known = {h.metadata.get("chunk_id") for h in hits}
        for year in sorted(by_year):
            chunk = by_year[year][1]
            if chunk.metadata.get("chunk_id") not in known:
                hits.append(chunk)
                known.add(chunk.metadata.get("chunk_id"))
        hits = hits[:18]
    citations = []
    context = []
    for h in hits:
        cit = {
            "document_id": h.metadata.get("document_id", ""),
            "document_title": h.metadata.get("source_file", ""),
            "page_number": h.metadata.get("page_number", 1),
            "bbox": h.metadata.get("bbox", []),
            "snippet": h.page_content[:300],
        }
        precise = locate_citation(store, patient_id, cit)
        cit["source_verified"] = precise is not None
        if precise:
            cit["bbox"] = precise
        citations.append(cit)
        context.append(
            f"[{len(citations)}] {cit['document_title']} "
            f"({h.metadata.get('visit_date') or h.metadata.get('year') or 'date unknown'}) "
            f"page {cit['page_number']}: {h.page_content[:300]}"
        )
    if not hits:
        return {
            "answer_markdown": "I could not find relevant documentation in this patient's records.",
            "citations": [],
        }
    model = LLMFactory.get_chat_model(max_tokens=700)
    if isinstance(model, MockClinicalChatModel):
        answer = "Relevant chart excerpts:\n\n" + "\n\n".join(context)
    else:
        sys, prompt, _ = format_rag_prompt(
            "clinical_chatbot", evidence_context="\n".join(context), doctor_query=question
        )
        if longitudinal:
            sys += "\nThe excerpts span multiple documented years. Summarize the years actually present; do not claim the whole history is unavailable when dated records are provided. Distinguish gaps from documented events."
        try:
            answer = str(
                model.invoke([SystemMessage(content=sys), HumanMessage(content=prompt)]).content
            )
        except Exception:
            answer = "The assistant could not complete a synthesis. Review the retrieved excerpts and sources below."
    return {"answer_markdown": answer, "citations": citations}
