# Judging strategy: prove the advantage

The supplied screenshot confirms the PDF's weights: security/architecture 20%, linguistic accuracy 30%, output quality 30%, UX 10%, presentation 10%. External runtime API calls disqualify the submission. We do not know competing products; assume they can transcribe, summarize and email. Differentiate through observed correctness and a short complete workflow.

**Product thesis:** multilingual speech becomes the final agreed decisions, with source evidence and fast correction of uncertain terms, entirely on local hardware.

| Criterion | Baseline everyone may have | Our intended advantage | Evidence to show |
|---|---|---|---|
| Security / architecture, 20% | Local model claim | Fresh-process disconnected pipeline, immutable source/model manifests, deterministic local recipients; same application on 8/16 GB profiles | New audio reaches local Mailpit offline; local artifacts verified; actual hardware/runtime report |
| Linguistic accuracy, 30% | Generic multilingual ASR | Original mixed-script text; measured medical/name/number cases; targeted uncertainty detection and fast human correction | Held-out mixed speech, raw error counts, true/false flags, original audio replay; separate automatic and reviewed scores |
| Output quality, 30% | Fluent summary | Distinguish proposal/decision/rejection; preserve final owner/date after late amendment; link each field to evidence | Monday/Andrei changes to Wednesday/Elena; rejected purchase absent; unknown date remains unknown |
| UX, 10% | Upload then wait | Audio/video/live entry, honest progress, automatic normal delivery; find-like review only where needed | Actual hour timing, minimal-action happy path, one short correction task with keyboard and batch preview |
| Presentation, 10% | Feature tour | One coherent story backed by real output, stage timings, limitations and new wording | Short live/new-file demonstration, offline mail receipt, surprise paraphrase; labeled backup |

## Spend time in this order

1. Complete P0, including manual corrections and both input modes. Get a real hour under 15 minutes on the demo laptop.
2. Improve errors affecting decisions: names, negation, dates, numerical values and language switches. These influence both 30% categories.
3. Add the **review queue + field audio replay** as the first polished differentiator. Reuse one evidence drawer across transcript flags and action fields.
4. Add visible decision change history. Keep the existing final-state correction logic working even if fancy history UI is cut.
5. Add anonymous speaker labels/correction only if there is time. Persistent voice enrollment, second recognizer and live decision cards stay stretch.

The screenshot asks for minutes usable without manual editing and minimal intervention. Consequently, review must be an exception path, with low false alarms. A system that needs dozens of approvals to produce a short MoM has not solved that scoring problem, even if its corrected transcript is excellent.

## One connected demo

Prepare a short multilingual hospital-operations meeting with one maintenance decision, a rejected purchase, a changed owner/date and a repeated specialist term. Include uncertain numeric wording as an unresolved discussion item, not a generated medical instruction.

1. Begin with the local/offline state visible and choose a new recording or record live.
2. Show the mixed-language transcript and final action card; point to the final correction that establishes owner/date.
3. **If the run actually produces a useful flag**, navigate to it, replay the source and approve/edit a correction. If recognition was correct, say so; demonstrate manual edit/undo or use a clearly labeled independent review fixture. Never manufacture an ASR failure to sell the feature.
4. Show revised minutes and the correct local email receipt. An unresolved clinical value is explicitly withheld/marked unresolved.
5. Present the measured one-hour benchmark separately; the short demo itself does not prove one-hour speed.

Adapt this sequence to the organizer's time limit. Have an automatically delivered unambiguous example so the jury sees the minimal-intervention path, as well as the short exception-review interaction. Avoid spending the pitch touring settings/model names.

## Score evidence sheet owned by CEO

For each claim, record a link to input fixture/hash, output, commit/model config, hardware, date, result and limitation. Collect these before making slides:

- External calls: actual test boundary and disconnected run; remote development is separately described.
- Language: sample count and languages, reviewer competence, raw word/entity errors, mixed-boundary failures.
- Review: number of true/false flags, correct/incorrect suggestions, manual interventions/time, residual errors.
- Decisions: expected/extracted actions, missing/extra actions, owner/deadline errors, amendment/rejection tests.
- Performance: cold/warm and upload/live boundaries, stage timings, peak VRAM/RAM on each tested GPU.
- UX: new operator completion and failure recovery, both automatic and exception paths.

No prediction of 100/100 and no claim of clinical validation. If a feature does not improve accuracy, completion time, review effort, or demonstrated trust, drop it before sacrificing a required gate. The strongest pitch is one where every important claim can be inspected.
