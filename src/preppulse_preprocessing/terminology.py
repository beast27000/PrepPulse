"""
Terminology normalization: map extracted concepts to standard codes.

  labs       -> LOINC
  medications-> RxNorm
  diagnoses  -> ICD-10

This ships a SEED table covering the common diabetes-care concepts in the corpus.
It is deliberately small and explicit; the lookup functions are the stable
interface. In production, swap the dict lookups for a real terminology service
(UMLS, RxNav, a LOINC FHIR server) without changing any caller. Unmapped
concepts return None and are FLAGGED upstream, never dropped.
"""
from __future__ import annotations

import re

# ---- LOINC (labs) ----
_LOINC = {
    "hba1c": "4548-4",
    "fasting blood glucose": "1558-6",
    "fasting glucose": "1558-6",
    "random blood glucose": "2345-7",
    "random glucose": "2345-7",
    "egfr": "33914-3",
    "serum creatinine": "2160-0",
    "creatinine": "2160-0",
    "total cholesterol": "2093-3",
    "ldl cholesterol": "2089-1",
    "ldl": "2089-1",
    "hdl cholesterol": "2085-9",
    "triglycerides": "2571-8",
}

# ---- RxNorm (medications) ----
_RXNORM = {
    "metformin": "6809",
    "gliclazide": "25789",
    "glimepiride": "25789",
    "sitagliptin": "593411",
    "empagliflozin": "1545658",
    "dapagliflozin": "1488564",
    "insulin glargine": "274783",
    "glargine": "274783",
    "insulin aspart": "51428",
    "semaglutide": "1991302",
    "ramipril": "35296",
    "amlodipine": "17767",
    "losartan": "52175",
    "atorvastatin": "83367",
    "rosuvastatin": "301542",
    "aspirin": "1191",
    "furosemide": "4603",
}

# ---- ICD-10 (diagnoses) ----
_ICD10 = {
    "type 2 diabetes mellitus": "E11.9",
    "type 1 diabetes mellitus": "E10.9",
    "hypertension": "I10",
    "chronic kidney disease": "N18.9",
    "diabetic retinopathy": "E11.319",
    "peripheral neuropathy": "G62.9",
    "hyperlipidaemia": "E78.5",
    "hyperlipidemia": "E78.5",
    "obesity": "E66.9",
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def loinc_for(test_name: str | None) -> str | None:
    if not test_name:
        return None
    return _LOINC.get(_norm(test_name))


def rxnorm_for(drug_name: str | None) -> str | None:
    if not drug_name:
        return None
    key = _norm(drug_name)
    if key in _RXNORM:
        return _RXNORM[key]
    # try the base drug word (strip trailing XL/MR/SR and salts)
    base = re.sub(r"\b(xl|mr|sr|hcl|hydrochloride)\b", "", key).strip()
    return _RXNORM.get(base)


def icd10_for(description: str | None) -> str | None:
    if not description:
        return None
    key = _norm(description)
    if key in _ICD10:
        return _ICD10[key]
    for name, code in _ICD10.items():
        if name in key:
            return code
    return None
