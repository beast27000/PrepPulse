"""
Deterministic mock provider.

Produces schema-shaped JSON from a chunk WITHOUT any LLM, using regexes tuned to
the document styles in the corpus. Its purpose is NOT production extraction; it
lets the whole pipeline (chunk -> extract -> ground -> FHIR -> Mongo) run and be
tested offline, in CI, and on a teammate's machine before Ollama is set up.

It is intentionally generic (no patient names / per-file hardcoding) per the
spec's Principle A, but it is rule-based and will miss messy real-world layouts
that a real LLM handles. Select it with LLM_PROVIDER=mock.
"""
from __future__ import annotations

import json
import re

from preppulse_preprocessing.config import LLMConfig
from preppulse_preprocessing.providers.base import LLMClient, LLMResponse

# crude but broad clinical patterns ------------------------------------------------
_LAB_PATTERNS = {
    "HbA1c": r"HbA1c\s*:?\s*([0-9]+(?:\.[0-9]+)?)\s*(%)",
    "Fasting Blood Glucose": r"Fasting\s+(?:Blood\s+)?Glucose\s*:?\s*([0-9]+(?:\.[0-9]+)?)\s*(mmol/L|mg/dL)?",
    "Random Blood Glucose": r"Random\s+(?:Blood\s+)?Glucose\s*:?\s*([0-9]+(?:\.[0-9]+)?)\s*(mmol/L|mg/dL)?",
    "eGFR": r"eGFR\s*:?\s*([0-9]+(?:\.[0-9]+)?)\s*(mL/min[^\s]*)?",
    "Serum Creatinine": r"(?:Serum\s+)?Creatinine\s*:?\s*([0-9]+(?:\.[0-9]+)?)\s*(umol/L|mg/dL)?",
    "Total Cholesterol": r"Total\s+Cholesterol\s*:?\s*([0-9]+(?:\.[0-9]+)?)\s*(mmol/L|mg/dL)?",
    "LDL Cholesterol": r"LDL(?:\s+Cholesterol)?\s*:?\s*([0-9]+(?:\.[0-9]+)?)\s*(mmol/L|mg/dL)?",
}
_REF_RANGE = r"\(([0-9.]+\s*-\s*[0-9.]+)\)"
_FLAG = r"\b(HIGH|LOW|NORMAL|H|L)\b"

# a broad, extensible drug vocabulary (names only; dose parsed separately)
_DRUGS = [
    "Metformin", "Gliclazide", "Glimepiride", "Sitagliptin", "Empagliflozin",
    "Dapagliflozin", "Insulin Glargine", "Insulin Aspart", "Glargine", "Semaglutide",
    "Ramipril", "Amlodipine", "Losartan", "Atorvastatin", "Rosuvastatin",
    "Aspirin", "Furosemide",
]
_DOSE = r"([0-9]+(?:\.[0-9]+)?\s*(?:mg|units|mcg|g))"
_FREQ = r"(once daily|twice daily|three times daily|at night|once weekly|with meals|BID|OD|TDS)"

_DIAGNOSES = {
    r"Type\s*2\s*Diabetes": "Type 2 Diabetes Mellitus",
    r"Type\s*1\s*Diabetes": "Type 1 Diabetes Mellitus",
    r"Hypertension": "Hypertension",
    r"Chronic Kidney Disease": "Chronic Kidney Disease",
    r"Retinopathy": "Diabetic Retinopathy",
    r"Neuropathy": "Peripheral Neuropathy",
}


class MockProvider(LLMClient):
    def __init__(self, cfg: LLMConfig) -> None:
        self.cfg = cfg

    def health(self) -> bool:
        return True

    def complete_json(self, system: str, user: str) -> LLMResponse:
        # `user` carries the chunk text after a known marker; parse that out.
        text = user
        marker = "<<<CHUNK_TEXT>>>"
        if marker in user:
            text = user.split(marker, 1)[1]

        labs = []
        for name, pat in _LAB_PATTERNS.items():
            for m in re.finditer(pat, text, re.IGNORECASE):
                val = float(m.group(1))
                unit = (m.group(2) or "").strip() or None
                window = text[m.start(): m.end() + 40]
                ref = re.search(_REF_RANGE, window)
                flag = re.search(_FLAG, window)
                labs.append({
                    "test_name": name,
                    "value": val,
                    "unit": unit,
                    "reference_range": ref.group(1) if ref else None,
                    "flag": (flag.group(1) if flag else None),
                    "anchor_text": m.group(0).strip(),
                })

        meds = []
        for drug in _DRUGS:
            for m in re.finditer(re.escape(drug), text, re.IGNORECASE):
                window = text[m.start(): m.end() + 60]
                dose = re.search(_DOSE, window, re.IGNORECASE)
                freq = re.search(_FREQ, window, re.IGNORECASE)
                meds.append({
                    "name": drug,
                    "dosage": dose.group(1).replace(" ", "") if dose else None,
                    "frequency": freq.group(1) if freq else None,
                    "anchor_text": (drug + " " + (dose.group(1) if dose else "")).strip(),
                })
                break  # one mention per drug per chunk is enough

        diags = []
        for pat, desc in _DIAGNOSES.items():
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                diags.append({"description": desc, "anchor_text": m.group(0)})

        advice = None
        am = re.search(r"(Advice|Plan)\s*:?\s*(.+)", text, re.IGNORECASE)
        if am:
            advice = am.group(2).strip()[:300]

        payload = {"labs": labs, "medications": meds, "diagnoses": diags, "advice": advice}
        return LLMResponse(text=json.dumps(payload), model="mock-regex", raw=None)
