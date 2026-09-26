# PBI-018: Suggest focused transcript corrections

Parent: `hackathon/pbis/README.md`  
Status: OPEN  
Priority: P1 — only after today's P0 passes  
Owner: You  
Recommended model: **GPT-6 Sol**  
Recommended reasoning: **High**  
Depends on: PBI-009, PBI-013, PBI-014, PBI-017

## Outcome

Find useful suspect spans without creating a long false-alarm review burden.

## Source of truth

`hackathon/07-transcript-review.md`; `08-judging-strategy.md`. Current user instructions and the PBI index override older H-task allocations. Inspect the branch before editing; proposed paths may have been created by another task.

## Target files

Extend `services/meeting/review.py`, LLM response schema and transcript-review UI; add `tests/test_review_issues.py`.

## Intended changes

- Use repeated variants/approved glossary and bounded LLM candidates with local context. Return exact revision/span, reason, optional alternatives and textual evidence. No silent medical repair or claim to hear phonetic similarity.
- Share loaded LLM/extraction budget; cap candidates/output tokens. Validate substrings, deduplicate and retain keep/defer disposition for unchanged revisions.
- UI supports highlighted issues, audio replay, alternative selection and approve selected/all eligible with preview. High-impact quantities/drug identity/negation/owners/dates remain occurrence-reviewed.
- Measure false flags, correct/incorrect suggestions and reviewer time against manual editing on unseen matched material.

## Acceptance

- Useful flags on real held-out errors; correct uncommon/code-switched terms remain unchanged unless reviewed; unaccepted suggestions never affect minutes.

## Targeted validation

Repeated wrong and genuinely different terms, unknown name, decimal/negation, nonexistent model spans, prompt injection, stale flag after edit; timed review and full performance regression.

## Exclude

Unbounded full transcript rewrite, second model requirement, automatic unreviewed clinical corrections.

## Stop rule

Timebox first experiment to 90 minutes after P0; disable suggestions if quality or processing-time gate regresses.

## Completion record

- Commit / changed files: pending
- Commands and observed behavior: pending
- Acceptance evidence / limitations: pending
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

