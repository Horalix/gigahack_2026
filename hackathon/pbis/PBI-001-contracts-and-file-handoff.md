# PBI-001: Freeze app contracts and Affan's output-file boundary

Parent: `hackathon/pbis/README.md`  
Status: OPEN  
Priority: P0 — today  
Owner: You; Affan confirms only the artifact interface  
Recommended model: **GPT-6 Luna**  
Recommended reasoning: **Medium**  
Depends on: None

## Outcome

Give all implementation sessions one versioned data contract and a concrete output-file fixture.

## Source of truth

`hackathon/02-target-architecture.md`; `hackathon/07-transcript-review.md`; latest user request. Current user instructions and the PBI index override older H-task allocations. Inspect the branch before editing; proposed paths may have been created by another task.

## Target files

Create: `contracts/meeting.schema.json`, `contracts/fixtures/meeting.json`, `contracts/fixtures/final-document.html`, `contracts/README.md`. No proposed `contracts/` files exist in the inspected baseline.

## Intended changes

- Define Meeting, Patient, PatientLink, Asset, Segment/revision, Action/evidence, Job, ReviewIssue, Artifact and error envelopes. Keep original multilingual text, millisecond audio offsets, nullable owner/date, organization ID, object grants and explicit source revisions.
- Patient links are operator-confirmed, never inferred from names. Meetings can have no patients or multiple patients; a link grants no access.
- Propose UTF-8 HTML as the initial final file, with printable styling. Internal manifest: artifact ID, meeting ID, snapshot revision, local path, MIME, SHA-256, status, created time. IDs in filenames; no patient names. Atomically publish file before marking ready.
- Ask Affan to confirm accepted format and handoff mechanism (path/callback/watch directory). Until answered, record these as provisional and use the local ready-artifact interface. Do not invent an agreed integration.
- Freeze fixture/schema version and one route/error example for each boundary. Artifact states: draft/ready/superseded/revoked; generation success is not delivery success.

## Acceptance

- Fixture validates; every nullable field and reference is documented; downstream agents can consume identical fixtures.
- No SMTP, recipients, delivery queue, retry or email design appears in this contract; Affan owns those decisions.
- Output format/trigger agreement is recorded, or explicitly remains pending without blocking core inference.

## Targeted validation

Validate good/bad schema fixtures, missing evidence references and malformed enums. Read the HTML locally; no external assets.

## Exclude

Mail implementation, database implementation, clinical orders, elaborate schema framework.

## Completion record

- Commit / changed files: pending
- Commands and observed behavior: pending
- Acceptance evidence / limitations: pending
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

