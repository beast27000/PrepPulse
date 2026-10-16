from preppulse_ocr.geometry import normalize_box
from preppulse_ocr.models import PageDimensions, SourceBoundingBox, Token
from preppulse_ocr.table_reconstruction import reconstruct_table


def make_token(identifier: str, text: str, x0: int, y0: int, x1: int, y1: int) -> Token:
    source = SourceBoundingBox(x0=x0, y0=y0, x1=x1, y1=y1)
    return Token(id=identifier, text=text, source_bbox=source, bbox=normalize_box(source, 1000, 1000))


def test_lab_table_keeps_rows_columns_and_values() -> None:
    tokens = [
        make_token("1", "Analyte", 10, 10, 100, 30),
        make_token("2", "Value", 300, 10, 360, 30),
        make_token("3", "Range", 600, 10, 670, 30),
        make_token("4", "HbA1c", 10, 60, 80, 80),
        make_token("5", "8.2", 300, 60, 340, 80),
        make_token("6", "4.0-5.6", 600, 60, 680, 80),
    ]
    table = reconstruct_table(tokens, PageDimensions(width=1000, height=1000, unit="pixel"))
    assert table is not None
    cells = {(cell.row_index, cell.column_index): cell for cell in table.cells}
    assert any(cell.text == "HbA1c" and cell.row_index == 1 for cell in table.cells)
    assert any(cell.text == "8.2" and cell.row_index == 1 for cell in table.cells)
    assert any(cell.text == "4.0-5.6" and cell.row_index == 1 for cell in table.cells)
    assert cells[(0, 0)].semantic_label == "analyte"
    assert cells[(0, 1)].semantic_label == "observed_value"
