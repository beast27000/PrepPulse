# Processing and maintenance release verification

## Deployed workflow

The verification used the supplied PP006 folder and existing administrator and doctor accounts. No accounts were created. The original test patient was removed after exercising individual record deletion, then the same folder was freshly imported with date of birth 1967 March 12. All 14 files were saved and all 12 clinical documents entered processing. The previous test identity and the newly imported test identity were both removed from the active workspace by the end of verification.

The complete new clinical analysis took approximately 85.27 seconds after upload. All 12 documents finished OCR, all 12 FHIR bundles were accessible and valid, 139 evidence chunks were used and four priority findings were produced. Saved stage history includes all eight workflow nodes and the additional history synthesis stage. An identical folder upload returned zero new files with the existing completed analysis, rather than an empty progress result.

Two subsequent chat questions exercised a cited history summary and a three year HbA1c/glucose chart request. Both replies were saved with citations, with 76 linked excerpts across the replies and one saved chart artifact. The live browser rendered the actual chart and opened a citation with its OCR highlight. This verifies functional retrieval, rendering and source navigation; it is not an independent clinical accuracy study.

A future appointment was created for the test patient. The API rejected starting the visit before its date. The browser Upcoming appointments date filter opened that patient in preview mode, and Start visit produced the date message. After the appointment was moved to the current day, an existing doctor could start the visit, obtain five checklist items and complete all five Tamil translation segments. The appointment was subsequently restored to a future date for the browser preview check, then removed with the test patient.

## Provider observations

The live Settings inference probe reported Sarvam healthy in 0.25 seconds and Azure unavailable with HTTP 404. The Azure model deployment restriction remains unresolved. Translation worked through its separately configured service. This release cannot guarantee provider uptime or supply a functioning Azure chat deployment where the subscription does not have one.

The application usage ledger during the verification window recorded 25 Sarvam requests and seven Azure service requests, with conservative recorded estimates of INR 1.69014 and USD 0.11226 respectively. These are application estimates, include reservations for some failed calls and may include concurrent activity. They are not a provider invoice or remaining wallet balance.

## Cleanup and regression checks

The individual source delete removed the imported file and extracted data and invalidated mutable generated outputs. Full deletion removed the test patient's documents, FHIR versions, brief, appointment, visit, conversation, chart, care draft, translations and associated queue tasks. Direct server checks found zero remaining patient rows in the mapped clinical collections for both PP006 test identities and no corresponding private directories. PP006's alias was free for reimport. Thirty two other patients and all seven existing accounts were present afterwards. The original local dataset files were retained. Historical encrypted backups remain governed by their existing retention schedule.

Regression coverage includes role and CSRF restrictions, typed confirmation, worker fencing, retry after storage cleanup failure, signed pathway protection, source removal invalidation, future appointment date enforcement, provider probes, bounded transient retries, stale worker recovery, existing caregiver workflows and composite lab grounding. Browser checks covered selection by keyboard, autocomplete synchronization, confirmation cancellation, provider Settings, chart and source rendering, and phone portrait Upcoming appointments. Both branch frontend builds passed. The UI branch retained its local model and thread pool configuration; deployment retained its cloud adapters and durable queue.

## Release and rollback

The deployment regression set passed 107 tests. Local browser checks used the isolated fixture rather than creating accounts in the active database. The configured LM Studio endpoint was unreachable from the operator PC at verification time, so no fresh local inference success is claimed. The local code, existing caregiver/API regressions, browser interactions and production build were verified separately from the live cloud inference run.

The hosted application code and static build were published using the existing VM release procedure. The previous source and static build were saved privately as `/home/preppulse/rollback-operations-20261106.tar.gz`. That archive is a code rollback, not a restore of deleted patient data. Restoring old code does not reverse a patient deletion; data recovery requires an appropriate protected backup. Main is outside this release.
