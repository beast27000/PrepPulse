"""Cited OCR occurrence tables for conditions outside the numerical chart tool."""

import re

from preppulse_api.chart_intent import CARDIAC, CHART_WORDS
from preppulse_api.evidence_catalog import citation_for, row_evidence


def occurrence_rows(store, patient_id: str, question: str) -> tuple[list[dict], int]:
    if re.search(CARDIAC, question, re.IGNORECASE):
        pattern = r"heart|cardiac|coronary|cardio|ejection|lvef|troponin|\becg\b|\bekg\b|echo|angina|myocard|hypertens"
    elif re.search(r"cholesterol|lipid|\bldl\b|\bhdl\b|triglycerid", question, re.IGNORECASE):
        pattern = r"cholesterol|lipid|\bldl\b|\bhdl\b|triglycerid"
    else:
        cleaned = re.sub(rf"\b(?:{CHART_WORDS})\b", "", question, flags=re.IGNORECASE)
        stop = {
            "please",
            "generate",
            "patient",
            "patients",
            "history",
            "years",
            "past",
            "last",
            "show",
            "make",
            "draw",
            "give",
            "this",
            "that",
            "with",
            "from",
            "charts",
            "condition",
            "disease",
            "records",
            "reports",
            "values",
            "about",
            "could",
            "would",
            "information",
            "occurrences",
            "list",
            "every",
            "look",
        }
        words = [word for word in re.findall(r"[a-z]{4,}", cleaned.lower()) if word not in stop]
        if not words:
            return [], 0
        pattern = "|".join(re.escape(word) for word in words[:12])
    parsed = {
        doc["document_id"]: doc
        for doc in store.db.patient_documents.find({"patient_id": patient_id})
    }
    rows = []
    total = 0
    for record in store.db.workspace_documents.find({"patient_id": patient_id}).sort(
        "visit_date", 1
    ):
        doc = parsed.get(record["record_id"])
        if not doc:
            continue
        for page in doc.get("stage_1_raw_ocr", {}).get("pages", []):
            for row in row_evidence(page):
                if re.search(pattern, row["text"], re.IGNORECASE):
                    total += 1
                    if len(rows) < 200:
                        rows.append(
                            {
                                "date": record.get("visit_date")
                                or doc.get("visit_date")
                                or "Date not recorded",
                                "text": row["text"],
                                "citation": citation_for(record, row),
                            }
                        )
    return rows, total


def occurrence_table(rows: list[dict], total: int, add_source) -> str:
    if not rows:
        return "No matching OCR occurrences were found for that topic in the currently processed patient records. You can still ask for a cited narrative review of the available reports."
    lines = [
        "### Matching documented occurrences",
        "",
        "The dates below identify source records; they do not establish diagnosis or event dates.",
        "",
        "| Source record date | Recorded text / values | Source |",
        "| --- | --- | --- |",
    ]
    for row in rows:
        index = add_source(row["citation"], row["text"], row["date"])
        text = row["text"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {row['date']} | {text} | [{index}] |")
    if total > len(rows):
        lines.extend(
            [
                "",
                f"Found {total} matching OCR rows; showing the first {len(rows)}. Browse the patient's records for the remaining occurrences.",
            ]
        )
    return "\n".join(lines)
