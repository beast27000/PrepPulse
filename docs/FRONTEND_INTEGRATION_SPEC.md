# PrepPulse browser workspace: UI and integration handoff

Updated 3 November 2026. This document describes the `UI` branch implementation and its intended user flows. PrepPulse is assistive clinical chart review. A generated finding, gap, or pathway suggestion is not an autonomous diagnosis or treatment instruction.

## 1. Source of truth and visual reference

The two Replit screenshots supplied by the project owner are the reference for the doctor **Patients** page. The screen uses a dark navy left rail, pale gray workspace, warm white rounded panels, compact teal labels, four colored consultation cards, a dated findings list, and a right Source Proof panel. The new app uses the same visual hierarchy and restrained line icons. The current subtitle is **Diabetes Clinical Intelligence**. Do not use emoji or a clinic name. The supplied screenshots are not stored as image files in this repository; use the owner's originals for pixel comparison.

The current code contract is `src/preppulse_agents/schemas.py:ConsultationBrief`. The old examples in this document referred to a nonexistent `DecadeConsultationBrief` and `cards[]`. Those were mock shapes and are **not** API payloads. `freshness_score` currently comes from a fixed agent compiler value, so the UI deliberately avoids claiming a clinically fresh score.

## 2. Roles, access, and navigation

| Capability | Doctor | Admin | Caregiver |
|---|---|---|---|
| Sign in | Yes | Yes | Yes |
| Search patients | Assigned patients | Registry metadata | Assigned patient cards |
| Register patient | No | Yes | No |
| Append documents | Assigned patients | Any registered patient | No |
| Clinical brief, source proof, chat | Assigned patients | No | No |
| Start/admit/end visit, review finding, approve pathway | Assigned patients | No | No |
| Create/edit/cancel appointments | No | Yes | No |
| Create/disable accounts, assign doctor/caregiver | No | Yes | No |
| Read signed care instructions / PDF | Assigned patients | No | Assigned patients |
| Report task completion and caregiver notes | Read reports | No | Assigned signed plans |

Accounts are admin managed. There is no public signup. The first account is created with `scripts/bootstrap_ui_admin.py` and environment variables. Session cookies are signed, HTTP only, and SameSite Strict. Mutating requests require the CSRF token returned by login or `/api/auth/me` in `X-CSRF-Token`. API routes enforce role and assignment. The first release binds to local loopback; this is not a shared production deployment.

Doctor rail: **Today**, **Patients**, **Previous patients**, **Records**, **Care pathways**, **Settings**. Admin rail: **New patient intake**, **Patient appointments**, **Patient directory**, **Accounts**, **Caregivers**, **Settings**. Caregiver rail: **My care plans** only. Patients and intake are the respective doctor/admin landing pages. Guidance library has been removed. Caregivers receive assigned signed instructions and follow-up only; admins have no clinical brief view.

## 3. Patient identity and longitudinal records

`patient_id` is an immutable internal ID with the `PRP-` prefix. It is the join key for visits, appointments, documents, brief jobs, and pathways. Existing sample folder codes, such as `PP001`, and the full folder name, such as `PP001_Ananya_Baruah`, are searchable aliases in `external_aliases`. Both IDs appear in the doctor's patient context where an external alias exists. A name search may return multiple patients; the user chooses one explicitly. Doctors can only search their assigned patients.

New patient intake now uses one panel for name, DOB or recorded age, sex, doctor, and record/folder upload. One selected folder must be named `ID_Patient_Name`; its short/full names become searchable aliases. Explicit registration demographics are authoritative. Select an existing patient to append files without another registration. Private storage, relative-path/hash deduplication, auxiliary-file retention and background progress remain unchanged. Alias collisions with another patient produce a conflict.

Admins register the patient name, optional birth date or recorded age and sex, and an assigned doctor. They may immediately attach initial records or later select the same patient to append visit documents. Doctors may append records for assigned patients from the Patients and Records pages. Each file gets a distinct `DOC-` record ID, visit date, document type, and private source path. Accepted formats: PDF, PNG, JPEG; maximum upload size: 30 MB. The browser never receives a filesystem path. Generated OCR is written to the existing `patient_documents` collection using the internal PrepPulse ID, so RAG patient filtering stays consistent across imported and new patients.

## 4. Doctor screens and interactions

### Today

Admin-entered appointments show on the doctor's Today page for the local date, ordered by time. Each horizontal card displays time, patient name, PrepPulse ID, age when available, sex when available, and visit date. Selecting a card opens Patients. The client refreshes appointments every 15 seconds; this is near-real-time polling, not a push subscription. Cancelled appointments are omitted from active Today cards.

### Patients (main workspace)

Top toolbar: breadcrumb, selected patient name and PrepPulse ID, patient search, user identity. Main greeting and action area: **Start visit**, **Upload new record**, then **Admit patient** and **Review pathway / end session** during an active visit. The pale teal information strip reminds clinicians to verify source records.

The center consultation panel follows the screenshot:

1. Patient header: name, age/sex when available, agent classification, PrepPulse ID, optional external alias, and review status.
   The diabetes journey leads the brief with dated source coverage, the documented diagnosis consultation when present, first/latest HbA1c, and selectable visit cards. Admissions, procedures, and other consultations also appear as source-linked tiles. These use `diabetes_history` and `record_summaries`; laboratory summaries preserve extracted values rather than model-generated interpretations.
2. Four cards: `trajectory.kpis`; `care_gaps.items`; `mismatches.items`; and the shared care bundle's active draft, previous signed checklist or first-visit suggestions. Card four's displayed family/caregiver mode follows the active visit's admission flag. Generic preparation templates are filtered; verified findings may supply review prompts when agent suggestions are absent. Suggestions require clinician review. An empty source-backed care gap is not converted to a fabricated instruction.
3. Visit focus strip: agent visit focus, latest available metric, and count of potential review items. It is not a clinical freshness claim.
4. Priority findings: verified current observations with prior-measurement links, and source-backed earlier admissions/procedures/consultations. Repeated unit suffixes are normalized. Unverified agent claims and generic care gaps without source evidence are excluded. Each finding has Accept/Edit/Reject review controls. Review decisions are stored per visit.
5. Assistive bubbles: exploratory prompts that open the chat workspace.

If no brief exists, show an empty state and **Run clinical analysis**. The top **Analyze records** action starts the same patient-scoped OCR, RAG, and eight-node agent workflow. Analysis creates a background job, reports queued/running/failed/complete, document counts and stage, and can be retried after failure. Uploading a new file does not silently regenerate a brief; the clinician reruns it. The previous brief remains visible while a replacement is built.

### Source Proof and chat

The right column has chat first, Source Proof second, then the six-language editable checklist and source/review status. Each section collapses independently; the whole rail can hide to give the brief the full width. When a brief loads, the first verified finding is selected as the initial source. Source Proof expands into a full record workspace with page navigation, text search, and selectable file tiles on the right. Chat opens its own dedicated workspace with patient context. On narrower browser widths, panels reflow below the consultation panel. The same selected patient context is used in both chat views.

For a verified citation, `document_id` is a `DOC-` record ID, `page_number` starts at 1, and `bbox` is `[x0, y0, x1, y1]` normalized to 0–1000. The authenticated page endpoint renders a PNG. The browser overlays the box with:

```
left = x0 / 10 %          top = y0 / 10 %
width = (x1-x0) / 10 %   height = (y1-y0) / 10 %
```

The overlay must remain aligned as the preview scales. Small previews scroll to center the verified span after image load or a citation change. The API checks patient ownership, page existence, non-default geometry, and a contiguous matching phrase in OCR tokens inside the candidate box. It replaces a broad retrieval-chunk box with the narrow token union before setting `source_verified: true`. Old broad citations are not highlighted in the full workspace until reanalysis. Generated agent citations may lack a matching document span; those display **Source needs verification**. The Records page may preview a document separately without claiming a particular highlighted span.

Chat is bound to the selected patient and the signed-in doctor. Sessions, messages, turns, and chart artifacts persist in MongoDB. A doctor assigned to the same patient cannot open another doctor's conversation. The UI restores the selected session after reload and provides a new-session action and conversation selector.

The chat workspace starts as one full-width conversation. A requested chart opens on the right with the conversation on the left. Collapse chat to give the chart the full available width, or collapse the chart to give chat the full width. Toolbar controls restore either view; saved chart links remain available. Clicking an inline citation, plotted point, or source-data table link switches the right panel to Source Proof and restores chat on the left. The source dock can close or open the full record workspace. Heart-disease chart requests show an explicit scope warning listing supported OCR measurements; they do not silently generate glucose charts. Cited text summaries of cardiac records remain available.

Replies render through `react-markdown` with `remark-gfm`: headings, lists, bold values, and actual HTML tables. Raw HTML is not enabled. Numeric references `[n]` become buttons bound to that response's structured citation array; artifact links bind to the saved artifact ID. Unverified spans remain inspectable as records but do not receive fabricated highlights. A model-generated answer remains assistive; chat never alters clinical records or care pathways.

Chart requests are handled by a chart tool. It extracts measurements from normalized OCR rows, retains document/page/box provenance, applies requested metric/year filters, creates a new artifact ID, and persists its series/events in the session. Recharts renders time-based axes, tooltips, keyboard-accessible source points, and an optional data table. Different units use separate plots. No missing observations are filled in. Distinct source reports on the same day retain their individual values and citations. HbA1c, fasting/post-meal glucose, eGFR, urine ACR, creatinine, LDL, and blood pressure are currently supported. Unsupported chart requests show a data gap. Chart construction is independent of model and embedding availability.

Non-chart questions use source records plus hybrid question retrieval and prior conversation turns. If embeddings fail, retrieval continues with BM25. The default inference URL is `http://127.0.0.1:1234/v1`, configurable via `LOCAL_LLM_BASE_URL`; connection timeouts are bounded. A synthesis outage produces labeled source excerpts rather than an ungrounded answer. Background turns expose actual processing stages and failure/retry states. Analysis uses LangGraph node updates for its stage bubble, followed by a bounded history synthesis pass. A restarted server marks interrupted work retryable instead of leaving it queued indefinitely. This local worker tracking assumes one API process.

### Records

Use assigned-patient cards, previous-appointment filters and dated visit links. Each link opens saved visit information, snapshots when captured, and signed care plans with caregiver follow-up. Older missing snapshots are explicitly identified. Browse patient records opens the existing full record workspace with file tiles, page navigation and text search; signed pathway PDFs appear beside uploaded source files.

### Care pathways

An active visit starts as a **family pathway**; the admission flag switches it to **caregiver**. Patients and Care pathways share an autosaved, revisioned draft. Doctors edit/delete/add checklist items, choose once/daily frequency, enter notes and add prescribed treatments with explicit name/dose, start date, duration, time-of-day slots and food timing. AI checklist content is marked as a suggestion until clinician sign-off.

English, Hindi, Tamil, Bengali, Odia and Telugu are supported. Text edits invalidate old translations and queue a revision-checked translation job; source text remains visibly labelled while pending or unavailable. Medication names and doses bypass the LLM. Fixed schedule labels are localized.

Sign-off requires clinician confirmation and records the source plan, approver, patient/available brief snapshot and document IDs. It ends the draft, completes a linked appointment and appends a source PDF to Records. PDFs paginate automatically; selected-language downloads require complete translations. Signed instructions remain immutable while derived translations and caregiver reports are stored separately. Earlier plans are accessed through Records.

Caregiver ticks and notes persist with actor/date/time. Each daily task has a distinct date/slot ID, future reporting is rejected, and past calendar-day tasks lacking completion reports are flagged. A later signed plan supersedes old daily tasks. This records caregiver-reported completion, not verified administration.

### Other pages

Guidance library has been removed. Settings supports local per-account display, voice, and scheduling defaults saved in the browser; no patient information is saved in those preferences. On Today, Records, Care pathways, and Settings, a small movable assistant bubble opens compact chat with typed or spoken input. It does not offer uploads and should not obscure essential controls.

## 5. Admin screens

**New patient intake:** one panel registers/selects a patient and captures demographics, doctor and record/folder uploads. The standalone option 3 was removed. Folder intake reports saved/unchanged file counts and an OCR/analysis job with ready/failed document counts. Registration and folder intake reject a missing active doctor assignment.

**Patient appointments:** choose registered patient and assigned doctor, visit date/time, and a scheduling note. Create, edit, and cancel appointments. The doctor sees scheduled appointments on Today after the next refresh. New appointment and Today's appointments are the first row; separate search and scrollable history panels occupy the second row. History supports name/either ID and exact-date filtering, is newest first, includes completed appointments from today, and has no edit/delete controls. Expand opens a separate workspace with Back, not a nested overlay. Starting a visit links the first scheduled appointment for that patient/doctor on that date; ending it completes the appointment.

**Patient directory:** browse registry cards with internal and optional external IDs and assign an additional doctor. Clicking a card opens editable demographics, assigned doctors, document states, visit log, and appointments; clinical notes and the consultation brief are excluded. All records is the default; select a visit/appointment date to filter, preview records, edit display title/type/date, or upload another record linked to the chosen visit. Source bytes, original filenames and signed pathway dates/types remain immutable. Poll every five seconds for records and processing states. **Accounts:** the sole place to create doctor/admin/family-caregiver/professional-caregiver accounts; search by name, username or public/internal ID, disable accounts; self-disable is rejected. **Caregivers:** patient-access assignment left and searchable roster/free-active status right; account creation is absent. **Settings:** Light/Dark/System display, text and contrast, and appointment start-time/step defaults; preferences remain in that browser.

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
| `GET/POST /chat/sessions`, `GET /chat/sessions/{id}` | Doctor, patient/owner scoped | Create/list/restore persistent conversations, messages and artifacts |
| `POST /chat/sessions/{id}/turns`, `GET /chat/turns/{id}` | Doctor, owner scoped | Queue a request and poll actual processing stage/result |
| `GET /voice/capabilities`, `POST /voice/transcribe`, `POST /voice/speak` | Doctor | Local dictation and opt-in WAV playback |
| `GET/POST /admin/accounts`, `PATCH /admin/accounts/{id}/disable` | Admin | Account management |

`GET /patients/{id}/brief` returns `{ patient_id, brief, generated_at }`. `brief` is the current `ConsultationBrief` model with `trajectory`, `care_gaps`, `mismatches`, `caregiver_prep`, `priority_findings`, `metric_series`, and `assistive_bubbles`. Nested citation objects add `source_verified`. Do not treat `classification.category` as `pre_diabetic`: the code uses `prediabetic`. KPI date is `date_str`; gap description is `details`; citation page is `page_number`. Frontend types are in `web/src/api.ts`.

The API adapter also adds `record_summaries`, `diabetes_history`, `history_synthesis`, and finding `related_citations`. `POST /chat/query` remains a synchronous compatibility route; the browser uses saved sessions and asynchronous turns. A turn request is `{ query }`; the response has `turn_id`, `status`, `stage`, `steps`, and timestamps. A session read returns `{ session, messages, artifacts, active_turn }`. Assistant messages store Markdown `text`, `citations`, `artifact_ids`, and presentation hints. Each chart artifact stores `artifact_id`, `title`, `kind`, source-linked `series` and `events`, its request, and creation time. The UI never executes model-supplied HTML, JavaScript, chart coordinates, or filesystem paths.

## 7. Voice and local models

Doctor microphone dictation uses browser audio capture, then `faster-whisper` `small` with CPU INT8 through `POST /voice/transcribe`. The transcript populates the input for review; it is never auto-sent. Temporary audio is deleted after transcription. Initial model download and CPU performance must be checked on the target machine.

The downloaded `mradermacher/Qwen3-1.7B-Multilingual-TTS-GGUF` is intended for optional spoken replies; it cannot transcribe dictation. `PREPPULSE_TTS_MODEL_PATH` is an optional local file reference. The active adapter uses `PREPPULSE_TTS_ENDPOINT` (a full `/v1/audio/speech` URL) and `PREPPULSE_TTS_MODEL_ID` (default `qwen3-1.7b-multilingual-tts`). `/voice/capabilities` sends a harmless probe and enables **Read aloud** only after the endpoint returns actual WAV data. `POST /voice/speak` requires a doctor, assignment to the specified patient, and an explicit click; audio is not stored, and the response is marked `Cache-Control: no-store`. The tested LM Studio server at `192.168.1.50:1234` lists the model but does not implement `/v1/audio/speech`, so this server does **not** currently enable playback. A compatible audio runtime and language tests remain required. Text chat and dictation remain usable. Spoken patient information must always be opt-in.

## 8. Run, test, and limitations

Install Python dependencies from `requirements.txt` and frontend dependencies with `npm install` in `web/`. Set a random `PREPPULSE_SESSION_SECRET` of at least 32 characters and local MongoDB. Set `PREPPULSE_ADMIN_USER`, `PREPPULSE_ADMIN_NAME`, and a 12+ character `PREPPULSE_ADMIN_PASSWORD`; run `python scripts/bootstrap_ui_admin.py` once. Start `python -m uvicorn preppulse_api.app:app --host 127.0.0.1 --port 8000` and `npm run dev` in `web/`; open the Vite local URL. Vite proxies `/api` to loopback port 8000.

For the owner-approved fresh start, `scripts/reset_ui_patient_data.py` previews collection counts and `--apply --confirm preppulse` clears patient-linked MongoDB collections after the API is stopped. It retains both login accounts, database indexes, and original local dataset files. It also clears patient audit events so old patient IDs do not remain in the workspace.

The current integration is local-only. It has no shared-host HTTPS, production secret management, backups, or approved content library. A working GGUF audio runtime remains to be connected, and target-model clinical translations need owner review. Checklist edits and caregiver reports now persist in MongoDB. `scripts/audit_dataset_pipeline.py` is **not** a UI entry point; it clears MongoDB. Existing agent citation generation and fixed freshness score remain backend limitations. The UI therefore hides unverified highlights and avoids a clinical freshness claim.

## 9. Caregiver release API and persistence (3 November 2026)

The detailed user workflow, classifier input rules and chart scope are also documented in [README](../README.md). Role checks remain server-side. Caregiver assignments are separate from doctor assignments; caregivers cannot access raw sources, briefs, chat, appointment history or unsigned drafts. Signed-plan responses exclude historical clinician snapshots and reviewed source citations.

| Route | Role / purpose |
|---|---|
| `GET /care/labels` | Authenticated six-language fixed-label dictionary |
| `GET /care/patients/{patient_id}?day=YYYY-MM-DD` | Assigned doctor/caregiver; returns `{draft, visit, plans, followup, day}`; caregiver draft/visit are null |
| `PUT /care/visits/{visit_id}/draft` | Owning doctor, active visit; accepts `{revision, items, medications, doctor_notes, notes_language}`; returns incremented revision; conflicting updates return 409 |
| `POST /care/visits/{visit_id}/translate` | Owning doctor; retry draft translation |
| `POST /visits/{visit_id}/end` | Owning doctor; `{confirm, confirm_evidence_only, draft_revision?}`; stores signed source plan/snapshots |
| `GET /care/pathways/{pathway_id}?day=...` | Assigned doctor/caregiver; returns `{plan, tasks, reports, past_due_unreported, notes}` |
| `PUT /care/pathways/{pathway_id}/report` | Assigned caregiver; `{task_id, day, completed}`; checks task/date membership and stores reporter/time |
| `POST /care/pathways/{pathway_id}/notes` | Assigned caregiver; `{text}`; appends timestamped note |
| `GET /care/pathways/{pathway_id}/pdf?language=en` | Assigned doctor/caregiver; private paginated download, 409 for incomplete translation |
| `POST /care/pathways/{pathway_id}/translate` | Assigned doctor/caregiver; retries a derived signed-plan translation |
| `GET/POST /admin/caregiver-assignments` | Admin; list/upsert `{patient_id, caregiver_id, kind: family|professional}` |
| `DELETE /admin/caregiver-assignments/{caregiver_id}/{patient_id}` | Admin revocation |
| `PATCH /patients/{patient_id}/demographics` | Admin; explicit name, DOB/recorded age, sex, selected active doctor |
| `POST /patients/{patient_id}/folder` | Admin/assigned doctor; multipart `files` and matching `paths`; append existing-patient folder and queue processing |
| `GET /appointment-history?q=&on=&scope=past&offset=0&limit=50` | Admin/doctor; name/either ID/date filters and pagination; doctor results are scoped |
| `GET /patients/{patient_id}/visit-records/{visit_id}` | Assigned doctor; saved visit, signed plan, snapshot availability, patient/brief snapshots, follow-up |

Checklist input: `{item_id, text, source_language, frequency: once|daily, source: agent|doctor}`. The server maintains `texts` by language; stale client translations are ignored. Prescription input: `{medication_id, name, dose, kind: medicine|injection|treatment, start_date, duration, duration_unit: days|months, times: [morning|afternoon|evening|bedtime], food: before food|after food|with food|not applicable}`. Durations are bounded to 730 days or 24 months. Month intervals use calendar months with month-end clamping.

New collections/indexes: `care_drafts` (unique visit), `caregiver_access` (unique patient/caregiver), `care_reports` (unique pathway/task), `care_notes` (pathway/time) and `care_translations` (unique signed pathway). Existing visits, appointments, pathways, source documents and audit events retain linked data. First API connection after restart creates indexes idempotently; existing accounts/patients remain intact.

Translations are derived from source text and checked for number preservation; a stale background result cannot overwrite a newer draft revision. Model outages produce an unavailable state with retry. Names/doses stay verbatim. These safeguards do not establish clinical translation accuracy: owner review with the target model is still required.

Tests use `tests/test_caregiver_workflow.py` and the isolated synthetic/in-memory browser fixture `tests/care_browser_app.py`, plus existing chart/citation/API/RAG regressions. Browser-fixture translations are deterministic substitutes; they do not measure live LLM quality.

## 10. Runtime, identity and historical review repairs

The browser checks `GET /api/runtime` every 30 seconds for `contract: preppulse-ui-care-2`. A missing/older API displays a clear restart notice. This distinguishes absent routes from absent patient data. The Windows launcher recognizes only `uvicorn preppulse_api.app:app` before stopping a listener, checks active jobs, preserves a private secret when no environment secret exists, and enables source reload. It does not modify patient collections or source files. See README for explicit restart behavior.

Existing `user_id` joins remain stable. Unique sparse `users.account_id` and unique `staff_directory.user_id/account_id` indexes support public `ADM-`, `DOC-`, `FAM-` and `CGV-` identities. Index initialization and account reads backfill older profiles; account creation, disable and availability updates mirror safe profile fields. Password hashes are excluded from the staff directory and responses. Availability is an admin-maintained label, not a grant of access. Assignment requires the caregiver's registered family/professional type to match the assignment type.

| Route | Contract / access |
|---|---|
| `GET /admin/accounts?q=` | Admin; name, username, public or internal ID; safe profiles only |
| `PATCH /admin/caregivers/{user_id}/availability` | Admin; `{availability: free|active}`; audited and mirrored |
| `PATCH /admin/patients/{patient_id}/documents/{record_id}` | Admin; `{display_name, document_type, visit_date}`; source content unchanged, signed pathway type/date locked |
| `POST /patients/{patient_id}/documents` | Existing upload contract plus optional `visit_id`; validates same-patient visit, otherwise binds active visit |
| `GET /previous-patients?q=&on=YYYY-MM-DD` | Assigned doctor; no filters returns an empty list; returns patients, visits and own appointments |
| `GET /patients/{patient_id}/historical-workspace?visit_id=` | Assigned doctor; `{patient, visit, visits, brief, snapshot_available, documents}` |

Previous patients starts with a search form and no automatic selection. Opening a result displays Patients in historical mode: source evidence and chat remain, while care editing, finding decisions and visit/analyze/upload controls are hidden. A signed visit uses its saved patient/brief and document membership when captured. Without a snapshot, the latest brief is labeled as current reference; no earlier brief is invented. Chat remains patient-wide and is explicitly labeled, rather than claiming a historical time boundary. Records retains dated visit detail and the full searchable source workspace.

The first care draft uses patient-specific agent suggestions, excluding known generic preparation templates; verified findings may provide explicit review prompts if suggestions are absent. After an earlier signed plan, the next draft starts empty and preserves the prior plan/reports separately. Reanalysis never overwrites clinician-edited drafts or re-adds signed instructions. Patients' preview card polls the shared bundle rather than independently rendering stale `caregiver_prep.checklist` data. Language translation/revision behavior remains as described above.

Repair regressions live in `tests/test_admin_repairs.py`; the browser fixture checks admin account/roster/history/directory interactions and doctor historical navigation alongside existing chart/citation and caregiver sign-off/reporting flows. It uses synthetic data and no live patient database.
