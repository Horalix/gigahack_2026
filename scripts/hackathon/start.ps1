param(
    [ValidateSet('Tauri', 'Browser')]
    [string]$Mode = 'Tauri',
    [ValidateSet('laptop8', 'hospital16', 'cpu')]
    [string]$ProfileId = 'laptop8'
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$dataRoot = if ($env:MOM_DATA_DIR) { $env:MOM_DATA_DIR } else { Join-Path $env:LOCALAPPDATA 'SecureMOM' }
$python = if ($env:MOM_PYTHON) { (Resolve-Path -LiteralPath $env:MOM_PYTHON).Path } else { Join-Path $env:LOCALAPPDATA 'SecureMOM/venv/Scripts/python.exe' }
. (Join-Path $PSScriptRoot 'preflight.ps1') -ProfileId $ProfileId -PythonPath $python

$runDirectory = Join-Path $dataRoot 'run'
$logDirectory = Join-Path $dataRoot 'logs'
New-Item -ItemType Directory -Force -Path $runDirectory, $logDirectory | Out-Null
$pidFile = Join-Path $runDirectory 'notavra-processes.json'
if (Test-Path -LiteralPath $pidFile) { throw "A Notavra run record already exists. Run scripts/hackathon/stop.ps1 first." }

$env:MOM_PROFILE = $ProfileId
$env:PYTHONPATH = if ($env:PYTHONPATH) { "$projectRoot;$env:PYTHONPATH" } else { $projectRoot }

function Assert-FreePort([int]$Port) {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
    try { $listener.Start(); $listener.Stop() }
    catch { $listener.Stop(); throw "Local port $Port is already in use." }
}

function Stop-OwnedProcesses($Records) {
    foreach ($record in @($Records)) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($record.pid)" -ErrorAction SilentlyContinue
        if ($process -and $process.CommandLine -and $process.CommandLine.Contains($record.marker)) {
            Stop-Process -Id $record.pid -Force -ErrorAction SilentlyContinue
        }
    }
}

Assert-FreePort 8000
if ($Mode -eq 'Browser') { Assert-FreePort 1420 }
$records = [System.Collections.Generic.List[object]]::new()
$node = (Get-Command node).Source
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'

try {
    $api = Start-Process -FilePath $python -ArgumentList @('-m', 'uvicorn', 'services.meeting.api:app', '--host', '127.0.0.1', '--port', '8000') `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logDirectory "api-$stamp.log") `
        -RedirectStandardError (Join-Path $logDirectory "api-$stamp.err.log")
    $records.Add([pscustomobject]@{ pid = $api.Id; name = 'api'; marker = 'uvicorn services.meeting.api:app' })

    $worker = Start-Process -FilePath $python -ArgumentList @('-m', 'services.meeting.jobs') `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logDirectory "worker-$stamp.log") `
        -RedirectStandardError (Join-Path $logDirectory "worker-$stamp.err.log")
    $records.Add([pscustomobject]@{ pid = $worker.Id; name = 'worker'; marker = 'services.meeting.jobs' })

    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if ($api.HasExited -or $worker.HasExited) { throw 'The local API or worker exited during startup. Check logs in the local data folder.' }
        try { Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 2 | Out-Null; $ready = $true; break }
        catch { Start-Sleep -Milliseconds 500 }
    }
    if (!$ready) { throw 'The local API did not become ready within 15 seconds.' }

    if ($Mode -eq 'Browser') {
        $vite = Start-Process -FilePath $node -ArgumentList @('node_modules/vite/bin/vite.js', 'dev', '--host', '127.0.0.1', '--port', '1420') `
            -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $logDirectory "vite-$stamp.log") `
            -RedirectStandardError (Join-Path $logDirectory "vite-$stamp.err.log")
        $records.Add([pscustomobject]@{ pid = $vite.Id; name = 'vite'; marker = 'node_modules/vite/bin/vite.js' })
        $uiReady = $false
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            if ($vite.HasExited) { throw 'Vite exited during startup. Check its local log.' }
            try { Invoke-WebRequest -Uri 'http://127.0.0.1:1420' -TimeoutSec 2 -UseBasicParsing | Out-Null; $uiReady = $true; break }
            catch { Start-Sleep -Milliseconds 500 }
        }
        if (!$uiReady) { throw 'The UI did not become ready within 15 seconds.' }
    }

    @($records) | ConvertTo-Json | Set-Content -LiteralPath $pidFile -Encoding utf8
    Write-Output "Notavra services started for profile $ProfileId. Logs: $logDirectory"
    if ($Mode -eq 'Browser') {
        Write-Output 'Opening http://127.0.0.1:1420. Run scripts/hackathon/stop.ps1 to stop owned helpers.'
        Start-Process 'http://127.0.0.1:1420'
    } else {
        Write-Output 'The desktop window is starting. Closing it stops the API and worker.'
        try { & (Join-Path $projectRoot 'scripts/windows-build.ps1') -Task dev }
        finally {
            Stop-OwnedProcesses $records
            Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
        }
    }
} catch {
    Stop-OwnedProcesses $records
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    throw
}
