from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DocumentType(StrEnum):
    OUTPATIENT_NOTE = "outpatient_note"
    DISCHARGE_SUMMARY = "discharge_summary"
    LAB_PANEL = "lab_panel"
    REFERRAL_ORDER = "referral_order"


class BoundingBox(BaseModel):
    """A top-left-origin box normalized to PrepPulse's 0–1000 coordinate space."""

    model_config = ConfigDict(frozen=True)

    x0: int = Field(ge=0, le=1000)
    y0: int = Field(ge=0, le=1000)
    x1: int = Field(ge=0, le=1000)
    y1: int = Field(ge=0, le=1000)

    @model_validator(mode="after")
    def has_valid_order(self) -> BoundingBox:
        if self.x0 > self.x1 or self.y0 > self.y1:
            raise ValueError("bounding-box start coordinates must not exceed end coordinates")
        return self


class SourceBoundingBox(BaseModel):
    """Original page-unit box; PDF points for PDFs and pixels for image OCR."""

    model_config = ConfigDict(frozen=True)

    x0: float = Field(ge=0)
    y0: float = Field(ge=0)
    x1: float = Field(ge=0)
    y1: float = Field(ge=0)


class PageDimensions(BaseModel):
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    unit: Literal["pdf_point", "pixel"]


class DocumentMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    patient_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    document_name: str = Field(min_length=1)
    document_type: DocumentType
    encounter_date: date | None = None
    encounter_date_raw: str | None = None
    source_sha256: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Token(BaseModel):
    id: str
    text: str = Field(min_length=1)
    bbox: BoundingBox
    source_bbox: SourceBoundingBox
    confidence: float | None = Field(default=None, ge=0, le=1)
    block_index: int | None = None
    line_index: int | None = None


class Line(BaseModel):
    id: str
    text: str
    bbox: BoundingBox
    source_bbox: SourceBoundingBox
    token_ids: list[str] = Field(min_length=1)


class TableCell(BaseModel):
    row_index: int = Field(ge=0)
    column_index: int = Field(ge=0)
    text: str
    bbox: BoundingBox
    source_bbox: SourceBoundingBox
    token_ids: list[str] = Field(default_factory=list)
    semantic_label: Literal[
        "analyte", "observed_value", "unit", "reference_range", "flag", "unknown"
    ] = "unknown"


class ExtractedTable(BaseModel):
    id: str
    bbox: BoundingBox
    source_bbox: SourceBoundingBox
    cells: list[TableCell] = Field(min_length=1)
    extraction_method: Literal["native", "layout_reconstruction"]


class ParsedPage(BaseModel):
    page_number: int = Field(ge=1)
    dimensions: PageDimensions
    extraction_method: Literal["native_pdf_text", "ocr", "hybrid"]
    tokens: list[Token]
    lines: list[Line]
    tables: list[ExtractedTable] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ParsedDocument(BaseModel):
    metadata: DocumentMetadata
    pages: list[ParsedPage] = Field(min_length=1)

    def write_json(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.model_dump_json(indent=2), encoding="utf-8")
