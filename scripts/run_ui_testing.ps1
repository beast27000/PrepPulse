param(
    [ValidateSet('sarvam', 'gemini', 'auto', 'local')][string]$Provider = 'sarvam',
    [string]$Database = 'preppulse_ui_testing',
    [int]$Port = 8001,
    [switch]$EnableGemini
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if ((git branch --show-current) -ne 'ui_testing') { throw 'Switch to ui_testing first.' }
if (-not $Database.StartsWith('preppulse_ui_testing')) { throw 'An isolated test database is required.' }
$profilePath = Join-Path $projectRoot '.tmp/ui_testing/profile.json'
if (-not (Test-Path -LiteralPath $profilePath)) { throw 'Run scripts/prepare_ui_testing.py first.' }
$profile = Get-Content -LiteralPath $profilePath -Raw | ConvertFrom-Json
$env:PREPPULSE_MONGO_DB = $Database
$env:PREPPULSE_PRIVATE_ROOT = $profile.private_root
$env:PREPPULSE_SESSION_SECRET = $profile.session_secret
$env:PREPPULSE_SESSION_COOKIE = 'preppulse_ui_testing_session'
$env:PREPPULSE_AI_PROVIDER = $Provider
$env:PREPPULSE_STRICT_AI = '1'
$env:PREPPULSE_RESUME_ANALYSIS = '1'
$env:PREPPULSE_SYNTHETIC_ONLY = '1'
$env:PREPPULSE_FHIR_ENABLED = '1'
$env:PREPPULSE_EMBED_PROVIDER = 'python'
$env:PREPPULSE_EMBED_REVISION = '614241f622f53c4eeff9890bdc4f31cfecc418b3'
$env:PREPPULSE_TRANSLATION_PROVIDER = 'sarvam'
$env:PREPPULSE_TRANSLATION_FALLBACK = 'local'
$env:PREPPULSE_VOICE_PROVIDER = 'sarvam'
$env:SARVAM_MODEL = 'sarvam-105b'
$env:GEMINI_MODEL = 'gemini-3.5-flash-lite'
$env:PREPPULSE_GEMINI_ENABLED = '0'
$env:PREPPULSE_GEMINI_REQUEST_LIMIT = '200'
if ($Provider -eq 'gemini' -or $EnableGemini) { $env:PREPPULSE_GEMINI_ENABLED = '1' }
& .\.venv\Scripts\python.exe -m uvicorn preppulse_api.app:app --host 127.0.0.1 --port $Port
