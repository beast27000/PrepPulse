from __future__ import annotations

from typing import Any

from langchain_core.documents import Document

# ---------- bbox union helper ----------


def union_boxes(boxes: list[list[int]]) -> list[int]:
    # Computes enclosing bounding box for a list of [x0, y0, x1, y1] boxes
    if not boxes:
        return [0, 0, 0, 0]
    return [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]


# ---------- provenance chunker ----------


class ClinicalProvenanceChunker:
    # Transforms multi-stage MongoDB patient documents into LangChain Documents with coordinates

    def __init__(self, max_tokens_per_chunk: int = 120) -> None:
        self.max_tokens_per_chunk = max_tokens_per_chunk

    def chunk_mongo_document(self, mongo_doc: dict[str, Any]) -> list[Document]:
        # Chunks a single document from patient_documents collection
        document_id = mongo_doc.get("document_id", "unknown_doc")
        patient_id = mongo_doc.get("patient_id", "unknown_patient")
        visit_date = mongo_doc.get("visit_date")
        document_type = mongo_doc.get("document_type", "clinical_record")
        source_file = mongo_doc.get("source_file", "")

        stage1 = mongo_doc.get("stage_1_raw_ocr", {})
        pages = stage1.get("pages", [])
        stage2 = mongo_doc.get("stage_2_structured_entities")

        # Resolve calendar year for longitudinal indexing
        year: int | None = None
        if visit_date:
            try:
                year = int(str(visit_date).split("-")[0])
            except (ValueError, IndexError):
                year = None
        if year is None and source_file:
            import re
            m = re.search(r"(\d{4})", source_file)
            if m:
                year = int(m.group(1))

        documents: list[Document] = []

        for page in pages:
            page_num = page.get("page_number", 1)
            tokens = page.get("tokens", [])
            tables = page.get("tables", [])

            # 1. Chunk tables: keep each table row atomic with enclosing bbox
            for table in tables:
                table_bbox = table.get("bbox") or [0, 0, 1000, 1000]
                for r_idx, row in enumerate(table.get("rows", [])):
                    row_text = " | ".join(c.strip() for c in row if c.strip())
                    if not row_text:
                        continue
                    meta = {
                        "chunk_id": f"{document_id}_p{page_num}_tbl_{r_idx}",
                        "patient_id": patient_id,
                        "document_id": document_id,
                        "source_file": source_file,
                        "document_type": document_type,
                        "visit_date": visit_date,
                        "year": year,
                        "page_number": page_num,
                        "bbox": table_bbox,
                        "is_table": True,
                    }
                    documents.append(Document(page_content=row_text, metadata=meta))

            # 2. Chunk text tokens into coherent lines/phrases
            if tokens:
                current_tokens: list[dict[str, Any]] = []
                for token in tokens:
                    current_tokens.append(token)
                    text = token.get("text", "")
                    # Split on sentence punctuation when minimum token length reached or token limit
                    if (
                        (len(current_tokens) >= 5 and text.endswith((".", ";")))
                        or len(current_tokens) >= self.max_tokens_per_chunk
                    ):
                        chunk_text = " ".join(t.get("text", "") for t in current_tokens).strip()
                        chunk_bbox = union_boxes([t.get("bbox", [0, 0, 0, 0]) for t in current_tokens])
                        meta = {
                            "chunk_id": f"{document_id}_p{page_num}_txt_{len(documents)}",
                            "patient_id": patient_id,
                            "document_id": document_id,
                            "source_file": source_file,
                            "document_type": document_type,
                            "visit_date": visit_date,
                            "year": year,
                            "page_number": page_num,
                            "bbox": chunk_bbox,
                            "is_table": False,
                        }
                        documents.append(Document(page_content=chunk_text, metadata=meta))
                        current_tokens = []

                if current_tokens:
                    chunk_text = " ".join(t.get("text", "") for t in current_tokens).strip()
                    chunk_bbox = union_boxes([t.get("bbox", [0, 0, 0, 0]) for t in current_tokens])
                    meta = {
                        "chunk_id": f"{document_id}_p{page_num}_txt_{len(documents)}",
                        "patient_id": patient_id,
                        "document_id": document_id,
                        "source_file": source_file,
                        "document_type": document_type,
                        "visit_date": visit_date,
                        "year": year,
                        "page_number": page_num,
                        "bbox": chunk_bbox,
                        "is_table": False,
                    }
                    documents.append(Document(page_content=chunk_text, metadata=meta))

            # If no tokens available, fall back to page full text
            elif page.get("full_text"):
                for idx, line in enumerate(page["full_text"].splitlines()):
                    line_clean = line.strip()
                    if not line_clean:
                        continue
                    meta = {
                        "chunk_id": f"{document_id}_p{page_num}_line_{idx}",
                        "patient_id": patient_id,
                        "document_id": document_id,
                        "source_file": source_file,
                        "document_type": document_type,
                        "visit_date": visit_date,
                        "page_number": page_num,
                        "bbox": [0, 0, 1000, 1000],
                        "is_table": False,
                    }
                    documents.append(Document(page_content=line_clean, metadata=meta))

        # Forward-compatible: enrich metadata if Stage 2 structured entities exist
        if stage2:
            self._enrich_with_stage2(documents, stage2)

        return documents

    def _enrich_with_stage2(self, documents: list[Document], stage2: dict[str, Any]) -> None:
        # Enriches chunk metadata with LOINC, RxNorm, and diagnoses when available
        med_codes = {m.get("name", "").lower(): m.get("rxnorm_code") for m in stage2.get("medications", []) if m.get("name")}
        lab_codes = {l.get("test_name", "").lower(): l.get("loinc_code") for l in stage2.get("labs", []) if l.get("test_name")}

        for doc in documents:
            content_lower = doc.page_content.lower()
            for med_name, code in med_codes.items():
                if med_name in content_lower and code:
                    doc.metadata["rxnorm_code"] = code
            for lab_name, code in lab_codes.items():
                if lab_name in content_lower and code:
                    doc.metadata["loinc_code"] = code
