# Privacy release verification, 7 November 2026

## Deployment storage and recovery

Azure reported `EncryptionAtRestWithPlatformKey` for both the deployed OS disk and the patient data disk. `/data/mongo` is mounted on the data disk. The daily backup timer was active.

A fresh backup, `preppulse-20261107T083214Z.tar.gz.enc`, was encrypted before uploading to the private Azure backup container. The upload was downloaded and its SHA 256 checksum matched. Decryption and Mongo restore into a separate verification database passed: 35 collection counts matched, 29 patients and 8 existing users were present, and 68 content addressed source files passed their hash checks. The verification database was removed afterwards. The encrypted backup remains available with its key stored separately.

## Real provider rehearsal

A separate temporary database copied an existing patient's profile and 15 original source document references. No new account was created. The source files were read from existing private storage. OCR and structured extraction were rerun from the originals in the temporary database.

| Check | Result |
| --- | --- |
| OCR and structured processing | 15 records, 15 completed FHIR outputs |
| Clinical workflow | All eight graph stages plus longitudinal history synthesis |
| Consultation result | 8 priority findings |
| Cited conversational answer | 69 available source citations |
| Three year HbA1c and fasting glucose chart | 1 artifact with recorded series |
| Care suggestions | 5 checklist items |
| Translation with a deliberately included patient name and HbA1c value | Tamil and Hindi complete; identity restored internally and 8.3% preserved |
| Outgoing request inspection | 26 chat requests and 2 translation requests; no registered identifier checked by the harness appeared in their text payloads |
| Runtime | Analysis 88.87 seconds; complete rehearsal 98.94 seconds |
| Production patient, user and source document counts | Unchanged by the isolated rehearsal |

The temporary patient workflow database was removed even on failure. All requests used the actual configured Sarvam and Azure Translator services. No prompt or identity mapping was written into the public test report.

## Hosted release and browser

The API and both workers were restarted with the reviewed privacy adapters. A real Sarvam inference from the running API passed a direct inspection of its outgoing payload and returned response metadata `privacy=pseudonymized`. The requested clinical value was preserved.

The live browser test passed doctor and admin navigation, saved chart generation, clickable citations and OCR highlights, and the existing caregiver portal. Existing doctor/admin credentials were used normally. The old stored caregiver test password no longer authenticated; the operator supplied a five minute signed test session for an existing active caregiver, without creating an account or resetting a password. Caregiver password login itself is not claimed as reverified by that test. API authorization continues checking the current account and assignments.

The React production build passed. The deployment regression suite passed 114 tests. The UI branch regression suite passed 57 tests with 5 skips: four deployment only provider tests and the existing durable queue test, which do not apply to the local thread pool implementation.

## Boundaries

This is pseudonymization of supported outgoing text requests, not complete anonymization. Clinical histories retain dates and other clinically useful facts. Pattern matching can miss an unregistered or unusual identifier in free text. Cloud speech transcription still receives microphone audio. Windows local storage encryption is machine specific and was not enabled or claimed by this release. See [Patient privacy](PATIENT_PRIVACY.md).

No database field encryption or schema migration was introduced. The main branch was not changed. UI and deployment receive separate commits so their local and cloud runtime differences remain intact. A private code rollback archive and the independently encrypted data backup were retained.
