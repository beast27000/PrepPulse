from preppulse_ocr.geometry import normalize_box
from preppulse_ocr.models import SourceBoundingBox


def test_normalizes_to_1000_space() -> None:
    box = normalize_box(SourceBoundingBox(x0=10, y0=20, x1=90, y1=180), width=100, height=200)
    assert box.model_dump() == {"x0": 100, "y0": 100, "x1": 900, "y1": 900}
