# PBI-012: Record and view live transcripts in the main app

Parent: `hackathon/pbis/README.md`  
Status: OPEN  
Priority: P0 — today  
Owner: You  
Recommended model: **GPT-6 Luna**  
Recommended reasoning: **Medium**  
Depends on: PBI-007, PBI-011

## Outcome

Doctor can start, stop and follow recording without a floating subtitle window.

## Source of truth

`hackathon/02-target-architecture.md`; existing source/meter UI for reusable visual ideas. Current user instructions and the PBI index override older H-task allocations. Inspect the branch before editing; proposed paths may have been created by another task.

## Target files

Create meeting recording component under `src/lib/components/meetings/`; extend `src/lib/api/meetings.ts` and meeting route.

## Intended changes

- Request microphone only after deliberate Record action; select supported MIME/device, show notice, timer and audio level.
- Stream ordered chunks with bounded in-flight bytes, acknowledgments and retry status. Preserve final data event before Stop/seal. Surface revoked permission/device/server loss.
- Show persisted duration separately from ASR lag/provisional transcript. Avoid auto-scroll while user is reviewing older text.
- Use localhost on demo laptop and trusted HTTPS for LAN browser microphone. Provide visible fallback/error rather than fake recording.

## Acceptance

- New operator records a short meeting, sees inline words, stops and obtains final output; no native overlay appears.

## Targeted validation

Permission denial, device removal, unsupported MIME, delayed acknowledgment, final chunk event order and reload/interruption messaging; real controlled microphone run.

## Exclude

Background recording after browser closes, speaker enrollment, native overlay functionality, automatic microphone activation.

## Completion record

- Commit / changed files: `00a5730`, `0fb96f0`; main-app microphone recording now uploads acknowledged browser chunks to the local service and resumes/declares saved partial captures after interruption.
- Commands and observed behavior: capture API tests cover durable sequence writes, duplicate retries, gap rejection, restart recovery, WAV sealing and access isolation; Svelte check/build pass.
- Acceptance evidence / limitations: the original implementation established safe local capture and final processing. The follow-ups below add a meter, confirmed-chunk status and inline provisional words; a physical microphone run has not been performed.
- Follow-up on `codex/notavra-finalization`: recording UI now displays a microphone level meter and counts acknowledged versus pending durable chunks. A mocked microphone/browser flow verifies level updates, chunk acknowledgment, Stop and final transcript processing. `npm run check`, `npm run test:ui` (4 passed) and `npm run build` pass.
- Follow-up on `codex/notavra-finalization`: mic PCM is resampled to bounded 20-second mono/16 kHz windows with 2-second overlap. Local Whisper returns source-timed provisional words inline while MediaRecorder continues saving the full source. Inference is serialized with file jobs and preview lag never stalls or drops the durable recording. The mocked UI flow now verifies provisional words appear before Stop.
- PBI remains OPEN: the browser mic is mocked; real-device recording, permission loss and preview timing on target GPUs are unverified. Final ASR reuses matching checkpoints and fills gaps, but this is not yet tested on an hour capture.
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

