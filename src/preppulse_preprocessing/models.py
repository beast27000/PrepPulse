"""
Stage 2 output models.

These intentionally mirror the owners' `preppulse_db.schemas` field-for-field
(LabEntity, MedicationEntity, DiagnosisEntity, Stage2StructuredEntities,
DocumentChunk) so that anything we write validates cleanly against their store
and a future merge needs no reshaping. All models allow extra fields
(`extra="allow"`) exactly as theirs do, so the LLM may add allergies, vitals,
surgical_history, etc. without validation errors.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class LabEntity(BaseModel):
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
    model_config = ConfigDict(extra="allow")
    description: str
    icd10_code: str | None = None
    recorded_date: str | None = None
    source_page: int = 1
    source_bbox: list[int] | None = None
    confidence: float = 1.0


class Stage2StructuredEntities(BaseModel):
    model_config = ConfigDict(extra="allow")
    schema_version: str = "1.0"
    compiled_at: str = Field(default_factory=_utc_now_iso)
    compiled_by: str = "preprocessing_layer_v1"
    patient: dict[str, Any] | None = None
    labs: list[LabEntity] = Field(default_factory=list)
    medications: list[MedicationEntity] = Field(default_factory=list)
    diagnoses: list[DiagnosisEntity] = Field(default_factory=list)
    vitals: list[dict[str, Any]] = Field(default_factory=list)
    advice: str | None = None
    flags: list[str] = Field(default_factory=list)
    # review_queue holds facts that failed grounding/verification (fail-closed).
    review_queue: list[dict[str, Any]] = Field(default_factory=list)


class DocumentChunk(BaseModel):
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
