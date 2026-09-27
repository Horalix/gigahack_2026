$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$dataRoot = if ($env:MOM_DATA_DIR) { $env:MOM_DATA_DIR } else { Join-Path $env:LOCALAPPDATA 'SecureMOM' }
$pidFile = Join-Path $dataRoot 'run/notavra-processes.json'
if (!(Test-Path -LiteralPath $pidFile)) {
    Write-Output 'No Notavra browser-mode helpers are recorded as running.'
    exit 0
}

$records = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
$stopped = 0
foreach ($record in @($records)) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($record.pid)" -ErrorAction SilentlyContinue
    if ($process -and $process.CommandLine -and $process.CommandLine.Contains($record.marker)) {
        Stop-Process -Id $record.pid -Force -ErrorAction SilentlyContinue
        $stopped++
    }
}
Remove-Item -LiteralPath $pidFile -Force
Write-Output "Stopped $stopped recorded Notavra helper process(es)."
