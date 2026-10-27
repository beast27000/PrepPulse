from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ==============================================================================
# TEAMMATE HANDOFF NOTES:
# 1. WHAT IS DONE (STAGE 1):
#    - Raw OCR text, word tokens, and [0, 1000] bounding boxes are extracted
#      from patient PDFs/images and stored in MongoDB under `stage_1_raw_ocr`.
# 2. WHAT YOU NEED TO DO (STAGE 2):
#    - Teammate A: Split stage_1 raw text into sections with source bounding boxes (DocumentChunk).
#    - Teammate B: Run local LLM (Qwen via Ollama) on chunks to pull clinical facts (labs, meds, diagnoses).
# 3. WHY USE AN LLM HERE:
#    - Hospital documents come in random, unstructured formats with doctor notes and theory.
#    - An LLM reliably extracts facts from messy text without needing rigid regex rules.
#    - All Stage 2 models use `extra="allow"` so ANY new clinical field discovered
#      by the LLM (e.g. allergies, surgical history, vitals) is automatically accepted and preserved.
# ==============================================================================

# ---------- helpers ----------


def _utc_now_iso() -> str:
    # Returns current UTC timestamp in ISO-8601 format
    return datetime.now(UTC).isoformat()


# ---------- stage 1: raw ocr models ----------


class TokenRecord(BaseModel):
    # Token with text, normalized bbox [0, 1000], and confidence
    text: str
    bbox: list[int] = Field(..., min_length=4, max_length=4)
    confidence: float = 1.0
    source: str = "ocr"


class TableRecord(BaseModel):
    # Reconstructed table grid with cell rows and outer bbox
    table_id: int
    rows: list[list[str]] = Field(default_factory=list)
    bbox: list[int] | None = None


class PageRecord(BaseModel):
    # Single page record with tokens and reconstructed tables
    page_number: int
    extraction_method: str = "native_pdf"
    full_text: str = ""
    tokens: list[TokenRecord] = Field(default_factory=list)
    tables: list[TableRecord] = Field(default_factory=list)


class Stage1RawOcr(BaseModel):
    # Full Stage 1 OCR container holding all pages and geometry
    engine_version: str = "1.0.0-frozen"
    processed_at: str = Field(default_factory=_utc_now_iso)
    page_count: int = 1
    pages: list[PageRecord] = Field(default_factory=list)


# ---------- stage 2: structured entities models ----------


class LabEntity(BaseModel):
    # Extracted lab test observation - permits extra fields dynamically
    model_config = ConfigDict(extra="allow")

    test_name: str
    loinc_code: str | None = None
    value: float | None = None
    unit: str | None = None
    reference_range: str | None = None
    flag: str | None = None
    visit_date: str | None = None
    source_page: int = 1
    source_bbox: list[int] | None = None
    confidence: float = 1.0
    anchor_text: str | None = None


class MedicationEntity(BaseModel):
    # Extracted medication prescription entity - permits extra fields dynamically
    model_config = ConfigDict(extra="allow")

    name: str
    rxnorm_code: str | None = None
    dosage: str | None = None
    frequency: str | None = None
    route: str | None = "oral"
    prescribed_date: str | None = None
    source_page: int = 1
    source_bbox: list[int] | None = None
    confidence: float = 1.0
    anchor_text: str | None = None


class DiagnosisEntity(BaseModel):
    # Extracted clinical condition or diagnosis - permits extra fields dynamically
    model_config = ConfigDict(extra="allow")

    description: str
    icd10_code: str | None = None
    recorded_date: str | None = None
    source_page: int = 1
    source_bbox: list[int] | None = None
    confidence: float = 1.0


class Stage2StructuredEntities(BaseModel):
    # Stage 2 container populated by LLM extraction pipeline - extra fields allowed dynamically
    model_config = ConfigDict(extra="allow")

    schema_version: str = "1.0"
    compiled_at: str = Field(default_factory=_utc_now_iso)
    compiled_by: str = "preprocessing_layer"
    patient: dict[str, Any] | None = None
    labs: list[LabEntity] = Field(default_factory=list)
    medications: list[MedicationEntity] = Field(default_factory=list)
    diagnoses: list[DiagnosisEntity] = Field(default_factory=list)
    vitals: list[dict[str, Any]] = Field(default_factory=list)
    advice: str | None = None
    flags: list[str] = Field(default_factory=list)


# ---------- primary document container ----------


class PatientDocument(BaseModel):
    # Compound MongoDB document holding all 3 stages for one file
    model_config = ConfigDict(extra="allow")

    document_id: str
    patient_id: str
    visit_date: str | None = None
    document_type: str
    document_form: str | None = None
    source_file: str
    requires_ocr: bool = False
    degradation: str | None = None
    status: str = "stage_1_complete"
    ingested_at: str = Field(default_factory=_utc_now_iso)
    stage_1_raw_ocr: Stage1RawOcr
    stage_2_structured_entities: Stage2StructuredEntities | None = None
    stage_3_fhir_output: dict[str, Any] | None = None


# ---------- intermediate chunk container ----------


class DocumentChunk(BaseModel):
    # Intermediate chunk produced by Teammate A for Teammate B
    model_config = ConfigDict(extra="allow")

    chunk_id: str
    document_id: str
    patient_id: str
    visit_date: str | None = None
    document_type: str | None = None
    section_type: str
    chunk_text: str
    source_page: int = 1
    source_bbox: list[int] | None = None
    created_at: str = Field(default_factory=_utc_now_iso)
