# PBI-004: Transcribe real audio on the laptop GPU

Parent: `hackathon/pbis/README.md`  
Status: OPEN  
Priority: P0 — today  
Owner: You  
Recommended model: **GPT-6 Sol**  
Recommended reasoning: **High**  
Depends on: PBI-002, PBI-003

## Outcome

Produce durable timed original-language transcripts from files, preserving RO/RU/EN and source audio.

## Source of truth

`hackathon/03-models-and-performance.md`; existing `src-tauri/src/asr.rs`, `audio_capture.rs` for known limitations. Current user instructions and the PBI index override older H-task allocations. Inspect the branch before editing; proposed paths may have been created by another task.

## Target files

Create: `services/meeting/adapters/asr.py`, `tests/test_asr_contract.py`; update proposed `pipeline.py`, `media.py`.

## Intended changes

- Load pinned CTranslate2 model from local path, run faster-whisper with configurable precision/beam/batch and transcription task. Consume the segments iterator fully before marking done.
- Preserve source sample/time mapping across VAD windows, overlap and resampling. Request word timings; use honest segment fallback where unavailable. Do not force one meeting language.
- Bound memory and queue processing; source remains on disk. Persist raw output/model parameters before display formatting. Emit stage progress using actual processed offsets.
- Release GPU process/model before LLM stage. Record duration, real wall time and peak memory; batch tuning requires paired quality samples.

## Acceptance

- A permitted real sample produces original Romanian/Cyrillic/English text and ordered source-bounded timestamps; errors are visible.
- Silence, overlap and code-switch behavior are evaluated; no cloud call or destructive source rewrite.

## Targeted validation

Real short multilingual recording plus silence/no-speech and boundary-negation cases; timestamp bounds; corrupt input; OOM/config failure; verify complete iterator consumption.

## Exclude

Second recognizer, diarization, guessing medical corrections, production old live-caption queue reuse.

## Completion record

- Commit / changed files: pending
- Commands and observed behavior: pending
- Acceptance evidence / limitations: pending
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.

