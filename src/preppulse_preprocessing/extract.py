"""
Stage 2 — Extraction (Teammate B).

Takes section-aware chunks and extracts clean clinical facts into the Stage 2
schema via the pluggable LLM provider. Key design choices:

  - SCHEMA-CONSTRAINED, not free-form. We instruct the model to emit JSON with a
    fixed shape and parse/validate it ourselves. Free-form "summaries" are never
    requested (they are the thing that drops a prescription).
  - Provider-agnostic. We call LLMClient.complete_json; Ollama/mock/other are
    interchangeable.
  - Robust parsing. Models sometimes wrap JSON in prose or code fences; we strip
    and recover rather than trust raw output.
  - Terminology mapping happens here (LOINC/RxNorm/ICD-10); unmapped -> None.

Grounding/verification (bbox re-attachment, fail-closed review) is a SEPARATE
pass in ground.py, run after extraction.
"""
from __future__ import annotations

import json
from typing import Any

from preppulse_preprocessing import terminology
from preppulse_preprocessing.providers.base import LLMClient

_SYSTEM = (
    "You are a precise clinical data extractor. You read one section of a medical "
    "document and return ONLY valid JSON. You never invent values. If a field is "
    "not present in the text, omit it or use null. Extract exactly what is written."
)

_INSTRUCTIONS = """Extract clinical facts from the document section below into this JSON shape:

{
  "labs": [
    {"test_name": str, "value": number|null, "unit": str|null,
     "reference_range": str|null, "flag": "HIGH"|"LOW"|"NORMAL"|null,
     "anchor_text": "the exact source substring"}
  ],
  "medications": [
    {"name": str, "dosage": str|null, "frequency": str|null, "route": str|null,
     "anchor_text": "the exact source substring"}
  ],
  "diagnoses": [
    {"description": str, "anchor_text": "the exact source substring"}
  ],
  "vitals": [ {"name": str, "value": str} ],
  "advice": str|null
}

Rules:
- Copy values verbatim. Do NOT convert units or round.
- anchor_text MUST be an exact substring of the section text (used for provenance).
- Omit anything not clearly stated. Never guess a dose, value, or code.
- Return ONLY the JSON object, no commentary.

<<<CHUNK_TEXT>>>
"""


def _parse_json(text: str) -> dict[str, Any]:
    """Recover a JSON object from a model response that may include fences/prose."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    # grab the outermost {...}
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        return {}


def extract_from_chunk(chunk: dict[str, Any], llm: LLMClient) -> dict[str, list[dict[str, Any]]]:
    """Run extraction on a single chunk; returns raw (pre-grounding) entities."""
    user = _INSTRUCTIONS + chunk.get("chunk_text", "")
    resp = llm.complete_json(system=_SYSTEM, user=user)
    data = _parse_json(resp.text)

    page = chunk.get("source_page", 1)
    visit_date = chunk.get("visit_date")

    labs = []
    for lab in data.get("labs", []) or []:
        if not lab.get("test_name"):
            continue
        labs.append({
            "test_name": lab["test_name"],
            "loinc_code": terminology.loinc_for(lab.get("test_name")),
            "value": lab.get("value"),
            "unit": lab.get("unit"),
            "reference_range": lab.get("reference_range"),
            "flag": lab.get("flag"),
            "visit_date": visit_date,
            "source_page": page,
            "anchor_text": lab.get("anchor_text"),
            "confidence": 1.0,  # provisional; ground.py sets the real value
        })

    meds = []
    for med in data.get("medications", []) or []:
        if not med.get("name"):
            continue
        meds.append({
            "name": med["name"],
            "rxnorm_code": terminology.rxnorm_for(med.get("name")),
            "dosage": med.get("dosage"),
            "frequency": med.get("frequency"),
            "route": med.get("route") or "oral",
            "prescribed_date": visit_date,
            "source_page": page,
            "anchor_text": med.get("anchor_text"),
            "confidence": 1.0,
        })

    diags = []
    for dx in data.get("diagnoses", []) or []:
        if not dx.get("description"):
            continue
        diags.append({
            "description": dx["description"],
            "icd10_code": terminology.icd10_for(dx.get("description")),
            "recorded_date": visit_date,
            "source_page": page,
            "anchor_text": dx.get("anchor_text"),
            "confidence": 1.0,
        })

    vitals = [v for v in (data.get("vitals") or []) if isinstance(v, dict)]
    advice = data.get("advice")

    return {"labs": labs, "medications": meds, "diagnoses": diags, "vitals": vitals,
            "advice": [advice] if advice else []}


def extract_document(chunks: list[dict[str, Any]], llm: LLMClient) -> dict[str, Any]:
    """Aggregate extraction across all chunks of a document."""
    agg: dict[str, list[Any]] = {"labs": [], "medications": [], "diagnoses": [], "vitals": [], "advice": []}
    for ch in chunks:
        part = extract_from_chunk(ch, llm)
        for k, v in agg.items():
            v.extend(part.get(k, []))
    # de-duplicate advice; join into one string
    advice = " ".join(dict.fromkeys(a for a in agg["advice"] if a)) or None
    return {
        "labs": agg["labs"],
        "medications": agg["medications"],
        "diagnoses": agg["diagnoses"],
        "vitals": agg["vitals"],
        "advice": advice,
    }
