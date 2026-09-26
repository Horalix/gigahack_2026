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

- Commit / changed files: pending
- Commands and observed behavior: pending
- Acceptance evidence / limitations: pending
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

