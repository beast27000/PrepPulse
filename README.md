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
pip install -e .
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

Bootstrap creates the first admin and MongoDB indexes. It refuses to overwrite an existing account. Sign in as that admin to create doctors, register patients, assign doctors, schedule appointments, or upload one patient folder at a time. The API requires `PREPPULSE_SESSION_SECRET` on every start.

Run the API and frontend in separate terminals, with the same session secret available to the API terminal:

```powershell
$env:PREPPULSE_SESSION_SECRET = "the-same-random-secret-used-above"
$env:LLM_PROVIDER = "local"
$env:LOCAL_LLM_BASE_URL = "http://127.0.0.1:1234/v1"
$env:LOCAL_CHAT_MODEL = "qwen/qwen3-4b-2507"
python -m uvicorn preppulse_api.app:app --host 127.0.0.1 --port 8000
```

```powershell
cd web
npm run dev
```

Open the local URL printed by Vite. It proxies `/api` to `127.0.0.1:8000`. Uploaded originals are stored under ignored `private_data/`; sample datasets and generated outputs stay local. Do not run `scripts/audit_dataset_pipeline.py` against patient data retained for the UI: that audit clears MongoDB collections.

On **Patients**, choose **Analyze records** to rerun OCR for pending files, patient-scoped RAG retrieval, and the review agents. The job shows its stage and document counts; the existing brief remains visible until the replacement is ready. A completed brief lists evidence chunks and only source-backed priority observations. Select a cited item to inspect its OCR span. The Source Proof expand button opens a full record workspace with page navigation, searchable record text, and a file rail. Reanalysis tightens older broad citation boxes.

The brief includes a diabetes journey, source visit cards, and admissions/procedure/consultation history across the uploaded records. Laboratory history is extracted directly from OCR rows; a separate history synthesis pass summarizes narrative records with linked excerpts. Review findings include previous recorded values and relevant earlier events.

### Patient conversations and charts

Chat sessions, messages, and requested charts are saved in MongoDB for the selected patient and signed-in doctor. Use **New chat session**, the conversation selector, and **Session charts** to return to earlier work. Replies render headings, emphasis, real HTML tables, and inline numbered source links. Clicking a citation or chart point opens its OCR evidence on the right. The Source Proof panel starts closed in chat and can close or expand into the record workspace. The navigation rail collapses on every screen.

Chart requests create a new named artifact from dated OCR measurements and save it in the session. Chat stays on the left and the chart opens on the right. Collapse chat for a full-width chart, or collapse the chart for full-width chat; toolbar controls restore either panel. Clicking a citation opens Source Proof in the right-hand panel. Supported extraction includes HbA1c, fasting/post-meal glucose, eGFR, urine ACR, creatinine, LDL, and recorded blood pressure. Heart-disease chart requests display a diabetes-agent scope warning instead of an unrelated chart; cited cardiac text summaries remain available. Missing requested data produces a gap state. No example values, model-invented points, or missing-year estimates are inserted. Chart generation does not require an LLM or embedding service.

The local model defaults to loopback (`127.0.0.1:1234`), avoiding a changing LAN address. Set `LOCAL_LLM_BASE_URL` explicitly if the model runs elsewhere. Local model calls have bounded timeouts. When embeddings fail, BM25 retrieval remains available; if synthesis fails, the response identifies itself as sourced excerpts. Processing bubbles show the actual active retrieval, chart, or review-agent stage. Interrupted jobs become retryable after a server restart.

**Settings** contains per-account browser preferences: Light/Dark/System appearance, larger text, contrast, doctor dictation language and Read aloud visibility, and admin appointment time defaults. These preferences stay in that browser; they are not synchronized through MongoDB. Read aloud is always click-to-play. Restart the API after pulling backend changes; the Vite UI updates automatically.

### Patient folder intake

In **New patient intake**, option 3 selects exactly one folder named like `PP001_Ananya_Baruah`. Choose its doctor and upload. PrepPulse derives `PP001` and `Ananya Baruah` from that folder name, creates a separate immutable `PRP-` ID, and stores every selected file privately. PDF, PNG, and JPEG files become clinical documents and are processed in a background job; a manifest or text index is retained as an auxiliary file. The page shows saved/unchanged counts and OCR/analysis progress. Reuploading the same folder skips files with the same relative path and content hash; changed files are retained as new versions. The browser supports folder selection in current Edge and Chrome. Option 1 still registers a patient manually, and option 2 still appends a single document.

To clear patient records from the local `preppulse` database while retaining admin and doctor accounts, first stop the API. Preview the counts, then run the guarded reset:

```powershell
python scripts/reset_ui_patient_data.py
python scripts/reset_ui_patient_data.py --apply --confirm preppulse
```

This clears patient, document, appointment, visit, pathway, job, conversation, chart artifact, and audit collections. It leaves the account collection, indexes, source datasets, and any previously uploaded private files on disk alone. Inspect private storage separately if you need those files removed too.

The local workspace was reset on 2 November 2026. Both existing login accounts were retained. Restart the API after a reset and sign in again.

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

Dictation uses local faster-whisper `small` on CPU. The doctor reviews the transcript before sending it to chat.

Read aloud uses a local OpenAI-compatible audio endpoint when one returns real WAV audio. Set `PREPPULSE_TTS_ENDPOINT` to the **full** `/v1/audio/speech` URL and, if needed, `PREPPULSE_TTS_MODEL_ID` to the model's API identifier. The backend sends a harmless voice check first; only a valid WAV response enables the button. A doctor must click Read aloud for each reply. Audio is returned directly to the browser and is not saved by PrepPulse. No API key is required for the local setup.

The owner-provided LM Studio server at `http://192.168.1.50:1234` lists `qwen3-1.7b-multilingual-tts`, but a live check of `POST /v1/audio/speech` returned `Unexpected endpoint or method`. Listing a TTS-named GGUF as a text model does not provide speech output. **Do not set that URL as a working TTS endpoint yet.** Text chat and dictation still work. `PREPPULSE_TTS_MODEL_PATH` remains an optional local file reference; the API adapter uses the endpoint, not that path. Once a compatible runtime exposes WAV audio, configure it before starting the API:

```powershell
$env:PREPPULSE_TTS_ENDPOINT = "http://127.0.0.1:PORT/v1/audio/speech"
$env:PREPPULSE_TTS_MODEL_ID = "qwen3-1.7b-multilingual-tts"
```

Keep any audio server on this machine or a trusted private network. Read aloud sends the chosen reply text to that server.

## Checks

```powershell
pytest
ruff check src/preppulse_api scripts/bootstrap_ui_admin.py
cd web
npm run build
npm audit
```

The focused local suite is `pytest tests/test_ui_api.py tests/test_hybrid_rag.py tests/test_pipeline.py tests/test_manifest_and_storage.py -q`. Browser regression tests use Playwright and installed Microsoft Edge: `cd web; npm run test:e2e`. Set `PREPPULSE_E2E_URL`, `PREPPULSE_E2E_USER`, and `PREPPULSE_E2E_PASSWORD` to an isolated test workspace with an assigned doctor and a processed patient. They create conversations in that account. `PREPPULSE_API_TARGET` can point a separate Vite instance to a validation API, leaving the main workspace untouched. The browser suite checks actual chart requests, rendered tables, point/citation source links, panel expansion/collapse, persisted session reloads, navigation collapse, and responsive width.

The first release targets a local browser and local MongoDB. Before any shared deployment, review authentication, TLS, file encryption, backups, and clinical data handling for that environment.
