# PBI-014: Deliver manual review, audio replay and bulk correction

Parent: `hackathon/pbis/README.md`  
Status: OPEN  
Priority: P0 — today  
Owner: You  
Recommended model: **GPT-6 Luna**  
Recommended reasoning: **High**  
Depends on: PBI-008, PBI-013

## Outcome

A reviewer edits any phrase, previews selected replacements and hears the corresponding source quickly.

## Source of truth

`hackathon/07-transcript-review.md`. Current user instructions and the PBI index override older H-task allocations. Inspect the branch before editing; proposed paths may have been created by another task.

## Target files

Create `src/lib/components/meetings/transcript-review.svelte`, shared evidence drawer; extend meeting client/route.

## Intended changes

- Inline edit and selected-occurrence replacement work even without AI flags. Preview exact before/after occurrences/count, apply selected and undo batch.
- Show original vs edited text, revision/rebuild state, and source audio replay with context; source intervals are not invented timing for replacement words.
- Prepare Previous/Next issue navigation and focus-safe Up/Down behavior for PBI-018. Do not intercept normal text cursor or browser Find.
- Show stale revision conflicts and refresh safely; prevent repeated clicks creating duplicate edits. Accessible labels and text indicators supplement colors.

## Acceptance

- Reviewer can edit an unflagged phrase, batch selected matches, undo and open updated minutes; no stale artifact appears ready during rebuild.

## Targeted validation

Keyboard/focus behavior, Unicode selection, matches in unrelated contexts excluded, batch preview/count, rejected stale edit, actual backend edit-to-artifact flow.

## Exclude

AI flag generation, global blind replace, patient diagnosis editing, advanced document editor.

## Completion record

- Commit / changed files: `47d30ed`; authorized normalized-audio playback, Unicode text search with match counters and Up/Down/Enter navigation, passage selection, before/after previews, atomic find/replace and existing audited Undo control.
- Commands and observed behavior: `python -m pytest services/meeting/tests -q` (46 passed, including audio route access); `npm run check` (0 errors/warnings); `npm run build` passed.
- Follow-up on `codex/notavra-finalization`: transcript rows now have an accessible Play control that seeks the local audio player to the passage start. `npm run test:ui` (3 passed, including seek/play invocation with a browser audio stub), `npm run check` (0 errors/warnings), and `npm run build` passed.
- Follow-up validation: five mocked Playwright workflows pass, including single-text correction, decision invalidation, audited Undo back to the original wording, and keeping decisions stale until saved audio is reprocessed. This validates the review state flow, not actual clinician acceptance or audio listening.
- Acceptance evidence / limitations: playback uses the normalized local WAV behind existing meeting access checks. Replacement selections operate on selected passages and preview the whole affected passage. Browser test verifies seek time and play invocation, but actual audio playback through the integrated desktop remains unverified; keep this PBI OPEN until manually exercised.
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

