# PBI-002: Create local API, storage and restartable jobs

Parent: `hackathon/pbis/README.md`  
Status: COMPLETE  
Priority: P0 — today  
Owner: You  
Recommended model: **GPT-6 Sol**  
Recommended reasoning: **High**  
Depends on: PBI-001

## Outcome

Persist uploaded recordings and meeting jobs independently of inference and expose the agreed local API.

## Source of truth

PBI-001; existing `src-tauri/src/transcript.rs`, `src-tauri/src/persistence.rs`, `.gitignore`. Current user instructions and the PBI index override older H-task allocations. Inspect the branch before editing; proposed paths may have been created by another task.

## Target files

Create: `services/meeting/pyproject.toml`, pinned lockfile, `api.py`, `contracts.py`, `storage.py`, `jobs.py`, `pipeline.py`, `media.py`, `tests/test_jobs.py`. Update `.gitignore` for local environments, models, audio and generated sensitive artifacts.

## Intended changes

- Use FastAPI and a separate SQLite database with versioned migrations. Implement meeting creation, streaming audio/video upload, safe local decode, source hash and timed audio derivatives.
- Enforce generated filenames, size/duration limits, codec validation and bounded decoder subprocess resources. Preserve source channels/timeline and handle multiple/no audio tracks explicitly.
- Run inference outside request handlers. Persist stage/config/artifact IDs and progress; claim one GPU job transactionally. Retry from valid checkpoint, avoid duplicate claims, and recover interrupted jobs after restart.
- Store outside this OneDrive-backed checkout by default (for example a dedicated local app-data directory). Fail visibly on disk exhaustion; do not silently drop speech.
- Add a deny-by-default authorization hook for PBI-005; isolated synthetic fixtures may use an explicit test principal before auth integration.

## Acceptance

- A real upload survives worker failure and restart; API remains responsive; bounded decoding supports the tested audio/video formats.
- Duplicate start requests cannot run the same job twice. Failed stages retain original audio and an actionable state.

## Targeted validation

Upload/traversal/oversize/no-audio fixtures; process interruption and restart; simultaneous job claims; disk-write failure.

## Exclude

Old transcript migration, native overlay refactor, email implementation, EHR integration.

## Completion record

- Commit / changed files: uncommitted on `noomy/freepalestine`; `services/meeting/{api,contracts,storage,jobs,pipeline,media}.py`, service package/dependency files and README, focused jobs tests, `.gitignore`, contract/status updates.
- Commands and observed behavior: 17 focused service/ASR/registry tests passed; Ruff and `compileall` passed. Actual FFmpeg ingest accepted synthetic WAV and MP4 with selected audio track; no-audio video, oversize input and simulated storage failure returned visible errors. The authorized Medpark M4A decoded to full-length WAV and returned a warning for one recoverable ALAC frame error; a synthetic warning persisted through the API. Parallel claim, duplicate API start, frozen model settings, expired lease, checkpoint reuse after failed commit and retry passed. A real local English-only CT2 model processed synthetic spoken audio on the laptop GPU through API/worker after simulated worker expiry: job `ready`, meeting `transcript_ready`, two timed segments, original source retained.
- Acceptance evidence / limitations: PBI-002's durable ingest/job slice is complete. The current `ready` job means transcript completion only; structured minutes belong to later PBIs. Synthetic-only access is explicitly gated and real authorization belongs to PBI-005. FFmpeg is bounded by input size/duration, codec allowlist, threads, per-allocation maximum and process timeout; no OS aggregate memory cap is implemented. The system Python has unrelated package conflicts, so the pinned lock is intended for an isolated environment. Multilingual full large-v3 acceptance remains PBI-003/004.
