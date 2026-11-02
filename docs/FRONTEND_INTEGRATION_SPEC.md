# PrepPulse browser workspace: UI and integration handoff

Updated 30 October 2026. This document describes the `UI` branch implementation and its intended user flows. PrepPulse is assistive clinical chart review. A generated finding, gap, or pathway suggestion is not an autonomous diagnosis or treatment instruction.

## 1. Source of truth and visual reference

The two Replit screenshots supplied by the project owner are the reference for the doctor **Patients** page. The screen uses a dark navy left rail, pale gray workspace, warm white rounded panels, compact teal labels, four colored consultation cards, a dated findings list, and a right Source Proof panel. The new app uses the same visual hierarchy and restrained line icons. The current subtitle is **Diabetes Clinical Intelligence**. Do not use emoji or a clinic name. The supplied screenshots are not stored as image files in this repository; use the owner's originals for pixel comparison.

The current code contract is `src/preppulse_agents/schemas.py:ConsultationBrief`. The old examples in this document referred to a nonexistent `DecadeConsultationBrief` and `cards[]`. Those were mock shapes and are **not** API payloads. `freshness_score` currently comes from a fixed agent compiler value, so the UI deliberately avoids claiming a clinically fresh score.

## 2. Roles, access, and navigation

| Capability | Doctor | Admin |
|---|---|---|
| Sign in | Yes | Yes |
| Search/open patients | Assigned patients only | Registry metadata |
| Register patient | No | Yes |
| Append documents | Assigned patients | Any registered patient |
| Clinical brief, source proof, chat | Assigned patients | No |
| Start/admit/end visit, review finding, approve pathway | Assigned patients | No |
| Create/edit/cancel appointments | No | Yes |
| Create/disable accounts, assign doctor | No | Yes |

Accounts are admin managed. There is no public signup. The first account is created with `scripts/bootstrap_ui_admin.py` and environment variables. Session cookies are signed, HTTP only, and SameSite Strict. Mutating requests require the CSRF token returned by login or `/api/auth/me` in `X-CSRF-Token`. API routes enforce role and assignment. The first release binds to local loopback; this is not a shared production deployment.

Doctor rail: **Today**, **Patients**, **Records**, **Care pathways**, **Guidance library**, **Settings**. Patients is the landing page. Admin rail: **New patient intake**, **Patient appointments**, **Patient directory**, **Accounts**, **Settings**. New patient intake is first and is the admin landing page. The admin has no clinical brief view by default.

## 3. Patient identity and longitudinal records

`patient_id` is an immutable internal ID with the `PRP-` prefix. It is the join key for visits, appointments, documents, brief jobs, and pathways. Existing sample folder codes, such as `PP001`, and the full folder name, such as `PP001_Ananya_Baruah`, are searchable aliases in `external_aliases`. Both IDs appear in the doctor's patient context where an external alias exists. A name search may return multiple patients; the user chooses one explicitly. Doctors can only search their assigned patients.

Option 3 in New patient intake accepts one browser-selected folder named `ID_Patient_Name`, such as `PP001_Ananya_Baruah`. The folder name supplies the external ID and display name; a new `PRP-` ID is assigned internally. The short ID and full folder name are searchable aliases. The browser uploads the selected files and their relative paths, and the API copies every file to patient-scoped private storage. PDF, PNG, and JPEG files become clinical documents; auxiliary files such as `manifest.json` and `RECORD_INDEX.txt` are retained but not sent through OCR. A manifest can supply visit date and document type, but cannot override the folder identity. Reimporting an unchanged relative path and hash skips that file; a changed file becomes a new stored version. Colliding external IDs are rejected rather than assigned to a different patient. The old all-dataset scanner was removed.

Admins register the patient name, optional birth date and sex, and an assigned doctor. They may immediately attach initial records or later select the same patient to append visit documents. Doctors may append records for assigned patients from the Patients and Records pages. Each file gets a distinct `DOC-` record ID, visit date, document type, and private source path. Accepted formats: PDF, PNG, JPEG; maximum upload size: 30 MB. The browser never receives a filesystem path. Generated OCR is written to the existing `patient_documents` collection using the internal PrepPulse ID, so RAG patient filtering stays consistent across imported and new patients.

## 4. Doctor screens and interactions

### Today

Admin-entered appointments show on the doctor's Today page for the local date, ordered by time. Each horizontal card displays time, patient name, PrepPulse ID, age when available, sex when available, and visit date. Selecting a card opens Patients. The client refreshes appointments every 15 seconds; this is near-real-time polling, not a push subscription. Cancelled appointments are omitted from active Today cards.

### Patients (main workspace)

Top toolbar: breadcrumb, selected patient name and PrepPulse ID, patient search, user identity. Main greeting and action area: **Start visit**, **Upload new record**, then **Admit patient** and **Review pathway / end session** during an active visit. The pale teal information strip reminds clinicians to verify source records.

The center consultation panel follows the screenshot:

1. Patient header: name, age/sex when available, agent classification, PrepPulse ID, optional external alias, and review status.
2. Four cards: `trajectory.kpis`; `care_gaps.items`; `mismatches.items`; and `caregiver_prep.checklist`. Card four's displayed family/caregiver mode follows the active visit's admission flag. Agent checklist content remains suggestions until a clinician chooses items for the pathway.
3. Visit focus strip: agent visit focus, latest available metric, and count of potential review items. It is not a clinical freshness claim.
4. Priority findings: list from verified agent milestones plus source-backed metric observations already present in the brief. Unverified agent claims are excluded. Each has Accept/Edit/Reject review controls. Review decisions are stored per visit.
5. Assistive bubbles: exploratory prompts that open the chat workspace.

If no brief exists, show an empty state and **Run clinical analysis**. The top **Analyze records** action starts the same patient-scoped OCR, RAG, and eight-node agent workflow. Analysis creates a background job, reports queued/running/failed/complete, document counts and stage, and can be retried after failure. Uploading a new file does not silently regenerate a brief; the clinician reruns it. The previous brief remains visible while a replacement is built.

### Source Proof and chat

The right column has a Source Proof panel above chat, followed by a six-language checklist and source/review status. When a brief loads, the first verified finding is selected as the initial source. Source Proof expands into a full record workspace with page navigation, text search, and selectable file tiles on the right. Chat opens its own dedicated workspace with patient context. On narrower browser widths, panels reflow below the consultation panel. The same selected patient context is used in both chat views.

For a verified citation, `document_id` is a `DOC-` record ID, `page_number` starts at 1, and `bbox` is `[x0, y0, x1, y1]` normalized to 0–1000. The authenticated page endpoint renders a PNG. The browser overlays the box with:

```
left = x0 / 10 %          top = y0 / 10 %
width = (x1-x0) / 10 %   height = (y1-y0) / 10 %
```

The overlay must remain aligned as the preview scales. The API checks patient ownership, page existence, non-default geometry, and a contiguous matching phrase in OCR tokens inside the candidate box. It replaces a broad retrieval-chunk box with the narrow token union before setting `source_verified: true`. Old broad citations are not highlighted in the full workspace until reanalysis. Generated agent citations may lack a matching document span; those display **Source needs verification**. The Records page may preview a document separately without claiming a particular highlighted span.

Chat is bound to the selected patient. The API creates a patient-scoped hybrid retriever from existing OCR documents and returns `answer_markdown` plus structured citations. Timeline questions add relevant excerpts from each documented year so five similar recent records do not hide earlier visits. When no live model is available, chat returns labeled source excerpts. A model-generated answer remains assistive and its citations require review. Chat cannot alter a visit, pathway, or record.

### Records

Use horizontally browsable patient cards, then a dated list of the selected patient's documents. Show type and processing state (`pending`, `ready`, `failed`) with useful failure text. New visits append documents to the same patient. Search and cards are scoped to assigned patients.

### Care pathways

An active visit starts as a **family pathway**. **Admit patient** records only a PrepPulse care-workflow flag and changes the draft to a **caregiver pathway**. It does not create a hospital admission. Switching the flag back restores the family mode. The doctor can save narrative handoff notes, add checklist items, check them off, and review agent suggestions before adding any suggestion as a clinician-selected item. Agent suggestions are not silently finalized.

The draft may list only clinician-reviewed findings with verified citations. **End session** asks for explicit confirmation. A visit with no notes or checklist items requires a separate evidence-only confirmation. Finalization stores a versioned, doctor-approved pathway and marks the visit ended. A later visit starts a new draft and preserves the older version. The Care pathways UI displays prior approved versions from the patient-scoped pathway history route.

### Other pages

Guidance library has an empty approved-content state. No clinical guidance is generated or imported without owner approval. Settings supports local per-account display, voice, and scheduling defaults saved in the browser; no patient information is saved in those preferences. On Today, Records, Care pathways, Guidance library, and Settings, a small movable assistant bubble opens compact chat with typed or spoken input. It does not offer uploads and should not obscure essential controls.

## 5. Admin screens

**New patient intake:** Option 1 registers a patient and doctor; option 2 appends a single document to an existing patient; option 3 uploads exactly one patient folder and all its files. Folder intake reports saved/unchanged file counts and an OCR/analysis job with ready/failed document counts. Registration and folder intake reject a missing active doctor assignment.

**Patient appointments:** choose registered patient and assigned doctor, visit date/time, and a scheduling note. Create, edit, and cancel appointments. The doctor sees scheduled appointments on Today after the next refresh. Appointment status and clinical visit status are separate.

**Patient directory:** browse registry cards with internal and optional external IDs and assign an additional doctor. Clicking a card opens an admin-only overview with assigned doctors, document states, visit log, and all appointments; clinical notes and the consultation brief are excluded. **Accounts:** create doctor/admin accounts and disable accounts; self-disable is rejected. **Settings:** Light/Dark/System display, text and contrast, and appointment start-time/step defaults; preferences remain in that browser.

## 6. API and data contracts

All routes start with `/api`; JSON except multipart upload/transcription and PNG preview. Mutations require `X-CSRF-Token`. Authenticated routes respond with 401 when signed out, 403 for wrong role or unassigned patient, 404 for unavailable records, and 400/409 for invalid or conflicting input.

| Route | Role | Purpose |
|---|---|---|
| `POST /auth/login`, `GET /auth/me`, `POST /auth/logout` | Both | Session and CSRF |
| `GET /patients?q=`, `GET /patients/{id}` | Both, scoped | Search and select |
| `POST /patients`, `POST /admin/import-folder`, `POST /patients/{id}/assign/{doctor_id}` | Admin | Register/upload one folder/assign |
| `GET /admin/patients/{id}/overview` | Admin | Patient administration history, without clinical brief or notes |
| `GET/POST /patients/{id}/documents`, `GET /patients/{id}/documents/{record_id}/page/{page}` | Scoped | Append and inspect source records |
| `GET /patients/{id}/documents/search?q=` | Doctor, scoped | Search OCR page text and filenames for the full record workspace |
| `POST /patients/{id}/brief/jobs`, `GET /patients/{id}/brief/jobs/latest`, `GET /patients/{id}/brief` | Doctor | Build and read agent brief |
| `GET/POST /appointments`, `PATCH /appointments/{id}`, `POST /appointments/{id}/cancel` | Admin writes; doctor reads own | Scheduling |
| `GET/POST /patients/{id}/visits`, `GET /patients/{id}/pathways`, `POST /visits/{id}/admission`, `POST /visits/{id}/notes`, `POST /visits/{id}/decisions` | Doctor | Visit, approved pathway history, and review state |
| `GET /visits/{id}/pathway`, `POST /visits/{id}/pathway/items`, `PATCH /visits/{id}/pathway/items/{item_id}`, `POST /visits/{id}/end` | Doctor | Draft checklist and approval |
| `POST /chat/query` | Doctor | Patient-scoped evidence answer |
| `GET /voice/capabilities`, `POST /voice/transcribe`, `POST /voice/speak` | Doctor | Local dictation and opt-in WAV playback |
| `GET/POST /admin/accounts`, `PATCH /admin/accounts/{id}/disable` | Admin | Account management |

`GET /patients/{id}/brief` returns `{ patient_id, brief, generated_at }`. `brief` is the current `ConsultationBrief` model with `trajectory`, `care_gaps`, `mismatches`, `caregiver_prep`, `priority_findings`, `metric_series`, and `assistive_bubbles`. Nested citation objects add `source_verified`. Do not treat `classification.category` as `pre_diabetic`: the code uses `prediabetic`. KPI date is `date_str`; gap description is `details`; citation page is `page_number`. Frontend types are in `web/src/api.ts`.

## 7. Voice and local models

Doctor microphone dictation uses browser audio capture, then `faster-whisper` `small` with CPU INT8 through `POST /voice/transcribe`. The transcript populates the input for review; it is never auto-sent. Temporary audio is deleted after transcription. Initial model download and CPU performance must be checked on the target machine.

The downloaded `mradermacher/Qwen3-1.7B-Multilingual-TTS-GGUF` is intended for optional spoken replies; it cannot transcribe dictation. `PREPPULSE_TTS_MODEL_PATH` is an optional local file reference. The active adapter uses `PREPPULSE_TTS_ENDPOINT` (a full `/v1/audio/speech` URL) and `PREPPULSE_TTS_MODEL_ID` (default `qwen3-1.7b-multilingual-tts`). `/voice/capabilities` sends a harmless probe and enables **Read aloud** only after the endpoint returns actual WAV data. `POST /voice/speak` requires a doctor, assignment to the specified patient, and an explicit click; audio is not stored, and the response is marked `Cache-Control: no-store`. The tested LM Studio server at `192.168.1.50:1234` lists the model but does not implement `/v1/audio/speech`, so this server does **not** currently enable playback. A compatible audio runtime and language tests remain required. Text chat and dictation remain usable. Spoken patient information must always be opt-in.

## 8. Run, test, and limitations

Install Python dependencies from `requirements.txt` and frontend dependencies with `npm install` in `web/`. Set a random `PREPPULSE_SESSION_SECRET` of at least 32 characters and local MongoDB. Set `PREPPULSE_ADMIN_USER`, `PREPPULSE_ADMIN_NAME`, and a 12+ character `PREPPULSE_ADMIN_PASSWORD`; run `python scripts/bootstrap_ui_admin.py` once. Start `python -m uvicorn preppulse_api.app:app --host 127.0.0.1 --port 8000` and `npm run dev` in `web/`; open the Vite local URL. Vite proxies `/api` to loopback port 8000.

For the owner-approved fresh start, `scripts/reset_ui_patient_data.py` previews collection counts and `--apply --confirm preppulse` clears patient-linked MongoDB collections after the API is stopped. It retains both login accounts, database indexes, and original local dataset files. It also clears patient audit events so old patient IDs do not remain in the workspace.

The current integration is local-only. It has no shared-host HTTPS, production secret management, backups, or approved content library. A working GGUF audio runtime remains to be connected, and the sidebar checklist's temporary check marks are not persisted. `scripts/audit_dataset_pipeline.py` is **not** a UI entry point; it clears MongoDB. Existing agent citation generation and fixed freshness score remain backend limitations. The UI therefore hides unverified highlights and avoids a clinical freshness claim.
