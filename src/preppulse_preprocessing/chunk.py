"""
Stage 2 — Chunking (Teammate A).

Reads a Stage 1 document's pages and splits each page into SECTION-AWARE chunks,
never fixed-size windows, so a dose is never severed from its drug and a lab
value never severed from its test name. Each chunk keeps:
  - section_type   (normalized label: medications / labs / assessment / ...)
  - chunk_text     (the section's text)
  - source_page    (page it came from)
  - source_bbox    (union bbox over the tokens that fall in the section)

The section detector is generic (header heuristics, not per-file templates) per
Principle A, so it degrades gracefully on arbitrary layouts: if no headers are
found, the whole page becomes one "body" chunk.
"""
from __future__ import annotations

import re
from typing import Any

# header text -> normalized section_type. Broad + extensible.
_SECTION_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(lab(oratory)?\s+(report|results?)|glycaemic\s+panel|biochemistry|haematology|renal|lipid)\b", re.IGNORECASE), "labs"),
    (re.compile(r"\b(rx|medications?|current\s+medications?|discharge\s+medications?|prescription)\b", re.IGNORECASE), "medications"),
    (re.compile(r"\b(diagnosis|assessment|impression|problem\s+list)\b", re.IGNORECASE), "assessment"),
    (re.compile(r"\b(plan|advice|follow[\s-]?up|recommendation)\b", re.IGNORECASE), "plan"),
    (re.compile(r"\b(history|hospital\s+course|reason\s+for\s+(admission|referral)|subjective)\b", re.IGNORECASE), "history"),
    (re.compile(r"\b(demographics?|patient\s+(details|information|record))\b", re.IGNORECASE), "demographics"),
    (re.compile(r"\b(findings?|interpretation|objective)\b", re.IGNORECASE), "findings"),
    (re.compile(r"\b(vitals?|observations?)\b", re.IGNORECASE), "vitals"),
]


def _classify_header(line: str) -> str | None:
    s = line.strip()
    if not s or len(s) > 70:
        return None
    # headers tend to be short, title/upper case, often ending with ':'
    looks_header = (s.isupper() or s.endswith(":") or s.istitle() or len(s.split()) <= 5)
    if not looks_header:
        return None
    for pat, label in _SECTION_RULES:
        if pat.search(s):
            return label
    return None


def _union_bbox(bboxes: list[list[int]]) -> list[int] | None:
    pts = [b for b in bboxes if b and len(b) == 4]
    if not pts:
        return None
    x0 = min(b[0] for b in pts); y0 = min(b[1] for b in pts)
    x1 = max(b[2] for b in pts); y1 = max(b[3] for b in pts)
    return [x0, y0, x1, y1]


def _tokens_for_text(line_text: str, tokens: list[dict[str, Any]]) -> list[list[int]]:
    """Best-effort: collect bboxes of tokens whose text appears in the line."""
    words = {w.strip(":%(),") for w in line_text.split() if w.strip()}
    out = []
    for t in tokens:
        if t.get("text", "").strip(":%(),") in words:
            out.append(t.get("bbox"))
    return out


def chunk_document(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a list of chunk dicts (DocumentChunk-shaped) for one Stage 1 doc."""
    document_id = doc["document_id"]
    patient_id = doc["patient_id"]
    visit_date = doc.get("visit_date")
    document_type = doc.get("document_type")
    stage1 = doc.get("stage_1_raw_ocr", {})
    pages = stage1.get("pages", [])

    chunks: list[dict[str, Any]] = []
    seq = 0
    for page in pages:
        page_no = page.get("page_number", 1)
        tokens = page.get("tokens", [])
        full_text = page.get("full_text", "")
        lines = [ln for ln in full_text.split("\n")]

        # walk lines, opening a new section when a header line is seen
        current_label = "body"
        current_lines: list[str] = []

        def flush(label: str, body_lines: list[str], p_no: int, p_tokens: list[dict[str, Any]]) -> None:
            nonlocal seq
            text = "\n".join(l for l in body_lines).strip()
            if not text:
                return
            bboxes: list[list[int]] = []
            for bl in body_lines:
                bboxes.extend(_tokens_for_text(bl, p_tokens))
            seq += 1
            chunks.append({
                "chunk_id": f"{document_id}_p{p_no}_c{seq}",
                "document_id": document_id,
                "patient_id": patient_id,
                "visit_date": visit_date,
                "document_type": document_type,
                "section_type": label,
                "chunk_text": text,
                "source_page": p_no,
                "source_bbox": _union_bbox(bboxes),
            })

        for ln in lines:
            label = _classify_header(ln)
            if label is not None:
                # header starts a new section: flush the previous one first
                flush(current_label, current_lines, page_no, tokens)
                current_label = label
                current_lines = [ln]  # keep the header line in the section
            else:
                current_lines.append(ln)
        flush(current_label, current_lines, page_no, tokens)

        # fallback: a page with no detected sections becomes one body chunk
        if not any(c["source_page"] == page_no for c in chunks) and full_text.strip():
            seq += 1
            chunks.append({
                "chunk_id": f"{document_id}_p{page_no}_c{seq}",
                "document_id": document_id,
                "patient_id": patient_id,
                "visit_date": visit_date,
                "document_type": document_type,
                "section_type": "body",
                "chunk_text": full_text.strip(),
                "source_page": page_no,
                "source_bbox": _union_bbox([t.get("bbox") for t in tokens]),
            })

    return chunks
