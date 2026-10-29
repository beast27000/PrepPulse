from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ---------- provenance citation model ----------


class SourceProofCitation(BaseModel):
    # Citation linked to a specific finding for UI bounding-box highlighting
    model_config = ConfigDict(extra="allow")

    document_id: str = ""
    document_title: str = ""
    document_name: str = ""
    encounter_date: str | None = None
    date_formatted: str = ""
    page_number: int = 1
    bbox: list[int] = Field(default_factory=lambda: [0, 0, 1000, 1000])  # [x0, y0, x1, y1] in [0, 1000]
    snippet: str = ""
    extracted_text: str = ""

    def model_post_init(self, context: Any, /) -> None:
        if not self.document_name and self.document_title:
            self.document_name = self.document_title
        elif not self.document_title and self.document_name:
            self.document_title = self.document_name
        if not self.snippet and self.extracted_text:
            self.snippet = self.extracted_text
        elif not self.extracted_text and self.snippet:
            self.extracted_text = self.snippet


# ---------- classification & priority findings ----------


class PatientClassification(BaseModel):
    # Dynamic classification from notes or lab thresholds
    stage: str = "Pre-Diabetic"  # "Non-Diabetic", "Pre-Diabetic", "Type 2 Diabetes"
    category: str = "prediabetic"  # "non_diabetic", "prediabetic", "diabetic"
    diagnostic_basis: str = ""


class PriorityFindingItem(BaseModel):
    # Reverse-chronological clinical finding tile for UI
    finding_id: str
    title: str
    subtitle: str
    status: str = "confirmed"  # "confirmed", "pending_review", "open"
    severity: str = "medium"  # "high", "medium", "low"
    date: str = ""
    citation: SourceProofCitation | None = None
    actions: list[str] = Field(default_factory=lambda: ["accept", "edit", "reject"])


# ---------- longitudinal time series models ----------


class TimeSeriesPoint(BaseModel):
    # Atomic data point for tabular flow and chart plotting
    date: str
    year: int
    value: float
    unit: str
    status: str = "normal"  # "normal", "borderline", "high", "critical"
    citation: SourceProofCitation | None = None


class LongitudinalMetricSeries(BaseModel):
    # Series of measurements over up to 10 years for charts and tables
    metric_name: str  # "HbA1c", "Fasting Glucose", "eGFR", "Urine ACR", "Systolic BP"
    category: str = "glycemic"  # "glycemic", "renal", "cardiac", "vitals"
    points: list[TimeSeriesPoint] = Field(default_factory=list)
    ten_year_trend: str = "stable"  # "worsening", "improving", "stable", "elevated"
    tabular_flow: dict[str, float | None] = Field(default_factory=dict)


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
    citations: list[SourceProofCitation] = Field(default_factory=list)


class RecordMismatches(BaseModel):
    # Category 3: Cross-document clinical conflicts
    items: list[MismatchItem] = Field(default_factory=list)


class ChecklistItem(BaseModel):
    # Action item for caregiver with multi-lingual support
    id: str = ""
    text_en: str
    text_hi: str
    text_ta: str = ""
    text_te: str = ""
    completed: bool = False


class CaregiverPrep(BaseModel):
    # Category 4: Family handoff or prep sheet with multi-lingual support
    mode: str = "prep_sheet"  # "handoff" (diabetic) or "prep_sheet" (prediabetic / non-diabetic)
    active_language: str = "en"  # "en", "hi", "ta", "te"
    checklist: list[ChecklistItem] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    ongoing_issues: list[str] = Field(default_factory=list)
    guidance_notes: str = ""


class SmartPromptBubble(BaseModel):
    # Non-diagnostic assistive prompt bubble
    bubble_id: str
    icon: str = "timeline"
    prompt_text: str
    action_type: str = "open_chart_modal"
    target_series: list[str] = Field(default_factory=list)
    milestone_id: str | None = None


# ---------- unified consultation brief ----------


class ConsultationBrief(BaseModel):
    # Complete pre-consultation workspace brief matching the UI layout
    patient_id: str
    patient_name: str
    age_sex: str = ""
    age: int = 48
    gender: str = "Male"
    mrn: str = ""
    diabetes_type: str = "Pre-Diabetic"
    classification: PatientClassification = Field(default_factory=PatientClassification)
    visit_focus: str = "Metabolic Review"
    trajectory: MetabolicTrajectory = Field(default_factory=MetabolicTrajectory)
    care_gaps: CareGaps = Field(default_factory=CareGaps)
    mismatches: RecordMismatches = Field(default_factory=RecordMismatches)
    caregiver_prep: CaregiverPrep = Field(default_factory=CaregiverPrep)
    priority_findings: list[PriorityFindingItem] = Field(default_factory=list)
    metric_series: list[LongitudinalMetricSeries] = Field(default_factory=list)
    assistive_bubbles: list[SmartPromptBubble] = Field(default_factory=list)
    raw_evidence_count: int = 0
    freshness_score: int = 85
