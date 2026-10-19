# PrepPulse Synthetic Dataset — Complete Guide

A fully synthetic, privacy-safe dataset for building and evaluating **PrepPulse**,
an intelligent chart-review assistant for diabetes care. Everything here is
machine-generated — **no real patient data** — so it is safe to share, copy, and
redistribute.

This guide explains **all 6 zip files**, how they fit together, and a concrete,
step-by-step path to build each of the four PrepPulse capabilities from them.

> **If you only read one thing:** start with `preppulse_synthetic_LITE.zip`.
> It contains every label, every patient record, the data dictionary, the
> generator code, and a 100-document sample. The other 5 zips are just the full
> image/PDF corpus, split by document type so you download only what you need.

---

## 1. What problem this data solves

PrepPulse has four core capabilities. Each one needs its own labelled data, and
this dataset provides all four plus the raw documents to feed them:

| PrepPulse capability | What it does | Dataset that trains/evaluates it |
|---|---|---|
| **Record changes** | Compare HbA1c, glucose, eGFR, meds across visits | `record_changes` |
| **Missing tasks & records** | Find ordered-but-unresulted tests, overdue exams, open referrals | `missing_tasks` |
| **Record mismatches** | Detect conflicting meds/doses/dates/values across documents | `record_mismatches` |
| **Consultation prep** | Produce a source-cited brief + caregiver checklist | all of the above + `documents` for citations |

The pipeline underneath needs **document OCR**, **hybrid retrieval (vector + BM25)**,
and **source-level provenance**. The document corpus is designed to exercise all
three.

---

## 2. The 6 zip files at a glance

| # | Zip file | Size | Contains | You need it for |
|---|----------|------|----------|-----------------|
| 1 | **`preppulse_synthetic_LITE.zip`** | 25 MB | All 5 labelled datasets, all 720 patient records, 100-doc sample, generator code, data dictionary | **Everything. Download first.** |
| 2 | `preppulse_docs_text_digital_pdf.zip` | 151 MB | 1,688 clean digital PDFs (text extractable) | Training the "read with pypdf" path |
| 3 | `preppulse_docs_OCR_scanned_pdf.zip` | 323 MB | 995 scanned/degraded PDFs (no embedded text) | Training/evaluating the **OCR** path |
| 4 | `preppulse_docs_OCR_scanned_images.zip` | 303 MB | 836 standalone scanned images (JPG) | Training/evaluating the **OCR** path |
| 5 | `preppulse_docs_OCR_handwritten.zip` | 22 MB | 97 handwritten note images (hardest OCR) | Stress-testing OCR robustness |
| 6 | `preppulse_docs_hybrid_pdf.zip` | 51 MB | 540 PDFs with real text **+** an embedded figure | Training the "text + figure needs OCR" path |

**Total if you take everything: ~875 MB.** The 4 document zips (2–6) all unpack
into the **same `documents/` folder structure**, so you can extract any subset
on top of each other and the paths in the manifest will resolve.

### Why the documents are split this way
The whole point of PrepPulse's document layer is a **router**: if a file has
embedded text, read it cheaply with `pypdf`; if it's an image/scan, send it
through OCR. The 5 document forms below let you train and measure that router on
every real-world case. The split just mirrors those forms so you can, e.g., grab
only the OCR-relevant zips (3, 4, 5) if that's your focus.

---

## 3. How to unpack

```bash
mkdir preppulse_data && cd preppulse_data

# 1) Always start with LITE — gives you datasets/, records/, generator/, sample
unzip preppulse_synthetic_LITE.zip

# 2) Add whichever document forms you need. They all merge into documents/.
unzip -o preppulse_docs_text_digital_pdf.zip     -d .
unzip -o preppulse_docs_OCR_scanned_pdf.zip      -d .
unzip -o preppulse_docs_OCR_scanned_images.zip   -d .
unzip -o preppulse_docs_OCR_handwritten.zip      -d .
unzip -o preppulse_docs_hybrid_pdf.zip           -d .
```

After unpacking everything you get:

```
preppulse_data/
├── README.md                      ← data dictionary (also inside LITE)
├── datasets/                      ← the 5 labelled datasets (.jsonl + .csv)
├── records/                       ← 720 full patient JSON files
├── generator/                     ← the Python code that made all of this
├── sample_documents/              ← 100 example docs (from LITE)
└── documents/                     ← full corpus, once you add zips 2–6
    └── <patient_id>/<doc_id>.pdf|.jpg
```

> **Tip:** the `documents_manifest` `file` column is a path **relative to the
> folder that holds `documents/`** (e.g. `documents/01a7.../01a7..._clinic_note_0.pdf`).
> Run your code from `preppulse_data/` and paths just work.

---

## 4. The 5 labelled datasets in detail

All are in `datasets/`, each as **`.jsonl`** (one JSON per line, best for code)
and **`.csv`** (open in Excel/Sheets). Everything links by `patient_id` + `mrn`.

### 4.1 `longitudinal_records_index` (720 rows) + `records/*.json`
The patient backbone. The index is a quick table; the full detail is in each
patient's JSON file.

A patient JSON has: identifiers (`patient_id`, `mrn`, `nhs_number`), demographics
(`name`, `sex`, `dob`, `age`, `ethnicity`, `blood_group`, `address`, `phone`),
clinical profile (`primary_diagnosis`, `diagnosis_year`, `glycemic_control`,
`comorbidities[]`, `allergies[]`), `medications[]` (`name`, `dose`, `form`,
`frequency`, `class`, `started`), `visits[]` (each with `visit_id`, `date`,
`type`, `clinician`, `labs`, `vitals`, `bp`), and `referrals[]` (`referral_id`,
`to`, `reason`, `date`, `status`).

Lab values move realistically over time — a poorly-controlled patient's HbA1c and
eGFR drift visit to visit — so changes are meaningful, not random.

### 4.2 `documents_manifest` (4,156 rows)
One row per **rendered** document. Key columns:

- `doc_id`, `patient_id`, `mrn` — identity + link to patient
- `kind` — `lab_report`, `clinic_note`, `referral_letter`, `discharge_summary`, `imaging_report`, `medication_list`, `handwritten_note`
- `form` — `digital_pdf`, `scanned_pdf`, `scanned_image`, `hybrid_pdf`, `handwritten_note`
- `file` — relative path to the file; `extra_files` — extra pages if any
- **`text_extractable`** — `true` if `pypdf` gets text, else `false`  ← routing label
- **`requires_ocr`** — `true`, `false`, or `"partial"` (hybrid)        ← routing label
- `degradation` — `light` / `medium` / `heavy` (scans only)
- `pages`, `image_format`, `has_embedded_images`, `doc_date`
- `facts[]` — the structured claims this document asserts, each with a date (this is your **provenance ground truth**)

There is also `documents_manifest_metadata_only` (4,969 rows): documents for 420
extra patients that have facts/provenance but **no rendered image file**
(`form = metadata_only`). They exist only to give the mismatch dataset more
volume; ignore them for OCR work.

### 4.3 `record_changes` (20,212 rows)
One row per metric change between two consecutive visits.
Columns: `patient_id`, `mrn`, `metric` (HbA1c, Fasting Glucose, eGFR, Serum
Creatinine, Total Cholesterol, LDL, Systolic BP, BMI), `from_value`, `to_value`,
`unit`, `from_date`, `to_date`, `change_pct`, `direction`
(increased/decreased/unchanged), **`clinically_significant`** (the label, ~14%
true), and `from_visit`/`to_visit` for provenance.

### 4.4 `record_mismatches` (1,227 rows)
Deliberately injected conflicts across documents, with ground truth.
Columns: `patient_id`, `mrn`, **`mismatch_type`** (`medication_dose`,
`medication_frequency`, `medication_name`, `medication_omission`,
`lab_value_conflict`, `demographic_dob`, `demographic_mrn`, `demographic_name`),
`field`, `medication`, `value_doc_a`, `value_doc_b`, **`source_doc_a`**,
**`source_doc_b`** (the two conflicting `doc_id`s), `date_a`, `date_b`,
`severity` (high/medium/low).

### 4.5 `missing_tasks` (6,268 rows)
Overdue/absent tasks and unresolved referrals — **plus compliant negatives** so
the model also learns what "on track" looks like.
Columns: `patient_id`, `mrn`, **`task_type`** (`overdue_screening`,
`screening_current` ← the negative class, `unresolved_referral`,
`never_performed`, `ordered_test_no_result`), `detail`, `reference_id`,
`due_or_made`, `days_outstanding`, `status`, `label`, `severity`
(none/low/medium/high).

---

## 5. Build the model — step by step

You do **not** need to train one giant model. PrepPulse is a pipeline of small,
testable components. Build them in this order.

### Step 0 — Environment
```bash
pip install pypdf pytesseract pdf2image pillow pandas scikit-learn \
            sentence-transformers rank-bm25 faiss-cpu
# system OCR engine:
sudo apt-get install tesseract-ocr poppler-utils
```

### Step 1 — Document ingestion + the OCR router
**Goal:** turn any file into clean text, choosing pypdf vs OCR automatically.

1. Read `documents_manifest`. For each row, open `file`.
2. If it's a PDF, try `pypdf` text extraction. If you get substantial text →
   it's a `digital_pdf`/`hybrid_pdf` (text path). If you get little/none → it's a
   scan → OCR it. For images → always OCR.
3. Use the `requires_ocr` / `text_extractable` columns as the **ground-truth
   labels** to measure your router's accuracy. The dataset is built so this rule
   works: digital PDFs yield text, scanned PDFs yield none.
4. For `hybrid_pdf` (`requires_ocr == "partial"`): take body text from pypdf
   **and** OCR/caption the embedded figure.

```python
import json, pypdf, pytesseract
from pdf2image import convert_from_path
from PIL import Image

def extract(path):
    if path.lower().endswith(".pdf"):
        text = "".join((p.extract_text() or "") for p in pypdf.PdfReader(path).pages)
        if len(text.strip()) > 30:
            return text, "pypdf"
        pages = convert_from_path(path, dpi=200)          # scanned PDF → OCR
        return "\n".join(pytesseract.image_to_string(p) for p in pages), "ocr"
    return pytesseract.image_to_string(Image.open(path)), "ocr"   # image → OCR

# Evaluate the router against the labels:
rows = [json.loads(l) for l in open("datasets/documents_manifest.jsonl")]
correct = 0
for r in rows[:500]:
    _, method = extract("" + r["file"])
    predicted_ocr = (method == "ocr")
    truth_ocr = (r["requires_ocr"] in (True, "partial"))
    correct += (predicted_ocr == truth_ocr)
print("router accuracy:", correct / 500)
```
**Metrics:** OCR character/word accuracy (compare OCR output to the facts in the
manifest), and router accuracy vs `requires_ocr`.

### Step 2 — Hybrid retrieval + provenance index
**Goal:** given a question, fetch the right passages and remember where they came from.

1. Chunk every extracted document into passages. For each chunk store
   `{doc_id, patient_id, page, text}` — this is your **provenance**.
2. Build two indexes over the chunks: a **vector index** (embed with
   `sentence-transformers`, store in FAISS) and a **BM25 index** (`rank-bm25`).
3. At query time, retrieve from both and merge (e.g. reciprocal-rank fusion).
   Every returned passage keeps its `doc_id`/`page`, so any downstream claim can
   cite its source.

**Metric:** retrieval recall@k — does the chunk containing the known fact appear
in the top-k? You know the true fact locations from `facts[]` in the manifest.

### Step 3 — Record-change detection
**Goal:** flag clinically significant changes between visits.

- **Baseline (rules):** from `records/*.json`, compute `change_pct` per metric
  between consecutive visits; threshold it. Compare to `clinically_significant`.
- **ML version:** train a classifier on `record_changes` using features
  (`metric`, `from_value`, `to_value`, `change_pct`, `direction`, time gap) →
  predict `clinically_significant`. Split by patient (see Step 6).

**Metric:** precision/recall/F1 on `clinically_significant`.

### Step 4 — Mismatch detection
**Goal:** find conflicting facts across a patient's documents.

- For each patient, gather `facts[]` from all their documents (grouped by type:
  same medication, same lab, demographics). Flag disagreements.
- `record_mismatches` is your answer key: each row names the two `source_doc_a` /
  `source_doc_b` and the conflicting values. Reproduce them, then measure how
  many you catch.

**Metric:** precision/recall per `mismatch_type`; report by `severity`.

### Step 5 — Missing-task detection
**Goal:** list overdue screenings, unresulted tests, and open referrals.

- From each patient: check recurring screenings against their due interval
  (overdue vs up-to-date), find referrals with `status != Completed`, and tests
  ordered without a result.
- `missing_tasks` is the answer key. Note it includes `screening_current`
  (compliant) rows — your model must **not** flag those, which is how you measure
  false positives.

**Metric:** precision/recall on the "needs attention" classes vs the compliant
class.

### Step 6 — Assemble the consultation brief
Combine Steps 3–5 into a single per-patient summary, and attach a citation
(`doc_id` + page from Step 2) to every statement. Add the caregiver checklist.
Keep the doctor accept/edit/reject control — the brief is a draft for a clinician,
not an autonomous decision.

---

## 6. Train / test splitting (important — avoid leakage)

**Always split by `patient_id`,** never by row. If one patient's documents land
in both train and test, your scores will be inflated.

```python
import json, random
ids = [json.loads(l)["patient_id"]
       for l in open("datasets/longitudinal_records_index.jsonl")]
random.seed(42); random.shuffle(ids)
cut = int(0.8 * len(ids))
train_ids, test_ids = set(ids[:cut]), set(ids[cut:])
# then filter every dataset by patient_id membership
```

The first 300 patients have rendered documents (use them for OCR/retrieval/
provenance); the full 720 give you more volume for the structured tasks.

---

## 7. Evaluation principles (please read)

- **Do not** use diabetes-prediction accuracy as your metric. PrepPulse is an
  administrative chart-review assistant, not a disease-prediction model.
- Measure the **workflow**: extraction accuracy, change precision/recall,
  mismatch detection, missing-task detection, citation correctness, and time to
  produce the brief.
- The data is intentionally **balanced** (significant vs not, all severities,
  both sexes, all control categories, all document forms and degradation levels)
  so the model learns to generalise rather than exploit a shortcut.

---

## 8. Caveats & honesty notes

- **Fully synthetic.** Great for development and demos. Before any real-world
  use, validate on real de-identified data (e.g. MIMIC-IV / MIMIC-IV-Note, which
  require credentialing) — synthetic data can't capture every real-world quirk.
- **420 of 720 patients are "metadata-only"** (structured facts, no image file),
  included only to scale the mismatch dataset. They're flagged with
  `form = metadata_only`; the 300 rendered patients are your document set.
- **OCR errors are intentional** on heavy scans and handwriting — that's what
  trains robustness. Don't treat them as data bugs.

---

## 9. Regenerate or scale the data

The `generator/` folder contains everything. To make a fresh, differently-
randomised corpus, change the seed:

```bash
# render documents in ~60-patient chunks (keeps each run quick)
python3 -m gen.build --patients 300 --seed 123 --mode chunk --start 0   --end 60
python3 -m gen.build --patients 300 --seed 123 --mode chunk --start 60  --end 120
python3 -m gen.build --patients 300 --seed 123 --mode chunk --start 120 --end 180
python3 -m gen.build --patients 300 --seed 123 --mode chunk --start 180 --end 240
python3 -m gen.build --patients 300 --seed 123 --mode chunk --start 240 --end 300
python3 -m gen.extra_mismatch
python3 -m gen.build --mode finalize --structured 720 --keep-mismatch
```

---

## 10. Quick reference — which zip for which task

| I want to… | Unpack these zips |
|---|---|
| Explore labels, build change/mismatch/missing models | **LITE only** |
| Build + test the OCR path | LITE + scanned_pdf + scanned_images + handwritten |
| Build the pypdf text path | LITE + digital_pdf |
| Build the hybrid text-plus-figure path | LITE + hybrid_pdf |
| Build the whole pipeline end-to-end | **All 6** |
