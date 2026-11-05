# Setup and operations

Local prerequisites, database configuration, model providers, translation, startup, checks and troubleshooting.

## 15. Reproduce PrepPulse on another system

The steps below target Windows PowerShell, matching the current local workflow. Use isolated or synthetic patient data for initial setup.

### 15.1 Prerequisites

Install or provide:

1. Git.
2. Python 3.11 or newer, with a working virtual environment.
3. Node.js 20.19+ with a compatible npm installation.
4. A local MongoDB service.
5. Tesseract OCR for scanned PDFs/images, available on `PATH`.
6. For chat/agent synthesis, either LM Studio with a compatible local chat model or a Sarvam API key. Embeddings are configured separately and currently use a compatible local embedding server when semantic retrieval is enabled.
7. Microsoft Edge for the repository's default browser test configuration, if running E2E checks.

The synthetic dataset, private uploads, model weights, and existing account database are not included in a clone. A new machine starts with its own data and accounts.

### 15.2 Clone the current application

```powershell
git clone --branch UI https://github.com/beast27000/PrepPulse.git
cd PrepPulse
git status
```

Use `UI` for the active review build or `main` for the stable copy of the same application release. Select the branch deliberately when reproducing a specific revision.

### 15.3 Create the Python environment

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

The development extra supplies test/lint helpers, including the in-memory browser fixture dependency. Explicit virtual-environment executable paths avoid accidentally using another Python from Conda or a global installation.

Check your tools:

```powershell
.\.venv\Scripts\python.exe --version
node --version
npm --version
tesseract --version
```

A native-PDF example may work without Tesseract, but scanned pages still need the OCR executable. Installing `pytesseract` alone does not install Tesseract.

### 15.4 Install the frontend

```powershell
cd web
npm ci
cd ..
```

The lockfile is committed. If Node/npm resolve to different installations, fix that environment before diagnosing frontend source code.

### 15.5 Start and configure MongoDB

Start your MongoDB service using your installation's service manager or configured `mongod` process.

The API defaults are:

```powershell
$env:PREPPULSE_MONGO_URI = "mongodb://127.0.0.1:27017"
$env:PREPPULSE_MONGO_DB = "preppulse"
```

Set these variables in the terminals that start the API or bootstrap accounts if using different values. The standalone preprocessing package also has its own `MONGO_URI` / `MONGO_DB` settings; do not assume every subsystem reads the same variable name.

The local setup does not automatically configure MongoDB authentication or encryption. Keep it restricted to the intended local environment.

### 15.6 Choose a chat and agent model provider

The review agents use one configured chat provider. Choose **one** of these modes:

1. **Local LM Studio (private/local inference):** set `LLM_PROVIDER=local` and configure `LOCAL_LLM_BASE_URL` plus `LOCAL_CHAT_MODEL` as below.
1. **Sarvam API (hosted inference):** set `LLM_PROVIDER=sarvam`, provide `SARVAM_AI_CREDITS` or `SARVAM_API_KEY`, and optionally set `SARVAM_MODEL` and `SARVAM_BASE_URL`. Patient-context prompts are sent to that external API, so use only an account and data handling arrangement approved for the data being processed.

The provider factory also checks a reachable local LM Studio server when `LLM_PROVIDER` is unset; configure the provider explicitly for repeatable runs. If the selected provider cannot initialize, some paths can fall back to a mock model. A mock response is for development only and must not be treated as live agent analysis. Check startup/runtime logs and the UI job state to confirm which provider actually answered.

This branch does **not** implement Gemini or Azure model routing or automatic provider failover. It does not rotate multiple Sarvam keys based on remaining credits. To switch providers, stop and restart the API after changing its environment variables.

For Sarvam, set the key only in the API process environment (or a private ignored `.env` file loaded by your launcher). In PowerShell:

```powershell
$env:LLM_PROVIDER = "sarvam"
$env:SARVAM_AI_CREDITS = "<your-sarvam-api-key>"
# Optional; defaults to sarvam-2b and https://api.sarvam.ai/v1
$env:SARVAM_MODEL = "sarvam-2b"
```

Restart the API after setting these values. Never place a real key in source control, screenshots, or a browser-side variable. Sarvam receives the prompts and retrieved excerpts used for the request.

#### Local LM Studio configuration

Download and load a chat model and an embedding model appropriate for your machine. Start the local server and copy the exact API identifiers from its model list.

The current tested local configuration uses:

```powershell
$env:LLM_PROVIDER = "local"
$env:LOCAL_LLM_BASE_URL = "http://127.0.0.1:1234/v1"
$env:LOCAL_CHAT_MODEL = "qwen/qwen3-4b-2507"
$env:LOCAL_EMBED_MODEL = "text-embedding-qwen3-embedding-0.6b"
$env:LOCAL_LLM_TIMEOUT = "45"
```

Check the server:

```powershell
Invoke-RestMethod http://127.0.0.1:1234/v1/models
```

A different model identifier or port is acceptable when explicitly configured. If LM Studio runs on another machine, use its reachable private-network address and understand that record text is sent to that service.

The chat and embedding models serve different purposes. **Current limitation:** the browser app uses the same `LLM_PROVIDER` setting when it selects embeddings. The `local` choice creates LM Studio embeddings; `ollama` creates Ollama embeddings; `sarvam` currently resolves to deterministic mock embeddings because this branch has no Sarvam embedding adapter. Therefore Sarvam chat currently runs with lexical retrieval plus mock dense vectors, not real semantic embeddings. Do not describe that configuration as full semantic hybrid retrieval. If real embeddings are needed with Sarvam chat, use the local provider configuration explicitly in code or add a separately configurable embedding provider in a reviewed code change. The optional standalone preprocessing provider reads `LLM_BASE_URL` and its own settings; it is separate from the browser application's `LLM_PROVIDER` factory.

### 15.6a Install the local IndicTrans2 translator

Chat and embeddings continue to run in LM Studio. The official IndicTrans2 checkpoints use a PyTorch encoder/decoder model with IndicTransToolkit; this integration runs them in a separate local WSL2 worker. It does not attempt to import these weights into LM Studio. [IndicTransToolkit](https://github.com/VarunGumma/IndicTransToolkit) documents Linux/macOS support and does not claim Windows support, so its dependencies are isolated from PrepPulse's Windows `.venv`.

One-time requirements:

1. Install Ubuntu WSL2 if needed: `wsl --install -d Ubuntu`, then complete Ubuntu's first-run account setup. Check `wsl --status`.
2. In Ubuntu, install the environment prerequisites: `sudo apt-get update` followed by `sudo apt-get install -y python3-venv build-essential`.
3. Sign into Hugging Face and accept the model access conditions for both [English→Indic 1B](https://huggingface.co/ai4bharat/indictrans2-en-indic-1B) and [Indic→English 1B](https://huggingface.co/ai4bharat/indictrans2-indic-en-1B).
4. Authenticate the Windows download utility once if necessary: `.\.venv\Scripts\hf.exe auth login`. Do not commit a token or paste one into application source.
5. Run the setup from the PrepPulse repository root:

```powershell
.\scripts\setup_translation.ps1
```

This downloads approximately 8.6 GB of official model weights into ignored `.local_models/indictrans2/`, verifies each weight file against its published SHA-256 digest, installs the isolated environment under the Ubuntu user's `~/.local/share/preppulse/translation/venv`, and writes ignored `private_data/translation.json`. Interrupted large downloads can resume from their `.part` files. The model revisions are pinned in `scripts/download_translation_models.py`; changing model revisions also requires updating `MODEL_VERSION` in `src/preppulse_api/local_translation.py` so old derived text is not reused.

The default PyTorch installation uses the CPU and avoids taking GPU memory from LM Studio. To opt into a CUDA runtime on a machine with sufficient free GPU memory:

```powershell
.\scripts\setup_translation.ps1 -WithCuda -Device auto -SkipDownload
```

`auto` selects CUDA only when at least 3.5 GB of GPU memory is free at model-load time; otherwise it uses the CPU. `-Device cpu` forces CPU use, and `-Device cuda` requires a functioning CUDA runtime and adequate memory. Only one model direction is held by the translation worker at a time. CPU translation is slower; cached language switches avoid new inference, while the first uncached translation shows progress. This is asynchronous processing, not a promise of instantaneous translation.

For a different installed WSL distribution, use `-Distro <name>`. If the weights are already downloaded, `-SkipDownload` only configures/updates the environment. To download weights separately:

```powershell
.\.venv\Scripts\python.exe scripts/download_translation_models.py
```

Restart the PrepPulse API after setup. There is no translation service to start manually: the API launches the worker on the first language request. Inference loads only local files with Hugging Face offline mode enabled. Download authentication is not an inference API key. The optional `PREPPULSE_TRANSLATION_CONFIG` selects a different private configuration file, and `PREPPULSE_TRANSLATION_TIMEOUT` controls the worker response timeout in seconds (default 600).

To run an opt-in live check without opening MongoDB or using patient records:

```powershell
.\.venv\Scripts\python.exe scripts/check_local_translation.py --reverse
```

This translates synthetic checklists, multiline notes and dose text in all five Indic languages, checks preserved values/units, renders PDFs, and tests Tamil→English. Review artifacts under ignored `.tmp/translation-smoke/`. The local implementation was checked with 76 focused automated tests, three Edge browser flows and this live model check. The pre-existing foot-exam assertion in `tests/test_clinical_agents.py` remains a documented failure and also fails on the prior committed baseline.

Select a care language in Patients, Care pathways, or My care plans. Verify that checklist instructions, doctor notes and dose text finish translating, then download a signed plan in that language. Review the wording before relying on it; the original signed text is preserved. If the translation fails, retry from the pathway page after checking setup. Keep `.local_models/`, the WSL environment and `private_data/translation.json` on your machine; only code and documentation belong in Git.

### 15.7 Create the first administrator

Choose a unique password of at least 12 characters. The following avoids putting a literal password into a copied command:

```powershell
$env:PREPPULSE_ADMIN_USER = "admin"
$env:PREPPULSE_ADMIN_NAME = "PrepPulse Admin"
$initialPassword = Read-Host "Initial admin password (12+ characters)" -AsSecureString
$env:PREPPULSE_ADMIN_PASSWORD = [System.Net.NetworkCredential]::new("", $initialPassword).Password
.\.venv\Scripts\python.exe scripts/bootstrap_ui_admin.py
Remove-Item Env:\PREPPULSE_ADMIN_PASSWORD
```

The script creates indexes and the initial account. It refuses to overwrite an existing username. The login username is the value of `PREPPULSE_ADMIN_USER`; the display name is not the login identifier.

For an already configured machine, do not bootstrap another account merely because the API needs restarting. Existing accounts are stored in MongoDB.

### 15.8 Start the API

In a PowerShell terminal at the repository root, set the MongoDB/model variables required by your setup and run:

```powershell
.\scripts\start_ui_api.ps1
```

The launcher uses the repository virtual environment, binds to `127.0.0.1:8000`, and enables source reload by default. If `PREPPULSE_SESSION_SECRET` is unset, it generates or reuses `private_data/.session-secret`, which is ignored by Git. Protect this file.

If a recognized older PrepPulse API occupies the port, the launcher checks active jobs before replacing it. It refuses to stop an unrelated service.

After another backend update:

```powershell
# Let active analysis/chat work finish first.
.\scripts\start_ui_api.ps1 -Restart
```

`-Restart` explicitly permits interrupting active work. `-NoReload` disables development reload. To use another port, pass `-Port` and point the frontend proxy to the same API target.

A manually launched uvicorn process must have `PREPPULSE_SESSION_SECRET` configured. Changing the secret invalidates existing sessions and requires another sign-in.

### 15.9 Start the browser frontend

Use another terminal:

```powershell
cd PrepPulse\web
npm run dev
```

If already at the repository root, use `cd web` instead. Open the loopback URL Vite prints, normally `http://127.0.0.1:5173`.

The default proxy targets `http://127.0.0.1:8000`. To use a different API:

```powershell
$env:PREPPULSE_API_TARGET = "http://127.0.0.1:8000"
npm run dev
```

Do not mix `localhost` and `127.0.0.1` inconsistently when debugging browser sessions. Refresh and sign in after changing service/session configuration.

### 15.10 Prepare the first patient workflow

1. Sign in as the administrator.
2. Create a doctor account in Accounts.
3. Register a patient in New patient intake, including demographics and doctor assignment.
4. Upload a supported file or one `ID_Patient_Name` folder.
5. Inspect upload/processing progress and any errors.
6. Schedule an appointment if desired.
7. Sign in as the assigned doctor and select the patient.
8. Use Analyze records and review source-linked outputs.
9. Request a supported chart and click a point/citation to inspect the source.
10. Start the visit, edit the pathway, review translations, and sign off only after checking the instructions.
11. Create a caregiver account in Accounts, assign it through Caregivers, and review the signed-plan portal.
12. Return to Records for saved visits, sources, pathways, and caregiver follow-up.

### 15.11 Dictation and retained audio adapter

Dictation uses the local faster whisper service. The default model setting is PREPPULSE_STT_MODEL=small.

Allow microphone access in the browser. Stop recording to transcribe, review and correct the text, then submit it. The transcript is not sent automatically.

The browser Read aloud controls have been removed. The API retains an optional audio adapter for a compatible private WAV service, but configuring that adapter does not restore a Read aloud control in the current UI. The Qwen3 TTS GGUF is not directly executed by the API, and a model listed by a text inference server is not evidence that it provides audio output.

### 15.12 Configuration reference

| Variable | Meaning / default |
| --- | --- |
| `PREPPULSE_MONGO_URI` | API MongoDB URI; `mongodb://127.0.0.1:27017`. |
| `PREPPULSE_MONGO_DB` | API database; `preppulse`. |
| `PREPPULSE_PRIVATE_ROOT` | Private original/derived storage; repository `private_data`. |
| `PREPPULSE_DATASET_ROOT` | Authorized local dataset root; not an automatic bulk import. |
| `PREPPULSE_SESSION_SECRET` | Signed-session secret; launcher can generate/reuse a private file if unset. |
| `PREPPULSE_ADMIN_USER/NAME/PASSWORD` | Initial bootstrap identity; not a general password-reset mechanism. |
| `LLM_PROVIDER` | Chat and embedding provider selector: `local`, `lmstudio`, `sarvam`, or `ollama`; see the Sarvam embedding limitation above. |
| `SARVAM_AI_CREDITS` or `SARVAM_API_KEY` | Sarvam chat API credential; keep it in a private environment and never commit it. |
| `SARVAM_BASE_URL` | Sarvam OpenAI-compatible API base; defaults to `https://api.sarvam.ai/v1`. |
| `SARVAM_MODEL` | Sarvam chat model identifier; defaults to `sarvam-2b` in the current factory. |
| `LOCAL_LLM_BASE_URL` | OpenAI-compatible base URL including `/v1`. |
| `LOCAL_CHAT_MODEL` | Exact chat model API identifier. |
| `LOCAL_EMBED_MODEL` | Exact embedding model API identifier. |
| `LOCAL_LLM_TIMEOUT` | Local chat request timeout, default 45 seconds. |
| `PREPPULSE_STT_MODEL` | Local transcription model, default `small`. |
| `PREPPULSE_TTS_ENDPOINT` | Optional private WAV audio endpoint for the retained API adapter; no current browser control. |
| `PREPPULSE_TTS_MODEL_ID` | Speech model identifier for the retained API adapter. |
| `PREPPULSE_TTS_MODEL_PATH` | Optional local file reference; the adapter does not execute the file. |
| `PREPPULSE_API_TARGET` | Vite development proxy target. |

Environment variables are read by the process that starts the service. A variable set in another terminal is not automatically inherited. The repository does not promise automatic loading of an arbitrary `.env` file.

### 15.13 Run the focused checks

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_chat_intent.py tests/test_care_presentation.py tests/test_admin_repairs.py tests/test_caregiver_workflow.py tests/test_ui_api.py tests/test_geometry.py tests/test_table_reconstruction.py tests/test_manifest_and_storage.py tests/test_pipeline.py tests/test_hybrid_rag.py -q
.\.venv\Scripts\python.exe -m ruff check src/preppulse_api scripts/bootstrap_ui_admin.py
cd web
npm run build
cd ..
```

Broader tests may require a test MongoDB, a local model, or optional configuration. Read their fixtures first. For example, MongoDB persistence tests clear their designated test database; they are not a reason to point tests at retained patient data.

### 15.14 Run isolated browser checks

Start the synthetic API in its own terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn care_browser_app:app --app-dir tests --host 127.0.0.1 --port 8001
```

Start a separate frontend:

```powershell
cd web
$env:PREPPULSE_API_TARGET = "http://127.0.0.1:8001"
npm run dev -- --port 5174
```

Run the fixture tests from another `web` terminal:

```powershell
$env:PREPPULSE_CARE_FIXTURE = "1"
$env:PREPPULSE_E2E_URL = "http://127.0.0.1:5174"
node node_modules/@playwright/test/cli.js test e2e/caregiver.spec.ts
```

The fixture is synthetic and in-memory. Restart it before repeating tests that create accounts or sign plans. Its credentials and fake translations are test data, not production setup instructions.

Other browser tests can target an isolated configured workspace using the documented E2E URL/user/password environment variables. They create conversations in that workspace, so do not casually run them against retained clinical data.

### 15.15 Troubleshooting

| Symptom | What to inspect |
| --- | --- |
| Care routes return Not Found or caregiver roles are rejected | An older API may still occupy port 8000. Check `/api/runtime` and restart the recognized service. |
| Chart request returns only prose | Use the updated API; plurals and visualization/plot requests must reach the chart tool. Check turn stage/artifact state. |
| No chart for a requested period | Verify that supported dated measurements actually exist inside that window. |
| Unsupported-condition chart warning | Use a whitelisted measurement, or request a cited narrative/occurrence table for the other condition. |
| Source page opens without a precise highlight | Exact source geometry/text could not be verified, or the span is too broad. Inspect the original page. |
| Missing older records | Check patient ID/aliases, upload counts, processing status, and Records before assuming retrieval is at fault. |
| Embedding service fails | Confirm exact embedding model ID; lexical fallback may still work. |
| Analysis is slow | Inspect the active processing stage, local model server, model loading, and failed files. Polling logs alone do not prove an agent is progressing. |
| Translation stays pending/unavailable | Run `scripts/setup_translation.ps1`, confirm access to both model downloads and the WSL environment, restart the API, and use Refresh translations. CPU work can take time; LM Studio's chat model is not the translation worker. |
| Dictation is static or empty | Check microphone permission, listening/transcribing state, selected language, model availability, and API errors. |
| Speech playback is unavailable | The browser feature has been removed. The retained API adapter requires a compatible WAV endpoint. |
| Login stopped working after restart | Confirm the intended database and session secret; refresh/sign in rather than recreating patients. |
| Pydantic native import errors | Use the correct virtual environment and repair that environment's dependency installation before debugging app routes. |

### 15.16 Data handling and reset operations

Patient documents, private uploads, model weights, and generated runtime artifacts must remain out of Git. The repository ignores `private_data`, datasets, local output directories, and test artifacts.

Do not run `scripts/audit_dataset_pipeline.py` against a workspace containing retained patient data: that audit clears MongoDB collections.

The optional reset script first previews counts. Applying a reset is destructive to patient/workflow records and requires explicit flags:

```powershell
# Preview only:
.\.venv\Scripts\python.exe scripts/reset_ui_patient_data.py

# Only for a deliberately disposable local workspace, with the API stopped:
.\.venv\Scripts\python.exe scripts/reset_ui_patient_data.py --apply --confirm preppulse
```

The script retains account records and source files on disk; it is not a secure erase or a substitute for a backup policy. Nothing in ordinary startup requires a reset.

### 15.17 Review and contribution workflow

Keep changes scoped, preserve source provenance, and update `README.md` / `TO_DO.md` when behavior changes. Test the affected paths with isolated data.

Current owner-review delivery goes to `UI`. A later merge to `main` is a separate decision. Before shared or production deployment, review the local-first architecture, authentication, data protection, backups, model hosting, and clinical validation requirements for that environment.