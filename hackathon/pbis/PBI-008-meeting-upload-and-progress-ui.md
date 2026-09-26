# PBI-008: Connect audio/video upload to real processing

Parent: `hackathon/pbis/README.md`  
Status: OPEN  
Priority: P0 — today  
Owner: You  
Recommended model: **GPT-6 Luna**  
Recommended reasoning: **Medium**  
Depends on: PBI-002, PBI-004, PBI-005; fixture development after PBI-001

## Outcome

Provide the shortest working upload-to-transcript/result path.

## Source of truth

`hackathon/02-target-architecture.md`; existing Svelte/domain conventions. Current user instructions and the PBI index override older H-task allocations. Inspect the branch before editing; proposed paths may have been created by another task.

## Target files

Create `src/routes/meetings/+page.svelte`, `src/routes/meetings/[id]/+page.svelte`, `src/lib/api/meetings.ts`, meeting upload/progress components.

## Intended changes

- Setup takes title, recording date/timezone, type, output language, optional participants and explicitly selected patient links. Keep no-patient meetings valid.
- Upload supported audio/video, display progress separately from decoding/ASR/extraction. Expose effective hardware profile without placing model knobs on the primary path.
- Poll real job state; show source transcript, unresolved fields, generated document and error/retry controls. Preserve job ID on reload.
- Include native local-path handling only through existing secure API boundaries; browser route remains fully usable.

## Acceptance

- One real upload reaches saved transcript and generated output after dependent stages are ready; reload restores progress; errors identify the failed stage.

## Targeted validation

Audio and video happy paths, no-audio video, large upload/reload, invalid metadata, API failure/retry, RO/Cyrillic text. Mock tests supplement a real service run.

## Exclude

Affan's sending UI, live capture internals, AI correction queue, visual redesign of unrelated settings.

## Completion record

- Commit / changed files: pending
- Commands and observed behavior: pending
- Acceptance evidence / limitations: pending
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

