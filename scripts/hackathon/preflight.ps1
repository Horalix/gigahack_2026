param(
    [ValidateSet('laptop8', 'hospital16', 'cpu')]
    [string]$ProfileId = 'laptop8',
    [string]$PythonPath = (Join-Path $env:LOCALAPPDATA 'SecureMOM/venv/Scripts/python.exe')
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$env:MOM_PROFILE = $ProfileId

foreach ($tool in @('node', 'npm', 'ffmpeg', 'ffprobe')) {
    if (!(Get-Command $tool -ErrorAction SilentlyContinue)) { throw "Required local tool is missing: $tool" }
}
if (!(Test-Path -LiteralPath $PythonPath)) { throw "Prepared Python environment is missing: $PythonPath. Create it and install services/meeting/requirements.lock as described in hackathon/RUNBOOK.md." }
if (!(Test-Path -LiteralPath (Join-Path $projectRoot 'node_modules/vite/bin/vite.js'))) {
    throw 'Node dependencies are missing. Run npm ci from the repository root.'
}

$pythonCheck = @'
import os
from services.meeting.models import resolve_profile, validate_assets
from services.meeting.storage import Storage
from services.meeting.api import host_available_memory_gb
profile = os.environ['MOM_PROFILE']
config = resolve_profile(profile_id=profile)
validate_assets(config)
if profile != 'cpu':
    from services.meeting.cuda_runtime import configure_cuda_dll_search
    ready, issue = configure_cuda_dll_search()
    if not ready:
        raise SystemExit('{}. Install services/meeting/requirements.lock or set MOM_CUDA_DLL_PATHS.'.format(issue))
Storage()
ram = host_available_memory_gb()
print('Profile {}: pinned ASR/LLM files and CUDA libraries verified; available RAM: {:.1f} GiB.'.format(profile, ram) if ram is not None else 'Profile {}: model assets verified; available RAM could not be detected.'.format(profile))
'@
$priorErrorAction = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$checkOutput = @(& $PythonPath -c $pythonCheck 2>&1)
$pythonExitCode = $LASTEXITCODE
$ErrorActionPreference = $priorErrorAction
if ($pythonExitCode -ne 0) { throw "Python/model preflight failed:`n$($checkOutput -join [Environment]::NewLine)" }
$checkOutput | Write-Output

$gpu = & nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>$null
if ($LASTEXITCODE -eq 0 -and $gpu) {
    $memoryGb = [math]::Round(([int]($gpu | Select-Object -First 1) / 1024), 1)
    Write-Output "Detected GPU memory: $memoryGb GiB."
    $required = if ($ProfileId -eq 'hospital16') { 14 } elseif ($ProfileId -eq 'laptop8') { 7 } else { 0 }
    if ($required -and $memoryGb -lt $required) { throw "Selected profile requires at least $required GiB detected VRAM." }
} elseif ($ProfileId -ne 'cpu') {
    throw 'NVIDIA GPU was not detected. Choose -ProfileId cpu only if its pinned models are installed.'
}

Write-Output 'Preflight passed. This checks local files and dependencies; it does not qualify accuracy, runtime or offline egress.'
