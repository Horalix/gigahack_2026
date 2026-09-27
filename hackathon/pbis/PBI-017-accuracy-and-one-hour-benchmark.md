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

Create `evaluation/benchmark.py`, `evaluation/README.md`, small synthetic gold fixtures and update `hackathon/ASR_COMPARISON_RESULTS.md`; keep actual recordings/raw sensitive outputs ignored.

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
- Commands and observed behavior: `python -m pytest services/meeting/tests -q` — 56 passed after the bounded extraction and compact reconciliation update; `npm run check` — 0 errors/warnings; `npm run build` passed; `scripts/hackathon/preflight.ps1 -ProfileId laptop8` passed. Current browser workflow tests are mocked. The original 702.635-second M4A reached `ready` after compact final reconciliation: 191 segments, 20 items, all requiring human review. ASR took 138.676s; successful checkpoint LLM extraction took 95.68s. Their 234.4s stage sum projects to 20.0 min/hour. A 6,000-byte batch experiment was valid but took 121.21s and produced 31 items; production remains 3,200 bytes. On the same 702.549-second WAV/reference, Whisper FP16 beam 1 took 129.2s and scored 59.7% WER / 39.3% CER, versus beam 5 at 118.6s / 51.8% / 33.3%; keep beam 5. Omni CTC scored 72.6% / 52.6%; Omni LLM forced `ron_Latn` scored 66.9% / 46.4%.
- Follow-up tuning decision: two forced-Romanian FP16/beam-5 batch-2 runs on the same WAV completed in 46.708s and 46.632s, both 51.64% WER / 35.28% CER with 4,539 MiB peak device-wide memory. Set `config/profiles/laptop8.json` to batch 2. Against the previous batch-1 sample, WER is essentially unchanged, CER is about 2 points higher, and the single recording is 2.54× faster. Combined with the earlier 95.68s LLM stage, this gives a provisional 12.2 min/hour linear stage-sum estimate; full-hour processing remains untested.
- Updated integrated batch-2 run: the 702.635s permitted Romanian M4A passed through upload/decode and the real local worker in an isolated temporary store, reaching `ready` in 123.04s (upload/decode 1.42s, ASR 44.84s, decision extraction 70.20s). Linear upload-to-ready projection: 10.5 min/hour. This is stronger evidence for the current laptop profile than combining separate ASR and LLM runs, but still not a full-hour or email-receipt test. One RAM spot check during LLM work showed 4.2 GiB available; ASR peak device-wide VRAM was 4,603 MiB and usage returned to 0 after completion.
- Acceptance evidence / limitations: the supplied share page could not be retrieved through the web tool; the saved Microsoft machine transcript (SHA-256 `49ef9ec13d9f70e181bf171d421db4e30598e74b28c285a2a9c22ccf57242eb5`) was used and remains unverified. Scores measure disagreement, not clinical accuracy. The current laptop8 batch-2 integrated run reached ready in 123.04s for 702.635s audio, a 10.5 min/hour projection; no one-hour or email-receipt run is available. The CUDA 13/5080 profile has not been run on its host, and no clinician reviewed the extracted items. Keep this PBI OPEN; this branch completes only single-recording model selection and tuning.
- Latest context check: with 4,096 LLM context / 2,048 output tokens, the actual 702.635-second Romanian M4A reached `ready` in 140.93s, with 6.75 GiB minimum free RAM and 4,694 MiB peak device-wide GPU use. This does not change the 8,192-token laptop default or qualify a one-hour run. A repeated-clip hour diagnostic failed the candidate-list context check before compacting the reconciliation prompt; it is excluded from acceptance evidence. The 15-minute target still requires a genuine one-hour recording timed upload-to-approved-file.
- Reproducible scoring: added `evaluation/benchmark.py`, a private manifest format in `evaluation/README.md`, and a synthetic gold fixture. Reports include hashes, transcript WER/CER, annotated critical-term counts, action precision/recall, owner/date accuracy and optional stage RTF; raw transcript text and filesystem paths are omitted. `python -m pytest services/meeting/tests evaluation -q` passes 61 tests. The evaluator is validated only on synthetic fixtures; human annotation and one-hour integration acceptance remain open.
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

