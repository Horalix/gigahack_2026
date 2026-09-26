# PBI-020: Map and correct speaker labels

Parent: `hackathon/pbis/README.md`  
Status: OPEN  
Priority: P1 — after PBI-019  
Owner: You  
Recommended model: **GPT-6 Luna**  
Recommended reasoning: **High**  
Depends on: PBI-019, PBI-013

## Outcome

Let reviewers associate voices with participant names and repair mistaken turns.

## Source of truth

`hackathon/04-speakers.md`. Current user instructions and the PBI index override older H-task allocations. Inspect the branch before editing; proposed paths may have been created by another task.

## Target files

Create speaker setup/review components; extend meeting API/contracts and `speakers.py` mapping endpoints.

## Intended changes

- Add/select participants or skip setup; allow any count. Map anonymous cluster to an explicit person, rename across meeting and correct individual turns.
- Preserve unknown/overlap states and mapping method. Cluster rename cannot disguise merged speakers; expose turn reassignment.
- Revalidate first-person owner fields and dependent output after changes; explicit named owners remain evidence-driven.

## Acceptance

- Reviewer can correct a misnamed cluster/turn and see the corresponding revised action owner where warranted.

## Targeted validation

Unknown speaker, split/merged cluster correction, participant removal, stale revision, owner distinct from speaker, keyboard access.

## Exclude

Voice biometrics, automatic patient linking, participant identity as authorization.

## Completion record

- Commit / changed files: pending
- Commands and observed behavior: pending
- Acceptance evidence / limitations: pending
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

