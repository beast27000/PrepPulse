# PrepPulse

PrepPulse is an assistive clinical chart-review workspace. It connects source-preserving OCR, preprocessing, hybrid retrieval, and clinical review agents to a local browser UI. Clinicians must review generated findings against the source record; PrepPulse does not autonomously diagnose or prescribe treatment.

## Branch status

The `UI` branch adds a React workspace and FastAPI integration layer. The existing OCR, preprocessing, RAG, and agent modules remain the data pipeline. The earlier Tkinter OCR test UI was removed from this branch. See [the detailed UI handoff](docs/FRONTEND_INTEGRATION_SPEC.md) and [delivery tracker](TO_DO.md) for implemented behavior and known limitations.

## Local setup

Requirements: Python 3.11+, Node.js 20.19+, MongoDB on local loopback, and Tesseract OCR for scanned PDFs/images. A local LM Studio model is optional; without it, chat shows source excerpts and agent inference may be limited.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd web
npm install
cd ..
```

Set local environment variables. Keep values out of version control:

```powershell
$env:PREPPULSE_SESSION_SECRET = "replace-with-a-random-secret-of-at-least-32-characters"
$env:PREPPULSE_ADMIN_USER = "admin"
$env:PREPPULSE_ADMIN_NAME = "PrepPulse Admin"
$env:PREPPULSE_ADMIN_PASSWORD = "replace-with-a-unique-long-password"
python scripts/bootstrap_ui_admin.py
```

Bootstrap creates the first admin and MongoDB indexes. It refuses to overwrite an existing account. Sign in as that admin to create doctors, register patients, assign doctors, schedule appointments, or import the local sample dataset. The API requires `PREPPULSE_SESSION_SECRET` on every start.

Run the API and frontend in separate terminals, with the same session secret available to the API terminal:

```powershell
$env:PREPPULSE_SESSION_SECRET = "the-same-random-secret-used-above"
python -m uvicorn preppulse_api.app:app --host 127.0.0.1 --port 8000
```

```powershell
cd web
npm run dev
```

Open the local URL printed by Vite. It proxies `/api` to `127.0.0.1:8000`. Uploaded originals are stored under ignored `private_data/`; sample datasets and generated outputs stay local. Do not run `scripts/audit_dataset_pipeline.py` against patient data retained for the UI: that audit clears MongoDB collections.

## Repository map

| Area | Purpose |
|---|---|
| `web/` | React and TypeScript doctor/admin browser workspace |
| `src/preppulse_api/` | Authenticated local API, patient registry, jobs, source preview, chat and voice integration |
| `src/preppulse_ocr/` | PDF/image OCR and normalized source geometry |
| `src/preppulse_db/` | MongoDB patient document and stage schemas |
| `src/preppulse_preprocessing/` | Section chunking, extraction, grounding, FHIR output |
| `src/preppulse_rag/` | Provenance chunking and hybrid BM25/dense retrieval |
| `src/preppulse_agents/` | LangGraph review workflow and `ConsultationBrief` schema |
| `prompts/` | External YAML agent and RAG prompts |
| `tests/` | OCR, storage, retrieval, and agent tests |

## Voice

Dictation uses local faster-whisper `small` on CPU. The doctor reviews the transcript before sending it to chat. The planned spoken-answer model is `mradermacher/Qwen3-1.7B-Multilingual-TTS-GGUF`; `PREPPULSE_TTS_MODEL_PATH` is a blank local configuration placeholder. Read aloud stays disabled until a compatible runtime and downloaded model are verified. No speech API key is required.

## Checks

```powershell
pytest
ruff check src/preppulse_api scripts/bootstrap_ui_admin.py
cd web
npm run build
npm audit
```

The first release targets a local browser and local MongoDB. Before any shared deployment, review authentication, TLS, file encryption, backups, and clinical data handling for that environment.
