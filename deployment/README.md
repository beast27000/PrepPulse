# PrepPulse Azure deployment

## Deployed technology stack

| Layer | Implementation on `deployment` |
| --- | --- |
| Public browser workspace | React, TypeScript and Vite production build; Caddy serves static files and `/api` under one HTTPS origin |
| Compute | Ubuntu 22.04 x64, Azure `Standard_D2s_v5`, 2 vCPU / 8 GB RAM, Central India |
| Runtime | Docker Compose: web, FastAPI API, clinical worker, care/translation worker, MongoDB |
| Clinical LLM | Sarvam `sarvam-105b`, using `Main_Sarvam_AI_Credits` as the first and only selected Sarvam account when supplied |
| LLM fallback | Azure OpenAI adapter; actual Azure model deployment currently blocked by subscription review |
| Translation | Azure AI Translator; complete versioned multilingual snapshots; Sarvam service fallback |
| Dictation | Azure AI Speech; Sarvam fallback; browser Read aloud controls removed |
| Retrieval | Patient-scoped hybrid retrieval and CPU multilingual E5-small Python embeddings, pinned model revision |
| OCR / evidence | Existing PyMuPDF/Tesseract pipeline, provenance chunking, original-page rendering and normalized source boxes |
| Clinical orchestration | Existing eight-node LangGraph workflow and validated application contracts |
| Structured records | Existing FHIR R4 validation, immutable versions, patient/document identities and source provenance |
| Database | MongoDB 8 on a private Docker network and persistent Azure managed data disk; Atlas is not used by this pilot |
| File and cache storage | Private persistent 64 GB data disk mounted at `/data`; authenticated document routes |
| Recovery | Leased Mongo work queues, encrypted private Azure Blob backups, separate restore verification |
| Secrets | Azure Key Vault plus root-only server environment file; managed identity for backups |

The deployed product provides patient, doctor, administrator and caregiver workflows through the hosted website. It is a controlled synthetic-data demonstration, with clinician review required for generated output.

## Current endpoint and operating status

**Website:** https://preppulse-pilot-b8bc.centralindia.cloudapp.azure.com/

**Provisioned 5 November 2026.** Resource group: `rg-preppulse-pilot-b8bc`. VM: `vm-preppulse-pilot-b8bc`. Storage: `stpreppulsepilotb8bc`. Key Vault: `kv-preppulse-pilot-b8bc`. Translator: `tr-preppulse-pilot-b8bc`. Speech: `speech-preppulse-pilot-b8bc`. **No five-day shutdown, application expiry or automatic resource deletion is configured.** Five days was the initial demonstration/test window; hosting can continue for the subscription's remaining trial period while credit is available.

The site, Sarvam LLM pipeline, Azure translation and Azure voice were exercised against the live HTTPS endpoint. Azure created the OpenAI account `ai-preppulse-pilot-b8bc`, but rejected its `preppulse-chat` model deployment with **715-123420, unusual activity**. The owner is contacting Azure support. An Azure key and account alone do not mean a model is running: forced Azure inference currently returns 404. Sarvam is the working primary; there is no working second LLM until Azure allows deployment. Translation and voice have separate working Azure resources and are unaffected by this chat restriction.

Credentials are private, outside Git, in the operator's protected credential store and the `pilot-access` Key Vault secret. Demonstration credentials include an administrator, assigned doctor and assigned family caregiver. The administrator password was rotated. Do not publish the credential file or share administrator credentials with participants.

## How inference is routed

1. `PREPPULSE_AI_PROVIDER=auto` and `PREPPULSE_AI_PROVIDER_ORDER=sarvam,azure` select Sarvam first.
2. `Main_Sarvam_AI_Credits` takes precedence over the earlier test accounts. Those old accounts are not silently consumed while the main key is configured.
3. A provider request failure, rate limit or budget failure can advance automatic routing to Azure. Structured output still must pass the clinical pipeline's existing parsing, schema and provenance checks. Invalid clinical output is not accepted merely because a request returned HTTP 200.
4. Admin **Settings → Cloud LLM routing** can choose automatic, Sarvam only, Azure only, or AI disabled. The preference is stored on the private disk and shared by the API/workers. Azure-only currently fails visibly until support resolves the model block.
5. Translation and voice continue to prefer Azure regardless of the LLM choice. AI-disabled blocks these outbound services too. Azure-service failures may use Sarvam when `PREPPULSE_AZURE_FALLBACK=sarvam`.
6. Provider calls are made by the deployed services using server-side configuration. Browser requests never contain provider keys.

An unavailable Azure chat deployment enters a chat-specific cooldown, not a global Azure cooldown. Thus an OpenAI 404 cannot disable working Translator or Speech calls. Existing answered conversations, saved charts, records, signed plans and completed reports remain stored when inference is unavailable; new processing reports an error rather than producing fabricated substitutes.

## Patient data and page behavior

The migration copied the source workspace into the deployed database. It preserved the six original patients, aliases, permanent PrepPulse IDs, assignments, documents, visits, appointments, chat sessions/messages, charts, source provenance, FHIR versions, decisions, signed pathways and caregiver reports. All **68 distinct private files** in the migration manifest were copied and SHA-256 checked. The source database was read only. A clearly labelled seventh patient, **Deployment verification (synthetic)**, holds the end-to-end upload and caregiver tests.

- **Patients:** consultation cards, source-linked findings, collapsible chat/source/checklist panels, Analyze records, record upload, visit lifecycle and review actions. Source boxes remain linked to authenticated original-page previews.
- **Today:** assigned doctor's current appointments and links to the patient workspace.
- **Records:** prior visits, FHIR exports, earlier signed caregiver plans, original documents and the full evidence browser. Saved chat sessions and chart artifacts remain patient-scoped.
- **Care pathways:** editable clinician checklist, notes and prescribed schedules; explicit review/sign-off; selected-language downloads. English archive copies remain in patient records.
- **Admin intake/directory:** repeat-patient uploads, demographic editing, folder aliases, assigned doctors and patient record management.
- **Admin appointments:** Today / Upcoming appointments tabs, future-date filtering and previous appointments with name/ID/date filters.
- **Accounts/caregivers:** administrator-created identities, family/professional caregiver types, patient assignments and type-scoped access. Caregivers see assigned signed instructions, daily tasks and notes rather than clinical briefs or unrestricted records.
- **Settings:** existing preferences plus deployed cloud LLM routing for administrators.
- **Global navigation:** doctor/admin menus place **Logout** directly below Settings; caregiver menus place it below My care plans. Desktop keeps the bottom sign-out control too. On phone portrait, the top navigation is horizontally scrollable, so swipe the menu to reach Logout after the other entries.

No guidance-library or separate previous-patients page has been reintroduced. The existing responsive chat, chart links, source proof and OCR geometry have not been redesigned for deployment.

### What the clinical system measures

The supported chart measurements are **HbA1c, fasting glucose, post-meal glucose, eGFR, urine ACR, creatinine, LDL cholesterol, systolic blood pressure and diastolic blood pressure**. This is nine plotted numeric series, with the two blood-pressure series belonging to one clinical measure. Available time windows depend on the patient's actual dated records. Missing years or measurements are not filled with guessed values. Other conditions can be retrieved and summarized in evidence-linked text/tables; unsupported condition charts receive an explicit scope explanation.

HbA1c and documented glucose findings contribute to the assistive diabetes review. Renal measurements, LDL, blood pressure, medicines, diagnoses and consultation history provide risk/context; they do not independently establish diabetes. A chart trend or generated classification is not an autonomous diagnosis. See the inherited root documentation for the detailed agent contracts and clinical limits.

## Background processing and persistence

The API schedules a durable Mongo task instead of keeping a long clinical job inside the web process. A clinical worker processes OCR/extraction/agents/chat sequentially. A separate care worker handles translation so language switching need not wait behind a full analysis. Leases last three minutes and heartbeat every twenty seconds. Expired leases can resume; after three interrupted attempts the task becomes visibly retryable. A completed business operation is not repeated solely because the worker lost its queue acknowledgement.

Remote calls are **at least once**: if a worker dies after a provider accepts a request but before completion is saved, recovery may repeat that request and incur another charge. Existing analysis checkpoints reduce unnecessary repeated nodes. This pilot has one clinical worker, not capacity for 100 simultaneous analyses.

`/data/mongo` stores MongoDB. `/data/private` stores original/derived documents, translation snapshots, provider preference and usage reservations. `/data/models` stores downloadable embedding weights/cache. `/data/caddy` stores TLS state. These paths are mounted outside container lifetimes. Recreating the API/worker containers does not reset records or keys.

## Translation, speech and multilingual downloads

English, Hindi, Tamil, Bengali, Odia and Telugu use the existing synchronized language selection and complete-snapshot UI. The adapter protects numbers, units and selected abbreviations; every requested segment must pass the existing validation before that translated revision is published. A partial translation remains a visible loading/error state instead of silently mixing unchecked content.

Doctor checklist edits, clinician notes and dosage descriptions are translated as derived display text. Signed source content, item identities, source citations, completion history and caregiver notes remain attached to the original patient/pathway. Selected-language PDF downloads render using installed Noto fonts and page breaks. The permanent archived pathway record remains English.

Browser Read aloud controls have been removed. Browser microphone audio is uploaded to authenticated dictation, decoded in memory and sent to Speech; the transcript is returned for correction before chat submission. The application does not retain microphone recordings. Language auto-detection and the public TTS→STT round trip were verified in the earlier release; the backend speech adapter remains available. Provider-side data processing is distinct from application retention and must be reviewed before processing real patient information.

## Verification performed against this release

Full results: [VERIFICATION.md](VERIFICATION.md). Key live checks:

- Original patient: 15 documents, validated FHIR bundles for all 15, 422 evidence chunks, all eight workflow nodes, 8 verified findings and 9 metric series; full cloud analysis completed in 125.22 seconds using the new Sarvam account.
- Chat: cited diabetes history, other admissions/conditions, three-year and ten-year chart requests, persistent sessions/artifacts and unsupported heart-chart scope. Source preview and chart interactions were checked in the live browser.
- All doctor/admin/caregiver page navigation, authenticated role boundaries, CSRF and origin checks, and original source PNG routes.
- New synthetic scanned upload: Tesseract, numeric extraction/FHIR, search box and rendered page. One scan label was misread: `HbA1c` → `HbAic`; that unrecognized measurement was omitted. The recognized fasting glucose value was correctly stored. OCR remains fallible and requires source review.
- Synthetic appointment → doctor draft → signed pathway → English archive → all five translated PDFs → caregiver tick/note → doctor-visible follow-up.
- 100 successful login/list/logout flows, 10 active flows, 13.72 seconds total and 2.02-second p95 on this VM. This is an authentication/read workload, not 100 simultaneous AI users or a five-day soak.
- Encrypted backup upload/download checksum plus restore into a separate database: all 32 collections recovered, stable collection counts matched, 68 private-file hashes verified.
- Selected Python regressions and a production frontend build; known legacy exclusions are listed in the verification report.

## Cost, credits and pilot limits

The Azure subscription was confirmed **Free Trial, spending limit On**. No Pay-As-You-Go upgrade was performed. This deployment consumes trial credit; it is **not an indefinitely free hosting offer**. The selected VM's queried Linux rate was approximately **USD 0.101/hour**, or USD 12.12 for 120 hours and **USD 72.72 for 30 days of continuous VM compute**, before disks, IP/storage and AI usage. The original short pilot used an infrastructure planning reserve of USD 25 for five days. For the owner's requested longer trial window, a rough USD 90 infrastructure planning allowance plus the USD 50 application Azure-AI allowance would fit within a fresh USD 200 credit **if actual usage and other subscription spending stay within those estimates**. These are estimates, not an Azure billing guarantee or a global subscription budget.

Application reservations cap Sarvam at **INR 500** and Azure AI at **USD 50** using configured conservative estimates. The Sarvam model's reported tokens adjust successful LLM estimates. Provider invoices and shared-account spending can differ. The application does not have a verified live Sarvam wallet-balance API; it cannot claim to know the remaining 1000+ credits. `scripts/report_pilot_usage.py` reports content-free application estimates only. Credit exhaustion and Azure restrictions can make new AI actions unavailable while previously saved data remains readable.

Monitor Azure Cost Management and the Sarvam dashboard throughout the trial. **There is no five-day service cutoff.** Use the actual trial-expiry date and remaining credit displayed in the Azure portal; credit exhaustion or subscription expiry can stop resources before any desired 30-day period ends. The 2-core single-VM design, one clinical worker, provider rate limits and upload/CPU load remain the principal capacity limits. The measured login workload is not a guarantee for concurrent clinical analyses.

## Reproduce the deployed runtime

### Prerequisites

An Azure subscription with allowed VM quota, Azure CLI login, SSH/SCP, Docker-compatible Linux x64, Python 3.11 and Node/npm for the web build. Translator and Speech must be provisioned and funded. Sarvam must have a valid funded key. Azure OpenAI additionally requires an **approved model deployment**, not merely an account key. No model support restriction is bypassed by this repository.

Clone and build on the operator machine:

```powershell
git clone --branch deployment https://github.com/beast27000/PrepPulse.git
cd PrepPulse
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[deployment-test]"
cd web
npm ci
npm run build
cd ..
az login
```

`infra/main.bicep` provisions the VM/network/disk, private backup Storage, Key Vault and managed-identity roles in an existing resource group. The checked-in parameter file records this pilot's names/region and must be changed for another deployment. Supply your SSH public key, source `/32` address and deployer object ID through a **private** parameters file. Validate and preview before creating resources:

```powershell
az deployment group validate -g YOUR_RESOURCE_GROUP -f infra/main.bicep -p '@YOUR_PRIVATE_PARAMETERS.json'
az deployment group what-if -g YOUR_RESOURCE_GROUP -f infra/main.bicep -p '@YOUR_PRIVATE_PARAMETERS.json'
az deployment group create -g YOUR_RESOURCE_GROUP -n preppulse-pilot -f infra/main.bicep -p '@YOUR_PRIVATE_PARAMETERS.json'
```

Azure AI accounts are provisioned separately from this Bicep. The pilot used Cognitive Services kinds `TextTranslation` S1 and `SpeechServices` S0 in Central India, plus an OpenAI S0 account in East US. The attempted model was `gpt-4.1-mini`, version `2025-04-14`, deployment `preppulse-chat`; its subscription block remains unresolved. Configure the endpoint/deployment that your own approved account actually exposes.

Upload this source, its `web/dist`, and the deployment scripts to `/opt/preppulse` on the VM. Run `deployment/setup_vm.sh` there. It initializes **only the dedicated Azure data disk at LUN 0**, never an OS disk or existing filesystem. Confirm your disk mapping before using it elsewhere.

Copy [server.env.example](server.env.example) to `/etc/preppulse/server.env`, replace all private credentials/placeholders and use a random session secret. Restrict `/etc/preppulse` to root (700) and its files to root (600). Use `scripts/seed_azure_secrets.py` only with the intended subscription/resource names and the private staging files: it stores runtime secrets in Key Vault without printing them. Runtime containers receive their environment from the root-owned file; backups use the VM's managed identity rather than Storage account keys.

Build/start from `/opt/preppulse`:

```bash
sudo docker compose -f deployment/compose.yaml build api
sudo docker compose -f deployment/compose.yaml up -d
sudo docker compose -f deployment/compose.yaml ps
curl -fsS https://YOUR_HOSTNAME/api/health
```

DNS must point to the VM before Caddy can obtain its HTTPS certificate. Expose 80/443 publicly; restrict SSH to the operator's address. Never publish Mongo port 27017 or API port 8000. This Compose setup intentionally runs Mongo only on an internal Docker network. Accounts are created through the existing administrator/bootstrap workflow, never through a public registration endpoint.

### Migration and repeat deployment

`prepare_azure_pilot.py` reads the designated source database and prepares a private snapshot and copied, hash-checked files. **It is configured for this operator's pilot**, including resource names; review and adjust it before reuse. `import_azure_snapshot.py` refuses a nonempty destination database. Do not rerun an initial import over an active deployed workspace. Use a fresh target and compare source/destination counts and file hashes. Never run the repository's destructive audit/reset script against the live database.

After code changes, rebuild `web/dist` in the release environment, package the allowlisted release, and copy it to the VM. For this existing pilot, the operator's private SSH key is stored in protected staging:

```powershell
.\.venv\Scripts\python.exe scripts/package_azure_release.py
scp -i .tmp/azure_pilot/id_ed25519 .tmp/azure_pilot/application.tar.gz preppulse@20.219.32.118:/home/preppulse/application.tar.gz
ssh -i .tmp/azure_pilot/id_ed25519 preppulse@20.219.32.118 "sudo tar -xzf /home/preppulse/application.tar.gz -C /opt/preppulse"
```

Then recreate the application services on the VM. If dependencies or the Dockerfile changed, rebuild the image too:

```bash
cd /opt/preppulse
sudo docker compose -f deployment/compose.yaml build api
sudo docker compose -f deployment/compose.yaml up -d --force-recreate api worker care-worker web
```

The bind mounts make source updates explicit. They do not update dependencies in an old image. Keep `/data` and `/etc/preppulse` independent of source releases. Keep the same session secret unless intentionally invalidating existing sessions. Re-run public health/login, evidence, voice and a bounded synthetic workflow check after releases.

## Backups and recovery

`deployment/backup.sh` briefly stops API/clinical/care writers, dumps MongoDB and snapshots `/data/private`, restarts the application, encrypts the archive using a separate random key and uploads it to the private `backups` Blob container. The uploaded file is downloaded again to verify its SHA-256. Raw patient files and generated PDFs are included; reproducible model caches are excluded.

The `preppulse-backup.timer` runs daily at **22:30 UTC / 04:00 IST**, with up to a minute's jitter. Install/enable the checked-in service and timer on the VM. A missed timer is persistent and runs when the VM next starts. Verify results; a configured timer alone does not establish that a backup succeeded.

```bash
sudo systemctl status preppulse-backup.timer
sudo systemctl start preppulse-backup.service
sudo journalctl -u preppulse-backup.service --no-pager -n 25
sudo python3 /opt/preppulse/scripts/verify_pilot_restore.py
```

The restore verifier uses **`preppulse_restore_verification`**, never the live database. Its `--drop` applies only to that explicitly mapped verification namespace. It decrypts to a private temporary directory, validates archived source hashes and compares stable collection counts; plaintext verification files are deleted on success. Actual disaster recovery must restore both Mongo and files/SQLite/preferences from the same snapshot, with correct ownership and runtime secrets restored separately.

Encrypted copies live on the VM and in Blob storage. The encryption key is `/etc/preppulse/backup.key`, with a separate protected copy outside Azure and a Key Vault secret. **Export a copy outside the resource group before deleting the group**: deleting the group also deletes its VM, disk, storage and Key Vault. A backup inside a deleted resource group is not independent disaster recovery.

## Security and next steps

TLS, secure HttpOnly strict-session cookies, CSRF tokens, origin checks, patient/role authorization, password hashing, bounded concurrent password verification, failed-login throttling, authenticated source routes and access auditing are enabled. Files/keys are not shipped to the browser or Git. Browser sources are served only through application authorization.

This is one region and one VM: no automatic failover, no five-day soak completed, no real-patient clinical/privacy certification. Before a shared clinical deployment, review processing agreements, restore drills, account lifecycle, firewall/OS maintenance, monitoring, rates/concurrency and resource-level cost alerts. Azure OpenAI support approval is the outstanding LLM redundancy dependency. Operator follow-ups include the `azure-compliance` audit skill and `azure-resource-visualizer` architecture skill, if installed.

After exporting and validating an independent backup, the operator can remove **only this pilot** with:

```powershell
az group delete --name rg-preppulse-pilot-b8bc --yes --no-wait
```

Do not run cleanup while the demonstration is still needed. No branch merge into `main` or `UI` is part of this deployment.
