from __future__ import annotations

from collections.abc import Iterable

from .models import BoundingBox, SourceBoundingBox


def normalize_box(box: SourceBoundingBox, width: float, height: float) -> BoundingBox:
    """Convert an original page box into PrepPulse's stable 0–1000 space."""

    def scale(value: float, dimension: float) -> int:
        return min(1000, max(0, round(1000 * value / dimension)))

    return BoundingBox(
        x0=scale(box.x0, width), y0=scale(box.y0, height),
        x1=scale(box.x1, width), y1=scale(box.y1, height),
    )


def union_source_boxes(boxes: Iterable[SourceBoundingBox]) -> SourceBoundingBox:
    items = list(boxes)
    if not items:
        raise ValueError("cannot calculate a union for no boxes")
    return SourceBoundingBox(
        x0=min(box.x0 for box in items), y0=min(box.y0 for box in items),
        x1=max(box.x1 for box in items), y1=max(box.y1 for box in items),
    )
