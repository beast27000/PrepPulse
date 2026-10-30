"""
Tests for the core Stage 2 + Stage 3 logic (no MongoDB needed).

Run with: pytest
These use the deterministic mock provider so they pass offline / in CI with no
Ollama and no network.
"""
from __future__ import annotations

from preppulse_preprocessing.chunk import chunk_document
from preppulse_preprocessing.config import GroundingConfig, LLMConfig
from preppulse_preprocessing.extract import extract_document
from preppulse_preprocessing.fhir import to_fhir_bundle
from preppulse_preprocessing.ground import ground_entities
from preppulse_preprocessing.providers.mock_provider import MockProvider


def test_chunking_is_section_aware(lab_document):
    chunks = chunk_document(lab_document)
    sections = {c["section_type"] for c in chunks}
    assert "labs" in sections
    assert "medications" in sections
    # a dose must never be split from its drug: the med chunk holds both
    med_chunk = next(c for c in chunks if c["section_type"] == "medications")
    assert "Empagliflozin" in med_chunk["chunk_text"]
    assert "10mg" in med_chunk["chunk_text"]
    # every chunk carries geometry
    assert all("source_bbox" in c for c in chunks)


def test_extraction_pulls_coded_facts(lab_document):
    chunks = chunk_document(lab_document)
    llm = MockProvider(LLMConfig(provider="mock"))
    ents = extract_document(chunks, llm)

    labs = {l["test_name"]: l for l in ents["labs"]}
    assert labs["HbA1c"]["value"] == 8.9
    assert labs["HbA1c"]["loinc_code"] == "4548-4"
    assert labs["Fasting Blood Glucose"]["value"] == 11.4

    meds = {m["name"]: m for m in ents["medications"]}
    assert meds["Empagliflozin"]["dosage"] == "10mg"
    assert meds["Empagliflozin"]["rxnorm_code"] == "1545658"

    dx = {d["description"]: d for d in ents["diagnoses"]}
    assert dx["Type 2 Diabetes Mellitus"]["icd10_code"] == "E11.9"


def test_grounding_attaches_bbox_and_verifies(lab_document):
    chunks = chunk_document(lab_document)
    llm = MockProvider(LLMConfig(provider="mock"))
    ents = extract_document(chunks, llm)
    grounded = ground_entities(ents, lab_document, GroundingConfig())

    # all real facts verified, nothing quarantined
    assert grounded["review_queue"] == []
    for lab in grounded["labs"]:
        assert lab["source_bbox"] is not None
        assert len(lab["source_bbox"]) == 4
        assert lab["confidence"] > 0.8


def test_grounding_is_fail_closed():
    """A hallucinated value and a fabricated drug must be quarantined, not kept."""
    full_text = "HbA1c: 8.9 % (4.0 - 6.0) HIGH"
    tokens = [{"text": w, "bbox": [80 + i * 40, 100, 110 + i * 40, 118],
               "confidence": 1.0, "source": "native"}
              for i, w in enumerate(full_text.split())]
    doc = {"stage_1_raw_ocr": {"pages": [{"page_number": 1, "full_text": full_text, "tokens": tokens}]}}

    ents = {
        "labs": [
            {"test_name": "HbA1c", "value": 8.9, "source_page": 1, "anchor_text": "HbA1c: 8.9 %", "confidence": 1.0},
            {"test_name": "HbA1c", "value": 12.5, "source_page": 1, "anchor_text": "HbA1c: 12.5 %", "confidence": 1.0},
        ],
        "medications": [
            {"name": "Metformin", "dosage": "500mg", "source_page": 1,
             "anchor_text": "Metformin 500mg once daily", "confidence": 1.0},
        ],
        "diagnoses": [], "vitals": [], "advice": None,
    }
    grounded = ground_entities(ents, doc, GroundingConfig())
    kept_lab_values = {l["value"] for l in grounded["labs"]}
    assert 8.9 in kept_lab_values
    assert 12.5 not in kept_lab_values           # hallucinated value quarantined
    assert grounded["medications"] == []          # fabricated drug quarantined
    assert len(grounded["review_queue"]) == 2


def test_fhir_bundle_shape(lab_document):
    chunks = chunk_document(lab_document)
    llm = MockProvider(LLMConfig(provider="mock"))
    ents = extract_document(chunks, llm)
    grounded = ground_entities(ents, lab_document, GroundingConfig())
    bundle = to_fhir_bundle(grounded, "b2b5967a")

    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "transaction"
    types = [e["resource"]["resourceType"] for e in bundle["entry"]]
    assert "Patient" in types
    assert "Observation" in types
    assert "MedicationRequest" in types
    assert "Condition" in types
    # LOINC coding present on an Observation
    obs = next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Observation")
    assert obs["code"]["coding"][0]["system"] == "http://loinc.org"
