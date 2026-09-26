# PBI-009: Extract evidence-backed final decisions locally

Parent: `hackathon/pbis/README.md`  
Status: OPEN  
Priority: P0 — today  
Owner: You  
Recommended model: **GPT-6 Sol**  
Recommended reasoning: **High**  
Depends on: PBI-001, PBI-003, PBI-004

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

## Completion record

- Commit / changed files: pending
- Commands and observed behavior: pending
- Acceptance evidence / limitations: pending
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

