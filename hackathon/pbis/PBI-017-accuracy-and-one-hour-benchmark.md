# PBI-017: Qualify language accuracy and one-hour performance

Parent: `hackathon/pbis/README.md`  
Status: OPEN  
Priority: P0 — today  
Owner: You run tooling; CEO coordinates human references  
Recommended model: **GPT-6 Luna**  
Recommended reasoning: **High**  
Depends on: PBI-004, PBI-009, PBI-010, PBI-012, PBI-016; collect references earlier

## Outcome

Provide defensible measurements on the actual laptop and comparison 16 GB host.

## Source of truth

`hackathon/03-models-and-performance.md`, `05-build-plan.md`, `08-judging-strategy.md`. Current user instructions and the PBI index override older H-task allocations. Inspect the branch before editing; proposed paths may have been created by another task.

## Target files

Create `evaluation/benchmark.py`, `evaluation/README.md`, small synthetic gold fixtures and `hackathon/BENCHMARK_RESULTS.md`; keep actual recordings/raw sensitive outputs ignored.

## Intended changes

- Run short RO/RU/EN and genuine mixed utterances plus a held-out uninterrupted hour with a late amendment. Do not repeat one English clip to simulate a meeting.
- Log every stage, upload-to-ready time, model cold load, live lag/Stop-to-ready, peak VRAM/RSS, config and source hashes. Consume all inference output before stopping timers.
- Joint final criterion is email receipt <=900 seconds; record Affan's observed completion separately when available. Until then mark end-to-end delivery gate unverified; do not substitute file readiness.
- Score raw ASR, critical terms/names/numbers, decision precision/recall, owners/dates; separate reviewed output. Compare same assets/settings on 5080 first with permitted non-sensitive data.
- If too slow, identify one largest bottleneck and escalate its bounded optimization to Sol, retaining baseline and quality regression results.

## Acceptance

- Actual results and limitations exist; required laptop hour target either passes with evidence or remains openly failed. No extrapolated 16 GB or clinical-accuracy claims.

## Targeted validation

Metric sanity fixture, real timed run, stage sum/boundary consistency, late correction correctness, disconnected confirmation. Independent human reference checks.

## Exclude

Fabricated scores, claiming human corrections improved raw ASR, remote demo inference, mailing implementation.

## Completion record

- Commit / changed files: pending
- Commands and observed behavior: pending
- Acceptance evidence / limitations: pending
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

