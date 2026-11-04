"""Verify isolated FHIR, original-file availability and content-addressed restore copies."""
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

from preppulse_api.evidence_catalog import build_catalog
from preppulse_api.store import WorkspaceStore
from preppulse_api.verified_measurements import same_name
from preppulse_preprocessing.fhir import validate_bundle
from preppulse_rag.runtime import ROOT


def main():
    report = {}
    restore_root = (ROOT / ".tmp/ui_testing/restored_sources").resolve()
    restore_root.mkdir(parents=True, exist_ok=True)
    for database_name in ("preppulse_ui_testing", "preppulse_ui_testing_gemini"):
        store = WorkspaceStore(db_name=database_name)
        counts = Counter()
        sources, matches, invalid = 0, 0, 0
        for row in store.db.workspace_files.find({}):
            original = Path(row["source_path"])
            sources += 1
            if not original.is_file():
                invalid += 1
                continue
            digest = hashlib.sha256(original.read_bytes()).hexdigest()
            target = restore_root / digest
            if not target.resolve().is_relative_to(restore_root):
                raise RuntimeError("Invalid restore destination")
            if not target.exists():
                shutil.copy2(original, target)
            matches += hashlib.sha256(target.read_bytes()).hexdigest() == digest == row["sha256"]
        docs = list(store.db.patient_documents.find({"preprocessing.status": "complete"}))
        matching_ocr = 0
        coverage = Counter()
        expected = Counter()
        catalogs = {}
        for doc in docs:
            pid = doc["patient_id"]
            if pid not in catalogs:
                catalogs[pid] = build_catalog(store, pid)
            facts = doc["stage_2_structured_entities"].get("labs", [])
            for series in catalogs[pid]["metric_series"]:
                for point in series["points"]:
                    citation = point["citation"]
                    if citation.get("document_id") != doc["document_id"] or not citation.get("source_verified"):
                        continue
                    name = series["metric_name"]
                    expected[name] += 1
                    found = any(same_name(name, fact) and fact.get("value") is not None
                                and abs(float(fact["value"]) - point["value"]) < 1e-6
                                for fact in facts)
                    assert found, f"Missing verified measurement: {name}"
                    coverage[name] += found
            original = store.client["preppulse"].patient_documents.find_one({"document_id": doc["document_id"]})
            if original:
                clean = lambda raw: {key: value for key, value in raw.items() if key != "processed_at"}
                matching_ocr += clean(original["stage_1_raw_ocr"]) == clean(doc["stage_1_raw_ocr"])
            validate_bundle(doc["stage_3_fhir_output"])
            for entry in doc["stage_3_fhir_output"]["entry"]:
                resource = entry["resource"]
                counts[resource["resourceType"]] += 1
                for extension in resource.get("extension", []):
                    values = {v["url"]: v for v in extension.get("extension", [])}
                    assert values["document-id"]["valueString"] == doc["document_id"]
                    bbox = json.loads(values["bbox"]["valueString"])
                    assert len(bbox) == 4 and all(0 <= value <= 1000 for value in bbox)
            assert store.db.fhir_versions.find_one({"document_id": doc["document_id"]})
        report[database_name] = {"validated_fhir_documents": len(docs), "resource_counts": dict(counts),
                        "file_records": sources, "restore_hash_matches": matches,
                        "missing_files": invalid,
                        "ocr_matches_original_except_run_timestamp": matching_ocr,
                        "supported_metric_coverage": {name: {"expected": count, "preserved": coverage[name]}
                                                      for name, count in expected.items()},
                        "quarantined_items": sum(len(doc["stage_2_structured_entities"].get("review_queue", []))
                                                 for doc in docs)}
        store.client.close()
    output = ROOT / ".tmp/ui_testing/results/integrity.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
