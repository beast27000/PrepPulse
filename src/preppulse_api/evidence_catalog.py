"""Patient-owned OCR evidence used by summaries, chart tools, and chat."""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from typing import Any

from preppulse_api.store import WorkspaceStore

METRICS = (
    ("HbA1c", r"\bhba1c\b|glycated ha?emoglobin", "%", 2, 25),
    (
        "Fasting glucose",
        r"fasting\s+(?:plasma\s+|blood\s+)?glucose|\bfpg\b|\bfbs\b",
        "mg/dL",
        30,
        700,
    ),
    (
        "Post-meal glucose",
        r"(?:2.hour\s+)?post.meal\s+(?:blood\s+)?glucose|\bppbs\b",
        "mg/dL",
        30,
        900,
    ),
    ("eGFR", r"\begfr\b", "mL/min/1.73m²", 2, 200),
    ("Urine ACR", r"urine\s+acr|urine\s+albumin.?creatinine\s+ratio|\buacr\b", "mg/g", 0, 10000),
    ("Creatinine", r"(?:serum\s+)?creatinine\b", "mg/dL", 0.1, 25),
    ("LDL cholesterol", r"\bldl(?:\s+cholesterol)?\b", "mg/dL", 10, 400),
)


def row_evidence(page: dict) -> list[dict]:
    """Reconstruct OCR rows while keeping exact normalized token geometry."""
    rows: list[list[dict]] = []
    for token in sorted(
        page.get("tokens", []), key=lambda t: ((t["bbox"][1] + t["bbox"][3]) / 2, t["bbox"][0])
    ):
        box = token.get("bbox", [])
        if len(box) != 4 or not token.get("text", "").strip():
            continue
        center = (box[1] + box[3]) / 2
        if (
            rows
            and abs(
                center - sum((t["bbox"][1] + t["bbox"][3]) / 2 for t in rows[-1]) / len(rows[-1])
            )
            <= 5
        ):
            rows[-1].append(token)
        else:
            rows.append([token])
    result = []
    for row in rows:
        row.sort(key=lambda token: token["bbox"][0])
        boxes = [token["bbox"] for token in row]
        result.append(
            {
                "text": " ".join(token["text"] for token in row).strip(),
                "bbox": [
                    min(b[0] for b in boxes),
                    min(b[1] for b in boxes),
                    max(b[2] for b in boxes),
                    max(b[3] for b in boxes),
                ],
                "page_number": page["page_number"],
            }
        )
    return result


def citation_for(record: dict, row: dict) -> dict:
    return {
        "document_id": record["record_id"],
        "document_title": record["filename"],
        "page_number": row["page_number"],
        "bbox": row["bbox"],
        "snippet": row["text"],
        "extracted_text": row["text"],
        "date_formatted": record.get("visit_date") or "",
        "source_verified": True,
    }


def readable_filename(filename: str) -> str:
    text = re.sub(r"^\d+_\d{4}-\d{2}-\d{2}_", "", filename)
    return re.sub(r"\.[^.]+$", "", text).replace("_", " ").strip()


def build_catalog(store: WorkspaceStore, patient_id: str) -> dict:
    records = list(
        store.db.workspace_documents.find(
            {"patient_id": patient_id}, {"_id": 0, "source_path": 0}
        ).sort("visit_date", 1)
    )
    parsed = {
        doc["document_id"]: doc
        for doc in store.db.patient_documents.find({"patient_id": patient_id}, {"_id": 0})
    }
    observations: dict[tuple[str, str, str], dict] = {}
    summaries = []
    for record in records:
        doc = parsed.get(record["record_id"])
        if not doc:
            continue
        rows = [
            row
            for page in doc.get("stage_1_raw_ocr", {}).get("pages", [])
            for row in row_evidence(page)
        ]
        is_lab = record.get("document_type") in {"lab", "lab_report"} or bool(
            re.search(r"lab|profile|panel", record["filename"], re.IGNORECASE)
        )
        date = record.get("visit_date") or doc.get("visit_date") or ""
        record_metrics = []
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            for row in rows:
                bp = re.search(
                    r"\b(?:blood pressure|bp)\s*[:=]?\s*(\d{2,3})\s*/\s*(\d{2,3})\b",
                    row["text"],
                    re.IGNORECASE,
                )
                if bp and 60 <= int(bp[1]) <= 260 and 30 <= int(bp[2]) <= 160:
                    for name, value in (("Systolic BP", bp[1]), ("Diastolic BP", bp[2])):
                        observations.setdefault(
                            (name, date, record["record_id"]),
                            {
                                "metric": name,
                                "date": date,
                                "year": int(date[:4]),
                                "value": float(value),
                                "unit": "mmHg",
                                "citation": citation_for(record, row),
                            },
                        )
        if is_lab and re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            for row in rows:
                for metric, pattern, unit, low, high in METRICS:
                    match = re.search(pattern, row["text"], re.IGNORECASE)
                    if not match:
                        continue
                    tail = row["text"][match.end() :]
                    # Narrative mentions and reference-only statements are not measurements.
                    number = re.match(r"\s*[:=|]?\s*(\d+(?:\.\d+)?)\b", tail)
                    if not number or not low <= float(number[1]) <= high:
                        continue
                    point = {
                        "date": date,
                        "year": int(date[:4]),
                        "value": float(number[1]),
                        "unit": unit,
                        "citation": citation_for(record, row),
                    }
                    key = (metric, date, record["record_id"])
                    if key not in observations:
                        observations[key] = {"metric": metric, **point}
                        record_metrics.append(f"{metric} {number[1]} {unit}")
        other = bool(
            re.search(
                r"discharge|coronary|angiography|pci|dengue|urolog|surgery|procedure|cardiac|cardiol",
                record["filename"],
                re.IGNORECASE,
            )
        )
        title = readable_filename(record["filename"])
        ranked = []
        for index, row in enumerate(rows):
            text = row["text"]
            if len(text) < 18 or re.search(
                r"sample was received|routine validated|source.?preserv|page \d|specimen|accession|identifiers matching|where applicable",
                text,
                re.IGNORECASE,
            ):
                continue
            nearby = text + " " + (rows[index + 1]["text"] if index + 1 < len(rows) else "")
            mentioned_years = [int(year) for year in re.findall(r"\b(?:19|20)\d{2}\b", nearby)]
            if date and mentioned_years and max(mentioned_years) > int(date[:4]):
                continue
            score = 0
            score += 7 * bool(
                re.search(
                    r"new diagnosis|type 2 diabetes|underwent|admitted|stent|angioplasty|dengue|discharged|clinical impression|assessment",
                    text,
                    re.IGNORECASE,
                )
            )
            score += 4 * bool(
                re.search(
                    r"metformin|insulin|glyc|hba1c|diabet|blood pressure|hypertension|renal|follow.up",
                    text,
                    re.IGNORECASE,
                )
            )
            score += 10 * bool(
                re.search(
                    r"new diagnosis|dengue fever|coronary artery|proximal lad|successful pci|drug.eluting|exertional|chest discomfort",
                    text,
                    re.IGNORECASE,
                )
            )
            if re.search(r"prescription", record["filename"], re.IGNORECASE):
                score += 10 * bool(
                    re.search(r"\bmg\b|tablet|aspirin|metformin|clopidogrel", text, re.IGNORECASE)
                )
            score -= 6 * bool(
                re.search(
                    r"patient:|patient name|name:|date of birth|laboratory investigation|no known drug allergy",
                    text,
                    re.IGNORECASE,
                )
            )
            if score > 0:
                ranked.append((score, index, row))
        chosen = []
        used: set[int] = set()
        for _, index, row in sorted(ranked, key=lambda item: (-item[0], item[1])):
            if index in used:
                continue
            parts = [row]
            used.add(index)
            if not is_lab and not re.search(r"prescription", record["filename"], re.IGNORECASE):
                for following in range(index + 1, min(index + 3, len(rows))):
                    next_row = rows[following]
                    if (
                        next_row["page_number"] != row["page_number"]
                        or next_row["text"].isupper()
                        or next_row["bbox"][1] - parts[-1]["bbox"][3] > 22
                    ):
                        break
                    if len(" ".join(part["text"] for part in parts)) > 260:
                        break
                    parts.append(next_row)
                    used.add(following)
            boxes = [part["bbox"] for part in parts]
            combined_text = " ".join(part["text"] for part in parts)
            future_years = [int(year) for year in re.findall(r"\b(?:19|20)\d{2}\b", combined_text)]
            if "where applicable" in combined_text.lower() or (
                date and future_years and max(future_years) > int(date[:4])
            ):
                continue
            chosen.append(
                {
                    "text": combined_text,
                    "page_number": row["page_number"],
                    "bbox": [
                        min(b[0] for b in boxes),
                        min(b[1] for b in boxes),
                        max(b[2] for b in boxes),
                        max(b[3] for b in boxes),
                    ],
                }
            )
            if len(chosen) >= 4:
                break
        if not chosen and rows:
            chosen = [rows[min(3, len(rows) - 1)]]
        evidence = [{"text": row["text"], "citation": citation_for(record, row)} for row in chosen]
        summary = (
            "; ".join(record_metrics[:3])
            if record_metrics
            else " ".join(item["text"] for item in evidence[:2])
        )
        summaries.append(
            {
                "record_id": record["record_id"],
                "date": date,
                "title": title,
                "category": "other_history" if other else "diabetes_history",
                "summary": summary[:420],
                "evidence": evidence,
                "citation": evidence[0]["citation"] if evidence else None,
                "filename": record["filename"],
                "document_type": record.get("document_type", "record"),
            }
        )
    grouped: dict[str, list] = defaultdict(list)
    for (metric, _, _), point in observations.items():
        grouped[metric].append({key: value for key, value in point.items() if key != "metric"})
    series = [
        {
            "metric_name": name,
            "points": sorted(points, key=lambda point: point["date"]),
            "category": "glycemic"
            if name in {"HbA1c", "Fasting glucose", "Post-meal glucose"}
            else "vitals"
            if "BP" in name
            else "renal",
        }
        for name, points in grouped.items()
    ]
    return {"record_summaries": summaries, "metric_series": series, "record_count": len(records)}


def enrich_history(catalog: dict, model: Any, progress=None) -> dict:
    """Summarize bounded record batches and validate every summary against its excerpts."""
    records = [
        record
        for record in catalog["record_summaries"]
        if not re.search(r"lab|profile|panel", record["title"], re.IGNORECASE)
    ]
    applied = 0
    for start in range(0, len(records), 5):
        batch = records[start : start + 5]
        if progress:
            progress(f"History synthesis agent · records {start + 1}–{start + len(batch)}")
        candidates = [
            {
                "index": index,
                "date": row["date"],
                "title": row["title"],
                "excerpts": [item["text"] for item in row["evidence"]],
            }
            for index, row in enumerate(batch)
        ]
        prompt = (
            'Return ONLY JSON: {"summaries":[{"index":0,"summary":"...","evidence_index":0}]}. '
            "Write ONE clear sentence (maximum 35 words) for EACH record. Explain the documented diagnosis, treatment, admission, procedure, or lab result. "
            "Use only that record's excerpts. Do not add facts, numeric values, dates, medication changes, or advice. Ignore templated phrases such as 'where applicable'. "
            "Do not label results elevated, normal, improved, or worsening unless that exact interpretation is written in the excerpt. "
            "Avoid demographics and laboratory boilerplate. Preserve drug doses and lab numbers exactly when included.\n"
            "Choose evidence_index as the zero-based excerpt that best supports the summary.\n"
            + json.dumps(candidates, ensure_ascii=False)
        )
        try:
            response = str(
                model.invoke(
                    [
                        {
                            "role": "system",
                            "content": "You summarize clinical records into concise readable sentences. Valid JSON only; source facts only.",
                        },
                        {"role": "user", "content": prompt},
                    ]
                ).content
            )
            parsed = json.loads(response[response.find("{") : response.rfind("}") + 1])
            for item in parsed.get("summaries", []):
                index = item.get("index")
                if not isinstance(index, int) or index < 0 or index >= len(batch):
                    continue
                original = batch[index]
                summary = str(item.get("summary") or "").strip()
                if not summary or len(summary) > 360:
                    continue
                source = original["date"] + " " + " ".join(e["text"] for e in original["evidence"])
                words = set(re.findall(r"[a-z]{4,}", summary.lower()))
                numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", summary))
                source_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", source))
                qualifiers = set(
                    re.findall(
                        r"\b(elevated|normal|worsening|improved|stable|severe|critical)\b",
                        summary.lower(),
                    )
                )
                if (
                    len(words & set(re.findall(r"[a-z]{4,}", source.lower()))) >= min(3, len(words))
                    and numbers <= source_numbers
                    and qualifiers
                    <= set(
                        re.findall(
                            r"\b(elevated|normal|worsening|improved|stable|severe|critical)\b",
                            source.lower(),
                        )
                    )
                ):
                    original["summary"] = summary
                    evidence_index = item.get("evidence_index", 0)
                    if isinstance(evidence_index, int) and 0 <= evidence_index < len(
                        original["evidence"]
                    ):
                        original["citation"] = original["evidence"][evidence_index]["citation"]
                    applied += 1
        except Exception:
            logging.getLogger(__name__).exception(
                "History summary batch failed; preserving source excerpts"
            )
    catalog["history_synthesis"] = "model_with_source_validation" if applied else "source_excerpts"
    catalog["summaries_synthesized"] = applied
    return catalog
