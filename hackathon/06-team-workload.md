# Two developers + CEO: 48-hour execution

**Assign names at kickoff.** Dev A owns speech/intelligence/core state. Dev B owns the product UI, rendering, delivery, and launch. CEO owns test material, human evaluation, organizer clarification, pitch, and demo operations. The clock below is elapsed time; plan sleep and staggered breaks, not 48 continuous working hours per person.

## Ownership boundaries

| Person | Owns | First action |
|---|---|---|
| Dev A | `services/meeting/` core API/storage/jobs/adapters/decisions/models; model configs; contracts; metrics | Inventory GPU and get one local audio file transcribed |
| Dev B | `src/` meeting UI/client; `rendering.py`, `delivery.py`, templates; recipient config; launch scripts | Build upload/progress/result flow against shared fixture; run local Mailpit |
| CEO | `evaluation/` reference data/report with A; demo/presentation; checklist tracking | Confirm brief, collect permitted audio, define expected decisions with language reviewers |

Dev A owns dependencies/schema changes in the Python service. Dev B requests additions and owns mail/render module internals. Agree the outbox/storage interface early; Dev B must not create a competing SQLite schema. Both approve shared contract changes. Frontend dependencies and scripts belong to B; model manifests/profile settings belong to A.

## Schedule

| Elapsed | Dev A | Dev B | CEO | Integration outcome |
|---|---|---|---|---|
| H0–H2 | GPU/runtime inventory; model acquisition; contract + fixture | Browser API boundary; upload UI skeleton; Mailpit | Organizer questions, evaluation audio permissions, shortlist of human reviewers | H01 contract frozen; assets downloading |
| H2–H6 | H02 + first H03 ASR path | H04 against fixture; H06 renderer/mail with synthetic approved result | Write gold actions for clips; collect mixed-language test speech | Real audio produces transcript; UI/mail plumbing works |
| H6–H12 | H05 local extraction + final state; connect pipeline | Wire real API; automatic routing/delivery; clear errors | Check actual output, log errors by consequence; draft pitch story | New short recording -> minutes -> Mailpit |
| H12–H20 | Connect incremental ASR to saved live windows; fix language/decision failures | H12 live recording/chunk persistence; offline launch/preflight; retry UI | Run upload/video/live acceptance; annotate held-out samples; draft slides | Both required input modes work; reproducible launch |
| H20–H24 | One-hour upload run and bottleneck analysis; compare remote 16 GB host on permitted fixtures | Test long live capture and video decode; fix recovery; package working version | Time both paths, capture results, verify late correction | Upload benchmark + live finalization measurement + cold-start evidence |
| H24–H32 | Close P0 accuracy/time gates; H16 edit revisions and dependent rebuild | H16 manual edit/batch preview/undo; close P0 UI/delivery gates | Test new operator correction and automatic flows; refine benchmark slide | All mandatory gates green or explicit no-go on extras |
| H32–H40 | If green: H17 bounded flags, then H10 history; H11 only if time remains | If green: H17 find-like review + shared replay drawer, then H10 history | Measure false suggestions/review effort; surprise paraphrase; demo rehearsal | One coherent differentiator; release candidate frozen |
| H40–H46 | Fix regressions only; verify model/config freeze | Bundle/launch checks; demo screen readability; backup | Practice timed pitch/Q&A; verify submission requirements | Three complete rehearsals, one disconnected cold start |
| H46–H48 | Technical support and submission verification | Technical support and submission verification | Lead submission, presentation, demo | Reproducible artifact and honest claims |

Reserve rest explicitly across H12–H32 and coordinate handoffs. If effective engineering capacity shrinks, drop P1/P2 first. If A's inference lane blocks the first complete flow, B finishes minimal UI/mail and helps integration; CEO continues independent labeling/presentation work.

## First tickets to hand off

**Dev A — H01/H02/H03:** read [architecture/contracts](02-target-architecture.md) and [profiles](03-models-and-performance.md). Deliver a bounded local upload/job API producing durable timed multilingual transcript JSON. Freeze fixture and API errors with B. Validate real audio and missing-model failure; do not start enrollment or multi-model retries.

**Dev B — H01/H04/H06:** read [current app](01-current-app.md) and [contracts](02-target-architecture.md). Add browser-safe meeting flow in the existing Svelte project. Use one clearly labeled development fixture until A's service works. Implement deterministic minutes and local configured SMTP delivery; test real receipt and failure/retry. Mock UI success is not completion.

**Dev B with A — H12, required after first integrated upload flow:** B owns microphone UI, sequenced chunk persistence and Stop/seal handling; A owns incremental ASR and final reconciliation. Agree recording state and timestamp mapping before parallel edits. This is P0, not a stretch feature. If capacity is tight, remove all P1/P2 work before cutting either required input mode.

**Dev A+B — H16 then H17:** read [transcript review](07-transcript-review.md). A owns versioned spans/edits, LLM candidates and downstream invalidation; B owns manual editing, find-like navigation, select/apply/undo and one reusable audio drawer. CEO labels true/false flags and times review. H17 gets an H32–H36 timebox after P0; keep manual editing and cut unreliable suggestions if the experiment fails.

**CEO — evaluation/pitch:** read [start here](README.md), [speakers](04-speakers.md), and [acceptance](05-build-plan.md). Prepare reference decisions, find fluent reviewers, run the checklist with developer guidance, and record concrete failures. Do not tune models or merge source changes. Aim for a usable slide outline by H20 and first spoken rehearsal by H28.

## Coordination rules

- Separate task branches/worktrees; small integration commits. No simultaneous edits to shared schema, lockfiles, or app startup without coordination.
- At H2 freeze representative meeting/transcript/action/error JSON; keep it versioned so each AI has the same contract.
- Integrate at least every four elapsed hours. No separate frontend/backend “finished” claims before the whole new-audio flow runs.
- Each handoff includes commit, task ID, changed paths, commands actually run, current artifact location, and next failing gate.
- Track status using **Done / Changed / Next / Risks**. Every claimed acceptance result links to a log/output; planning checkboxes stay open until measured.
- No optional work while a P0 gate is red. Each optional experiment has a time cap and a clear removal path.
- Before changing a contract, tell the other owner; after changing it, update fixtures and this pack's affected contract description.

## CEO checklist and pitch

Organizer clarification, early: n8n implementation expectation; required submission format/deadline; demo length; whether audio may be bundled/shared; any supplied distribution-list conventions. These questions need not block the simple local implementation.

Suggested five-slide outline:

1. Problem: confidential hospital meetings mix Romanian, Russian, and English; decisions change during discussion.
2. Product: upload/record -> original transcript -> decisions/owners/deadlines -> internal email.
3. Technical advantage: final confirmed commitment survives corrections; source evidence is inspectable; targeted term review fixes consequential errors with few actions. Show only features actually qualified.
4. Proof: actual hardware, dataset size, accuracy/error counts, one-hour timing, offline run. Mark untested 16 GB deployment as untested.
5. Demo + next steps: local mail receipt, limitations, hospital pilot requirements.

Rehearse against the organizer's actual time limit. Use a short meeting with a rejected proposal, owner/date correction, mixed-language term, and unresolved number. Prepare a new paraphrase so the result demonstrates generalization beyond memorized wording. Have a labeled prerecorded fallback and known-good release. A polished failure explanation is preferable to fake output.

Likely questions: “What happens with a missing owner?”, “How do you handle Russian mid-sentence?”, “Does it work without internet after restart?”, “Which hardware produced this timing?”, “Was that speaker identified or manually named?”, “Can the audio trick it into sending mail elsewhere?” Each answer should point to a tested behavior or an explicit limitation.
