from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

import fitz
from langchain_core.messages import HumanMessage, SystemMessage

from preppulse_agents.graph import create_clinical_review_workflow
from preppulse_agents.prompt_loader import format_rag_prompt
from preppulse_agents.schemas import ConsultationBrief
from preppulse_api.config import DATASET_ROOT, MONGO_URI, PRIVATE_ROOT
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


def process_patient(store: WorkspaceStore, patient_id: str) -> dict:
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
                raise
        docs = mongo.get_patient_documents(patient_id)
        if not docs:
            raise ValueError("No processed patient documents")
        chunker = ClinicalProvenanceChunker()
        chunks = [chunk for doc in docs for chunk in chunker.chunk_mongo_document(doc)]
        retriever = HybridEnsembleRetriever(chunks)
        dob = patient.get("dob")
        age = date.today().year - int(dob[:4]) if dob and len(dob) >= 4 and dob[:4].isdigit() else 0
        initial = {
            "patient_id": patient_id,
            "patient_name": patient["name"],
            "mrn": patient_id,
            "age_sex": f"{age} years / {patient.get('sex', 'Unknown')}",
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
        brief: ConsultationBrief = create_clinical_review_workflow().invoke(initial)["final_brief"]
        raw = brief.model_dump(mode="json")
        checked = annotate_citations(store, patient_id, raw)
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


def validate_citation(store: WorkspaceStore, patient_id: str, citation: dict) -> bool:
    doc_id = citation.get("document_id")
    bbox = citation.get("bbox")
    page_no = citation.get("page_number")
    snippet = citation.get("snippet") or citation.get("extracted_text") or ""
    if not doc_id or not isinstance(page_no, int) or not isinstance(bbox, list) or len(bbox) != 4:
        return False
    if bbox == [0, 0, 1000, 1000] or not all(isinstance(v, int) and 0 <= v <= 1000 for v in bbox):
        return False
    if bbox[0] >= bbox[2] or bbox[1] >= bbox[3]:
        return False
    rec = store.db.workspace_documents.find_one({"record_id": doc_id, "patient_id": patient_id})
    doc = store.db.patient_documents.find_one(
        {"document_id": doc_id, "patient_id": patient_id}, {"stage_1_raw_ocr.pages": 1}
    )
    if not rec or not doc:
        return False
    page = next(
        (p for p in doc.get("stage_1_raw_ocr", {}).get("pages", []) if p["page_number"] == page_no),
        None,
    )
    if not page or not snippet:
        return False
    overlapping = [
        t["text"]
        for t in page.get("tokens", [])
        if t["bbox"][0] <= bbox[2]
        and t["bbox"][2] >= bbox[0]
        and t["bbox"][1] <= bbox[3]
        and t["bbox"][3] >= bbox[1]
    ]
    wanted = _tokens(snippet)
    found = _tokens(" ".join(overlapping))
    return len(wanted & found) >= min(2, len(wanted)) and bool(wanted)


def annotate_citations(store: WorkspaceStore, patient_id: str, value: Any) -> Any:
    if isinstance(value, list):
        return [annotate_citations(store, patient_id, v) for v in value]
    if isinstance(value, dict):
        result = {k: annotate_citations(store, patient_id, v) for k, v in value.items()}
        if "bbox" in result and "page_number" in result:
            result["source_verified"] = validate_citation(store, patient_id, result)
        return result
    return value


def retriever_for_patient(store: WorkspaceStore, patient_id: str) -> HybridEnsembleRetriever:
    docs = list(store.db.patient_documents.find({"patient_id": patient_id}, {"_id": 0}))
    chunker = ClinicalProvenanceChunker()
    return HybridEnsembleRetriever([c for d in docs for c in chunker.chunk_mongo_document(d)])


def answer_chat(store: WorkspaceStore, patient_id: str, question: str) -> dict:
    retriever = retriever_for_patient(store, patient_id)
    hits = retriever.retrieve(question, patient_id=patient_id, top_k=5)
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
        cit["source_verified"] = validate_citation(store, patient_id, cit)
        citations.append(cit)
        context.append(
            f"[{len(citations)}] {cit['document_title']} page {cit['page_number']}: {h.page_content[:300]}"
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
        try:
            answer = str(
                model.invoke([SystemMessage(content=sys), HumanMessage(content=prompt)]).content
            )
        except Exception:
            answer = "The assistant could not complete a synthesis. Review the retrieved excerpts and sources below."
    return {"answer_markdown": answer, "citations": citations}
