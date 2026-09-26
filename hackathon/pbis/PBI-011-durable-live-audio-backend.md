# PBI-011: Persist live audio and transcribe completed windows

Parent: `hackathon/pbis/README.md`  
Status: OPEN  
Priority: P0 — today  
Owner: You  
Recommended model: **GPT-6 Sol**  
Recommended reasoning: **High**  
Depends on: PBI-002, PBI-004, PBI-005

## Outcome

Live recognition can lag or fail without losing an otherwise healthy recording.

## Source of truth

`hackathon/02-target-architecture.md`; existing capture/ASR overload limitations in `docs/ENGINEERING_NOTES.md`. Current user instructions and the PBI index override older H-task allocations. Inspect the branch before editing; proposed paths may have been created by another task.

## Target files

Create `services/meeting/capture.py`, `tests/test_capture.py`; extend media/pipeline/API.

## Intended changes

- Implement recording session, sequenced chunk PUT and Stop/seal endpoints. Acknowledge only durable writes; idempotent duplicate retries, sequence gaps and final chunk explicitly tracked.
- Reassemble browser container stream correctly; blobs are not assumed independent audio files. Use sample timestamps for source mapping, not browser timeslice timer counts.
- Process bounded complete speech windows from saved data; provisional segment revisions are replaceable. Preserve overlap mapping and avoid duplicate final words.
- Capture state is separate from inference state. Disk/device/network failure surfaces promptly; storage stops explicitly rather than buffering indefinitely.
- Stop seals complete asset, handles last window, reuses completed ASR and queues final LLM once. Single GPU admission also covers live/file jobs.

## Acceptance

- Controlled hour recording retains full source duration, repeated chunks are harmless, ASR failure does not lose source, and final transcript covers the tail once.

## Targeted validation

Retry/reorder/missing chunk, final chunk racing Stop, restart with incomplete session, inference crash, disk full, long recording and source-offset continuity.

## Exclude

Native system/application capture expansion, simultaneous GPU models, live decision generation.

## Completion record

- Commit / changed files: pending
- Commands and observed behavior: pending
- Acceptance evidence / limitations: pending
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

