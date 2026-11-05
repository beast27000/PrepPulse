param([int]$Port = 8000, [switch]$Restart, [switch]$NoReload)
$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $workspaceRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create .venv and install requirements first; see README.md.' }
Set-Location -LiteralPath $workspaceRoot
$listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
    $existing = $null
    try { $existing = Invoke-RestMethod "http://127.0.0.1:$Port/api/runtime" -TimeoutSec 3 } catch { }
    if ($existing.contract -eq 'preppulse-ui-care-4' -and -not $Restart) {
        Write-Output "Current PrepPulse API already runs on port $Port. Use -Restart after code updates."
        return
    }
    if ($processInfo.CommandLine -notmatch 'uvicorn\s+preppulse_api\.app:app') {
        throw "Port $Port belongs to a different service (PID $($listener.OwningProcess)). Choose another port; it was not stopped."
    }
    $runningJobs = & $pythonPath -c "from preppulse_api.store import WorkspaceStore; s=WorkspaceStore(); print(s.db.jobs.count_documents({'status':{'`$in':['queued','running']}})+s.db.chat_turns.count_documents({'status':{'`$in':['queued','running']}})); s.client.close()"
    if ($LASTEXITCODE -ne 0) { throw 'Could not check background jobs. The existing API was not stopped.' }
    if ([int]($runningJobs | Select-Object -Last 1) -gt 0 -and -not $Restart) {
        throw 'Analysis/chat work is active. Let it finish, or explicitly use -Restart to interrupt it and make it retryable.'
    }
    Stop-Process -Id $listener.OwningProcess
    Write-Output 'Replaced the older PrepPulse API process. Refresh the browser and sign in again.'
}
if (-not $env:PREPPULSE_SESSION_SECRET) {
    $secretDirectory = Join-Path $workspaceRoot 'private_data'
    New-Item -ItemType Directory -Path $secretDirectory -Force | Out-Null
    $secretFile = Join-Path $secretDirectory '.session-secret'
    if (Test-Path -LiteralPath $secretFile) {
        $env:PREPPULSE_SESSION_SECRET = (Get-Content -LiteralPath $secretFile -Raw).Trim()
    } else {
        $secretBytes = New-Object byte[] 48
        $randomSource = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        $randomSource.GetBytes($secretBytes)
        $randomSource.Dispose()
        $env:PREPPULSE_SESSION_SECRET = [Convert]::ToBase64String($secretBytes)
        Set-Content -LiteralPath $secretFile -Value $env:PREPPULSE_SESSION_SECRET -NoNewline
    }
}
if ($env:PREPPULSE_SESSION_SECRET.Length -lt 32) { throw 'PREPPULSE_SESSION_SECRET must contain at least 32 characters.' }
$serverArguments = @('-m', 'uvicorn', 'preppulse_api.app:app', '--host', '127.0.0.1', '--port', $Port.ToString())
if (-not $NoReload) { $serverArguments += @('--reload', '--reload-dir', (Join-Path $workspaceRoot 'src')) }
& $pythonPath @serverArguments
