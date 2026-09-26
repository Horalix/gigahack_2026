# PBI-010: Generate a final document for Affan

Parent: `hackathon/pbis/README.md`  
Status: OPEN  
Priority: P0 — today  
Owner: You; Affan consumes the final file  
Recommended model: **GPT-6 Luna**  
Recommended reasoning: **High**  
Depends on: PBI-001, PBI-009; fixture rendering can start immediately

## Outcome

Produce a professional, versioned output file that Affan can attach.

## Source of truth

PBI-001 agreed/provisional artifact contract; `hackathon/02-target-architecture.md`. Current user instructions and the PBI index override older H-task allocations. Inspect the branch before editing; proposed paths may have been created by another task.

## Target files

Create `services/meeting/rendering.py`, `templates/minutes.html`, artifact storage/API helpers and `tests/test_artifacts.py`.

## Intended changes

- Render accepted structured facts deterministically into agreed format (initial proposal: standalone UTF-8 HTML). Include title/timezone/type, decisions, actions/owners/dates, explicit unresolved values, revision and actual review state.
- Escape source text; embed/bundle styles and local fonts as necessary. No remote image/font fetches. Do not include whole source audio or patient directory fields by default.
- Atomically write ID-based filename; record checksum, immutable snapshot and authorization/classification metadata. Expose a ready artifact only after successful generation; pending edits invalidate unsent readiness.
- Implement only the agreed file handoff adapter with bounded scoped paths. Generated, handed off, and externally reported delivery are distinct states. Update superseded/revoked metadata without claiming to recall sent files.

## Acceptance

- Affan receives a readable final file through the agreed boundary; fixture and real generated file agree with final action state.
- Draft/stale/unauthorized artifacts cannot be fetched as current final output; source strings cannot inject active HTML.

## Targeted validation

Long text, no decisions, null owner/date, Romanian/Cyrillic rendering, HTML injection, atomic-write failure, stale snapshot access and checksum. Integration receipt at artifact boundary only.

## Exclude

SMTP, email addresses, recipient routing, delivery outbox/retries or any mailing implementation. PDF only if agreed and time-qualified.

## Completion record

- Commit / changed files: pending
- Commands and observed behavior: pending
- Acceptance evidence / limitations: pending
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

