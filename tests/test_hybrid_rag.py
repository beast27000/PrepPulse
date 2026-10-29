import time

import pytest
from langchain_core.documents import Document

from preppulse_rag.chunker import ClinicalProvenanceChunker
from preppulse_rag.llm_provider import LLMFactory
from preppulse_rag.retriever import HybridEnsembleRetriever, SparseBM25Index

# ---------- test fixtures ----------


@pytest.fixture
def sample_patient_documents() -> list[Document]:
    # Provides test chunks representing two different patients with bounding boxes
    return [
        Document(
            page_content="Rx: Empagliflozin 10mg once daily oral. Strict diet compliance.",
            metadata={
                "chunk_id": "doc_williams_rx_1",
                "patient_id": "patient_williams",
                "document_id": "williams_rx_2024",
                "source_file": "prescription_20240601.pdf",
                "page_number": 1,
                "visit_date": "2024-06-01",
                "bbox": [80, 210, 400, 230],
            },
        ),
        Document(
            page_content="Glycaemic Panel | HbA1c: 8.9 % HIGH | Fasting Blood Glucose: 11.4 mmol/L",
            metadata={
                "chunk_id": "doc_williams_lab_1",
                "patient_id": "patient_williams",
                "document_id": "williams_lab_2024",
                "source_file": "lab_report_20240601.pdf",
                "page_number": 2,
                "visit_date": "2024-06-01",
                "bbox": [120, 340, 600, 420],
            },
        ),
        Document(
            page_content="Metformin 500mg twice daily with meals.",
            metadata={
                "chunk_id": "doc_tanaka_rx_1",
                "patient_id": "patient_tanaka",
                "document_id": "tanaka_rx_2023",
                "source_file": "prescription_tanaka.pdf",
                "page_number": 1,
                "visit_date": "2023-05-01",
                "bbox": [90, 180, 350, 210],
            },
        ),
    ]


# ---------- tests ----------


def test_chunker_provenance_and_bounding_boxes():
    # Verifies that chunker computes valid normalized [0, 1000] bounding boxes
    chunker = ClinicalProvenanceChunker(max_tokens_per_chunk=10)
    mock_mongo_doc = {
        "document_id": "test_doc_100",
        "patient_id": "patient_test",
        "visit_date": "2024-03-14",
        "document_type": "lab_report",
        "source_file": "test_lab.pdf",
        "stage_1_raw_ocr": {
            "pages": [
                {
                    "page_number": 1,
                    "tokens": [
                        {"text": "HbA1c:", "bbox": [100, 200, 150, 220]},
                        {"text": "8.4%", "bbox": [160, 200, 210, 220]},
                    ],
                    "tables": [
                        {
                            "table_id": 0,
                            "bbox": [50, 300, 800, 500],
                            "rows": [["Test", "Result"], ["eGFR", "68"]],
                        }
                    ],
                }
            ]
        },
    }

    chunks = chunker.chunk_mongo_document(mock_mongo_doc)
    assert len(chunks) >= 2

    # Check table chunk
    table_chunks = [c for c in chunks if c.metadata.get("is_table")]
    assert len(table_chunks) >= 2
    assert any("eGFR | 68" in c.page_content for c in table_chunks)
    assert all(c.metadata["bbox"] == [50, 300, 800, 500] for c in table_chunks)

    # Check text chunk and bounding box coordinates
    text_chunk = next(c for c in chunks if not c.metadata.get("is_table"))
    assert "HbA1c" in text_chunk.page_content
    bbox = text_chunk.metadata["bbox"]
    assert len(bbox) == 4
    assert bbox[0] == 100 and bbox[1] == 200 and bbox[2] == 210 and bbox[3] == 220


def test_sparse_bm25_exact_medication_100_percent_precision(sample_patient_documents: list[Document]):
    # Acceptance Criteria 1: Retrieval for exact medication names achieves 100% precision
    bm25_index = SparseBM25Index(sample_patient_documents)

    results = bm25_index.search("Empagliflozin 10mg", top_k=1)
    assert len(results) == 1
    top_doc, score = results[0]
    assert score > 0
    assert "Empagliflozin 10mg" in top_doc.page_content
    assert top_doc.metadata["patient_id"] == "patient_williams"

    # Exact search for Metformin
    results_metformin = bm25_index.search("Metformin", top_k=1)
    assert len(results_metformin) == 1
    assert "Metformin 500mg" in results_metformin[0][0].page_content


def test_hybrid_latency_under_500ms(sample_patient_documents: list[Document]):
    # Acceptance Criteria 2: Hybrid query latency remains strictly under 500ms
    retriever = HybridEnsembleRetriever(sample_patient_documents)

    start = time.perf_counter()
    results = retriever.retrieve("glycaemic HbA1c blood glucose", top_k=2)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert len(results) > 0
    assert elapsed_ms < 500.0
    # Latency should typically be sub-50ms
    assert elapsed_ms < 100.0


def test_patient_isolation_boundary(sample_patient_documents: list[Document]):
    # Verifies queries scoped to Patient A never leak Patient B documents
    retriever = HybridEnsembleRetriever(
        sample_patient_documents,
        embeddings=LLMFactory.get_embeddings(provider="mock"),
    )

    # Search for Metformin (which belongs to Tanaka) scoped to Williams
    williams_results = retriever.retrieve("Metformin", patient_id="patient_williams", top_k=5)
    assert len(williams_results) == 0

    # Search for Metformin scoped to Tanaka
    tanaka_results = retriever.retrieve("Metformin", patient_id="patient_tanaka", top_k=5)
    assert len(tanaka_results) == 1
    assert tanaka_results[0].metadata["patient_id"] == "patient_tanaka"


def test_plug_and_play_llm_factory():
    # Verifies factory returns working chat models and embeddings across configurations
    model = LLMFactory.get_chat_model(provider="mock")
    assert model is not None

    embeddings = LLMFactory.get_embeddings(provider="mock")
    vec = embeddings.embed_query("test clinical query")
    assert len(vec) == 128
