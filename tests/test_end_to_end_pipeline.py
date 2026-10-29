from __future__ import annotations

import pytest
from langchain_core.documents import Document

from preppulse_agents.graph import create_clinical_review_workflow
from preppulse_agents.schemas import ConsultationBrief
from preppulse_db.mongo_store import MongoStore
from preppulse_rag.chunker import ClinicalProvenanceChunker
from preppulse_rag.retriever import HybridEnsembleRetriever


@pytest.fixture(scope="module")
def mongo_store() -> MongoStore:
    # Connects to local MongoDB for testing
    store = MongoStore(uri="mongodb://localhost:27017", db_name="preppulse")
    store.connect()
    return store


@pytest.fixture(scope="module")
def arvind_patient_chunks(mongo_store: MongoStore) -> list[Document]:
    # Fetches all ingested Stage 1 OCR documents for PP001_Arvind_Narayanan and chunks them
    docs = mongo_store.get_patient_documents("PP001_Arvind_Narayanan")
    if not docs:
        # Fallback query if patient_id was ingested without prefix
        docs = [d for d in mongo_store.list_documents() if "Arvind" in d.get("patient_id", "") or "PP001" in d.get("patient_id", "")]

    assert len(docs) >= 10, f"Expected at least 10 documents for Arvind Narayanan in MongoDB, found {len(docs)}"

    chunker = ClinicalProvenanceChunker(max_tokens_per_chunk=15)
    all_chunks: list[Document] = []
    for doc in docs:
        chunks = chunker.chunk_mongo_document(doc)
        all_chunks.extend(chunks)

    assert len(all_chunks) > 0, "No chunks generated from patient documents"
    return all_chunks


def test_end_to_end_stage1_provenance_integrity(mongo_store: MongoStore):
    # Verifies that raw Stage 1 OCR documents in MongoDB strictly preserve [0, 1000] bounding boxes
    docs = mongo_store.get_patient_documents("PP001_Arvind_Narayanan")
    if not docs:
        docs = [d for d in mongo_store.list_documents() if "PP001" in d.get("patient_id", "")]

    assert len(docs) == 13, f"Expected 13 documents for PP001_Arvind_Narayanan, got {len(docs)}"

    for doc in docs:
        assert doc.get("status") == "stage_1_complete"
        stage1 = doc.get("stage_1_raw_ocr", {})
        pages = stage1.get("pages", [])
        assert len(pages) >= 1
        for page in pages:
            tokens = page.get("tokens", [])
            assert len(tokens) > 0
            for t in tokens[:10]:
                bbox = t.get("bbox", [])
                assert len(bbox) == 4
                assert all(0 <= c <= 1000 for c in bbox), f"Invalid normalized bbox: {bbox}"


def test_end_to_end_hybrid_rag_retrieval(arvind_patient_chunks: list[Document]):
    # Verifies hybrid RAG retrieval precision and latency on Arvind Narayanan 10-year corpus
    retriever = HybridEnsembleRetriever(arvind_patient_chunks)

    # 1. Search for acute admission (COVID-19 2020)
    covid_hits = retriever.retrieve("COVID-19 discharge", top_k=3)
    assert len(covid_hits) > 0
    assert any("covid" in h.page_content.lower() for h in covid_hits)
    assert covid_hits[0].metadata.get("latency_ms") < 100.0

    # 2. Search for Dengue admission (2018)
    dengue_hits = retriever.retrieve("Dengue fever hospital discharge", top_k=3)
    assert len(dengue_hits) > 0
    assert any("dengue" in h.page_content.lower() for h in dengue_hits)

    # 3. Search for Atorvastatin reconciliation (2026)
    ator_hits = retriever.retrieve("Atorvastatin 10mg discontinued", top_k=3)
    assert len(ator_hits) > 0
    assert any("atorvastatin" in h.page_content.lower() for h in ator_hits)


def test_end_to_end_langgraph_clinical_brief(arvind_patient_chunks: list[Document]):
    # Executes the full 8-node LangGraph review pipeline against Arvind Narayanan's 10-year records
    retriever = HybridEnsembleRetriever(arvind_patient_chunks)
    workflow = create_clinical_review_workflow()

    initial_state = {
        "patient_id": "PP001_Arvind_Narayanan",
        "patient_name": "Arvind Narayanan",
        "mrn": "PP-001",
        "age_sex": "48 years / Male",
        "age": 48,
        "gender": "Male",
        "diabetes_type": "Pre-Diabetic",
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
    brief: ConsultationBrief = final_state["final_brief"]

    assert brief is not None
    assert brief.patient_name == "Arvind Narayanan"

    # 1. Verify Dynamic Classification
    assert brief.classification is not None
    assert brief.classification.category == "prediabetic"
    assert "pre" in brief.classification.stage.lower()

    # 2. Verify Metabolic Trajectory & Series
    assert len(brief.trajectory.kpis) >= 2
    hba1c_kpi = next((k for k in brief.trajectory.kpis if k.name == "HbA1c"), None)
    assert hba1c_kpi is not None
    assert "6.2" in hba1c_kpi.value or "5.8" in hba1c_kpi.value
    assert hba1c_kpi.citation is not None
    assert all(0 <= c <= 1000 for c in hba1c_kpi.citation.bbox)

    # 3. Verify Medication Reconciliation (Atorvastatin mismatch detected from Doc 13)
    assert len(brief.mismatches.items) >= 1
    ator_mismatch = next((m for m in brief.mismatches.items if "atorvastatin" in m.title.lower() or "atorvastatin" in m.description.lower()), None)
    assert ator_mismatch is not None
    assert ator_mismatch.source_a_citation is not None
    assert all(0 <= c <= 1000 for c in ator_mismatch.source_a_citation.bbox)

    # 4. Verify Comorbidities & Acute Admissions (Reverse Chronological Priority Findings)
    assert len(brief.priority_findings) >= 2
    titles_combined = " ".join(f.title.lower() for f in brief.priority_findings)
    assert "covid" in titles_combined or "dengue" in titles_combined or "urology" in titles_combined

    # 5. Verify Dynamic Caregiver Prep Sheet (mode == "prep_sheet" with Indic translations)
    assert brief.caregiver_prep.mode == "prep_sheet"
    assert len(brief.caregiver_prep.checklist) >= 3
    for item in brief.caregiver_prep.checklist:
        assert len(item.text_en) > 0
        assert len(item.text_hi) > 0
        assert len(item.text_ta) > 0

    # 6. Verify Smart Assistive Bubbles (Non-Diagnostic)
    assert len(brief.assistive_bubbles) >= 2
    for b in brief.assistive_bubbles:
        assert "?" in b.prompt_text  # Must be an exploratory question, not diagnostic claim
