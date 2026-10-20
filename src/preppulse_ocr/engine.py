from __future__ import annotations

import argparse
import hashlib
import shutil
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from itertools import pairwise
from pathlib import Path
from statistics import median
from typing import Literal

import fitz
import pytesseract
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------- data models ----------

class DocumentType(StrEnum):
    """Supported clinical document categories."""
    OUTPATIENT_NOTE = "outpatient_note"
    DISCHARGE_SUMMARY = "discharge_summary"
    LAB_PANEL = "lab_panel"
    REFERRAL_ORDER = "referral_order"


class BoundingBox(BaseModel):
    """Normalized top-left box in 0-1000 space."""
    model_config = ConfigDict(frozen=True)

    x0: int = Field(ge=0, le=1000)
    y0: int = Field(ge=0, le=1000)
    x1: int = Field(ge=0, le=1000)
    y1: int = Field(ge=0, le=1000)

    @model_validator(mode="after")
    def has_valid_order(self) -> BoundingBox:
        # /3 ensure min coordinates do not exceed max coordinates
        if self.x0 > self.x1 or self.y0 > self.y1:
            raise ValueError("bounding-box start coordinates must not exceed end coordinates")
        return self


class SourceBoundingBox(BaseModel):
    """Original page coordinate box in points or pixels."""
    model_config = ConfigDict(frozen=True)

    x0: float = Field(ge=0)
    y0: float = Field(ge=0)
    x1: float = Field(ge=0)
    y1: float = Field(ge=0)


class PageDimensions(BaseModel):
    """Page dimension metadata and units."""
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    unit: Literal["pdf_point", "pixel"]


class DocumentMetadata(BaseModel):
    """Clinical document identifier and provenance metadata."""
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
    """Word-level token with dual coordinates and OCR confidence."""
    id: str
    text: str = Field(min_length=1)
    bbox: BoundingBox
    source_bbox: SourceBoundingBox
    confidence: float | None = Field(default=None, ge=0, le=1)
    block_index: int | None = None
    line_index: int | None = None


class Line(BaseModel):
    """Reconstructed text line composed of tokens."""
    id: str
    text: str
    bbox: BoundingBox
    source_bbox: SourceBoundingBox
    token_ids: list[str] = Field(min_length=1)


class TableCell(BaseModel):
    """Structured table cell mapped to row and column indices."""
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
    """Structured table containing cell records."""
    id: str
    bbox: BoundingBox
    source_bbox: SourceBoundingBox
    cells: list[TableCell] = Field(min_length=1)
    extraction_method: Literal["native", "layout_reconstruction"]


class ParsedPage(BaseModel):
    """Page containing tokens, reconstructed lines, and tables."""
    page_number: int = Field(ge=1)
    dimensions: PageDimensions
    extraction_method: Literal["native_pdf_text", "ocr", "hybrid"]
    tokens: list[Token]
    lines: list[Line]
    tables: list[ExtractedTable] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ParsedDocument(BaseModel):
    """Complete document extraction payload with metadata."""
    metadata: DocumentMetadata
    pages: list[ParsedPage] = Field(min_length=1)

    def write_json(self, output_path: Path) -> None:
        # /3 write durable structured OCR json to destination
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.model_dump_json(indent=2), encoding="utf-8")


# ---------- geometry helpers ----------

def normalize_box(box: SourceBoundingBox, width: float, height: float) -> BoundingBox:
    """Scale source coordinates to normalized 0-1000 space."""
    def scale(value: float, dimension: float) -> int:
        return min(1000, max(0, round(1000 * value / dimension)))

    return BoundingBox(
        x0=scale(box.x0, width), y0=scale(box.y0, height),
        x1=scale(box.x1, width), y1=scale(box.y1, height),
    )


def union_source_boxes(boxes: Iterable[SourceBoundingBox]) -> SourceBoundingBox:
    """Compute the union envelope covering all given source boxes."""
    items = list(boxes)
    if not items:
        raise ValueError("cannot calculate a union for no boxes")
    return SourceBoundingBox(
        x0=min(b.x0 for b in items), y0=min(b.y0 for b in items),
        x1=max(b.x1 for b in items), y1=max(b.y1 for b in items),
    )


# ---------- table reconstruction ----------

HEADER_LABELS = {
    "analyte": "analyte",
    "test": "analyte",
    "result": "observed_value",
    "value": "observed_value",
    "unit": "unit",
    "range": "reference_range",
    "reference": "reference_range",
    "flag": "flag",
}


def reconstruct_table(tokens: list[Token], dimensions: PageDimensions) -> ExtractedTable | None:
    """Cluster tokens into table rows and columns using 2D geometric alignment."""
    if not tokens:
        return None

    # /3 group tokens into rows based on median height tolerance
    row_tolerance = max(12, int(median([t.bbox.y1 - t.bbox.y0 for t in tokens]) * 0.8))
    rows: list[list[Token]] = []
    for token in sorted(tokens, key=lambda item: ((item.bbox.y0 + item.bbox.y1) / 2, item.bbox.x0)):
        center = (token.bbox.y0 + token.bbox.y1) / 2
        matching = next(
            (r for r in rows if abs(center - sum((t.bbox.y0 + t.bbox.y1) / 2 for t in r) / len(r)) <= row_tolerance),
            None,
        )
        if matching is None:
            rows.append([token])
        else:
            matching.append(token)

    # /3 compute column anchor clusters from horizontal gaps
    x_centers = sorted((t.bbox.x0 + t.bbox.x1) / 2 for t in tokens)
    gaps = [right - left for left, right in pairwise(x_centers)]
    gap_threshold = max(45, int(median(gaps) * 2)) if gaps else 45
    anchors: list[float] = []
    for center in x_centers:
        if not anchors or center - anchors[-1] > gap_threshold:
            anchors.append(center)
        else:
            anchors[-1] = (anchors[-1] + center) / 2

    # /3 map grouped tokens to row and column grid cells
    cells: list[TableCell] = []
    semantic_by_column: dict[int, str] = defaultdict(lambda: "unknown")
    for row_index, row in enumerate(rows):
        groups: dict[int, list[Token]] = defaultdict(list)
        for token in sorted(row, key=lambda item: item.bbox.x0):
            column = min(range(len(anchors)), key=lambda idx: abs(anchors[idx] - (token.bbox.x0 + token.bbox.x1) / 2))
            groups[column].append(token)
        for column_index, group in groups.items():
            text = " ".join(t.text for t in group)
            if row_index == 0:
                normalized_header = text.lower().strip().replace(" ", "")
                semantic_by_column[column_index] = next(
                    (lbl for key, lbl in HEADER_LABELS.items() if key in normalized_header), "unknown"
                )
            source_bbox = union_source_boxes(t.source_bbox for t in group)
            cells.append(TableCell(
                row_index=row_index, column_index=column_index, text=text,
                bbox=normalize_box(source_bbox, dimensions.width, dimensions.height),
                source_bbox=source_bbox, token_ids=[t.id for t in group],
                semantic_label=semantic_by_column[column_index],
            ))

    source_bbox = union_source_boxes(t.source_bbox for t in tokens)
    return ExtractedTable(
        id="table-1", bbox=normalize_box(source_bbox, dimensions.width, dimensions.height),
        source_bbox=source_bbox, cells=cells, extraction_method="layout_reconstruction",
    )


# ---------- OCR pipeline & router ----------

@dataclass(frozen=True)
class PipelineConfig:
    """Extraction tuning parameters."""
    native_word_threshold: int = 8
    min_image_area_ratio: float = 0.02
    full_page_image_threshold: float = 0.70
    render_dpi: int = 300
    tesseract_config: str = "--oem 1 --psm 6"


class OcrPipeline:
    """Hybrid document parser dispatching between PyMuPDF text and Tesseract OCR."""

    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()
        self._configure_tesseract()

    @staticmethod
    def _configure_tesseract() -> None:
        # /3 auto-detect Tesseract binary on standard Windows path if missing from PATH
        if shutil.which("tesseract"):
            return
        windows_binary = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        if windows_binary.is_file():
            pytesseract.pytesseract.tesseract_cmd = str(windows_binary)

    def parse(self, input_path: Path, metadata: DocumentMetadata) -> ParsedDocument:
        """Parse digital PDF, scanned PDF, or image file into structured provenance document."""
        path = Path(input_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        hashed_metadata = metadata.model_copy(update={"source_sha256": self._sha256(path)})
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            pages = self._parse_pdf(path, hashed_metadata.document_type)
        elif suffix in {".png", ".jpg", ".jpeg"}:
            pages = [self._parse_image(path, 1, hashed_metadata.document_type)]
        else:
            raise ValueError(f"Unsupported document type: {suffix}")
        return ParsedDocument(metadata=hashed_metadata, pages=pages)

    def _parse_pdf(self, path: Path, document_type: DocumentType) -> list[ParsedPage]:
        # /3 open PDF and process each page independently
        pdf = fitz.open(path)
        try:
            return [self._parse_pdf_page(pdf, idx, document_type) for idx in range(len(pdf))]
        finally:
            pdf.close()

    def _parse_pdf_page(self, pdf: fitz.Document, index: int, document_type: DocumentType) -> ParsedPage:
        # /3 inspect digital words and embedded image regions for structural routing
        page = pdf[index]
        words = page.get_text("words", sort=True)
        images = page.get_image_info(xrefs=True)
        page_area = max(1.0, page.rect.width * page.rect.height)

        # /3 check for full-page background scan
        has_full_scan = any(
            (fitz.Rect(img["bbox"]).width * fitz.Rect(img["bbox"]).height) / page_area >= self.config.full_page_image_threshold
            for img in images
        )
        if len(words) == 0 or (has_full_scan and len(words) < 15):
            pixmap = page.get_pixmap(dpi=self.config.render_dpi, alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            return self._ocr_image(image, index + 1, document_type)

        dimensions = PageDimensions(width=page.rect.width, height=page.rect.height, unit="pdf_point")
        tokens = self._native_tokens(words, dimensions)
        hybrid_tokens: list[Token] = []

        # /3 crop and OCR embedded image regions within the page
        for img_idx, img in enumerate(images):
            rect = fitz.Rect(img["bbox"]) & page.rect
            area_ratio = (rect.width * rect.height) / page_area
            if area_ratio < self.config.min_image_area_ratio or rect.width < 30 or rect.height < 30:
                continue
            region_tokens = self._ocr_image_region(page, rect, dimensions, img_idx)
            for rt in region_tokens:
                if not any(self._boxes_overlap(rt.bbox, nt.bbox) for nt in tokens):
                    hybrid_tokens.append(rt)

        extraction_method = "hybrid" if hybrid_tokens else "native_pdf_text"
        tokens.extend(hybrid_tokens)
        return self._build_page(index + 1, dimensions, extraction_method, tokens, document_type)

    def _ocr_image_region(
        self, page: fitz.Page, rect: fitz.Rect, dimensions: PageDimensions, image_index: int,
    ) -> list[Token]:
        # /3 crop and OCR embedded image region, mapping coordinates back to page points
        pixmap = page.get_pixmap(clip=rect, dpi=self.config.render_dpi, alpha=False)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        data = pytesseract.image_to_data(image, config=self.config.tesseract_config, output_type=pytesseract.Output.DICT)
        scale_x = rect.width / max(1, image.width)
        scale_y = rect.height / max(1, image.height)
        tokens: list[Token] = []
        for idx, text in enumerate(data["text"]):
            if not text.strip() or int(float(data["conf"][idx])) < 0:
                continue
            left, top = data["left"][idx], data["top"][idx]
            w, h = data["width"][idx], data["height"][idx]
            source_box = SourceBoundingBox(
                x0=rect.x0 + (left * scale_x),
                y0=rect.y0 + (top * scale_y),
                x1=rect.x0 + ((left + w) * scale_x),
                y1=rect.y0 + ((top + h) * scale_y),
            )
            tokens.append(Token(
                id=f"img-{image_index}-token-{len(tokens) + 1}", text=text,
                bbox=normalize_box(source_box, dimensions.width, dimensions.height),
                source_bbox=source_box, confidence=float(data["conf"][idx]) / 100,
                block_index=200 + image_index, line_index=data["line_num"][idx],
            ))
        return tokens

    @staticmethod
    def _boxes_overlap(b1: BoundingBox, b2: BoundingBox, threshold: float = 0.5) -> bool:
        # /3 test if two bounding boxes overlap significantly
        x_left = max(b1.x0, b2.x0)
        y_top = max(b1.y0, b2.y0)
        x_right = min(b1.x1, b2.x1)
        y_bottom = min(b1.y1, b2.y1)
        if x_right <= x_left or y_bottom <= y_top:
            return False
        intersection = (x_right - x_left) * (y_bottom - y_top)
        min_area = min((b1.x1 - b1.x0) * (b1.y1 - b1.y0), (b2.x1 - b2.x0) * (b2.y1 - b2.y0))
        return (intersection / min_area) >= threshold if min_area > 0 else False

    def _parse_image(self, path: Path, page_number: int, document_type: DocumentType) -> ParsedPage:
        # /3 parse standalone image via OCR
        with Image.open(path) as image:
            return self._ocr_image(image.convert("RGB"), page_number, document_type)

    def _native_tokens(self, words: list[tuple], dimensions: PageDimensions) -> list[Token]:
        # /3 convert PyMuPDF word tuples to structured tokens
        tokens: list[Token] = []
        for index, word in enumerate(words):
            box = SourceBoundingBox(x0=word[0], y0=word[1], x1=word[2], y1=word[3])
            tokens.append(Token(
                id=f"token-{index + 1}", text=word[4], bbox=normalize_box(box, dimensions.width, dimensions.height),
                source_bbox=box, confidence=1.0, block_index=word[5], line_index=word[6],
            ))
        return tokens

    def _ocr_image(self, image: Image.Image, page_number: int, document_type: DocumentType) -> ParsedPage:
        # /3 run Tesseract OCR on rendered page image and build word tokens
        dimensions = PageDimensions(width=image.width, height=image.height, unit="pixel")
        data = pytesseract.image_to_data(image, config=self.config.tesseract_config, output_type=pytesseract.Output.DICT)
        tokens: list[Token] = []
        for index, text in enumerate(data["text"]):
            if not text.strip() or int(float(data["conf"][index])) < 0:
                continue
            box = SourceBoundingBox(
                x0=data["left"][index], y0=data["top"][index],
                x1=data["left"][index] + data["width"][index], y1=data["top"][index] + data["height"][index],
            )
            tokens.append(Token(
                id=f"token-{len(tokens) + 1}", text=text, bbox=normalize_box(box, dimensions.width, dimensions.height),
                source_bbox=box, confidence=float(data["conf"][index]) / 100,
                block_index=data["block_num"][index], line_index=data["line_num"][index],
            ))
        return self._build_page(page_number, dimensions, "ocr", tokens, document_type)

    def _build_page(
        self, page_number: int, dimensions: PageDimensions, extraction_method: str,
        tokens: list[Token], document_type: DocumentType,
    ) -> ParsedPage:
        # /3 assemble reconstructed lines and lab tables for page
        lines = self._lines(tokens, dimensions)
        tables = []
        warnings = []
        if document_type == DocumentType.LAB_PANEL:
            table = reconstruct_table(tokens, dimensions)
            if table is None:
                warnings.append("No text tokens available for lab-table reconstruction.")
            else:
                tables.append(table)
        return ParsedPage(
            page_number=page_number, dimensions=dimensions, extraction_method=extraction_method,
            tokens=tokens, lines=lines, tables=tables, warnings=warnings,
        )

    @staticmethod
    def _lines(tokens: list[Token], dimensions: PageDimensions) -> list[Line]:
        # /3 group tokens into lines using block and line indices
        groups: dict[tuple[int | None, int | None], list[Token]] = {}
        for token in tokens:
            groups.setdefault((token.block_index, token.line_index), []).append(token)
        lines: list[Line] = []
        for index, group in enumerate(groups.values(), start=1):
            ordered = sorted(group, key=lambda t: t.source_bbox.x0)
            source_bbox = union_source_boxes(t.source_bbox for t in ordered)
            lines.append(Line(
                id=f"line-{index}", text=" ".join(t.text for t in ordered),
                bbox=normalize_box(source_bbox, dimensions.width, dimensions.height),
                source_bbox=source_bbox, token_ids=[t.id for t in ordered],
            ))
        return lines

    @staticmethod
    def _sha256(path: Path) -> str:
        # /3 calculate SHA-256 source document hash
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()


# ---------- CLI entry point ----------

def main() -> None:
    parser = argparse.ArgumentParser(description="Extract provenance-preserving PrepPulse OCR JSON.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--patient-id", required=True)
    parser.add_argument("--document-id")
    parser.add_argument("--document-type", required=True, choices=[item.value for item in DocumentType])
    parser.add_argument("--encounter-date", type=date.fromisoformat)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    metadata = DocumentMetadata(
        patient_id=args.patient_id, document_id=args.document_id or args.input.stem,
        document_name=args.input.name, document_type=DocumentType(args.document_type),
        encounter_date=args.encounter_date,
    )
    result = OcrPipeline().parse(args.input, metadata)
    result.write_json(args.output)


if __name__ == "__main__":
    main()
