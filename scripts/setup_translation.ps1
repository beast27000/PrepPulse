param(
    [string]$Distro = 'Ubuntu',
    [ValidateSet('auto', 'cpu', 'cuda')][string]$Device = 'auto',
    [switch]$SkipDownload,
    [switch]$WithCuda
)
$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $workspaceRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Install PrepPulse requirements in .venv first.' }
if (-not $SkipDownload) {
    & $pythonPath (Join-Path $PSScriptRoot 'download_translation_models.py')
    if ($LASTEXITCODE -ne 0) { throw 'Model download is incomplete. Follow the access/login instructions above and retry.' }
}
$linuxRoot = (& wsl.exe -d $Distro -e wslpath -a $workspaceRoot.Replace('\', '/')).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Ubuntu WSL2 is required. See README.md local translation setup.' }
$linuxUserHome = (& wsl.exe -d $Distro -e printenv HOME).Trim()
$linuxData = "$linuxUserHome/.local/share/preppulse/translation"
& wsl.exe -d $Distro -- python3 -m venv "$linuxData/venv"
if ($LASTEXITCODE -ne 0) { throw 'Install python3-venv in Ubuntu, then retry: sudo apt-get install python3-venv build-essential' }
& wsl.exe -d $Distro -- "$linuxData/venv/bin/python" -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'Could not prepare the isolated translation environment.' }
$torchIndex = if ($WithCuda) { 'https://download.pytorch.org/whl/cu126' } else { 'https://download.pytorch.org/whl/cpu' }
$torchVersion = if ($WithCuda) { 'torch==2.7.1+cu126' } else { 'torch==2.7.1+cpu' }
& wsl.exe -d $Distro -e "$linuxData/venv/bin/python" -m pip install $torchVersion --index-url $torchIndex
if ($LASTEXITCODE -ne 0) { throw 'Could not install the local PyTorch runtime.' }
& wsl.exe -d $Distro -- "$linuxData/venv/bin/python" -m pip install -r "$linuxRoot/local_translation/requirements.txt"
if ($LASTEXITCODE -ne 0) { throw 'Could not install IndicTrans2 dependencies. Check the install output above.' }
$settings = @{
    command = @('wsl.exe', '-d', $Distro, '-e', "$linuxData/venv/bin/python", '-u',
        "$linuxRoot/local_translation/worker.py", '--models', "$linuxRoot/.local_models/indictrans2", '--device', $Device)
}
$privateDirectory = Join-Path $workspaceRoot 'private_data'
New-Item -ItemType Directory -Path $privateDirectory -Force | Out-Null
$settings | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $privateDirectory 'translation.json') -Encoding UTF8
Write-Output 'Local translation configured. Restart the PrepPulse API. Models load on the first language request.'
