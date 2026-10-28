from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# ---------- provenance citation model ----------


class SourceProofCitation(BaseModel):
    # Citation linked to a specific finding for UI bounding-box highlighting
    model_config = ConfigDict(extra="allow")

    document_name: str
    encounter_date: str | None = None
    page_number: int = 1
    bbox: list[int] = Field(..., min_length=4, max_length=4)  # [x0, y0, x1, y1] in [0, 1000]
    snippet: str


# ---------- core review category models ----------


class KpiMetric(BaseModel):
    # Single metabolic KPI metric with trajectory direction
    name: str  # "HbA1c", "Fasting glucose", "eGFR"
    value: str
    unit: str
    date_str: str
    trend_direction: str = "stable"  # "up", "down", "stable"
    citation: SourceProofCitation | None = None


class MetabolicTrajectory(BaseModel):
    # Category 1: Longitudinal metabolic progression
    kpis: list[KpiMetric] = Field(default_factory=list)
    summary: str = ""


class CareGapItem(BaseModel):
    # Overdue screening or missing clinical order
    title: str
    details: str
    severity: str = "warning"  # "warning", "critical", "info"
    citation: SourceProofCitation | None = None


class CareGaps(BaseModel):
    # Category 2: Screenings and follow-ups still to close
    items: list[CareGapItem] = Field(default_factory=list)


class MismatchItem(BaseModel):
    # Discrepancy between two medical records
    title: str
    description: str
    source_a_citation: SourceProofCitation | None = None
    source_b_citation: SourceProofCitation | None = None


class RecordMismatches(BaseModel):
    # Category 3: Cross-document clinical conflicts
    items: list[MismatchItem] = Field(default_factory=list)


class ChecklistItem(BaseModel):
    # Action item for caregiver with bilingual support
    text_en: str
    text_hi: str
    completed: bool = False


class CaregiverPrep(BaseModel):
    # Category 4: Family handoff prep sheet with EN / HI translations
    active_language: str = "en"  # "en" or "hi"
    checklist: list[ChecklistItem] = Field(default_factory=list)
    guidance_notes: str = ""


# ---------- unified consultation brief ----------


class ConsultationBrief(BaseModel):
    # Complete pre-consultation workspace brief matching the UI layout
    patient_id: str
    patient_name: str
    age_sex: str
    mrn: str
    diabetes_type: str
    visit_focus: str
    trajectory: MetabolicTrajectory
    care_gaps: CareGaps
    mismatches: RecordMismatches
    caregiver_prep: CaregiverPrep
    raw_evidence_count: int = 0
