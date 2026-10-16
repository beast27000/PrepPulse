from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import fitz
import pytesseract
from PIL import Image

from .geometry import normalize_box, union_source_boxes
from .models import (
    DocumentMetadata,
    DocumentType,
    Line,
    PageDimensions,
    ParsedDocument,
    ParsedPage,
    SourceBoundingBox,
    Token,
)
from .table_reconstruction import reconstruct_table


@dataclass(frozen=True)
class PipelineConfig:
    native_word_threshold: int = 8
    render_dpi: int = 300
    tesseract_config: str = "--oem 1 --psm 6"


class OcrPipeline:
    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()

    def parse(self, input_path: Path, metadata: DocumentMetadata) -> ParsedDocument:
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
        pdf = fitz.open(path)
        try:
            return [self._parse_pdf_page(pdf, index, document_type) for index in range(len(pdf))]
        finally:
            pdf.close()

    def _parse_pdf_page(self, pdf: fitz.Document, index: int, document_type: DocumentType) -> ParsedPage:
        page = pdf[index]
        words = page.get_text("words", sort=True)
        if len(words) >= self.config.native_word_threshold:
            dimensions = PageDimensions(width=page.rect.width, height=page.rect.height, unit="pdf_point")
            tokens = self._native_tokens(words, dimensions)
            return self._build_page(index + 1, dimensions, "native_pdf_text", tokens, document_type)
        pixmap = page.get_pixmap(dpi=self.config.render_dpi, alpha=False)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        return self._ocr_image(image, index + 1, document_type)

    def _parse_image(self, path: Path, page_number: int, document_type: DocumentType) -> ParsedPage:
        with Image.open(path) as image:
            return self._ocr_image(image.convert("RGB"), page_number, document_type)

    def _native_tokens(self, words: list[tuple], dimensions: PageDimensions) -> list[Token]:
        tokens: list[Token] = []
        for index, word in enumerate(words):
            box = SourceBoundingBox(x0=word[0], y0=word[1], x1=word[2], y1=word[3])
            tokens.append(Token(
                id=f"token-{index + 1}", text=word[4], bbox=normalize_box(box, dimensions.width, dimensions.height),
                source_bbox=box, confidence=1.0, block_index=word[5], line_index=word[6],
            ))
        return tokens

    def _ocr_image(self, image: Image.Image, page_number: int, document_type: DocumentType) -> ParsedPage:
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

    def _build_page(self, page_number: int, dimensions: PageDimensions, extraction_method: str, tokens: list[Token], document_type: DocumentType) -> ParsedPage:
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
        groups: dict[tuple[int | None, int | None], list[Token]] = {}
        for token in tokens:
            groups.setdefault((token.block_index, token.line_index), []).append(token)
        lines: list[Line] = []
        for index, group in enumerate(groups.values(), start=1):
            ordered = sorted(group, key=lambda token: token.source_bbox.x0)
            source_bbox = union_source_boxes(token.source_bbox for token in ordered)
            lines.append(Line(
                id=f"line-{index}", text=" ".join(token.text for token in ordered),
                bbox=normalize_box(source_bbox, dimensions.width, dimensions.height),
                source_bbox=source_bbox, token_ids=[token.id for token in ordered],
            ))
        return lines

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
