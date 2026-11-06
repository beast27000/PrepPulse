# Backend guide

## Service stack

The deployed backend uses Python 3.11, FastAPI, Pydantic contracts, MongoDB 8 and Docker Compose. Caddy is the public HTTPS entry point. MongoDB, the API and workers communicate over a private network. Persistent files and model cache are mounted from the Azure data disk.

## API responsibilities

FastAPI provides authentication and protected sessions, role-aware page data, patient assignment checks, appointment and account administration, document upload and preview, analysis and care job status, chat, chart artifacts, pathway editing/sign-off, caregiver completion reports, FHIR access, translation and dictation. Provider secrets and filesystem paths stay server-side.

The API validates incoming structured data and authorizes the patient scope before querying records or evidence. Browser responses use patient-scoped document identifiers rather than filesystem paths. Clinical decisions and source-linked output are stored separately from the original documents.

## Durable work

Long OCR, clinical analysis and translation work is not held open inside an ordinary page request. The API creates durable Mongo work items. A clinical worker handles document processing, extraction, FHIR, retrieval and the review graph. A separate care worker handles translation and care-plan tasks. Leases and heartbeats identify abandoned work; retries and terminal failures are visible to the application. Analysis checkpoints reduce repeated work after interruption.

If a language model places a combined blood-pressure and pulse reading into a numeric lab field, the grounding pass retains it as a source-linked review item and processes the remaining valid facts and documents. It does not coerce the composite text into a clinical number.

Remote provider calls may be repeated after a worker crash between provider response and persisted completion. Thus remote calls are at-least-once and retries can consume additional provider credits. Application reservations and provider dashboards should both be monitored.

## Mongo data and FHIR

Mongo collections persist patient and account identities, external aliases, assignments, documents, appointments, visits, observations, source provenance, FHIR resource versions, job state, conversations, chart data, clinician review state, pathways, caregiver reports and audit events. Unique identity constraints protect permanent identifiers. FHIR resources are validated before being stored as versioned patient-linked data.

## Private files and backups

Source files and derived previews reside on the private persistent data disk. Authenticated routes render document pages and enforce patient ownership. Encrypted backups include Mongo data and private source/derived files; model caches are reproducible. The backup archive is copied to private Azure Blob storage and checksum-verified. Restore verification runs against a separate database name, leaving live data untouched. Follow the [Azure runbook](../../deployment/README.md#backups-and-recovery) for actual commands and key handling.

## Security boundaries

The deployed service uses password hashes, secure session cookies, CSRF protection, origin checks, failed-login controls, access auditing and server-enforced roles. Doctors are limited to assigned patients. Caregivers are limited to their assignment. Secrets are stored in Key Vault and a root-only server environment file; the virtual machine managed identity is used for backup access. These controls do not replace a complete privacy, penetration or regulatory review.
