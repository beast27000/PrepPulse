# Azure pilot verification — 5 November 2026

This report describes checks actually performed on the `deployment` release. The website is https://preppulse-pilot-b8bc.centralindia.cloudapp.azure.com/. Tests used imported synthetic patients and a separately labelled synthetic verification patient. Credentials, patient text, provider keys, screenshots with patient details and raw responses remain outside Git in ignored private staging.

## Provider result

| Capability | Result | Evidence / limit |
| --- | --- | --- |
| Sarvam LLM, new hackathon key | Passed | Main account connectivity plus complete 15-document extraction/FHIR/agent workflow and real cited chat |
| Azure OpenAI LLM | Blocked | Azure rejected model deployment with 715-123420 unusual-activity restriction; account exists but deployment does not. Forced inference returns 404. Owner contacting support |
| Automatic fallback adapter | Unit-tested | Azure/Sarvam fallback, disabled state, cap rejection, service-specific cooldown and provider egress restrictions tested; a successful live Azure fallback is not claimed |
| Azure Translator | Passed | Hindi, Tamil, Bengali, Odia and Telugu; protected numbers/units, complete snapshots, translated notes/checklists/dosage and downloadable PDFs |
| Azure Speech | Passed | Synthetic TTS→STT, plus actual public authenticated voice endpoints with default-language auto-detection |
| Python embeddings | Passed | Server-side CPU E5 and patient-scoped retrieval |

The new key is selected via `Main_Sarvam_AI_Credits`. While configured, old Sarvam test-account keys are not selected. The admin routing preference was switched to Sarvam-only and back to automatic through the actual HTTPS API, then read back. Automatic remains the deployed setting.

## Full clinical run

The actual cloud analysis job `JOB-2F06B4E47BE248F9` completed in **125.22 seconds**:

- 15 original patient records ready; no failed records.
- 15 validated FHIR bundles.
- 422 evidence chunks.
- Eight workflow nodes completed, with their visible process stages.
- Eight verified priority findings and nine supported numeric metric series.
- Original-page PNG endpoints and source-box interactions remained functional.

This run reused the imported OCR for the existing source records. A **separate genuinely rasterized PDF upload** tested the cloud Tesseract path: successful upload, background processing, fasting glucose 130 mg/dL in FHIR, searchable OCR box and authenticated original-page PNG. Tesseract misread the synthetic scan's `HbA1c` label as `HbAic`; that measurement was not emitted as a FHIR observation. This is a remaining recognition limitation, not a passing HbA1c extraction claim. Original dated HbA1c values from the imported patient did populate verified trends and charts.

## Chat, charts and source proof

Five real conversation cases passed: cited diabetes journey; other conditions/earlier admissions; three-year supported chart request; ten-year supported chart request; unsupported heart-chart request. Supported chart requests saved session artifacts and linked them to the conversation. The unsupported request did not create an unsupported chart. The source buttons opened original-page evidence with the highlight overlay in the live browser.

The existing supported nine numeric series and diabetes-chart scope were preserved. Neither missing years nor arbitrary heart-disease values were synthesized into charts.

## Roles, pages and caregiver lifecycle

Live Playwright navigated doctor Today, Patients, Records, Care pathways and Settings; admin intake, appointments, patient directory, caregivers, Accounts and Settings; and the caregiver portal. The test checked the chat workspace, saved chart UI and citation/source preview, with no observed JavaScript exceptions or API 5xx responses in the verified journey.

Live HTTP checks included anonymous denial, caregiver denial of clinical briefs, administrator denial of clinical briefs, doctor denial of account administration, secure session cookies, CSRF rejection and unexpected-origin rejection. These are targeted boundary checks, not a complete penetration test.

A new labelled synthetic patient was used for a complete workflow:

1. Admin assignment, current appointment and family-caregiver assignment.
2. Doctor visit/draft with clinician-added checklist entries, note and an explicitly synthetic three-day schedule.
3. Explicit review/sign-off and visit ending.
4. English signed archive present in patient records.
5. Hindi, Tamil, Bengali, Odia and Telugu translations and PDFs all completed. Observed translation times were approximately 1.28–2.41 seconds for this small plan; exported PDFs ranged from about 139 KB to 277 KB.
6. Caregiver tick and note persisted; doctor saw the same completion and note, including daily schedule tasks.

Automatic script/number checks and successful PDFs do **not** establish fluent clinical translation accuracy. Human review remains necessary.

## Data, restart, load and recovery

All original six patients and associated collection records were copied into the separate cloud database. The migration hash manifest verified **68 distinct private files**. The seventh patient is explicitly a deployment verification fixture; it is not imported as a real patient.

Application containers were recreated and restarted while Mongo, files and model caches stayed on the persistent disk. The subsequent live tests could still read all seven patients and the signed care data. The migration source remained unchanged.

**100 live login → assigned-patient list → logout flows passed at 10 active flows**, taking **13.72 seconds total**, with **2.02-second p95 flow time**. These reused a demonstration doctor account in independent sessions. This verifies a bounded auth/read workload, not 100 distinct real accounts, 100 simultaneous analyses, a production capacity guarantee or a completed five-day soak.

An encrypted snapshot was uploaded using VM managed identity. Downloaded Blob content matched the upload SHA-256. The archive was decrypted and restored into **`preppulse_restore_verification`**, leaving the live database intact:

- 32 restored collections.
- Seven patients and six accounts.
- Stable source/restored collection counts matched; transient audit/login/session counts were excluded from the comparison.
- 68 archived private-file hashes matched their content-addressed filenames.
- Plaintext verification archives were removed after verification.

The backup timer is installed for 22:30 UTC daily. The operator also retains a separate encrypted copy and encryption key outside the Azure resource group. Future scheduled runs still need monitoring; the timer has not completed a five-day soak.

The owner subsequently clarified that hosting should remain available during the Azure trial rather than stop after five days. No application expiry or five-day shutdown was installed. Azure's resource lookup returned no VM auto-shutdown schedules in the deployment group. The initial five-day wording describes the test window only; trial expiry and available credit remain external service limits.

## Automated regression selection

**116 selected Python tests passed**, including new Azure/provider-budget, hackathon-account priority, cooldown isolation, durable lease recovery and shared routing-preference checks. Command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests --ignore=tests/test_end_to_end_pipeline.py -k "not test_langgraph_clinical_review_workflow" src/preppulse_preprocessing/tests --junitxml=.tmp/azure_pilot/regression.xml -q
```

The three end-to-end tests requiring absent `PP001_Arvind_Narayanan` fixture data and the previously documented clinical foot-exam expectation were excluded. They are not reported as passing. FastAPI emits existing lifespan-event deprecation warnings.

`npm run build` passed. The opt-in live Playwright test passed using private credentials:

```powershell
$env:PREPPULSE_DEPLOYMENT_E2E = "1"
$env:PREPPULSE_E2E_URL = "https://preppulse-pilot-b8bc.centralindia.cloudapp.azure.com"
cd web
npx playwright test e2e/deployment.spec.ts
```

Targeted Ruff and Git whitespace checks passed. Bicep compilation, ARM validation, ARM what-if and actual VM deployment succeeded. Some newly versioned Azure resource APIs lacked type definitions in the installed Bicep tooling; actual ARM validation/deployment established their accepted properties.

## Issues found during verification

- Azure subscription model-deployment restriction: unresolved, correctly reported; Sarvam remains usable.
- Concurrent first-use SQLite journal initialization could intermittently return `database is locked`: initialization now serializes threads and retries bounded cross-process locks. Atomic-budget regression passed afterward.
- Private backup directory initially prevented the non-root uploader from traversing it: directory group permissions were corrected while archive files remain private. Actual encrypted upload/download and restore then passed.
- The host's Ubuntu Python is 3.10 whereas the application image is 3.11: the restore helper now hashes streams without a Python-3.11-only API.
- Exhausted final worker leases could otherwise remain running: they now become failed/retryable after the third interruption, verified with a targeted test.
- Sparse synthetic scan label recognition remains limited as described above; no unsupported numeric observation was invented.

## Usage and remaining limits

At the recorded server-ledger checkpoint, the cloud had **38 Sarvam chat calls**, 40,648 input tokens and 12,687 output tokens, estimated at **INR 2.49**, and **20 Azure translation + one STT + one TTS call**, estimated around **USD 0.033**. Separate small operator-side connectivity checks are not included in that server-only ledger. These are application estimates, not invoices or live wallet balances. No successful test reported exhausting the new main account; remaining credits cannot be independently confirmed by the application.

Remaining work: Azure support approval and a live Azure LLM rerun; real five-day monitoring; fluent translation/clinical review; broader security/privacy review before real patient use; and capacity changes if concurrent clinical demand exceeds one worker. No high-availability or uninterrupted-credit guarantee is made.
