"""
Audit and verification script for the end-to-end PrepPulse clinical pipeline.
Processes real 10-year patient records from the PrepPulse Dataset, runs Stage 1 OCR,
Stage 2 preprocessing & chunking, Hybrid BM25+Dense RAG, and all 8 LangGraph clinical agents.
Strictly wipes MongoDB clean after audit completion to prevent database corruption.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from preppulse_agents.graph import create_clinical_review_workflow
from preppulse_agents.schemas import ConsultationBrief
from preppulse_db.mongo_store import MongoStore
from preppulse_db.schemas import (
    PageRecord,
    PatientDocument,
    Stage1RawOcr,
    TokenRecord,
)
from preppulse_ocr.engine import DocumentMetadata, DocumentType, OcrPipeline
from preppulse_preprocessing.chunk import chunk_document
from preppulse_rag.chunker import ClinicalProvenanceChunker
from preppulse_rag.retriever import HybridEnsembleRetriever

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("audit_pipeline")

TYPE_MAP = {
    "lab": DocumentType.LAB_PANEL,
    "consult": DocumentType.OUTPATIENT_NOTE,
    "rx": DocumentType.REFERRAL_ORDER,
    "discharge": DocumentType.DISCHARGE_SUMMARY,
    "procedure": DocumentType.DISCHARGE_SUMMARY,
}


def run_pipeline_audit(patient_folder_name: str = "PP001_Ananya_Baruah") -> dict[str, Any]:
    dataset_dir = Path("datasets/PrepPulse Dataset") / patient_folder_name
    if not dataset_dir.is_dir():
        raise FileNotFoundError(f"Dataset folder not found: {dataset_dir}")

    meta_file = dataset_dir / "manifest.json" if (dataset_dir / "manifest.json").exists() else dataset_dir / "record_index.json"
    if not meta_file.exists():
        raise FileNotFoundError(f"Manifest not found in {dataset_dir}")

    manifest = json.loads(meta_file.read_text(encoding="utf-8"))
    patient_name = manifest.get("patient_name") or manifest.get("name") or "Patient"
    patient_category = manifest.get("diabetes_category") or manifest.get("category") or "Type 2 diabetes"
    dob_str = manifest.get("dob") or manifest.get("date_of_birth") or "1970-01-01"

    # Calculate approximate age
    birth_year = int(dob_str.split("-")[0]) if dob_str else 1970
    age = 2026 - birth_year

    records = manifest.get("records") or manifest.get("documents") or []
    logger.info("==================================================================")
    logger.info(f"STARTING AUDIT: {patient_name} ({patient_folder_name})")
    logger.info(f"Category: {patient_category} | DOB: {dob_str} (Age ~{age})")
    logger.info(f"Total Source Records: {len(records)} PDFs")
    logger.info("==================================================================")

    store = MongoStore()
    store.connect()

    # Step 0: Ensure pristine database state
    logger.info("Step 0: Pre-clearing MongoDB collections...")
    store.clear_database()

    ocr = OcrPipeline()
    chunker = ClinicalProvenanceChunker(max_tokens_per_chunk=120)
    all_rag_documents = []

    try:
        # Step 1: Stage 1 Ingestion via OcrPipeline
        logger.info("Step 1: Running Stage 1 OCR parsing on all patient PDFs...")
        ingested_count = 0
        for rec in records:
            filename = rec.get("file") or rec.get("filename")
            pdf_path = dataset_dir / filename
            if not pdf_path.exists():
                logger.warning(f"File not found: {pdf_path}")
                continue

            rec_type = rec.get("type", "consult")
            doc_type = TYPE_MAP.get(rec_type, DocumentType.OUTPATIENT_NOTE)
            visit_date = rec.get("date")

            doc_meta = DocumentMetadata(
                patient_id=patient_folder_name,
                document_id=filename.replace(".pdf", ""),
                document_name=filename,
                document_type=doc_type,
            )
            parsed_doc = ocr.parse(pdf_path, doc_meta)

            pages_records: list[PageRecord] = []
            for page in parsed_doc.pages:
                tokens = [
                    TokenRecord(
                        text=t.text,
                        bbox=[t.bbox.x0, t.bbox.y0, t.bbox.x1, t.bbox.y1],
                        confidence=t.confidence,
                        source="ocr",
                    )
                    for t in page.tokens
                ]
                full_text = "\n".join(l.text for l in page.lines)
                pages_records.append(PageRecord(
                    page_number=page.page_number,
                    extraction_method=page.extraction_method,
                    full_text=full_text,
                    tokens=tokens,
                ))

            p_doc = PatientDocument(
                document_id=filename.replace(".pdf", ""),
                patient_id=patient_folder_name,
                visit_date=visit_date,
                document_type=doc_type.value,
                source_file=filename,
                stage_1_raw_ocr=Stage1RawOcr(
                    page_count=len(pages_records),
                    pages=pages_records,
                ),
            )
            store.write_stage1(p_doc)
            ingested_count += 1

        logger.info(f"Stage 1 Complete: Ingested {ingested_count} patient documents into MongoDB.")

        # Step 2: Teammate Preprocessing Section-Aware Chunking
        logger.info("Step 2: Executing Section-Aware Preprocessing Chunking...")
        mongo_docs = store.get_patient_documents(patient_folder_name)
        total_chunks = 0
        for m_doc in mongo_docs:
            chunks = chunk_document(m_doc)
            for ch in chunks:
                store.write_chunk(ch)
            total_chunks += len(chunks)

            # Also generate LangChain Provenance documents for RAG
            langchain_chunks = chunker.chunk_mongo_document(m_doc)
            all_rag_documents.extend(langchain_chunks)

        logger.info(f"Stage 2 Complete: Created {total_chunks} section chunks and {len(all_rag_documents)} RAG provenance chunks.")

        # Step 3: Initialize Hybrid Ensemble Retriever
        logger.info("Step 3: Initializing HybridEnsembleRetriever (BM25 + Qwen Dense Vector Index)...")
        retriever = HybridEnsembleRetriever(all_rag_documents)
        logger.info(f"Retriever indexed {len(all_rag_documents)} chunks successfully.")

        # Step 4: Run LangGraph Clinical Review Workflow
        logger.info("Step 4: Invoking 8-Node LangGraph Clinical Review Workflow with live local Qwen LLM...")
        t_start = datetime.now()
        workflow = create_clinical_review_workflow()
        initial_state = {
            "patient_id": patient_folder_name,
            "patient_name": patient_name,
            "mrn": f"PP-{patient_folder_name[:5]}",
            "age_sex": f"{age} years / Female",
            "age": age,
            "gender": "Female",
            "diabetes_type": patient_category,
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

        final_state = workflow.invoke(initial_state)
        elapsed_sec = (datetime.now() - t_start).total_seconds()
        logger.info(f"LangGraph Workflow completed in {elapsed_sec:.2f} seconds.")

        brief: ConsultationBrief = final_state["final_brief"]
        assert brief is not None, "ConsultationBrief must not be None"

        # Step 5: Audit & Verify Generated Brief
        logger.info("Step 5: Verifying Output Structure and Dynamic Bindings...")

        # 5.1 Classification
        cls_stage = brief.classification.stage if brief.classification else "N/A"
        cls_basis = brief.classification.diagnostic_basis if brief.classification else "N/A"
        logger.info(f"[Classification] Stage: {cls_stage} | Basis: {cls_basis}")

        # 5.2 Trajectory KPIs & Bounding Boxes
        kpis = brief.trajectory.kpis
        logger.info(f"[Trajectory] Extracted {len(kpis)} Key Metabolic KPIs:")
        for k in kpis:
            cit_txt = k.citation.extracted_text[:60] if k.citation else "No citation"
            bbox_str = str(k.citation.bbox) if k.citation else "None"
            logger.info(f"   - {k.name}: {k.value} {k.unit} ({k.date_str}) | Trend: {k.trend_direction} | BBox: {bbox_str} | Cite: {cit_txt}")
            if k.citation:
                assert all(0 <= coord <= 1000 for coord in k.citation.bbox), f"Bounding box out of bounds: {k.citation.bbox}"

        # 5.3 Care Gaps
        care_gaps = brief.care_gaps.items
        logger.info(f"[Care Gaps] Identified {len(care_gaps)} overdue/pending clinical gaps:")
        for g in care_gaps:
            logger.info(f"   - [{g.severity.upper()}] {g.title}: {g.details}")

        # 5.4 Mismatches & Medication Conflicts
        mismatches = brief.mismatches.items
        logger.info(f"[Mismatches] Identified {len(mismatches)} clinical reconciliation conflicts:")
        for m in mismatches:
            logger.info(f"   - {m.title}: {m.description}")
            if m.source_a_citation:
                logger.info(f"     Source A: {m.source_a_citation.document_title} | {m.source_a_citation.extracted_text[:60]}")
            if m.source_b_citation:
                logger.info(f"     Source B: {m.source_b_citation.document_title} | {m.source_b_citation.extracted_text[:60]}")

        # 5.5 Comorbidities & Acute Admissions Timeline
        findings = brief.priority_findings
        logger.info(f"[Comorbidities] Reverse-Chronological Timeline ({len(findings)} events):")
        for f in findings:
            logger.info(f"   - {f.date}: {f.title} ({f.subtitle}) [Severity: {f.severity}]")

        # 5.6 Multi-lingual Caregiver Checklist
        checklist = brief.caregiver_prep.checklist
        logger.info(f"[Caregiver Prep] Checklist Items ({len(checklist)} items) in 6 Languages:")
        for idx, item in enumerate(checklist, 1):
            logger.info(f"   Item {idx}:")
            logger.info(f"     [en]: {item.text_en}")
            logger.info(f"     [hi]: {item.text_hi}")
            logger.info(f"     [ta]: {item.text_ta}")
            logger.info(f"     [bn]: {item.text_bn}")
            logger.info(f"     [or]: {item.text_or}")
            logger.info(f"     [te]: {item.text_te}")
            assert len(item.text_en) > 0, "English text missing"
            assert len(item.text_hi) > 0, "Hindi text missing"
            assert len(item.text_ta) > 0, "Tamil text missing"
            assert len(item.text_bn) > 0, "Bengali text missing"
            assert len(item.text_or) > 0, "Odia text missing"
            assert len(item.text_te) > 0, "Telugu text missing"

        # 5.7 Smart Assistive Bubbles
        bubbles = brief.assistive_bubbles
        logger.info(f"[Assistive Bubbles] Generated {len(bubbles)} dynamic prompt bubbles:")
        for b in bubbles:
            logger.info(f"   - [{b.action_type} | {b.icon}] {b.prompt_text}")

        audit_result = {
            "patient_name": patient_name,
            "patient_id": patient_folder_name,
            "documents_ingested": ingested_count,
            "section_chunks": total_chunks,
            "rag_chunks": len(all_rag_documents),
            "execution_time_sec": elapsed_sec,
            "classification_stage": cls_stage,
            "kpis_extracted": len(kpis),
            "care_gaps_found": len(care_gaps),
            "mismatches_found": len(mismatches),
            "timeline_events": len(findings),
            "checklist_items": len(checklist),
            "languages_verified": ["en", "hi", "ta", "bn", "or", "te"],
            "assistive_bubbles": len(bubbles),
        }
        return audit_result

    finally:
        # Step 6: STRICT DATABASE TEARDOWN
        logger.info("==================================================================")
        logger.info("Step 6: STRICT DATABASE HYGIENE - Wiping MongoDB test collections...")
        store.clear_database()
        doc_count = store.db["patient_documents"].count_documents({})
        chunk_count = store.db["document_chunks"].count_documents({})
        logger.info(f"Teardown verified: patient_documents count = {doc_count}, document_chunks count = {chunk_count}")
        assert doc_count == 0, "Database leak detected! patient_documents is not empty."
        assert chunk_count == 0, "Database leak detected! document_chunks is not empty."
        store.close()
        logger.info("MongoDB cleanly wiped and closed. Zero test data retained.")
        logger.info("==================================================================")


if __name__ == "__main__":
    patient = sys.argv[1] if len(sys.argv) > 1 else "PP001_Ananya_Baruah"
    res = run_pipeline_audit(patient)
    print("\nFINAL AUDIT SUMMARY JSON:")
    print(json.dumps(res, indent=2))
