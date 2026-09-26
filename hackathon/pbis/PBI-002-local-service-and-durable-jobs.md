# PBI-002: Create local API, storage and restartable jobs

Parent: `hackathon/pbis/README.md`  
Status: OPEN  
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

- Commit / changed files: pending
- Commands and observed behavior: pending
- Acceptance evidence / limitations: pending
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

