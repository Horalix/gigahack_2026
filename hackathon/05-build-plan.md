# Prioritized build and acceptance plan

**Status at handoff: every task below is OPEN.** Existing captions are useful infrastructure; they do not complete any end-to-end Secure MOM gate. Hours are planning targets within 48 elapsed hours, not estimates of guaranteed completion.

## Priority rule

- **P0 — required:** audio/video upload and live microphone recording with provisional transcript, complete offline minutes/email workflow, multilingual evidence, usable UI, measured target-hardware performance. Both input modes are required by the team even though the brief permits either.
- **P1 — differentiators:** only after every P0 gate passes. Best order: AI transcript flags + fast review/replay, decision change-history polish, then speaker labels/correction. See [review spec](07-transcript-review.md) and [judging strategy](08-judging-strategy.md).
- **P2 — stretch:** only after P1 is stable. Enrollment, known-voice suggestions, second ASR, live decision previews.

If a P0 gate regresses, stop optional work and repair it. A reliable simple solution has priority over the research dossier's complete architecture.

## P0 task board

| ID / owner | Deliverable and target paths | Depends on | Acceptance |
|---|---|---|---|
| H01 / A+B | Hardware inventory, contracts and one shared JSON fixture; `contracts/`, `config/` | — | Both developers use identical IDs/fields/errors; actual GPU/backend known |
| H02 / A | Local service, meeting DB, audio/video upload and extraction, durable assets/jobs; `services/meeting/{api,storage,jobs}.py` | H01 | Audio and video yield correct speech track; uploads survive worker restart; malformed/no-audio input fails clearly |
| H03 / A | ASR adapter, local model registry/profile resolver; `adapters/asr.py`, `models.py`, manifest | H02 | Real RO/RU/EN audio produces timed original text; no runtime download; model switch changes next job only |
| H04 / B | Browser meeting UI and HTTP client; `src/routes/meetings/`, `src/lib/api/meetings.ts` | H01; integrates H02 | Upload, type/recipient group, progress, transcript, result and errors work outside Tauri |
| H05 / A | Local LLM extraction, evidence validation, final action reconciliation; `adapters/llm.py`, `decisions.py` | H03; develop first with gold text | Structured actions with owners/dates/nulls; rejected proposal omitted; late confirmed amendment replaces earlier value |
| H06 / B | Deterministic minutes and local SMTP outbox; `rendering.py`, `delivery.py`, templates, recipients | H01 fixture; integrates H05 | New valid result automatically appears in Mailpit; configured type changes routing; output contains decisions/owners/deadlines |
| H16 / A+B / P0 | Manual transcript edits, selected-occurrence replacement, preview/undo; `review.py`, meeting review UI/contracts | H02, H04–H06 | Unflagged text editable; source preserved; atomic versioned edits refresh affected minutes and invalidate stale unsent output |
| H12 / B with A / promoted to P0 | Live capture UI + durable chunk ingest; `capture.py`, meeting UI; A connects incremental ASR | H02–H04; integrate after first H06 flow | Start/Stop, levels, provisional transcript; audio survives ASR failure; Stop produces final minutes/email |
| H07 / B+A | Offline preparation/preflight/launch, network restrictions, packaged local assets; `scripts/hackathon/` | H02–H06 | Disconnected restart handles new audio and delivers email; missing model fails without network fallback |
| H08 / A+CEO | Short-set accuracy report and one-hour benchmark; `evaluation/` | H03–H07 | Actual 8 GB run <=900 s or gate remains open; RO/RU/EN and critical errors manually checked; measurements reproducible |
| H09 / B+CEO | Full browser-to-Mailpit rehearsal for upload and live; fix misleading states | H07–H08, H12, H16 | New operator completes both flows and correction; final mail agrees with source; configured safe list is enforced |

Suggested AI task size: implement one row or a narrowly bounded substep. Read the target contracts first. H05 deserves the deepest reasoning/review; avoid spending that effort on styling. New paths are proposed; do not duplicate an equivalent module introduced by another branch.

### P0 validation specifics

**H02:** source hash and duration preserved; retries do not create duplicate active jobs; job resumes from valid artifacts; path traversal and oversized uploads rejected.

**H12 (task ID, not hour 12):** microphone permission denial, disconnect, long recording, duplicated/missing chunks, server loss, storage failure and ASR crash tested. Audio is saved before inference; persisted duration and transcript progress are distinct. Final chunk is acknowledged before sealing. No unbounded browser/RAM buffer. Provisional text is clearly labeled; final output reconciles the whole meeting. Measure live lag and Stop-to-email independently of uploaded-file timing.

**H03:** output preserves Cyrillic, Romanian diacritics, English terms, silence, and source offsets. Short-window language locking must not erase foreign phrases. Installation/runtime versions and parameters are recorded.

**H05:** test on gold text before audio: proposal vs commitment, rejection, cancellation, owner/date change, late amendment near the end of an hour, unknown owner/date, relative dates with timezone, negation, ambiguous decimal, and spoken prompt injection. Exact quote matching proves reference validity, not the decision's meaning; audit semantics manually too.

**H06:** selected/suggested meeting type is metadata; recipients come only from configured group IDs and policy. Never send to an address from audio. SMTP outage shows a retryable delivery failure while preserving minutes; ambiguous acceptance is visible. Plain text + styled HTML is sufficient initially; PDF is optional unless organizer clarifies otherwise.

**H07:** all frontend assets local, no external fonts/CDNs, no public model IDs that auto-download at runtime, no external mail relay. Verify host and any container boundaries. A disconnected laptop proves no successful WAN exchange during that run; log blocked attempts separately and do not claim a comprehensive security audit.

**H16:** follow [review contract](07-transcript-review.md). Test Unicode offsets, stale revisions, selected-occurrence scope, atomic batch apply, undo and edits racing with delivery. Keep review optional on the unambiguous automatic path; edited or withheld fields cannot leak into a stale MoM.

## P1 / P2 board

| ID / priority / owner | Addition | Done when |
|---|---|---|
| H17 / P1 / A+B | Bounded AI term/error flags + find-like keyboard review + accept selected/all eligible | Exact spans/reasons, alternatives or no candidate, replay, keep/defer, before/after batch preview; measured false flags and reviewer effort |
| H10 / P1 / A+B | Decision event ledger + replay drawer | Final owner/date links to exact original clip; proposed and superseded values stay auditable |
| H11 / P1 / A+B | Diarization + participant/turn correction | Anonymous turns, unknown identity, manual mapping, affected owner revalidation all work |
| H13 / P2 / A+B | Optional enrollment and saved participant suggestions | Known/unknown held-out tests pass chosen thresholds; deletion and correction work |
| H14 / P2 / A | Selective second ASR on risky spans | Paired benchmark shows benefit on names/numbers/switches within time budget |
| H15 / P2 / B | Live decision previews, nicer PDF, proof panel | Clearly provisional, offline, does not regress required path or timings |

Do not build EHR integration, clinical orders, custom hardware, a graph database, a broad agent with tools, or a large workflow platform for its own sake. If n8n is explicitly required by organizers, add a thin local routing/mail workflow to H06; do not transfer inference/state ownership into an opaque workflow.

## Evaluation: collect evidence we can defend

Start with permitted organizer recordings plus short synthetic meeting content spoken by consenting people. CEO coordinates Romanian/Russian reviewers where possible; without fluent reference checking, mark those results unverified.

| Set | Purpose |
|---|---|
| Gold text with expected actions | Isolate extraction/decision failures from ASR |
| Short human clips: RO, RU, EN, genuine mixed sentences | Select settings; inspect names, terminology, numbers, negation |
| Held-out short meeting/paraphrase | Detect overfitting to demo wording |
| One uninterrupted 60-minute meeting, with late changes | Timing, memory, completion and global reconciliation |

Do not build the hour test by repeating one English clip. Keep tuning and held-out meetings separate. Use the same permitted roster/glossary and input conditions in baseline and final comparisons.

Record: input duration/hash, model artifact hashes, runtime/profile, hardware/driver/RAM, stage seconds, total seconds, peak VRAM/RSS, output count, failed/retried stages, WER by language/mixed condition, critical term/name/number errors, action precision/recall, owner/deadline correctness, unresolved count. If time only permits manual counts, report the denominator and method honestly. No invented confidence percentages.

If H17 is enabled, separately report flag precision/recall, suggestion correctness, wrong changes proposed to correct speech, and review time/interventions. Keep raw ASR, machine-only minutes, and human-reviewed results distinct. A long approval queue can lower UX/output quality scores; disable unhelpful flags rather than counting them as a feature win.

Baseline = same ASR + simple structured extraction. Compare improvements on the same recordings. Proposed quantitative quality cutoffs must be chosen with the team/reviewer; until set and met, publish actual errors instead of saying “clinically accurate.”

## Stop rules

| Time | Required state | If behind |
|---|---|---|
| H6 | New short audio produces transcript in the local service | Stop model tournament; use working multilingual baseline |
| H12 | New short audio reaches minutes and Mailpit | Freeze UI extras, use simplest valid HTML/text output, join integration work |
| H24 | First offline rehearsal + full-hour measurement | Fix largest correctness/time failure; no optional features |
| H32 | P0 acceptance complete on demo laptop | Continue P0 only if any gate remains open |
| H40 | Release candidate frozen | Bug fixes and rehearsals only |
| H46 | Disconnected fresh-process rehearsal succeeds | Use last known-good release; clearly disclose any missing gate |

## Demo and release checklist

- [ ] P0 H01–H09 verified; actual 8 GB hardware/config recorded.
- [ ] P0 H12 live mode verified; audio and video upload formats tested, including no-audio video errors.
- [ ] P0 H16 correction/undo rebuilds consistent minutes; optional H17 demonstrates useful flags without excessive review effort.
- [ ] One-hour upload-to-email <=900 s measured; cold/warm boundaries explicit.
- [ ] One-hour live recording preserves audio; ASR lag and Stop-to-email measured separately, finalization <=900 s.
- [ ] Offline fresh-process run with a new recording; models already installed.
- [ ] Three languages and genuine switching checked by capable reviewers.
- [ ] Proposal Monday/Andrei becomes confirmed Wednesday/Elena; rejected purchase stays absent.
- [ ] Uncertain number remains unresolved; no invented owner/date.
- [ ] Minutes appear in local Mailpit; type-to-list routing visible.
- [ ] UI states, failures, retry, and optional review understandable.
- [ ] No real patient identifiers/voice templates/secrets committed or exposed in screenshots.
- [ ] Lockfiles, model hashes/licenses, launch instructions, benchmark and known limits bundled.
- [ ] CEO rehearsed timed pitch; backup recording is labeled as prerecorded, never presented as live.

Winning thesis to demonstrate: **the system preserves the final commitment through multilingual corrections, gives evidence for its output, and completes delivery without the internet**. Winning cannot be guaranteed; measured correctness carries more scoring weight than optional features.
