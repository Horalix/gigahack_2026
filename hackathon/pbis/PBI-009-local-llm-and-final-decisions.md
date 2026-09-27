# PBI-009: Extract evidence-backed final decisions locally

Parent: `hackathon/pbis/README.md`  
Status: OPEN  
Priority: P0 — today  
Owner: You  
Recommended model: **GPT-6 Sol**  
Recommended reasoning: **High**  
Depends on: PBI-001 and PBI-003 for fixture/model implementation; PBI-004 for end-to-end audio acceptance

## Outcome

Turn the original transcript into accurate structured minutes content with owners, dates and explicit uncertainty.

## Source of truth

`hackathon/02-target-architecture.md`, `03-models-and-performance.md`, `08-judging-strategy.md`. Current user instructions and the PBI index override older H-task allocations. Inspect the branch before editing; proposed paths may have been created by another task.

## Target files

Create `services/meeting/adapters/llm.py`, `decisions.py`, `tests/test_decisions.py`; update pipeline/contracts only through agreed schema version.

## Intended changes

- Run Qwen3.5-4B Q4_K_M locally with pinned runtime/template and bounded schema output. Serialize transcript as untrusted data; no tools/network recipients or generated authorization.
- Extract compact candidates from bounded timed chunks, retaining evidence references per task/owner/date. Preserve original languages; render requested locale only after facts are accepted.
- Reconcile across the full meeting: distinguish proposal/confirmation/amendment/rejection/cancellation. A later tentative mention cannot replace a confirmed commitment. Keep owner/date unknown where absent.
- Validate shape, source quotes/revisions and semantic commitments; resolve dates only with meeting timezone/context and retain original expression. Mark ambiguous clinical quantities unresolved; do not infer plausible doses.
- Separate unsupported/uncertain items from publishable facts. Save model/config/revision; malformed/truncated responses fail/retry within a bound, never partially publish.

## Acceptance

- Actual local extraction passes held-out gold-text cases and a new audio pipeline. Correct final owner/date survives a late amendment; rejected purchase does not become action.

## Targeted validation

Gold fixtures for six decision operations, first-person unknown owner, missing date, relative date, mixed-language negation, ambiguous number, prompt injection, late amendment; actual model outputs manually reviewed.

## Exclude

Automatic diagnosis/orders, second LLM verifier, broad agent framework, optimizing beyond measured bottlenecks.

## Implementation progress (26 September 2026)

- Added an offline, loopback-only llama.cpp server adapter. It loads the model once per job, requires a per-process API key, disables Qwen thinking output, uses JSON Schema constrained output, and does not log prompts or responses.
- Added bounded transcript batching, candidate extraction followed by cross-batch reconciliation, source quote/revision validation, relative-date preservation, and fail-closed persistence. Unsupported owner/date claims are left unknown; every result requires human review.
- Integrated decisions into the existing worker and authenticated meeting response; decision records are persisted outside the repository and exposed only for the current transcript revision after the job reaches ready.
- Updated final reconciliation to return indexes into validated candidate events. The service now assembles source evidence from those events instead of asking the model to repeat every quote in its final JSON. Invalid candidate evidence gets one bounded correction attempt; candidates that still lack valid source evidence are dropped, optional unsupported owner/date evidence is cleared, and final event indexes remain strictly validated.
- Added per-item clinician disposition in the workbench: include or exclude each suggested action before approval. The API stores reviewer identity/time and disposition history with the current decision result, rejects stale revisions, invalidates a prior approved artifact when a disposition changes, and renders only accepted actions. Approval is blocked while any item still needs review.
- 27 September real app run: the consented 702.5-second Romanian Medpark upload completed on the RTX 3070 Ti using the local CUDA LLM runtime. The job reached `ready` with 166 transcript segments and 35 evidence-linked actions/decisions. They are all explicitly flagged for human review; nobody has manually assessed their clinical or meeting accuracy.
- Synthetic local 4B smoke runs extracted two supported items with verbatim evidence. Outputs varied in whether an explicit "will call" was marked proposed or confirmed; owner attribution was over-broad, and date evidence was omitted. Validators now clear unsupported owner labels and recover only literal, recognized date expressions from cited text. A fixed generation seed is set, but semantic consistency still needs held-out testing. This is not a gold-suite pass.
- PBI remains OPEN: multilingual gold cases, late amendment/rejection behavior on the real model, prompt-injection case, and a new audio-to-decisions run still need manual qualification. One-hour combined timing is also unmeasured.

## Completion record

- Commit / changed files: `c57e289` and earlier app adapter implementation; decision schema, bounded quote retry and local CUDA runtime/profile support in `services/meeting/adapters/llm.py`, `services/meeting/decisions.py`, `services/meeting/models.py`, and profiles.
- Commands and observed behavior: `python -m pytest services/meeting/tests -q` — 52 passed; a real browser upload + local worker run produced `ready`, 182 passages and 18 review-required items after a checkpoint retry. Local Qwen ran through llama.cpp CUDA 12 on the 3070 Ti.
- Acceptance evidence / limitations: the original 702.635-second Romanian M4A completes with compact event-index reconciliation. One browser/worker run produced 182 transcript passages and 18 evidence-validated items requiring human review, then generated/downloaded the approved HTML after automated checkbox interaction. It first exposed unsupported candidate evidence; a saved-checkpoint retry succeeded after the validator was changed to drop only unsupported candidates. A separate run produced 191 segments and 20 items. The 6,000-byte batch was slower than production's 3,200-byte setting. A repeated-clip 3,600s upload-to-ready soak completed without OOM; this does not qualify semantic quality on a genuine hour-long meeting. No clinician reviewed decisions. PBI stays OPEN.
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.
