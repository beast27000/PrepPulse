# Local API deployment rehearsal

Date: 4 November 2026. Branch: `ui_testing`, based on `UI` commit `9fd08a6`.

This is the engineering rehearsal before a separately approved deployment. It does not publish a website, migrate the original workspace, validate autonomous clinical use, or change the `UI`/`main` branches. The existing doctor/admin/caregiver interfaces remain intact. The [README](README.md) starts with this branch's stack and setup; the full inherited product guide follows it.

## Result and provider decision

Keep **Sarvam as the primary provider** for this rehearsal. Gemini is an explicitly enabled synthetic-data comparison/fallback, followed by the existing reachable LM Studio service. Forced-provider tests never use the other provider to conceal a failure.

Both providers completed the same 15-source synthetic patient's OCR, grounded extraction, FHIR rendering, eight-node clinical workflow and two conversational history questions. Both generated cited history answers; deterministic chart requests produced real saved chart artifacts without extra generation calls. An unsupported cardiac-chart request returned a scope explanation and source occurrence table rather than an unrelated glucose plot.

The supplied Google project rejected actual Gemini 2.5 Flash generation with HTTP 404 despite model-list visibility. A Gemini 3.8 probe returned 503. The working comparison uses **`gemini-3.5-flash-lite`**. A low-reasoning setting required by that model was tested directly. Do not assume a model name, million-token context window or advertised daily allowance guarantees this project's actual access or quota.

Google's adapter requires `PREPPULSE_SYNTHETIC_ONLY=1`. This is an operator declaration, not automatic de-identification. The [Gemini API terms](https://ai.google.dev/gemini-api/terms) restrict sensitive information on unpaid services and prohibit clinical-practice use. Successful synthetic tests do not authorise real-patient clinical deployment on that service.

## Defects exposed and corrected

| Area | Finding and change |
| --- | --- |
| Agent contract | The prompt loader omitted declared output schemas. Models could return inconsistent classification labels, leaving a misleading prediabetes default. Schemas now reach the model; supported aliases normalize, missing/invalid categories fail explicitly in strict mode. Both final runs return the documented Type 2 diabetes classification. |
| Provider output | Sarvam hidden reasoning could consume a small token allowance without visible content. The adapter disables it and rejects empty/truncated replies; extraction has a larger bounded response budget. |
| FHIR integration | Browser analysis did not run a reliable Stage 2/3 path. It now performs document-scoped grounded extraction, validation, version storage and assigned-doctor export. |
| Grounding | A numeric value elsewhere on the page could support an incorrect row. Numeric lab and medication-dose checks now use the matched source anchor. Unverified vitals are quarantined. An absent route is not invented as oral. |
| Measurement omissions | Both generative extractors omitted some otherwise verified chart measurements. A deterministic, document-owned OCR-catalog reconciliation preserves those supported values, dates, units, boxes and qualifiers in FHIR. It does not invent facts or claim complete extraction of every condition/medication. |
| FHIR structure | Stable resource IDs, valid transaction requests, patient-reference resolution and standard extension containers replace invalid provenance fields. Reported medications are distinguished from newly authorised active prescriptions. |
| Interrupted work | Completed document results and compatible failed-node checkpoints are resumable. Source/provider/model/prompt/code changes prevent inappropriate checkpoint reuse. Re-rendering cached facts after a renderer or demographic change needs no model call. |
| Chat context | Ranked excerpts alone sometimes hid older supported measurements. All verified metric points now accompany the retrieved evidence. Grouped citations become individually clickable references; invalid citation indexes are unavailable rather than guessed. Known record dates are labelled to avoid presenting them as definite admission dates. |
| Embeddings | Pinned multilingual E5-small runs on Python CPU, independently of LM Studio. Passage/query prefixes, bounded token windows and model/content-scoped persistent caching are included. |
| Translation | The service can lose opaque markers or transliterate units. Numeric protected markers, complete-segment validation and one source-only translation repair precede optional local IndicTrans2 fallback. Incomplete snapshots remain unpublished. |
| Speech | Sarvam's synchronous transcription has a per-request audio duration limit. In-memory decoding and 25-second chunks support longer dictation; transcripts remain reviewable. |
| Database connections | Per-request Mongo clients created unnecessary monitoring sockets. Request handlers now share a thread-safe client/pool and close it on shutdown. |

## Reproducible verification

| Check | Outcome |
| --- | --- |
| Selected Python regression | **107 passed**, zero failures/errors; command below explicitly excludes known legacy cases. |
| Existing Edge browser workflows | **3 passed**: doctor/caregiver checklist, records and charts; admin accounts/assignments/appointments/directory; dictation listening/transcription/review. These use synthetic in-memory fixture data. |
| Frontend | Production TypeScript/Vite build passed. No React UI rewrite was required. |
| Python packaging | Wheel built successfully; the official FHIR schema is included in the wheel. |
| Lint | All changed/new Python files passed targeted Ruff checks. |
| Sarvam live workflow | 15 processed records; all eight nodes completed; saved brief and cited history answers available in the isolated database. |
| Gemini live workflow | Same 15 original source hashes and same pinned embeddings; all eight nodes completed; saved brief and cited history answers available separately. |
| Protected FHIR endpoint | Anonymous request 401; administrator clinical access 403; assigned doctor 200 with `application/fhir+json`. |
| Source preservation | For each provider, all **65/65** copied workspace files restored with matching SHA-256; no missing files. |
| OCR preservation | Each provider's **15/15** regenerated OCR records matched original text/tokens/tables/geometry, excluding run timestamps. |
| FHIR conformance | **15/15 bundles per provider** passed the official R4 4.0.1 base JSON schema, reference and provenance-bound checks. |
| Chart behavior | New saved artifact for a supported 3-year HbA1c/fasting-glucose request; cardiac-chart scope warning/table and no unrelated artifact. Existing tests cover year windows 1-10 and follow-up wording. |
| Multilingual API-only test | Hindi, Tamil, Bengali, Odia and Telugu: complete text, protected numeric/unit values and rendered PDFs passed, with local fallback disabled. Tamil-to-English reverse translation also passed. |
| Voice | Synthetic English synthesis/transcription round trip passed; a **35.33-second** live sample transcribed across multiple requests. A unit test verifies 61 seconds splits into 25/25/11-second chunks. |
| Fallback/budget tests | Insufficient-credit rotation, no Sarvam key rotation on rate limits, durable atomic reservations, estimated 10-credit guard, synthetic guard and Sarvam-to-Gemini/local ordering passed using simulated responses. |

### Supported OCR measurement preservation

These are counts in the selected 15-source synthetic chart, not assumed patient values. Both providers preserve every listed verified point in their structured export:

| Measurement | Verified points | Preserved per provider |
| --- | ---: | ---: |
| HbA1c | 6 | 6 |
| Fasting glucose | 6 | 6 |
| Post-meal glucose | 2 | 2 |
| Creatinine | 5 | 5 |
| eGFR | 2 | 2 |
| Urine ACR | 3 | 3 |
| LDL cholesterol | 3 | 3 |
| Systolic blood pressure | 4 | 4 |
| Diastolic blood pressure | 4 | 4 |

The supported measurement list includes metabolic, renal and vascular context; these are not nine independent diagnostic criteria for diabetes. Classification remains assistive and depends on documented history and reviewed evidence. Other conditions can be summarized from records, but arbitrary cardiac measurements are not silently converted into supported chart series.

Sarvam's final exports contain 61 Observations, 24 Conditions and 21 reported MedicationRequests; Gemini's contain 46, 25 and 14 respectively. Both include a Patient resource in each document bundle. The different counts show that base-schema validity does **not** mean identical or exhaustive clinical extraction. There are 31 quarantined items in the Sarvam copy and 17 in the Gemini copy. They remain for review; no completeness or clinical-accuracy certification is claimed.

The caregiver agent produced five checklist suggestions in each final run. This imported patient's existing signed pathway/completion history is intentionally preserved; a later draft may contain zero newly seeded items rather than overwriting an earlier signed checklist. That state is different from an agent failing to generate suggestions.

## Latency, usage and credit reporting

The final cached-structured-document analysis took 399.92 seconds on Sarvam and 201.55 seconds on Gemini. Earlier runs and cold extraction differed substantially; a full initial Google structured run took roughly eleven minutes. These are observed end-to-end runs, **not** controlled throughput benchmarks. Remote hangs/retries, cold extraction and CPU model startup affect latency.

The last two conversational questions took 20.75/7.03 seconds for Sarvam and 41.80/28.47 seconds for Gemini. Supported/unsupported chart tools completed in approximately 0.03-0.05 seconds using already processed records. Translation of five sample segments per language took approximately 5-8 seconds in the final run; an earlier Bengali repair encountered a timeout and took 96 seconds. Fast atomic UI publication cannot remove upstream translation latency.

Final durable-ledger snapshot after testing:

| Provider | Recorded attempts | Successful responses | Token totals returned by service | Cost accounting |
| --- | ---: | ---: | --- | --- |
| Sarvam | 218 | 212 | 75,477 input / 23,563 output for chat responses | **INR 36.73 conservative estimate/reservations**, including translation and speech; not an invoice or live wallet balance. |
| Gemini | 59 | 55 | 58,396 input / 15,390 output | Request/token accounting only; ledger zero is not proof of free billing. Check the Google dashboard. |

Sarvam attempts include 139 translations, 67 successful chat responses, three incomplete chat responses, three transport failures, two synthesis requests and four transcription requests. Gemini includes one each of HTTP 400, 404, 503 and a transport failure. Initial connectivity probes preceded the ledger: four small Sarvam generation/authentication probes, two failed native Gemini generation probes and one Google model-list GET. Their actual charges are not inferred from the ledger.

No live response indicated exhausted provider credits or rate quota. Earlier Google **local test counters** were reached and extended with the owner's approval. The Sarvam INR 50 test guard was not reached. Rate-limit/exhaustion behavior was tested with simulated responses rather than intentionally spending down a wallet.

Sarvam credits are organisation-scoped. Multiple keys may share one wallet; configure `SARVAM_ACC_n_POOL` accordingly. No official live-balance endpoint was confirmed. The requested switch below ten credits therefore uses optional manually supplied starting balances minus conservative local reservations. Unspecified balances stay unknown. External spending can invalidate an estimate; provider insufficient-credit responses still rotate eligible accounts. This is an outstanding operational limitation, not a live credit-monitoring claim.

## Capacity and persistence rehearsal

The load database contains **100 synthetic patients, 100 distinct doctor accounts and 1,500 replicated processed documents**. A real local HTTP server served ten active flows until all 100 users had logged in, fetched assigned patients and received a denial for another patient's brief. Final result: **100/100 passed**, 8.59 seconds total, flow p50 0.844 seconds, p95 0.906 seconds. Data size was 56.70 MiB plus 0.64 MiB of indexes. A separate restored database matched BSON content hashes.

The existing ten synthetic dataset folders total about 2.75 MiB, averaging 0.27 MiB; another 100 equally small folders would add about 27.5 MiB of originals. Scanned PDFs, immutable FHIR versions, translation segments, chat histories, audit logs and chart artifacts can grow considerably. Files are private on disk, not embedded in the public frontend. The source-file restore test and BSON database restore test cover different parts of recovery.

This evidence supports a small **local demo**. It does not establish 100 simultaneous AI generations, five-day uptime, cloud network latency, an available Oracle free VM, a free-service SLA or generalisation to 100 distinct clinically reviewed histories. There has been no five-day soak. Provider token budgets and worker concurrency need measured admission control before real multi-user deployment.

## Manual demonstration

1. Start MongoDB. Follow the README's dependency/embedding setup. Preparation is once-only and refuses to replace an existing test database.
2. Run `.\scripts\run_ui_testing.ps1 -Provider sarvam`. Start Vite against port 8001 and open **http://127.0.0.1:5174**. Original ports 8000/5173 are separate.
3. Sign in with the copied existing doctor credentials. Select the assigned synthetic `PP001` patient from Today or search. Repeated rehearsal visits are retained as test history; they are not new real-patient registrations.
4. Review the completed brief, dated diabetes measurements, earlier conditions/admissions and caregiver suggestions. Select a citation to inspect the original page and exact source box. Existing signed caregiver ticks must remain intact.
5. Ask: **Summarize this patient's documented diabetes journey and changes in HbA1c, with source citations.** Check the six dated HbA1c values and follow references.
6. Ask: **What admissions and other conditions are explicitly documented? Cite the records and do not invent dates.** Distinguish a document date from an asserted admission date.
7. Ask: **Plot HbA1c and fasting glucose over the past 3 years.** Open the saved chart, inspect dates, click source-linked points and collapse panels as usual. Then ask for a heart-disease chart and check the scope explanation/table.
8. Change checklist language, wait for complete publication, then download. Confirm the selected-language PDF and unchanged English signed archive. Edit only through the existing pathway flow; an edit invalidates translations for changed text, not checklist identity/completion history.
9. Test dictation, review/correct its transcript and submit deliberately. Read-aloud remains opt-in. Live audio tests used synthetic WAVs; a real microphone/device/language still needs manual verification.
10. Stop the test API and start `.\scripts\run_ui_testing.ps1 -Provider gemini -Database preppulse_ui_testing_gemini` to compare the separately processed records. The URL/credentials are the same, but patient/job/chat history comes from the Google copy.
11. To enable the approved fallback order, use `.\scripts\run_ui_testing.ps1 -Provider auto -EnableGemini` with synthetic data. Live fallback was not triggered by deliberately exhausting credits; deterministic tests verify failure transitions.

The existing local model/IndicTrans2 setup remains optional fallback; it cannot be reached by a future cloud server unless deliberately hosted and secured. No secret needs to be placed in a frontend variable.

### Repeat engineering checks

```powershell
.\.venv\Scripts\python.exe -m pytest tests --ignore=tests/test_end_to_end_pipeline.py -k "not test_langgraph_clinical_review_workflow" src/preppulse_preprocessing/tests --junitxml=.tmp/ui_testing/results/regression.xml -q
.\.venv\Scripts\python.exe scripts/verify_ui_testing.py
.\.venv\Scripts\python.exe scripts/benchmark_ui_testing.py --refresh-template
.\.venv\Scripts\python.exe -m pip wheel --no-deps . --wheel-dir .tmp/ui_testing/wheels
cd web
npm run build
```

Live provider commands and the isolated frontend launch are in the README. Paid live checks require configured keys and sufficient ceilings. Private test responses, PDFs, database/profile secrets, voice samples and ledgers stay under ignored `.tmp/ui_testing`; model weights remain ignored too.

## Remaining work before deployment

- The full unfiltered legacy test suite is **not green**: its existing live care-gap foot-exam expectation and three cases dependent on absent `PP001_Arvind_Narayanan` fixture data remain excluded from the selected regression command. The original foot-exam failure was reproduced on an unchanged earlier commit. These are recorded limitations, not silently passing tests.
- Clinical/fluent review is required for extraction, classifications and all translated instructions. Numeral/script checks cannot verify negation, meaning or appropriate treatment. Base FHIR schema validation is not terminology-service validation, implementation-guide certification or EHR interoperability testing.
- Replace local private-file assumptions with authenticated durable storage, configure TLS/secure cookies, deployment origins, backups/restore, secret management, account recovery, monitoring and abuse controls. The current local-only cookie configuration is not a public-site configuration.
- A durable worker queue, bounded concurrent AI work, idempotent scheduling, shared budget/cache coordination and retry/backpressure policies are needed for multiple hosts. Local checkpoints do not provide a distributed queue; SQLite reservations coordinate only processes sharing that file.
- Verify provider commercial/data terms, actual Google model eligibility/quotas, Sarvam wallet organisations, and billed usage in dashboards. Do not treat finite credits as permanently free inference.
- Select an available host/database/object-store combination and test its actual RAM, CPU embedding latency, file persistence, quotas, egress and five-day workload. Small local storage measurements alone cannot guarantee a free cloud tier will run the complete stack.
- No website deployment or merge into `UI`/`main` is part of this delivery. A later deployment plan and approval remain required.
