# PBI-019: Add anonymous speaker turns

Parent: `hackathon/pbis/README.md`  
Status: OPEN  
Priority: P1 — after review feature is qualified  
Owner: You  
Recommended model: **GPT-6 Sol**  
Recommended reasoning: **High**  
Depends on: PBI-004, PBI-017

## Outcome

Attach anonymous speaker clusters to transcript intervals using an offline diarization model.

## Source of truth

`hackathon/04-speakers.md`; existing `src-tauri/src/diarization.rs` heuristic is unsuitable. Current user instructions and the PBI index override older H-task allocations. Inspect the branch before editing; proposed paths may have been created by another task.

## Target files

Create `services/meeting/speakers.py`, local diarization manifest entry and `tests/test_speaker_mapping.py`.

## Intended changes

- Qualify a pinned local diarization pipeline (initial candidate Community-1), acquire all gated assets during setup, and schedule sequentially within GPU budget.
- Map turn overlap to timed segments/words; retain ambiguity and unknown labels. Optional speaker count/range guides clustering without forced naming.
- Persist stable meeting-local cluster IDs; keep speaker distinct from named action owner. Save model/config and mapping revision.

## Acceptance

- Two/three-person held-out clips produce useful turn labels, overlaps visible, and the hour budget still passes if diarization is enabled.

## Targeted validation

Single speaker, unseen extra speaker, overlap, mid-turn language switch, source-time mapping and real runtime/memory.

## Exclude

Employee recognition, identity confidence percentages, replacing the entire transcription stack.

## Completion record

- Commit / changed files: pending
- Commands and observed behavior: pending
- Acceptance evidence / limitations: pending
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

