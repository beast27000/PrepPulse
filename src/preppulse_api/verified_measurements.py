"""Reconcile supported measurements against the same verified OCR rows used by charts."""
import copy
import re

from preppulse_preprocessing.models import LabEntity
from preppulse_preprocessing.terminology import loinc_for


def same_name(name, fact):
    code = loinc_for(name)
    if code and fact.get("loinc_code") == code:
        return True
    def words(text):
        return set(re.findall(r"[a-z0-9]+", text.lower())) - {"serum", "plasma", "blood", "level", "levels"}
    return words(name) <= words(fact.get("test_name", ""))


def reconcile(doc, entities, catalog):
    result = copy.deepcopy(entities)
    result.setdefault("labs", [])
    for series in catalog["metric_series"]:
        for point in series["points"]:
            citation = point["citation"]
            if citation.get("document_id") != doc["document_id"] or not citation.get("source_verified"):
                continue
            box = citation.get("bbox")
            page = citation.get("page_number")
            if not box or len(box) != 4 or not isinstance(page, int) or page < 1:
                continue
            anchor = citation.get("snippet") or citation.get("extracted_text") or ""
            comparator = None
            number = re.search(r"(?<![\d.])" + re.escape(f"{point['value']:g}") + r"(?![\d.])", anchor)
            if number:
                prefix = re.search(r"(<=|>=|<|>|≤|≥)\s*$", anchor[:number.start()])
                if prefix:
                    comparator = {"≤": "<=", "≥": ">="}.get(prefix[1], prefix[1])
            existing = next((lab for lab in result["labs"] if same_name(series["metric_name"], lab)
                             and lab.get("value") is not None
                             and abs(float(lab["value"]) - point["value"]) < 1e-6), None)
            if existing:
                if comparator:
                    existing["value_comparator"] = comparator
                continue
            tokens = [token for p in doc.get("stage_1_raw_ocr", {}).get("pages", [])
                      if p.get("page_number") == page for token in p.get("tokens", [])
                      if token.get("bbox") and token["bbox"][0] >= box[0] and token["bbox"][1] >= box[1]
                      and token["bbox"][2] <= box[2] and token["bbox"][3] <= box[3]]
            confidence = min([max(0, min(1, token.get("confidence", 1))) for token in tokens] or [1])
            fact = LabEntity(test_name=series["metric_name"], loinc_code=loinc_for(series["metric_name"]),
                             value=point["value"], unit=point["unit"], visit_date=point["date"],
                             source_page=page, source_bbox=box, anchor_text=anchor, confidence=confidence,
                             evidence_method="verified_ocr_catalog", value_comparator=comparator)
            result["labs"].append(fact.model_dump())
    return result
