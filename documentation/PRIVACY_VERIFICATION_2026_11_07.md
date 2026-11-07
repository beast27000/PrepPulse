# Privacy verification, 7 November 2026

The local UI branch passed 57 regression tests with 5 skips. Four skipped checks require the deployment only cloud adapters; the remaining skip is the durable worker check, which does not apply to this branch's thread pool. The React production build passed.

The local factory now uses the privacy adapter for its external Sarvam / OpenAI compatible requests. Private LAN and loopback LM Studio requests retain their existing local behavior. Unit tests inspect external request content, JSON restoration and clinical value preservation. The existing patient, appointment, caregiver, language, source and API regression tests remain passing. No fresh local model inference is claimed when a running local model was not available for this release.

The separate deployed release was also exercised against actual providers: 15 original documents went through OCR and completed FHIR outputs, all eight clinical workflow stages ran, eight findings and five checklist suggestions were produced, cited chat and a three year chart passed, and Tamil and Hindi translation preserved a clinical value while restoring the patient's name internally. All 28 inspected outgoing text requests omitted the registered identifiers checked by the harness. This rehearsal used a temporary database and did not change the live patient records.

The live Azure disks reported encryption at rest. A fresh encrypted backup was uploaded, downloaded with matching checksum, and restored separately: 35 collection counts and 68 content addressed source hashes passed. Both temporary verification databases were removed. These Azure storage checks do not establish that a local Windows disk is encrypted.

The live browser check passed doctor/admin navigation, chart links, OCR source highlights and the caregiver portal. Doctor/admin credentials were used normally. The old caregiver fixture password was stale, so the operator used a five minute session for an existing caregiver rather than changing its password. That test does not reverify caregiver password login.

The privacy filter reduces disclosure of direct identifiers; it is pseudonymization, not full anonymity. Cloud dictation remains an audio processing exception. See [Patient privacy](PATIENT_PRIVACY.md) for the boundaries and recovery notes.
