# PrepPulse dataset context

Fast reference for the synthetic dataset delivered in `datasets/`. The detailed source guide is
[`README_DELIVERY.md`](README_DELIVERY.md).

## Safety and repository handling

- The corpus is fully synthetic and has no real patient data.
- Dataset ZIP archives and extracted data are local working assets. Do **not** add them to Git
  unless the project owner explicitly requests it.
- Extracted corpus data should live under the Git-ignored path
  `data/raw/preppulse_synthetic_lite/` (or another approved `data/raw/` subdirectory), not in
  the source package.

## Verified LITE archive contents

`preppulse_synthetic_LITE.zip` is the correct first archive to use. It was inspected without
extraction and contains 845 files:

- 720 complete synthetic patient JSON records in `records/`.
- 100 rendered sample documents in `sample_documents/`, plus one sample-document manifest.
- The five labelled datasets in both `.jsonl` and `.csv` forms.
- Generator source and a data dictionary/readme.

Important: LITE has **720 patient records**, not 100 patient records. The number 100 refers to
the included rendered-document sample for initial OCR testing.

## Primary labelled datasets

| Dataset | Scale | Purpose | OCR relevance |
|---|---:|---|---|
| `longitudinal_records_index` + `records/*.json` | 720 patients | Demographics, medications, visits, labs, and referrals | Patient/encounter context; not rendered OCR input |
| `documents_manifest` | 4,156 rendered documents | Document identity, path, kind, form, dates, routing labels, and source facts | Primary OCR routing/provenance ground truth |
| `record_changes` | 20,212 rows | Longitudinal clinical metric changes | Later chronology/change capability |
| `record_mismatches` | 1,227 rows | Deliberately injected cross-document conflicts | Later discrepancy capability |
| `missing_tasks` | 6,268 rows | Open referrals, overdue screenings, and unresulted orders, including compliant negatives | Later care-gap/loop-closure capability |

Auxiliary dataset: `documents_manifest_metadata_only` has facts/provenance for 420 additional
patients but no rendered document files. Ignore it for OCR evaluation; use it later only for
structured mismatch-scale work.

## Manifest fields that matter to the OCR pipeline

Use `documents_manifest` as metadata/routing ground truth. Key fields:

- `doc_id`, `patient_id`, `mrn`: document and patient identity.
- `kind`: `lab_report`, `clinic_note`, `referral_letter`, `discharge_summary`,
  `imaging_report`, `medication_list`, or `handwritten_note`.
- `form`: `digital_pdf`, `scanned_pdf`, `scanned_image`, `hybrid_pdf`, or
  `handwritten_note`.
- `file` and `extra_files`: source paths, relative to the extracted dataset root.
- `text_extractable`: routing ground truth for native PDF text.
- `requires_ocr`: `true`, `false`, or `"partial"`; `"partial"` denotes hybrid documents.
- `degradation`: scan difficulty (`light`, `medium`, or `heavy`).
- `pages`, `image_format`, `has_embedded_images`, and `doc_date`.
- `facts[]`: structured claims asserted by the source document; use later to evaluate source
  provenance and retrieval/citation correctness.

Metadata from this manifest is authoritative. OCR must not overwrite its patient identity,
document type, or date values.

## Six available archives

| Archive | Contents | Intended use |
|---|---|---|
| `preppulse_synthetic_LITE.zip` | Labels, 720 records, 100 sample documents, manifests, generator | Start here; initial OCR integration and tests |
| `preppulse_docs_text_digital_pdf.zip` | 1,688 text-extractable PDFs | Native PDF extraction path |
| `preppulse_docs_OCR_scanned_pdf.zip` | 995 scanned/degraded PDFs | OCR route evaluation |
| `preppulse_docs_OCR_scanned_images.zip` | 836 scanned JPG images | OCR route evaluation |
| `preppulse_docs_OCR_handwritten.zip` | 97 handwriting images | OCR robustness stress test |
| `preppulse_docs_hybrid_pdf.zip` | 540 PDFs with native text plus embedded figures | Hybrid text-plus-figure extraction |

The full optional corpus is about 875 MB. Archives 2–6 merge into the same `documents/`
directory after extraction.

## Relationship to Sprint 1

The original four-document patient-pack requirement is covered by the corpus:

- outpatient clinic notes → `clinic_note`
- hospital discharge summaries → `discharge_summary`
- scanned lab panels → `lab_report` with scanned forms
- referral/order forms → `referral_letter`

The corpus also includes imaging reports, medication lists, and handwritten notes. Those are
useful robustness cases but are not required for the first acceptance run.

### Verified document coverage

The local `documents_manifest.jsonl` contains 4,156 rendered documents for **300** patients.
The remaining 420 of the 720 structured patient records are represented by the separate
metadata-only manifest and have no rendered OCR source files. Coverage for the four required
types is:

| Required kind | Rendered documents | Patients represented |
|---|---:|---:|
| `clinic_note` | 1,207 | 299 |
| `discharge_summary` | 115 | 115 |
| `lab_report` | 1,527 | 300 |
| `referral_letter` | 480 | 230 |

**93 patients** have all four kinds, so those 93 are the valid ready-made complete packs for
the initial end-to-end Sprint 1 acceptance test. The 100 LITE sample documents are only a
small OCR smoke-test subset, not a 100-patient pack.

## Agreed first-use path (no code implemented yet)

1. Extract **only** `preppulse_synthetic_LITE.zip` into
   `data/raw/preppulse_synthetic_lite/`.
2. Use its 100 sample documents and `sample_documents_manifest.jsonl` as the first OCR test
   corpus.
3. Add a manifest loader and batch runner only after a scoped implementation plan is approved.
4. Evaluate the OCR router against `text_extractable` and `requires_ocr`.
5. Expand to scanned PDFs/images/handwriting/hybrid archives only after the LITE test path is
   stable.

## Evaluation rules

- Split future training/evaluation data by `patient_id`, never individual rows, to avoid leakage.
- Measure workflow quality: routing accuracy, OCR/text quality, table-cell integrity,
  provenance/citation correctness, and later task precision/recall.
- Do not use this corpus for autonomous diagnosis or treatment recommendations.
