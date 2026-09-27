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
- Follow-up on `codex/cuda-memory-guard`: faster-whisper/CTranslate2 are pinned to 1.2.1/4.8.2, Windows CUDA DLL discovery is checked before ASR loads, and job admission requires 8 GiB available system RAM plus profile-specific free VRAM. FP16 is used because int8-float16 failed on the installed CUDA stack. The current laptop profile uses batch 2 after two identical same-sample runs; a verified llama.cpp b11200 CUDA 12 runtime runs the local 4B LLM. The 5080 profile is prepared for CUDA 13 but requires a host-side check.
- Real local API/worker run on the consented challenge sample reached `ready` with Romanian-forced Whisper. The original M4A produced 191 segments and 20 review-required decisions after compact LLM reconciliation; another actual browser upload produced 182 passages and 18 items, followed by generated/downloaded HTML. `python -m pytest services/meeting/tests -q` passes 52 tests; `npm run check` and `npm run build` pass; `npm run test:ui` passes 3 mocked workflow tests. The actual browser journey used the real worker, with an API checkpoint retry after the first extraction attempt failed. The automated test checked the approval box; no clinician assessed the content. Batch-2 ASR (46.7s on 702.5s) plus the latest 95.68s LLM stage projects to 12.2 minutes/hour by linear stage sum; the complete hour remains unmeasured.
- Commands and observed behavior: PowerShell parser accepted all three scripts; `preflight.ps1 -ProfileId laptop8` verified the installed pinned ASR/LLM files and found 8 GiB VRAM; Browser mode started API, worker and Vite and returned HTTP 200 from UI and API; Playwright rendered the setup form with no client errors; `stop.ps1` stopped exactly the three recorded helpers and released both ports.
- Acceptance evidence / limitations: The documented launcher starts the native Tauri dev app together with its API and worker; health returns `ok`. `libclang==18.1.1` was installed only under ignored `.tools/python`; no tracked dependency changed. The actual browser journey verified upload, transcript/actions, and HTML download, but the clinician's review was simulated. The packaged release build, WAN-disconnected startup/egress, physical microphone, one-hour upload and full one-hour timing remain unqualified. Keep this PBI OPEN.
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

