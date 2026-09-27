# PBI-016: Launch the complete app offline from prepared assets

Parent: `hackathon/pbis/README.md`  
Status: OPEN  
Priority: P0 — today  
Owner: You  
Recommended model: **GPT-6 Luna**  
Recommended reasoning: **High**  
Depends on: PBI-003, PBI-005, PBI-007, PBI-008, PBI-010, PBI-012

## Outcome

One documented local launch brings up UI, API and model stages after internet removal.

## Source of truth

Existing `package.json`, `scripts/windows-build.ps1`, `src-tauri/tauri.conf.json`; `hackathon/03-models-and-performance.md`. Current user instructions and the PBI index override older H-task allocations. Inspect the branch before editing; proposed paths may have been created by another task.

## Target files

Create `scripts/hackathon/preflight.ps1`, `start.ps1`, `stop.ps1`, `hackathon/RUNBOOK.md`; update only necessary build/package settings.

## Intended changes

- Check model hashes, runtime/GPU support, writable non-synced data path and configured access; fail clearly on missing dependency. Bundle UI fonts/styles and static files locally.
- Reuse current Svelte build; serve UI/API under a local origin to simplify authentication. Do not require native installer compilation for browser demo unless selected explicitly.
- Start background helpers hidden with owned process IDs; stop only those processes. Document LAN TLS separately and keep loopback default.
- Validate external egress denial for actual processes/containers; distinguish blocked attempts from successful traffic and unavailable monitoring. No runtime package/model downloads.
- Record code/model/runtime versions and startup troubleshooting. Affan launches his component under his own instructions; list only agreed external readiness boundary.

## Acceptance

- Fresh process startup with WAN disconnected processes new input to a ready file, including live mode; no subtitle window or missing remote frontend assets.

## Targeted validation

Disconnected start, missing model, occupied port, bad data permissions, start/stop twice, browser auth/reload, direct source access checks.

## Exclude

SMTP setup, emailing runbooks, OS firewall changes without scoped review, full native installer redesign.

## Completion record

- Commit / changed files: `9bb3404`; added PowerShell preflight/start/stop scripts and a concise offline-demo runbook; the selected profile now sets the default profile in the new-meeting flow.
- Follow-up on `codex/cuda-memory-guard`: faster-whisper/CTranslate2 are pinned to 1.2.1/4.8.2, Windows CUDA DLL discovery is checked before ASR loads, and job admission reserves 8 GiB system RAM plus profile-specific free VRAM. The laptop profile uses FP16 batch 1 after int8-float16 failed on the installed CUDA stack; preflight and the 60-second GPU inference smoke pass.
- Commands and observed behavior: PowerShell parser accepted all three scripts; `preflight.ps1 -ProfileId laptop8` verified the installed pinned ASR/LLM files and found 8 GiB VRAM; Browser mode started API, worker and Vite and returned HTTP 200 from UI and API; Playwright rendered the setup form with no client errors; `stop.ps1` stopped exactly the three recorded helpers and released both ports.
- Acceptance evidence / limitations: Browser launch works on this laptop with network disconnected not tested. Tauri compilation remains unverified because CMake and `libclang.dll` are not installed here (browser-mode fallback works). Neither offline egress nor a full one-hour transcription pipeline is qualified. Keep this PBI OPEN.
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

