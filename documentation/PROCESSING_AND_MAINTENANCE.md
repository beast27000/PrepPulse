# Processing, provider checks and patient maintenance

## Understanding processing status

An upload saves private files before clinical processing begins. Waiting for processing means the background clinical worker is busy with earlier work. The displayed queue position is an observation, not a promised completion time. OCR, structured extraction, FHIR validation and each clinical agent report their actual stage. The interface shows OCR completion counts, current file, elapsed time and the last progress timestamp. Pulsing dots indicate a queued or running operation; they do not imply that inference is producing tokens continuously.

Uploading identical files again does not duplicate them. The result says No new files and shows the existing job. Administrators can retry failed processing from intake or patient details without uploading again. Completed extraction and analysis checkpoints are reused when their input fingerprints still match. A transient transport, decoding or HTTP 408/500/502/503/504 error receives up to two retries with bounded backoff. Authorization, missing deployment and rate limit failures do not receive immediate transient retries. Existing budget and cooldown controls still apply. Remote retries may incur additional provider usage.

Malformed composite lab values are retained in a source linked review queue instead of being forced into invented numbers. One such value no longer fails the entire document schema. Blood pressure and pulse remain separate vital measurements.

## Provider checks

Doctor and administrator Settings include Test providers. The deployed product checks Sarvam and Azure chat inference separately with a minimal nonclinical prompt. The browser receives status, timing and sanitized errors, never provider credentials. A check may consume a small amount of provider credit. A successful check establishes availability at that moment, not guaranteed uptime or clinical answer quality. Translation and dictation use separate services and are not covered by this chat inference probe.

Administrators manage the shared route: automatic Sarvam then Azure, Sarvam only, Azure only or pause. Doctors can inspect and test the current route. A local installation tests its local model endpoint. Azure chat requires an actual deployed model; the pilot currently has a blocked model deployment and its chat fallback therefore remains unavailable. Azure Translator and Speech are independent of that restriction.

## Upcoming appointments

The doctor's Upcoming appointments page initially selects today and accepts a future date. Cards open the patient workspace for evidence review, records, analysis and conversational charts. When a patient has a future scheduled appointment and no appointment today, the API prevents starting or changing a clinical visit before that date. Existing unscheduled intake remains available for patients without a future booking. Admission, checklist draft changes and sign off use the same visit authorization. Server dates use the configured clinic day, currently Asia/Kolkata.

## Deleting a patient

Only administrators can delete patients or original source records. The patient details action area contains Edit patient details and Delete patient with spacing below the summary. The confirmation presents document, uploaded file, visit, appointment and signed pathway counts and requires the permanent PrepPulse ID.

Deletion fences new work and cancels queued work. If a worker is still processing, the action returns a clear stopping message; retry after the current step exits. The locked patient stays unavailable until cleanup is resumed and finished. A stored cleanup manifest allows another attempt after a partial failure. The operation removes aliases, assignments, appointments, visits, private imported copies, OCR, extracted data, FHIR versions, evidence chunks, briefs, conversations, charts and caregiver history. A minimal receipt retains the administrator identity, time and deletion counts without clinical content. Staff login accounts remain intact.

Deletion targets only the patient directory under configured private storage. The original dataset supplied by the operator is not deleted. Encrypted historical backups remain subject to their retention schedule; deleting from the active application does not rewrite those backups.

## Deleting one source record

Open Edit record in the directory and choose Delete record. Its confirmation identifies the file, type and date. The private source, file registry entry, OCR, structured output and FHIR versions are removed. Mutable AI briefs, analysis checkpoints, conversations, chart artifacts and active care drafts are invalidated because they may quote that source. Analyze records again to rebuild those outputs. Previously signed plans remain historical signed content and are protected from individual record deletion. Full patient deletion includes those signed plans.

## Capacity and recovery

The deployed pilot already runs asynchronous durable clinical and care workers. The clinical queue is sequential; translations use a separate worker. Adding workers requires measured CPU, memory and provider capacity. This change improves visibility and recovery without promising simultaneous full analyses on a small VM. The local installation uses its existing thread pool. Worker status and business operation failures are aligned so a failed analysis is not reported as a successful queue operation.
