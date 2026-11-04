"""Grounded FHIR R4 transactions, not newly issued medical orders.

Schema: https://hl7.org/fhir/R4/fhir.schema.json.zip (4.0.1, CC0)
SHA256: 2230406893b4cf002a4ee1e5e2bbeca22ac5d2d4931b3e9ef7b9594bbc376a01
Licence: https://hl7.org/fhir/R4/license.html; terminology has separate terms.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from jsonschema import Draft6Validator, FormatChecker, validators

BASE = "https://preppulse.example/StructureDefinition/source-evidence"
LOINC_SYS = "http://loinc.org"
RXNORM_SYS = "http://www.nlm.nih.gov/research/umls/rxnorm"
ICD10_SYS = "http://hl7.org/fhir/sid/icd-10"


@lru_cache(maxsize=1)
def validator():
    schema = json.loads((Path(__file__).parent / "schema/fhir-r4.schema.json").read_text(encoding="utf-8"))
    # FHIR's ResourceList has disjoint resourceType constants. Dispatching that
    # oneOf by its constant is equivalent to trying every resource definition,
    # and avoids quadratic validation work in large transaction bundles.
    typed_refs = {f"#/definitions/{name}": definition["properties"]["resourceType"]["const"]
                  for name, definition in schema["definitions"].items()
                  if "const" in definition.get("properties", {}).get("resourceType", {})}
    original = Draft6Validator.VALIDATORS["oneOf"]

    def resource_one_of(current, choices, instance, parent):
        refs = [choice.get("$ref") if set(choice) == {"$ref"} else None for choice in choices]
        if isinstance(instance, dict) and instance.get("resourceType") and all(ref in typed_refs for ref in refs):
            matches = [choice for choice, ref in zip(choices, refs)
                       if typed_refs[ref] == instance["resourceType"]]
            if len(matches) == 1:
                yield from current.descend(instance, matches[0])
                return
        yield from original(current, choices, instance, parent)

    fast_validator = validators.extend(Draft6Validator, {"oneOf": resource_one_of})
    return fast_validator(schema, format_checker=FormatChecker())


def validate_bundle(bundle):
    # Official base JSON schema; not clinical terminology/profile certification.
    validator().validate(bundle)
    if bundle.get("type") != "transaction":
        raise ValueError("A transaction bundle is required")
    urls = {entry["fullUrl"] for entry in bundle["entry"]}
    for entry in bundle["entry"]:
        resource = entry["resource"]
        if entry["request"] != {"method": "PUT", "url": f"{resource['resourceType']}/{resource['id']}"}:
            raise ValueError("Transaction identity mismatch")
        subject = resource.get("subject", {}).get("reference")
        if subject and subject not in urls:
            raise ValueError("Unresolved patient reference")


def concept(text, code=None, system=None):
    result = {"text": text}
    if code:
        result["coding"] = [{"system": system, "code": code}]
    return result


def evidence(fact, document_id):
    values = [{"url": "document-id", "valueString": document_id}]
    for field, typ, value in (
        ("page", "valuePositiveInt", fact.get("source_page")),
        ("bbox", "valueString", json.dumps(fact["source_bbox"]) if fact.get("source_bbox") else None),
        ("anchor", "valueString", fact.get("anchor_text")),
        ("confidence", "valueDecimal", fact.get("confidence")),
    ):
        if value is not None:
            values.append({"url": field, typ: value})
    return [{"url": BASE, "extension": values}]


def to_fhir_bundle(entities, patient_id, document_id="standalone"):
    patient = {"resourceType": "Patient", "id": patient_id}
    metadata = entities.get("patient") or {}
    if metadata.get("name"):
        patient["name"] = [{"text": metadata["name"]}]
    if metadata.get("dob"):
        patient["birthDate"] = metadata["dob"]
    if metadata.get("sex"):
        patient["gender"] = {"m": "male", "male": "male", "f": "female", "female": "female",
                             "other": "other"}.get(str(metadata["sex"]).lower(), "unknown")
    patient_url = "urn:uuid:" + str(uuid5(NAMESPACE_URL, "preppulse:patient:" + patient_id))
    resources = [(patient, patient_url)]
    for kind in ("labs", "medications", "diagnoses", "vitals"):
        for fact in entities.get(kind, []):
            if not fact.get("source_bbox"):
                continue
            if kind == "vitals":
                resource = {"resourceType": "Observation", "status": "final",
                            "code": {"text": fact["name"]}, "valueString": str(fact["value"])}
            elif kind == "labs":
                resource = {"resourceType": "Observation", "status": "final",
                            "code": concept(fact["test_name"], fact.get("loinc_code"), LOINC_SYS)}
                if fact.get("value") is not None:
                    quantity = {"value": fact["value"]}
                    if fact.get("unit"):
                        quantity["unit"] = fact["unit"]
                    if fact.get("value_comparator"):
                        quantity["comparator"] = fact["value_comparator"]
                    resource["valueQuantity"] = quantity
                if fact.get("visit_date"):
                    resource["effectiveDateTime"] = fact["visit_date"]
                if fact.get("reference_range"):
                    resource["referenceRange"] = [{"text": fact["reference_range"]}]
            elif kind == "medications":
                resource = {"resourceType": "MedicationRequest", "status": "unknown",
                            "intent": "proposal", "reportedBoolean": True,
                            "medicationCodeableConcept": concept(fact["name"], fact.get("rxnorm_code"), RXNORM_SYS)}
                dosage = " ".join(str(fact[key]) for key in ("dosage", "frequency", "route") if fact.get(key))
                if dosage:
                    resource["dosageInstruction"] = [{"text": dosage}]
                if fact.get("prescribed_date"):
                    resource["authoredOn"] = fact["prescribed_date"]
            else:
                resource = {"resourceType": "Condition",
                            "code": concept(fact["description"], fact.get("icd10_code"), ICD10_SYS)}
                if fact.get("recorded_date"):
                    resource["recordedDate"] = fact["recorded_date"]
            resource["subject"] = {"reference": patient_url}
            resource["extension"] = evidence(fact, document_id)
            identity = str(uuid5(NAMESPACE_URL, document_id + patient_id + json.dumps(resource, sort_keys=True)))
            resource["id"] = identity
            resources.append((resource, "urn:uuid:" + identity))
    bundle = {"resourceType": "Bundle", "type": "transaction", "entry": [
        {"fullUrl": url, "resource": resource,
         "request": {"method": "PUT", "url": f"{resource['resourceType']}/{resource['id']}"}}
        for resource, url in resources
    ]}
    validate_bundle(bundle)
    return bundle
