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

- Commit / changed files: pending
- Commands and observed behavior: pending
- Acceptance evidence / limitations: pending
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

