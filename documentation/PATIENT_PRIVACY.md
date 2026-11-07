# Patient privacy

PrepPulse protects stored data separately from the content sent to external AI services. These controls do not make the application an anonymous dataset or establish healthcare regulatory certification.

## Stored records and browser access

The deployed Azure OS and data disks use platform managed encryption at rest. MongoDB and private patient files reside on the data disk. The backup job encrypts its archive with AES 256 CBC and PBKDF2 before uploading it to private Blob storage. The encryption key is stored separately from the archive. Backups include confidential records and need the same access restrictions as the live data. The existing CBC archive format is not an authenticated encryption format; upload/download SHA 256 verification checks transfer integrity, not malicious authenticity.

On 7 November 2026 both disk encryption settings were verified through Azure. A fresh encrypted backup was uploaded, downloaded with checksum verification, decrypted, and restored into the separate `preppulse_restore_verification` database. All 35 collection counts matched the snapshot; 68 content addressed source file hashes passed. The encrypted archive was `preppulse-20261107T083214Z.tar.gz.enc`. Production data was not replaced.

HTTPS protects transport to the website. Existing server authorization determines which patients each doctor or caregiver may access. Authorized staff continue to see original names and source files. Disk encryption does not prevent a database administrator or a compromised running application from reading mounted data.

The local UI installation uses the same request privacy filter for supported external clients. Azure disk encryption does not apply to a Windows PC: local disk encryption and local backup configuration depend on that machine. No local database field migration or operating system encryption changes are performed by this release.

## External text requests

Before a supported external model request, `preppulse_rag.privacy.PrivacyFilter` reads a restricted projection of registered patient names, DOBs, permanent IDs, aliases, and contact fields. It replaces matching identifiers with fresh opaque tokens. It also detects common labelled identifiers and email/phone/ID patterns inside narrative text. Structured identity keys are protected without changing the surrounding JSON protocol. Names embedded in filenames are covered by the registered identity matches.

This applies to the deployed Sarvam, Azure and optional Gemini chat routes, including extraction, agent prompts, synthesis, chat history and chat questions. Azure and Sarvam translation protect the same identifiers and restore them internally after response validation. External OpenAI compatible chat and embedding adapters also apply the filter. Private LAN and loopback model endpoints continue using local content. Deployments currently compute OCR and E5 embeddings locally, so original PDFs and OCR images do not go to a cloud OCR or embedding API.

The temporary token mapping exists only inside the request process. No mapping or original prompt is added to the usage ledger. The model's returned tokens are restored inside the backend so source anchors, filenames, identity fields and citations remain compatible with existing validators and UI. If the registry cannot be read, the supported external text request fails before sending content. This is enabled by the adapters themselves and requires no browser toggle.

## Preserved clinical content

Clinical measurements, medication names and doses, age, sex, report dates, diagnoses, evidence numbers, page numbers and OCR coordinates remain available. This preserves clinical review and chart generation. Exact DOB and patient identifiers are not needed by the external model; the original registry demographics still populate the internal FHIR output and browser profile.

Pseudonymization reduces disclosure of direct identifiers. It cannot guarantee detection of every arbitrary name, handwritten identifier, unusual address or misspelling in free text. Clinical dates, ages and rare histories can remain indirectly identifying. No claim of complete anonymization is made. Information is still sent to the configured external provider, subject to its processing terms.

## Dictation and other boundaries

Cloud dictation sends audio to Azure Speech or its configured Sarvam fallback. A text filter cannot remove spoken names before a transcription service hears the audio. Dictation filenames remain generic and the application does not retain microphone recordings. The resulting transcript is filtered before any subsequent external text LLM request. Local speech transcription remains an option in the local installation. Browser Read aloud controls remain removed; backend cloud speech synthesis adapters also filter text if invoked.

The filter is not a general network firewall, a malware boundary, or a replacement for server permissions. It does not change originals, database identity fields, clinical record ownership, patient search, appointment assignment, or caregiver permissions. Provider error reporting and usage ledgers continue to omit prompt bodies and credentials. Existing traces, exports, manually added integrations and future model adapters must be reviewed separately before claiming they are covered.

## Verification and rollback

Automated tests inspect outgoing HTTP payloads for identifier removal, preserve clinical evidence and JSON escaping, verify token restoration, cover Azure and Sarvam translation, and ensure registry failures send no request. Existing API, FHIR, caregiver, appointment, citation and chat tests are run alongside them. Real provider and isolated patient workflow results are recorded in the release verification document.

The privacy release is applied to `UI` and `deployment`; `main` is not changed by this release. The hosted release keeps a code rollback copy and a separately encrypted data backup. Restoring old code would remove the new request privacy protection, so use rollback only as a deliberate operational recovery action.
