"""
Stage 3 — FHIR R4 standardization.

Maps verified Stage 2 entities into a FHIR R4 `transaction` Bundle:
  lab        -> Observation       (LOINC-coded)
  medication -> MedicationRequest (RxNorm-coded)
  diagnosis  -> Condition         (ICD-10-coded)
  patient    -> Patient

Only verified facts reach here (grounding ran first), so the bundle inherits the
provenance guarantees. We keep each resource minimal-but-valid for R4; extend
with more elements as downstream consumers require.
"""
from __future__ import annotations

from typing import Any

LOINC_SYS = "http://loinc.org"
RXNORM_SYS = "http://www.nlm.nih.gov/research/umls/rxnorm"
ICD10_SYS = "http://hl7.org/fhir/sid/icd-10"
UCUM_SYS = "http://unitsofmeasure.org"


def _patient_resource(patient_id: str, patient: dict[str, Any] | None) -> dict[str, Any]:
    res: dict[str, Any] = {"resourceType": "Patient", "id": patient_id}
    if patient:
        if patient.get("sex"):
            g = str(patient["sex"]).lower()
            res["gender"] = {"m": "male", "male": "male", "f": "female", "female": "female"}.get(g, "unknown")
        if patient.get("dob"):
            res["birthDate"] = patient["dob"]
        if patient.get("name"):
            res["name"] = [{"text": patient["name"]}]
    return {"resource": res}


def _observation(lab: dict[str, Any], patient_id: str) -> dict[str, Any]:
    coding = []
    if lab.get("loinc_code"):
        coding.append({"system": LOINC_SYS, "code": lab["loinc_code"], "display": lab.get("test_name")})
    res: dict[str, Any] = {
        "resourceType": "Observation",
        "status": "final",
        "code": {"coding": coding, "text": lab.get("test_name")},
        "subject": {"reference": f"Patient/{patient_id}"},
    }
    if lab.get("visit_date"):
        res["effectiveDateTime"] = lab["visit_date"]
    if lab.get("value") is not None:
        res["valueQuantity"] = {
            "value": lab["value"],
            "unit": lab.get("unit"),
            "system": UCUM_SYS,
            "code": lab.get("unit"),
        }
    if lab.get("flag"):
        res["interpretation"] = [{"text": lab["flag"]}]
    # provenance echo (non-normative extension-style fields are allowed by consumers)
    if lab.get("source_bbox"):
        res["_provenance"] = {"page": lab.get("source_page"), "bbox": lab["source_bbox"],
                              "anchor": lab.get("anchor_text"), "confidence": lab.get("confidence")}
    return {"resource": res}


def _medication_request(med: dict[str, Any], patient_id: str) -> dict[str, Any]:
    coding = []
    if med.get("rxnorm_code"):
        coding.append({"system": RXNORM_SYS, "code": med["rxnorm_code"], "display": med.get("name")})
    dosage_text = " ".join(x for x in [med.get("dosage"), med.get("frequency"), med.get("route")] if x)
    res: dict[str, Any] = {
        "resourceType": "MedicationRequest",
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {"coding": coding, "text": med.get("name")},
        "subject": {"reference": f"Patient/{patient_id}"},
    }
    if med.get("prescribed_date"):
        res["authoredOn"] = med["prescribed_date"]
    if dosage_text:
        res["dosageInstruction"] = [{"text": dosage_text}]
    if med.get("source_bbox"):
        res["_provenance"] = {"page": med.get("source_page"), "bbox": med["source_bbox"],
                              "anchor": med.get("anchor_text"), "confidence": med.get("confidence")}
    return {"resource": res}


def _condition(dx: dict[str, Any], patient_id: str) -> dict[str, Any]:
    coding = []
    if dx.get("icd10_code"):
        coding.append({"system": ICD10_SYS, "code": dx["icd10_code"], "display": dx.get("description")})
    res: dict[str, Any] = {
        "resourceType": "Condition",
        "code": {"coding": coding, "text": dx.get("description")},
        "subject": {"reference": f"Patient/{patient_id}"},
    }
    if dx.get("recorded_date"):
        res["recordedDate"] = dx["recorded_date"]
    if dx.get("source_bbox"):
        res["_provenance"] = {"page": dx.get("source_page"), "bbox": dx["source_bbox"],
                              "anchor": dx.get("anchor_text"), "confidence": dx.get("confidence")}
    return {"resource": res}


def to_fhir_bundle(entities: dict[str, Any], patient_id: str) -> dict[str, Any]:
    """Build a FHIR R4 transaction Bundle from grounded Stage 2 entities."""
    entry: list[dict[str, Any]] = [_patient_resource(patient_id, entities.get("patient"))]
    for lab in entities.get("labs", []):
        entry.append(_observation(lab, patient_id))
    for med in entities.get("medications", []):
        entry.append(_medication_request(med, patient_id))
    for dx in entities.get("diagnoses", []):
        entry.append(_condition(dx, patient_id))
    return {"resourceType": "Bundle", "type": "transaction", "entry": entry}
