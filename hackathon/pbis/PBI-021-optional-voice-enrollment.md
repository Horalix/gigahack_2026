# PBI-021: Qualify optional returning-speaker voice profiles

Parent: `hackathon/pbis/README.md`  
Status: OPEN  
Priority: P2 — later unless every earlier gate is green  
Owner: You; data-protection reviewer approves intended use  
Recommended model: **GPT-6 Sol**  
Recommended reasoning: **High**  
Depends on: PBI-019, PBI-020, PBI-015, PBI-022

## Outcome

Offer consented optional identity suggestions with an unknown fallback.

## Source of truth

`hackathon/04-speakers.md`; `hackathon/09-patient-data-and-eu.md`. Current user instructions and the PBI index override older H-task allocations. Inspect the branch before editing; proposed paths may have been created by another task.

## Target files

Extend `speakers.py`, profile storage/migrations, enrollment UI, privacy policy/tests.

## Intended changes

- Prompt clean speech with level/overlap/quality checks; initial 20–30 second duration is an experiment. Store model-versioned embeddings and minimal consent/deletion metadata locally.
- Match only selected eligible participant profiles. Calibrate thresholds/margins on held-out known/unknown voices; suggest until confirmed. Do not use identity as login or patient match.
- Keep opt-out quick recording functional; deletion removes templates and associated retained enrollment data under approved policy.

## Acceptance

- Measured false-match and unknown rates, correction/deletion demonstrated, legal/ethics gate documented. If unqualified, feature remains disabled.

## Targeted validation

Unknown impostor, same person/new microphone, noisy/short sample, revoked profile, incorrect identity and downstream correction.

## Exclude

Biometric authentication, worker emotion/performance analysis, claiming a checkbox alone makes processing lawful.

## Completion record

- Commit / changed files: pending
- Commands and observed behavior: pending
- Acceptance evidence / limitations: pending
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

