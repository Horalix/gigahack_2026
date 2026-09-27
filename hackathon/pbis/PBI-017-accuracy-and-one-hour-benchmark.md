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

- Commit / changed files: `codex/asr-comparison` report refresh; implementation/runtime support in `0d8cd6d` and `c57e289`. Public-safe comparison is in `hackathon/ASR_COMPARISON_RESULTS.md`. Private audio, references, hypotheses and current app transcript stay under `%LOCALAPPDATA%\SecureMOM\evaluation`.
- Commands and observed behavior: `python -m pytest services/meeting/tests -q` — 51 passed; `npm run check` — 0 errors/warnings; `npm run build` passed; `scripts/hackathon/preflight.ps1 -ProfileId laptop8` passed. The real 702.549-second Romanian upload reached job state `ready`; ASR took 118.6 seconds and created 166 segments. The local GPU LLM produced 35 review-required items. Current Whisper FP16 scored 51.8% WER / 33.3% CER against saved reference. Previously tested Omni CTC scored 72.6% / 52.6%; Omni LLM forced `ron_Latn` scored 66.9% / 46.4%.
- Acceptance evidence / limitations: the supplied share page could not be independently retrieved; the saved Microsoft machine transcript (SHA-256 `49ef9ec13d9f70e181bf171d421db4e30598e74b28c285a2a9c22ccf57242eb5`) was used and remains unverified. Scores measure disagreement, not clinical accuracy. ASR-only one-hour extrapolation is 10.1 minutes; no one-hour recording was available, so total pipeline, review and Affan delivery under 15 minutes are unverified. The CUDA 13/5080 profile has not been run on its target host. No clinician reviewed the 35 extracted items. Keep this PBI OPEN; this branch completes only the single-recording selection experiment.
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

