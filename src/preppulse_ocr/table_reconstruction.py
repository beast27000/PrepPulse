from __future__ import annotations

from collections import defaultdict
from itertools import pairwise
from statistics import median

from .geometry import normalize_box, union_source_boxes
from .models import ExtractedTable, PageDimensions, TableCell, Token

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
    """Deterministically form a grid from OCR token geometry.

    This conservative fallback is intentionally structural: it never invents a value or
    discards a token. A production layout engine can replace it while preserving this schema.
    """
    if not tokens:
        return None

    row_tolerance = max(12, int(median([token.bbox.y1 - token.bbox.y0 for token in tokens]) * 0.8))
    rows: list[list[Token]] = []
    for token in sorted(tokens, key=lambda item: ((item.bbox.y0 + item.bbox.y1) / 2, item.bbox.x0)):
        center = (token.bbox.y0 + token.bbox.y1) / 2
        matching = next(
            (row for row in rows if abs(center - sum((t.bbox.y0 + t.bbox.y1) / 2 for t in row) / len(row)) <= row_tolerance),
            None,
        )
        if matching is None:
            rows.append([token])
        else:
            matching.append(token)

    x_centers = sorted((token.bbox.x0 + token.bbox.x1) / 2 for token in tokens)
    gaps = [right - left for left, right in pairwise(x_centers)]
    gap_threshold = max(45, int(median(gaps) * 2)) if gaps else 45
    anchors: list[float] = []
    for center in x_centers:
        if not anchors or center - anchors[-1] > gap_threshold:
            anchors.append(center)
        else:
            anchors[-1] = (anchors[-1] + center) / 2

    cells: list[TableCell] = []
    semantic_by_column: dict[int, str] = defaultdict(lambda: "unknown")
    for row_index, row in enumerate(rows):
        groups: dict[int, list[Token]] = defaultdict(list)
        for token in sorted(row, key=lambda item: item.bbox.x0):
            column = min(range(len(anchors)), key=lambda index: abs(anchors[index] - (token.bbox.x0 + token.bbox.x1) / 2))
            groups[column].append(token)
        for column_index, group in groups.items():
            text = " ".join(token.text for token in group)
            if row_index == 0:
                normalized_header = text.lower().strip().replace(" ", "")
                semantic_by_column[column_index] = next(
                    (label for key, label in HEADER_LABELS.items() if key in normalized_header), "unknown"
                )
            source_bbox = union_source_boxes(token.source_bbox for token in group)
            cells.append(TableCell(
                row_index=row_index, column_index=column_index, text=text,
                bbox=normalize_box(source_bbox, dimensions.width, dimensions.height),
                source_bbox=source_bbox, token_ids=[token.id for token in group],
                semantic_label=semantic_by_column[column_index],
            ))

    source_bbox = union_source_boxes(token.source_bbox for token in tokens)
    return ExtractedTable(
        id="table-1", bbox=normalize_box(source_bbox, dimensions.width, dimensions.height),
        source_bbox=source_bbox, cells=cells, extraction_method="layout_reconstruction",
    )
