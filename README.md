# PrepPulse

PrepPulse is an assistive clinical chart-review workspace. It connects source-preserving OCR, preprocessing, hybrid retrieval, and clinical review agents to a local browser UI. Clinicians must review generated findings against the source record; PrepPulse does not autonomously diagnose or prescribe treatment.

## Release status

`main` contains the previously reviewed browser release. The `UI` branch contains the next release for owner review: caregiver accounts and follow-up, editable care plans, prescription schedules, unified intake, and appointment/visit history. It combines React/TypeScript, authenticated FastAPI, source-preserving OCR/preprocessing, patient-scoped hybrid RAG, and the LangGraph review agents. See the [detailed UI handoff](docs/FRONTEND_INTEGRATION_SPEC.md) and [delivery tracker](TO_DO.md) for contracts, permissions, and limitations. The caregiver release is not automatically merged into `main`.

The `old-ui` branch preserves the existing `main` revision from 3 November 2026. The simplified checklist changes remain on `UI` for owner review; no merge to `main` is automatic.

## Local setup

Requirements: Python 3.11+, Node.js 20.19+, MongoDB on local loopback, and Tesseract OCR for scanned PDFs/images. LM Studio (or another OpenAI-compatible local server) is strongly recommended for full agent-generated briefs and chat. This release targets a single local browser; review security, TLS, file encryption, backups, and access controls before shared deployment.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
cd web
npm install
cd ..
```

Start MongoDB before bootstrapping or using the API. The default connection is `mongodb://127.0.0.1:27017/preppulse`; keep the API and Vite development server in separate PowerShell terminals.

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
$env:LOCAL_EMBED_MODEL = "text-embedding-qwen3-embedding-0.6b"
python -m uvicorn preppulse_api.app:app --host 127.0.0.1 --port 8000
```

For full analysis, load a chat model and an embedding model in LM Studio, start its local server, and use the exact model identifiers shown by LM Studio. If LM Studio is on another machine, replace `LOCAL_LLM_BASE_URL` with its reachable `/v1` URL. Without it, source excerpts and deterministic fallbacks remain available but synthesis and some agent outputs are limited.

```powershell
cd web
npm run dev
```

Open the local URL printed by Vite. It proxies `/api` to `127.0.0.1:8000`. Uploaded originals are stored under ignored `private_data/`; sample datasets and generated outputs stay local. Do not run `scripts/audit_dataset_pipeline.py` against patient data retained for the UI: that audit clears MongoDB collections.

On **Patients**, choose **Analyze records** to rerun OCR for pending files, patient-scoped RAG retrieval, and the review agents. The job shows its stage and document counts; the existing brief remains visible until the replacement is ready. A completed brief lists evidence chunks and only source-backed priority observations. Select a cited item to inspect its OCR span. The Source Proof expand button opens a full record workspace with page navigation, searchable record text, and a file rail. Reanalysis tightens older broad citation boxes.

The brief includes a diabetes journey, source visit cards, and admissions/procedure/consultation history across the uploaded records. Laboratory history is extracted directly from OCR rows; a separate history synthesis pass summarizes narrative records with linked excerpts. Review findings include previous recorded values and relevant earlier events.

On Patients, the right column contains **chat first**, **Source Proof second**, and **caregiver checklist third**. Each section collapses to its heading; **Collapse right panels** gives the consultation brief the full width. Dedicated chat and record workspace expansion remains available. Selecting an observation reveals its Source Proof.

### Diabetes classification inputs and chart scope

The classifier retrieves patient-scoped excerpts about diabetes, prediabetes, impaired fasting glucose, HbA1c, metabolic findings, and documented diagnoses. Its current prompt is in [`classification_agent.yaml`](prompts/agents/classification_agent.yaml), with execution/fallback logic in [`graph.py`](src/preppulse_agents/graph.py). These are the implemented prompt rules, not a substitute for clinician diagnosis:

| Input | How the current classifier uses it |
|---|---|
| Recorded diagnoses and clinician impressions | Evidence for documented type 1/type 2 diabetes, prediabetes, impaired fasting glucose or impaired glucose tolerance. |
| HbA1c | The prompt lists `>= 6.5%` as diabetic-range evidence, `5.7–6.4%` as prediabetic-range evidence, and `< 5.7%` alongside absent history for the non-diabetic category. |
| Glucose findings | Fasting glucose and documented IFG/IGT inform the retrieved context. The prompt explicitly lists fasting glucose `< 100 mg/dL` for its non-diabetic rule. It does not implement a complete fasting/random/OGTT diagnostic algorithm. |
| Diabetes medication history | Existing glucose-lowering treatment contributes context. A medication mention alone is not independently verified proof of a diagnosis. |
| Documented type 1 history / insulin dependence with DKA history | Additional context specified by the prompt for its type 1 category. |

**Blood pressure, eGFR, urine ACR, creatinine and LDL are monitoring/context measures, not independent diabetes classification criteria.** The current classifier has a known limitation: failed/empty model output can retain a default prediabetic label or use keyword fallbacks. Its label and diagnostic basis always require clinician verification; the implementation does not validate all diagnostic criteria, repeat-testing requirements, or alternative indications for medicines.

Requested numerical charts are limited to supported diabetes-related OCR measurements: **HbA1c, fasting/post-meal glucose, eGFR, urine ACR, creatinine, LDL, and systolic/diastolic blood pressure**. Only documented, dated, source-linked values are plotted. General cardiac/heart-disease charts are outside this release's supported scope. Narrative records about other conditions can still be retrieved and summarized with citations. Missing years and measurements remain gaps.

### Patient conversations and charts

Chat sessions, messages, and requested charts are saved in MongoDB for the selected patient and signed-in doctor. Use **New chat session**, the conversation selector, and **Session charts** to return to earlier work. Replies render headings, emphasis, real HTML tables, and inline numbered source links. Clicking a citation or chart point opens its OCR evidence on the right. The Source Proof panel starts closed in chat and can close or expand into the record workspace. The navigation rail collapses on every screen.

Chart requests create a new named artifact from dated OCR measurements and save it in the session. Chat stays on the left and the chart opens on the right. Collapse chat for a full-width chart, or collapse the chart for full-width chat; toolbar controls restore either panel. Clicking a citation opens Source Proof in the right-hand panel. Supported extraction includes HbA1c, fasting/post-meal glucose, eGFR, urine ACR, creatinine, LDL, and recorded blood pressure. Heart-disease chart requests display a diabetes-agent scope warning instead of an unrelated chart; cited cardiac text summaries remain available. Missing requested data produces a gap state. No example values, model-invented points, or missing-year estimates are inserted. Chart generation does not require an LLM or embedding service.

The local model defaults to loopback (`127.0.0.1:1234`), avoiding a changing LAN address. Set `LOCAL_LLM_BASE_URL` explicitly if the model runs elsewhere. Local model calls have bounded timeouts. When embeddings fail, BM25 retrieval remains available; if synthesis fails, the response identifies itself as sourced excerpts. Processing bubbles show the actual active retrieval, chart, or review-agent stage. Interrupted jobs become retryable after a server restart.

**Settings** contains per-account browser preferences: Light/Dark/System appearance, larger text, contrast, doctor dictation language and Read aloud visibility, and admin appointment time defaults. These preferences stay in that browser; they are not synchronized through MongoDB. Read aloud is always click-to-play. Restart the API after pulling backend changes; the Vite UI updates automatically.

### Patient folder intake

**New patient intake** is one panel for registration and records. Enter full name, DOB (or age when DOB is unknown), sex, and doctor; choose **Upload record** or **Upload patient folder**, or register without a file. To append records later, select the existing patient in the same panel. Explicit demographics are stored in the registry and remain separate from agent inference. An entered age is a recorded observation; no artificial birth date is invented.

Folder selection accepts one folder such as `PP001_Ananya_Baruah`. Its `PP001` ID and complete folder name become searchable aliases; PrepPulse creates or reuses a separate immutable `PRP-` ID. Selecting an existing patient attaches the folder to that patient instead of registering another one. Alias collisions with a different patient are rejected; names alone never silently merge patients. The UI shows selected/saved/unchanged counts, document totals, processing stages and failures. PDF, PNG, and JPEG files are processed; auxiliary files remain private. Unchanged relative-path/hash pairs are skipped and changed files are retained as new versions. Current Edge and Chrome support browser folder selection. Doctors can append a record or folder to an assigned patient from the upload dialog.

### Caregiver portal and signed care plans

Admins create every account in **Accounts**. Choose the caregiver role and **Family caregiver** or **Professional caregiver** there. **Caregivers** contains patient assignment on the left and the searchable caregiver roster on the right; it does not duplicate account creation. Filter registered caregivers by type, name, username or ID, assign/revoke patient access, and mark availability **Free** or **Active**. Availability is an administrator-maintained status, separate from patient access. Caregivers sign into the same PrepPulse browser address and receive a dedicated **My care plans** workspace with one menu item. They see assigned patients and signed instructions, not clinician briefs, original source files, chat sessions, or unsaved drafts. Admins can revoke assignments and disable accounts.

All existing and new accounts receive a stable searchable public ID: `ADM-` for admins, `DOC-` for doctors, `FAM-` for family caregivers, and `CGV-` for professional caregivers. The original internal `user_id` remains unchanged so existing assignments and visit links remain intact. A separate `staff_directory` collection mirrors non-secret account identity and status fields. Accounts can be searched by name, username, public ID or internal ID.

Patients shows a simple checkbox list, a shared language selector, a small **Edit pathway** link, and the selected-language download for the latest signed plan. All text editing, adding/removing items, frequency controls, notes and prescribing remain in **Care pathways**. Each pathway item initially shows a checkbox; its **Edit** link reveals the existing text/frequency/remove controls, and **Done editing** returns to the checkbox view. New-item entry remains available there. The pathway editor adds doctor notes and medicine/injection/treatment entries: free-text name and dose/application, start date, duration in days/months, morning/afternoon/evening/bedtime buttons, and food timing. `+ Add medication / treatment` adds another entry. PrepPulse never chooses a prescription or dose automatically. Admission selects caregiver mode; otherwise the plan is a family pathway.

The **Family / caregiver pathway** card shows up to three items: doctor-written/edited instructions first, then agent suggestions in their original priority order. Its language and ticks stay synchronized with the lower checklist and pathway screen. Active-visit ticks are clinician preparation checks, stored separately in `care_visit_checks`; they do not change translation revisions or create caregiver treatment-completion reports. Signed-plan ticks display caregiver-reported completion and are read-only for the doctor.

Caregiver preparation uses short, everyday actions: bring earlier reports and discharge papers, bring current medicine packets and existing requested home logs, and note new/returning symptoms or questions. The prompt receives documented dated measurements and other recorded conditions so it can suggest discussing changes without inventing a spike or condition. It does not issue new testing/monitoring schedules, prescriptions or diet instructions from classification alone. Raw findings such as "Review eGFR: 90" are no longer turned into fallback checklist tasks. With a brief but unavailable synthesis, general visit-preparation reminders are explicitly suggestions. With no brief, the checklist remains empty. Existing signed instructions remain unchanged; improving their wording requires a newly reviewed plan. A later visit preserves previous signed instructions and completion reports, while its new draft starts empty for the clinician; rerunning analysis does not overwrite it or regenerate an already signed checklist.

Edits autosave after a short pause. Conflicting revisions are rejected instead of overwriting another window's changes. English, Hindi, Tamil, Bengali, Odia, and Telugu toggles are available. Checklist and doctor-note translations run in the background through the configured LLM; edited text invalidates old translations. Source text stays visible with a pending/unavailable label while translation is unavailable. **Refresh translations** retries it. Medication names/doses remain exactly as entered; schedule labels have fixed translations. Check translated wording before clinical use.

**Sign off and end session** saves a permanent pathway, clinician identity/time, patient snapshot, available brief snapshot, and source-record IDs. **Download and end session** also downloads the selected language. PDFs paginate automatically and have page numbers. The signed source PDF is appended to patient Records; previous plans remain available under **Previous caregiver pathways and follow-up**. The active draft ends with the visit. Translated copies are stored separately from the signed source data. A PDF in a language with incomplete translations returns a clear unavailable message rather than pretending source text is a completed translation.

Caregivers tick dated tasks and add timestamped notes. Daily medication tasks run through the selected duration; each new date starts with its own completion state. Past dates can be reviewed and reported later; future completion is rejected. The next signed pathway supersedes the old daily checklist going forward. Completed/past-due states and notes persist in MongoDB and refresh in the doctor's next visit and Records view. The label is **caregiver-reported completion**, not proof that medication was actually administered. Past-due means a past calendar-day task was not reported complete; this release does not send reminders or infer a missed dose by clock time.

### Appointment and visit history

Admin appointments use two rows: **New appointment** and **Today's appointments** above, then **Find previous appointments** and a vertically scrollable **Previous appointments** list below. Search by name, PrepPulse ID, or folder alias across dates; filter by a specific date, Today, Previous, or All dates. The history list is newest first and has no edit/delete controls. Completed appointments from today also appear in previous history. **Expand appointments** opens a separate full workspace with a Back button. Doctors use the same history filters in **Records**. Starting a visit links the next scheduled appointment for that patient/doctor on the current date; sign-off marks that linked appointment completed. Unscheduled visits still retain their own visit ID.

Patient cards in Records open dated visit links, signed pathways and caregiver follow-up. **Browse patient records** opens the full Source Proof-style record workspace with searchable text and selectable files. New visits preserve sign-off snapshots; older visits without a captured snapshot are explicitly identified rather than reconstructed from today's brief. Guidance library has been removed from the navigation and page implementation.

Previous patients and visits are accessed through **Records**; the separate Previous patients menu/page has been removed. Existing search, dates, dropdowns, collapses, saved visit details and source workspaces remain. Expanded appointment history can open the historical consultation view, where a banner distinguishes a saved snapshot from current reference data. Chat remains patient-wide. The visit/record section now has more spacing between its disclosures and visit links.

In the admin **Patient directory**, select a card to edit demographics, retain/add doctor assignments, inspect appointment/visit dates, and browse all records by default. A dropdown filters records to a visit or appointment date. Uploads can be attached to the selected visit; older documents without a visit link are matched by date and labeled accordingly. Administrators may edit a document's display title/type/date, never its original filename or source bytes. Signed pathway dates and types remain immutable. Records and processing counts refresh every five seconds, including newly signed pathway PDFs.

After updating, restart the Python API. MongoDB collections/indexes are added automatically on the API's first connection; existing patients and accounts are retained. No database reset or re-registration is required.

### Avoiding an outdated API on port 8000

An older Python process can keep serving the previous release even after Vite shows updated pages. Symptoms include `role: Input should be 'doctor' or 'admin'`, or **Not Found** for care plans and appointment history. The UI checks `/api/runtime` for contract `preppulse-ui-care-3` and shows a compatibility banner when these routes are unavailable.

From the repository root, use the Windows launcher:

```powershell
.\scripts\start_ui_api.ps1
# After another backend update, when analysis/chat jobs have finished:
.\scripts\start_ui_api.ps1 -Restart
```

It refuses to stop an unrelated service, checks analysis/chat work before replacing an older PrepPulse API, and uses development reload by default. `-Restart` explicitly permits interruption of active work, so let jobs finish first. Use `-NoReload` if reload is unwanted. If `PREPPULSE_SESSION_SECRET` is unset, the launcher generates or reuses `private_data/.session-secret`, which is ignored by Git; keep it private. An existing API using another secret will require a fresh browser sign-in after replacement. Patients, accounts, uploaded sources and existing joins are not reset. Environment variables for LM Studio still need to be available in the launcher terminal, as shown above.

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

Caregiver/admin API regressions: `pytest tests/test_care_presentation.py tests/test_admin_repairs.py tests/test_caregiver_workflow.py tests/test_ui_api.py -q`. The isolated browser fixture uses an in-memory MongoDB substitute and synthetic patient data; it never opens your MongoDB. Start it with `python -m uvicorn care_browser_app:app --app-dir tests --port 8001`, point a separate Vite process to `PREPPULSE_API_TARGET=http://127.0.0.1:8001` on port 5174, then set `PREPPULSE_CARE_FIXTURE=1` and run `node node_modules/@playwright/test/cli.js test e2e/caregiver.spec.ts` from `web`. Its translation service is a deterministic test substitute; live LLM translation quality must be reviewed separately.

The first release targets a local browser and local MongoDB. Before any shared deployment, review authentication, TLS, file encryption, backups, and clinical data handling for that environment.
