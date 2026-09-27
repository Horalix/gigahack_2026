# Notavra demo runbook

## One-time preparation

Use PowerShell from the repository root. Keep models, recordings and the service database outside Git and OneDrive.

```powershell
npm ci
$venv = Join-Path $env:LOCALAPPDATA 'SecureMOM/venv'
New-Item -ItemType Directory -Force -Path (Split-Path $venv) | Out-Null
python -m venv $venv
$python = Join-Path $venv 'Scripts/python.exe'
& $python -m pip install -r services/meeting/requirements.lock
powershell -ExecutionPolicy Bypass -File scripts/hackathon/prepare-models.ps1 -Model All
powershell -ExecutionPolicy Bypass -File scripts/hackathon/prepare-llm-runtime.ps1 -Runtime cuda12
```

The model/runtime setup commands download and verify pinned assets. They need internet; app runtime does not download models. The locked Python environment includes CUDA 12/cuDNN 9 libraries for Windows GPU ASR. The laptop profile uses the CUDA 12 llama.cpp runtime; on the RTX 5080 workstation prepare the same models and use `-Runtime cuda13` for its CUDA 13 runtime. The CPU profile uses the separately prepared `llama-b11200-cpu` runtime. Preflight checks both ASR libraries and the selected LLM runtime. Set `MOM_CUDA_DLL_PATHS` only if ASR libraries are installed outside the app environment. Prepare files separately on each machine.

## Start the demo

Laptop, RTX 3070 Ti Mobile / 8 GB:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/hackathon/start.ps1 -ProfileId laptop8
```

The script verifies model hashes and local dependencies, starts the loopback-only API and worker in hidden windows, and opens the Tauri app. Close the app/terminal to stop those helpers. If Tauri's Windows C++/LLVM prerequisites are unavailable, run the browser app instead:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/hackathon/start.ps1 -Mode Browser -ProfileId laptop8
# Stop later:
powershell -ExecutionPolicy Bypass -File scripts/hackathon/stop.ps1
```

5080 workstation / 16 GB, run on that machine:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/hackathon/start.ps1 -ProfileId hospital16
```

`MOM_PROFILE` may also select the startup default; `MOM_LLM_RUNTIME` can override the selected llama.cpp runtime (`cpu`, `cuda12` or `cuda13`). `MOM_PYTHON` can point the launcher at a prepared venv when `MOM_DATA_DIR` is customized. The in-app profile setting applies to new jobs only; a running job retains its saved configuration. New jobs require at least 8 GiB available physical RAM and the profile's free-VRAM reserve; low-memory jobs are refused before loading models. ASR and LLM remain serial with bounded transcript batches. Romanian is the default language; the language selector can choose Romanian, Russian, English or automatic detection. Do not use automatic detection for the Romanian-only comparison run.

Sign in or create the first installation administrator, create a meeting, then upload audio/video or record from the microphone. Microphone chunks are saved as you speak; transcription begins after Stop. Review the transcript and evidence-backed actions, correct passages if needed, reprocess after edits, check the approval box and download the HTML minutes file.

## Offline and performance claims

Run preflight while connected once, then disconnect WAN and repeat a complete demo with an allowed synthetic/consented recording. This runbook does not assert that offline egress, the 5080 profile, a one-hour recording, or the 15-minute end-to-end target has passed. Record cold/warm stage times, peak RAM/VRAM and the exact model files for any competition claim. Whisper vs OmniASR results and limitations are in [ASR comparison](ASR_COMPARISON_RESULTS.md).

## Local files and logs

Default app data is under `%LOCALAPPDATA%\SecureMOM`; `MOM_DATA_DIR` can select another local directory outside OneDrive. API/worker/UI logs are under its `logs` subfolder. Stop browser-mode helpers with `stop.ps1`. Do not put patient audio, transcript exports or credentials in the repository.

Deleting a completed meeting is owner-only and removes app-managed files. It is not assured physical erasure from backups, snapshots, downloaded files or external mail. This build is a synthetic/consented hackathon prototype, not a GDPR-approved clinical system.
