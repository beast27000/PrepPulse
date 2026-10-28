from __future__ import annotations

import re
import time

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from rank_bm25 import BM25Okapi

from preppulse_rag.llm_provider import LLMFactory

# ---------- clinical tokenizer ----------


def clinical_tokenize(text: str) -> list[str]:
    # Tokenizes text while preserving drug names, decimal numbers, and units
    # Matches words with hyphens, numbers with decimals, and standard alphanumeric tokens
    tokens = re.findall(r"[A-Za-z0-9]+(?:[\.\-][A-Za-z0-9]+)*", text.lower())
    return [t for t in tokens if len(t) > 0]


# ---------- sparse bm25 index ----------


class SparseBM25Index:
    # High-precision sparse retrieval for exact drug names and lab numbers

    def __init__(self, documents: list[Document]) -> None:
        self.documents = documents
        self.corpus = [clinical_tokenize(doc.page_content) for doc in documents]
        self.bm25 = BM25Okapi(self.corpus) if self.corpus else None

    def search(self, query: str, top_k: int = 5) -> list[tuple[Document, float]]:
        # Returns top-k documents scored by BM25
        if not self.bm25 or not self.documents:
            return []
        tokenized_query = clinical_tokenize(query)
        if not tokenized_query:
            return []
        scores = self.bm25.get_scores(tokenized_query)
        ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [(self.documents[i], float(scores[i])) for i in ranked_indices if scores[i] > 0]


# ---------- dense vector index ----------


class DenseVectorIndex:
    # Semantic dense vector index with in-memory cosine similarity

    def __init__(self, documents: list[Document], embeddings: Embeddings | None = None) -> None:
        self.documents = documents
        self.embeddings = embeddings or LLMFactory.get_embeddings()
        self.doc_vectors: list[list[float]] = []
        if documents:
            texts = [d.page_content for d in documents]
            self.doc_vectors = self.embeddings.embed_documents(texts)

    def search(self, query: str, top_k: int = 5, min_score: float = 0.0) -> list[tuple[Document, float]]:
        # Returns top-k documents by cosine similarity above min_score threshold
        if not self.doc_vectors or not self.documents:
            return []
        q_vec = self.embeddings.embed_query(query)
        scores: list[float] = []
        for d_vec in self.doc_vectors:
            dot = sum(a * b for a, b in zip(q_vec, d_vec))
            scores.append(dot)
        ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [(self.documents[i], float(scores[i])) for i in ranked_indices if scores[i] > min_score]


# ---------- hybrid ensemble retriever ----------


class HybridEnsembleRetriever:
    # Fuses BM25 sparse and dense vector results using Reciprocal Rank Fusion (RRF)

    def __init__(
        self,
        documents: list[Document],
        embeddings: Embeddings | None = None,
        bm25_weight: float = 0.5,
        dense_weight: float = 0.5,
        rrf_k: int = 60,
    ) -> None:
        self.documents = documents
        self.bm25_weight = bm25_weight
        self.dense_weight = dense_weight
        self.rrf_k = rrf_k
        self.sparse_index = SparseBM25Index(documents)
        self.dense_index = DenseVectorIndex(documents, embeddings=embeddings)

    def retrieve(
        self,
        query: str,
        patient_id: str | None = None,
        top_k: int = 5,
    ) -> list[Document]:
        # Executes hybrid search with strict patient isolation and latency tracking
        start_time = time.perf_counter()

        # 1. Fetch top candidates from both retrievers
        sparse_hits = self.sparse_index.search(query, top_k=top_k * 2)
        dense_hits = self.dense_index.search(query, top_k=top_k * 2)

        # 2. Reciprocal Rank Fusion
        rrf_scores: dict[str, float] = {}
        doc_map: dict[str, Document] = {}

        for rank, (doc, _) in enumerate(sparse_hits):
            cid = doc.metadata.get("chunk_id", str(id(doc)))
            doc_map[cid] = doc
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (self.bm25_weight / (self.rrf_k + rank + 1))

        for rank, (doc, _) in enumerate(dense_hits):
            cid = doc.metadata.get("chunk_id", str(id(doc)))
            doc_map[cid] = doc
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (self.dense_weight / (self.rrf_k + rank + 1))

        # 3. Sort by fused score
        sorted_cids = sorted(rrf_scores.keys(), key=lambda c: rrf_scores[c], reverse=True)

        results: list[Document] = []
        for cid in sorted_cids:
            doc = doc_map[cid]
            # Strict patient boundary isolation check
            if patient_id and doc.metadata.get("patient_id") != patient_id:
                continue
            doc.metadata["rrf_score"] = rrf_scores[cid]
            results.append(doc)
            if len(results) >= top_k:
                break

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        for doc in results:
            doc.metadata["latency_ms"] = elapsed_ms

        return results

    def as_tool(self, patient_id: str | None = None):
        # Exposes retriever as a standard LangChain Tool for LangGraph agents
        from langchain_core.tools import Tool

        def _tool_query(query: str) -> str:
            hits = self.retrieve(query, patient_id=patient_id, top_k=4)
            if not hits:
                return "No matching clinical evidence found."
            formatted = []
            for h in hits:
                bbox_str = str(h.metadata.get("bbox", []))
                doc_file = h.metadata.get("source_file", "unknown")
                page = h.metadata.get("page_number", 1)
                formatted.append(f"[{doc_file} p.{page} bbox:{bbox_str}]: {h.page_content}")
            return "\n\n".join(formatted)

        return Tool(
            name="clinical_chart_retriever",
            description="Searches patient clinical records, prescriptions, and lab panels. Returns evidence with source bounding boxes.",
            func=_tool_query,
        )
