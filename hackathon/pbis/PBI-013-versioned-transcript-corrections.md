# PBI-013: Apply transcript corrections and rebuild dependent output

Parent: `hackathon/pbis/README.md`  
Status: OPEN  
Priority: P0 — today  
Owner: You  
Recommended model: **GPT-6 Sol**  
Recommended reasoning: **High**  
Depends on: PBI-002, PBI-009, PBI-010

## Outcome

Manual single/batch edits and undo preserve original evidence and produce consistent revised minutes.

## Source of truth

`hackathon/07-transcript-review.md`; PBI-001 contracts. Current user instructions and the PBI index override older H-task allocations. Inspect the branch before editing; proposed paths may have been created by another task.

## Target files

Create `services/meeting/review.py`, `tests/test_review.py`; extend contracts/storage/pipeline/artifact readiness.

## Intended changes

- Store immutable raw transcript plus revisioned edits with actor, span, original text, replacement and batch ID. Verify exact source at expected revision and Unicode code-point offsets.
- Apply explicit selected replacements atomically; reject overlaps/stale revisions. Undo creates an inverse revision and retains the audit trail.
- Invalidate affected evidence and current artifact; re-extract surrounding changed context and globally reconcile final actions. Never reuse stale flags/source offsets silently.
- Publish fresh artifact only after dependent state agrees; preserve existing snapshots and mark superseded. Coordinate version/readiness at file boundary with Affan; do not implement mail logic.

## Acceptance

- Edited display, action fields and final document agree; wrong revision/overlap never partially applies; raw source audio/text unchanged.

## Targeted validation

RO/Cyrillic/emoji offset conversions, concurrent edits, batch apply/undo, late owner change, interrupted rebuild, artifact handoff during edit.

## Exclude

LLM suggestions, arbitrary whole-file text rewriting, mail retry/recall, destructive replacement of source.

## Completion record

- Commit / changed files: pending
- Commands and observed behavior: pending
- Acceptance evidence / limitations: pending
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

