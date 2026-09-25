param(
    [ValidateSet('build', 'test', 'fixtures', 'lint', 'package')]
    [string]$Task = 'package',
    [switch]$Release
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location $projectRoot
try {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
    if (!(Test-Path -LiteralPath $vswhere)) { throw 'Install Visual Studio Build Tools with Desktop development with C++.' }
    $installation = (& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -format json | ConvertFrom-Json)[0]
    if (!$installation) { throw 'Visual Studio C++ build tools were not found.' }
    $vsRoot = $installation.installationPath
    $vsMajor = ([version]$installation.installationVersion).Major
    $env:CMAKE_GENERATOR = switch ($vsMajor) { 17 { 'Visual Studio 17 2022' } 18 { 'Visual Studio 18 2026' } default { throw "Unsupported Visual Studio version: $vsMajor" } }
    $cmakeBin = Join-Path $vsRoot 'Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin'
    if (Test-Path -LiteralPath (Join-Path $cmakeBin 'cmake.exe')) { $env:Path = "$cmakeBin;$env:Path" }
    if (!(Get-Command cmake -ErrorAction SilentlyContinue)) { throw 'Install CMake or enable the C++ CMake tools component in Visual Studio Installer.' }
    if (!$env:LIBCLANG_PATH) {
        $clangCandidates = @((Join-Path $env:ProgramFiles 'LLVM/bin'), (Join-Path $projectRoot '.tools/python/clang/native'))
        $env:LIBCLANG_PATH = $clangCandidates | Where-Object { Test-Path -LiteralPath (Join-Path $_ 'libclang.dll') } | Select-Object -First 1
    }
    if (!$env:LIBCLANG_PATH -or !(Test-Path -LiteralPath (Join-Path $env:LIBCLANG_PATH 'libclang.dll'))) { throw 'Install LLVM and set LIBCLANG_PATH to the folder containing libclang.dll.' }
    $vcVersion = (Get-Content -LiteralPath (Join-Path $vsRoot 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt')).Trim()
    $vcInclude = Join-Path $vsRoot "VC/Tools/MSVC/$vcVersion/include"
    $kitsRoot = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots').KitsRoot10
    $sdk = Get-ChildItem -LiteralPath (Join-Path $kitsRoot 'Include') -Directory | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'ucrt') } | Sort-Object { [version]$_.Name } -Descending | Select-Object -First 1
    if (!$sdk) { throw 'Install the Windows 10 or 11 SDK with Visual Studio Build Tools.' }
    $env:BINDGEN_EXTRA_CLANG_ARGS = '-isystem "' + $vcInclude + '" -isystem "' + (Join-Path $sdk.FullName 'ucrt') + '"'
    [string[]]$releaseArgs = if ($Release) { @('--release') } else { @() }
    switch ($Task) {
        'build' { cargo build @releaseArgs --manifest-path src-tauri/Cargo.toml }
        'test' { cargo test @releaseArgs --manifest-path src-tauri/Cargo.toml }
        'fixtures' { cargo test @releaseArgs --manifest-path src-tauri/Cargo.toml real_model_recognizes_prerecorded_speech_and_saves_final_chunks -- --ignored --nocapture }
        'lint' { cargo clippy @releaseArgs --manifest-path src-tauri/Cargo.toml --all-targets -- -D warnings }
        'package' { npm run tauri -- build }
    }
    if ($LASTEXITCODE -ne 0) { throw "The $Task command failed with exit code $LASTEXITCODE." }
} finally {
    Pop-Location
}
