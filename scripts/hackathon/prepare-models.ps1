[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('ASR', 'LLM', 'All')]
    [string] $Model
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$manifestPath = Join-Path $repoRoot 'models\manifest.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$modelRoot = if ($env:MOM_MODEL_ROOT) {
    [System.IO.Path]::GetFullPath($env:MOM_MODEL_ROOT)
} elseif ($env:LOCALAPPDATA) {
    Join-Path $env:LOCALAPPDATA 'SecureMOM\models'
} else {
    Join-Path $HOME '.local\share\secure-mom\models'
}

$aliases = switch ($Model) {
    'ASR' { @('whisper-large-v3-local') }
    'LLM' { @('qwen35-4b-q4km-local') }
    'All' { @('whisper-large-v3-local', 'qwen35-4b-q4km-local') }
}

foreach ($alias in $aliases) {
    $entry = $manifest.models.$alias
    $destination = Join-Path $modelRoot $entry.path
    $artifactEntries = if ($entry.artifact) { @($entry.artifact) } else { @($entry.artifacts) }
    foreach ($artifact in $artifactEntries) {
        $target = if ($entry.artifact) { $destination } else { Join-Path $destination $artifact.path }
        $parentDirectory = Split-Path -Parent $target
        if (-not (Test-Path -LiteralPath $parentDirectory -PathType Container)) {
            New-Item -ItemType Directory -Path $parentDirectory -Force | Out-Null
        }
        $validExisting = $false
        if (Test-Path -LiteralPath $target -PathType Leaf) {
            if ($artifact.sha256) {
                $validExisting = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -eq $artifact.sha256
            } else {
                $validExisting = $true
            }
        }
        if ($validExisting) { continue }

        $temporary = "$target.download"
        $encodedPath = [Uri]::EscapeDataString($artifact.path)
        $uri = "https://huggingface.co/$($entry.upstream)/resolve/$($entry.revision)/$($encodedPath)?download=true"
        if (-not $PSCmdlet.ShouldProcess($target, "Download pinned model asset from $($entry.upstream)")) {
            Write-Output "Skipped $alias/$($artifact.path)"
            continue
        }
        if ($artifact.size_bytes -and $artifact.size_bytes -gt 100000000 -and $artifact.sha256) {
            & python (Join-Path $PSScriptRoot 'download-ranges.py') $uri $temporary $artifact.size_bytes $artifact.sha256
        } elseif (Test-Path -LiteralPath $temporary -PathType Leaf) {
            & curl.exe --fail --location --continue-at - --retry 3 --retry-all-errors --show-error --output $temporary $uri
        } else {
            & curl.exe --fail --location --range 0- --retry 3 --retry-all-errors --show-error --output $temporary $uri
        }
        if ($LASTEXITCODE -ne 0) {
            throw "Download failed for $alias/$($artifact.path) (curl exit $LASTEXITCODE). Partial data is kept for resume at $temporary."
        }
        if ($artifact.size_bytes -and (Get-Item -LiteralPath $temporary).Length -ne $artifact.size_bytes) {
            Remove-Item -LiteralPath $temporary -Force
            throw "Unexpected size for $alias/$($artifact.path)."
        }
        if ($artifact.sha256) {
            $actual = (Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($actual -ne $artifact.sha256) {
                Remove-Item -LiteralPath $temporary -Force
                throw "SHA-256 mismatch for $alias/$($artifact.path)."
            }
        }
        Move-Item -LiteralPath $temporary -Destination $target -Force
    }
    Write-Output "Prepared pinned assets for $alias at $destination"
}
