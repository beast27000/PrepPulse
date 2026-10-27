# PrepPulse — 10-Patient High-Quality Cohort

A small, carefully-built set of **10 internally-consistent diabetes patients** for
OCR and chart-review testing. Every document for a patient uses that patient's own
name, MRN, dates, labs and medications — **nothing crosses between patients**.

## What's here

```
v2_out/
├── SUMMARY.json                  ← counts + which patients have discharge
├── MANIFEST.jsonl                ← every document, one JSON per line
├── patient_01_<Last>/ ... patient_10_<Last>/
│   ├── ground_truth.json         ← this patient's facts for every document
│   ├── patient_record.pdf        ← master record (always clean digital)
│   ├── lab_report_visit1_*.pdf   ← one per visit (some scanned for OCR)
│   ├── lab_report_visit2_*.pdf
│   ├── prescription_visit1_*.pdf ← one per visit (some scanned for OCR)
│   ├── prescription_visit2_*.pdf
│   ├── handwritten_prescription.jpg  ← handwritten, for OCR test
│   └── discharge_summary.pdf     ← ONLY for the 3 "serious" patients
```

## The clinical story (what makes it realistic)

Each patient starts with a **new diabetes diagnosis and a high sugar reading**, then
has follow-up visits ~1 month apart where sugar changes. The prescription at each
visit **responds to that visit's labs**:

| Trend vs last visit | What the prescription does |
|---|---|
| Sugar improved | Medication dose **reduced** |
| Sugar worse | Medication dose **increased** |
| No real change | Second medication **added** or switched, new advice |

So the lab report, the prescription, and the master record for a given visit all
agree. Example (real, from this set — Patient 2):

```
01/06/2024  fasting 11.4  HbA1c 8.9  [diagnosed]  Empagliflozin 10mg
11/07/2024  fasting 8.7   HbA1c 7.4  [improving]  Empagliflozin 10mg
22/08/2024  fasting 7.1   HbA1c 6.5  [improving]  Empagliflozin 10mg
24/09/2024  fasting 8.5   HbA1c 7.3  [worse]      Empagliflozin 25mg  ← dose up
```

Some patients also see a **second doctor** partway through (the clinic and doctor
name change on later visits) — the "patient brings old records to a new consultant"
scenario.

## Document rules (as requested)

- **All 10 patients** have: patient record, lab reports (one per visit),
  doctor prescriptions (one per visit), and one handwritten prescription.
- **Exactly 3 patients** (see `SUMMARY.json` → `serious_with_discharge`) also have a
  discharge summary — they are the serious cases who were admitted. The other 7 do
  not, exactly as in real life (consultation-only patients).

## For OCR testing

Each document in `MANIFEST.jsonl` carries:
- `form` — `digital_pdf` (pypdf reads text), `scanned_pdf` (degraded, needs OCR),
  or `handwritten_image` (needs OCR, hardest)
- `requires_ocr` — `true` / `false` (your routing label)
- `degradation` — `light` / `medium` / `heavy` for scanned items
- `facts` — the true values in that document, so you can check OCR output

Measured on this set: pypdf-vs-OCR routing is **100%** accurate against the labels,
lab values are recoverable from the degraded scans ~**96%** of the time, and the
handwritten drug name is read **9/10** times — a realistic difficulty spread.

## Counts

- 10 patients, 91 documents total
- 10 patient records, 34 lab reports, 34 prescriptions, 10 handwritten, 3 discharge
- 51 clean digital PDFs, 30 scanned PDFs, 10 handwritten images (40 require OCR)
