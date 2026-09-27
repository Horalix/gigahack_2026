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

- Commit / changed files: `0fb96f0`; added capture-session/chunk tables, authenticated create/status/delete/chunk/seal routes, bounded sequential durable writes, idempotent retries, contiguous sequence validation, media reassembly/decode, and workbench recovery for acknowledged chunks.
- Follow-up on `codex/notavra-finalization`: added authenticated `/api/captures/{id}/preview` for 1–30 second mono PCM16/16 kHz windows, source-offset word timings and overlap ownership filtering. A cross-process file lock serializes live previews with worker inference; preview requests fail fast while busy, enforce profile RAM/VRAM/model checks, and delete their temporary WAV. The complete sealed recording remains the durable source and final jobs still transcribe it again.
- Commands and observed behavior: `python -m pytest services/meeting/tests -q` (46 passed in the final combined suite); `npm run check` (0 errors/warnings); `npm run build` passed. Capture tests verify same-byte retry, conflicting/gapped chunks, incomplete seal rejection, persistence across service restart, WAV seal, idempotent seal and access isolation.
- Live-preview follow-up validation: `python -m pytest services/meeting/tests -q` (54 passed); preview-focused API cases confirm timed ownership filtering, temporary WAV cleanup and malformed WAV rejection. Ruff passes on all changed service files. `npm run check` (0 errors/warnings), `npm run test:ui` (5 passed, including provisional words before Stop and correction/undo state) and `npm run build` pass.
- Real laptop API check on the permitted Medpark sample: one 20-second Romanian preview returned HTTP 200 with one timed segment; ASR reported 6.46 seconds and full request took 14.42 seconds on RTX 3070 Ti Mobile 8 GB. Preview temp directory was empty afterward and `nvidia-smi` showed GPU usage returned to 0 MiB. This is one preview window, not microphone, hour-long capture or end-to-end evidence.
- Acceptance evidence / limitations: captured bytes are durably saved to disk in sequenced chunks; complete sessions reassemble into a source asset and can be retried independently of inference. Live windows are transcribed but are not checkpointed/reused by final processing. There is no one-hour capture, browser-produced WebM, physical-microphone or target-machine run yet, and one-hour source-offset/tail accuracy is unproven. Keep this PBI OPEN until those acceptance conditions are measured.
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

