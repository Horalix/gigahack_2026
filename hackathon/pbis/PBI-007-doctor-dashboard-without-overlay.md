# PBI-007: Replace the caption home with the doctor dashboard

Parent: `hackathon/pbis/README.md`  
Status: OPEN  
Priority: P0 — today  
Owner: You  
Recommended model: **GPT-6 Luna**  
Recommended reasoning: **Medium**  
Depends on: PBI-001; integrate PBI-005 and PBI-006

## Outcome

Open a useful dashboard with patient search and meeting entry, with all transcription inside the main app.

## Source of truth

Existing `src/routes/+page.svelte`, `+layout.svelte`, `src-tauri/src/lib.rs`, `app_state.rs`; new doctor workflow request. Current user instructions and the PBI index override older H-task allocations. Inspect the branch before editing; proposed paths may have been created by another task.

## Target files

Update `src/routes/+page.svelte`; create `src/routes/patients/+page.svelte`, `src/routes/patients/[id]/+page.svelte`, `src/lib/api/patients.ts`, shared dashboard components. Touch native `lib.rs`/tray wiring only where needed to prevent overlay entry.

## Intended changes

- Dashboard: search patients, paginated patient list, recent authorized meetings, New recording and Upload audio/video. Provide empty/loading/error states and clear fictional demo-data labels.
- Debounce search and ignore stale responses; keyboard navigation, Next/Previous page, visible result scope. Show patient identity/reference before link selection.
- Patient detail lists authorized linked documents/meetings; clinical notes are not automatically generated from the entire meeting.
- Remove automatic separate subtitle-window launch and hide overlay controls/shortcuts from the new doctor path. Transcript/progress lives inline. Retain unused native renderer code for now; deletion is unnecessary to complete this task.
- Ordinary browser mode must not call Tauri IPC. If packaged Tauri is launched, its default path/tray must reach the dashboard rather than start the obsolete overlay.

## Acceptance

- Doctor can search, page, open a patient and start an upload/recording flow; no subtitle window opens during the new journey.

## Targeted validation

Browser flow with >25 patients, stale search responses, no results and unauthorized detail; actual Tauri launch smoke if packaging is included; npm check.

## Exclude

Native renderer cleanup, medical advice panels, polished charts, changing app framework.

## Completion record

- Commit / changed files: pending
- Commands and observed behavior: pending
- Acceptance evidence / limitations: pending
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

