"""SQLite system of record for OCR documents and source evidence."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import ParsedDocument

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS patients (
  patient_id TEXT PRIMARY KEY, mrn TEXT NOT NULL, display_name TEXT
);
CREATE TABLE IF NOT EXISTS documents (
  document_id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(patient_id),
  document_name TEXT NOT NULL, document_type TEXT NOT NULL, encounter_date TEXT,
  source_path TEXT NOT NULL, source_sha256 TEXT, extraction_path TEXT, status TEXT NOT NULL,
  error_message TEXT
);
CREATE TABLE IF NOT EXISTS pages (
  document_id TEXT NOT NULL REFERENCES documents(document_id), page_number INTEGER NOT NULL,
  width REAL NOT NULL, height REAL NOT NULL, unit TEXT NOT NULL, extraction_method TEXT NOT NULL,
  PRIMARY KEY (document_id, page_number)
);
CREATE TABLE IF NOT EXISTS evidence_anchors (
  anchor_id INTEGER PRIMARY KEY AUTOINCREMENT, document_id TEXT NOT NULL,
  page_number INTEGER NOT NULL, anchor_type TEXT NOT NULL, source_id TEXT NOT NULL,
  text TEXT NOT NULL, bbox_json TEXT NOT NULL, source_bbox_json TEXT NOT NULL,
  confidence REAL, table_row INTEGER, table_column INTEGER,
  UNIQUE(document_id, page_number, anchor_type, source_id)
);
"""


class SqliteStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)

    def close(self) -> None:
        self.connection.close()

    def is_ingested(self, document_id: str) -> bool:
        row = self.connection.execute(
            "SELECT status FROM documents WHERE document_id = ?", (document_id,)
        ).fetchone()
        return row is not None and row["status"] == "ingested"

    def save_document(
        self, parsed: ParsedDocument, source_path: Path, extraction_path: Path, mrn: str, display_name: str | None,
    ) -> None:
        metadata = parsed.metadata
        with self.connection:
            self.connection.execute(
                "INSERT INTO patients(patient_id, mrn, display_name) VALUES(?, ?, ?) "
                "ON CONFLICT(patient_id) DO UPDATE SET mrn=excluded.mrn, display_name=excluded.display_name",
                (metadata.patient_id, mrn, display_name),
            )
            self.connection.execute(
                "INSERT INTO documents(document_id, patient_id, document_name, document_type, encounter_date, "
                "source_path, source_sha256, extraction_path, status, error_message) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, 'ingested', NULL) "
                "ON CONFLICT(document_id) DO UPDATE SET source_path=excluded.source_path, "
                "source_sha256=excluded.source_sha256, extraction_path=excluded.extraction_path, status='ingested', error_message=NULL",
                (metadata.document_id, metadata.patient_id, metadata.document_name, metadata.document_type.value,
                 metadata.encounter_date.isoformat() if metadata.encounter_date else None, str(source_path),
                 metadata.source_sha256, str(extraction_path)),
            )
            self.connection.execute("DELETE FROM pages WHERE document_id = ?", (metadata.document_id,))
            self.connection.execute("DELETE FROM evidence_anchors WHERE document_id = ?", (metadata.document_id,))
            for page in parsed.pages:
                self.connection.execute(
                    "INSERT INTO pages VALUES (?, ?, ?, ?, ?, ?)",
                    (metadata.document_id, page.page_number, page.dimensions.width, page.dimensions.height,
                     page.dimensions.unit, page.extraction_method),
                )
                anchors = [("token", token.id, token.text, token.bbox, token.source_bbox, token.confidence, None, None)
                           for token in page.tokens]
                anchors += [("line", line.id, line.text, line.bbox, line.source_bbox, None, None, None)
                            for line in page.lines]
                for table in page.tables:
                    anchors += [
                        ("table_cell", f"{table.id}:{cell.row_index}:{cell.column_index}", cell.text, cell.bbox,
                         cell.source_bbox, None, cell.row_index, cell.column_index)
                        for cell in table.cells
                    ]
                self.connection.executemany(
                    "INSERT INTO evidence_anchors(document_id, page_number, anchor_type, source_id, text, bbox_json, "
                    "source_bbox_json, confidence, table_row, table_column) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [(metadata.document_id, page.page_number, anchor_type, source_id, text,
                      json.dumps(bbox.model_dump()), json.dumps(source_bbox.model_dump()), confidence, row, column)
                     for anchor_type, source_id, text, bbox, source_bbox, confidence, row, column in anchors],
                )

    def save_error(self, document_id: str, patient_id: str, mrn: str, source_path: Path, message: str) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO patients(patient_id, mrn) VALUES(?, ?) ON CONFLICT(patient_id) DO NOTHING",
                (patient_id, mrn),
            )
            self.connection.execute(
                "INSERT INTO documents(document_id, patient_id, document_name, document_type, source_path, status, error_message) "
                "VALUES (?, ?, ?, 'unknown', ?, 'failed', ?) "
                "ON CONFLICT(document_id) DO UPDATE SET status='failed', error_message=excluded.error_message",
                (document_id, patient_id, source_path.name, str(source_path), message),
            )

    def documents_for_patient(self, patient_id: str) -> list[sqlite3.Row]:
        return self.connection.execute(
            "SELECT * FROM documents WHERE patient_id = ? ORDER BY document_type", (patient_id,)
        ).fetchall()

    def anchors_for_page(self, document_id: str, page_number: int) -> list[sqlite3.Row]:
        return self.connection.execute(
            "SELECT * FROM evidence_anchors WHERE document_id = ? AND page_number = ? "
            "ORDER BY CASE anchor_type WHEN 'line' THEN 0 WHEN 'table_cell' THEN 1 ELSE 2 END, anchor_id",
            (document_id, page_number),
        ).fetchall()
