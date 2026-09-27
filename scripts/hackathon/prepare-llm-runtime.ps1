[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('cuda12', 'cuda13')]
    [string] $Runtime
)

$ErrorActionPreference = 'Stop'
$version = 'b11200'
$baseName = "llama-$version"
$assets = if ($Runtime -eq 'cuda12') {
    @(
        @{ Name = "$baseName-bin-win-cuda-12.4-x64.zip"; Sha256 = '8f9fcdb185dcd99a63cdfa3716f1ab12584060baef96a48bc6db157a4db843d1' },
        @{ Name = 'cudart-llama-bin-win-cuda-12.4-x64.zip'; Sha256 = '8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6' }
    )
} else {
    @(
        @{ Name = "$baseName-bin-win-cuda-13.4-x64.zip"; Sha256 = 'ac88b6102fb9cb6344f897ddfa7400e67ff8d687ad34c124ca5764293ef5ef3f' },
        @{ Name = 'cudart-llama-bin-win-cuda-13.4-x64.zip'; Sha256 = '738f8c251ac22b70c3ae6f83a10cf222725df0395246a2cf58f32bdb85fbe668' }
    )
}
$runtimeRoot = if ($env:LOCALAPPDATA) {
    Join-Path $env:LOCALAPPDATA "SecureMOM\runtimes\llama-$version-$Runtime"
} else {
    Join-Path $HOME ".local\share\secure-mom\runtimes\llama-$version-$Runtime"
}
$downloadRoot = Join-Path $runtimeRoot 'downloads'
New-Item -ItemType Directory -Force -Path $downloadRoot | Out-Null

foreach ($asset in $assets) {
    $archive = Join-Path $downloadRoot $asset.Name
    $url = "https://github.com/ggml-org/llama.cpp/releases/download/$version/$($asset.Name)"
    if (-not (Test-Path -LiteralPath $archive -PathType Leaf) -or
        (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $asset.Sha256) {
        if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
        if (-not $PSCmdlet.ShouldProcess($archive, "Download and verify official llama.cpp $version CUDA runtime")) { continue }
        & curl.exe --fail --location --retry 3 --retry-all-errors --show-error --output $archive $url
        if ($LASTEXITCODE -ne 0) { throw "Download failed for $($asset.Name) (curl exit $LASTEXITCODE)." }
    }
    $digest = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($digest -ne $asset.Sha256) {
        Remove-Item -LiteralPath $archive -Force
        throw "SHA-256 mismatch for $($asset.Name)."
    }
}

if (-not $PSCmdlet.ShouldProcess($runtimeRoot, "Extract pinned llama.cpp $version $Runtime runtime")) { return }
foreach ($asset in $assets) {
    Expand-Archive -LiteralPath (Join-Path $downloadRoot $asset.Name) -DestinationPath $runtimeRoot -Force
}
$server = Get-ChildItem -LiteralPath $runtimeRoot -Filter 'llama-server.exe' -File -Recurse | Select-Object -First 1
if (-not $server) { throw 'The verified archives did not contain llama-server.exe.' }
if ($server.DirectoryName -ne $runtimeRoot) {
    Get-ChildItem -LiteralPath $server.DirectoryName -Force | Move-Item -Destination $runtimeRoot -Force
    Remove-Item -LiteralPath $server.DirectoryName -Force
}
& (Join-Path $runtimeRoot 'llama-server.exe') --version
if ($LASTEXITCODE -ne 0) { throw 'The extracted llama-server failed its version check.' }
Write-Output "Prepared llama.cpp $version ($Runtime) at $runtimeRoot"
