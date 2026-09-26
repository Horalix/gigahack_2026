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

- Commit / changed files: uncommitted on `noomy/freepalestine`; `services/meeting/adapters/asr.py`, checkpoint integration in `pipeline.py`, aligned API records/schema and `tests/test_asr_contract.py`. PBI stays OPEN.
- Commands and observed behavior: complete iterator consumption, source-bounded timing, words, local-only model loading, CUDA compute-type checks, progress and model errors are implemented. The pinned large-v3 ran on the RTX 3070 Ti with `int8_float16`, beam 5, batch 1 and word timestamps. The permitted 702.5-second Medpark WAV produced 193 segments and 1,207 word spans in 101.5 seconds of ASR work (108.3 seconds including startup/checksum); observed total GPU usage peaked at 3,293 MiB. Controlled English and negation sentences were transcribed exactly; two seconds of silence returned no segments. The 17 focused service/registry tests pass.
- Acceptance evidence / limitations: Medpark output contains Cyrillic and Romanian script, but no reference transcript/WER or clinician review establishes medical accuracy. A controlled two-voice overlap lost the second voice. In a composite containing identical Medpark opening PCM followed by a later Romanian section, changing only the English suffix changed the opening output from Cyrillic to Romanian Latin; shorter 10/15-second windows restored Cyrillic but also changed wording, so no quality improvement is claimed. The user confirmed the first 25 seconds are Romanian; the Cyrillic rendition is wrong. Testing the full first 120 seconds with and without VAD at 30/15-second windows still rendered the start in Cyrillic, so changing those switches alone does not fix it. A public [Google FLEURS-R](https://huggingface.co/datasets/google/fleurs-r) CC-BY-4.0 RO/RU plus [whisper.cpp JFK](https://github.com/ggml-org/whisper.cpp/blob/master/samples/jfk.wav) English composite showed that the default VAD-compressed 30-second pass misrendered the first Russian clip and dropped the English ending; pause-bounded decode clips recovered the three scripts. A prototype combining VAD clips into language-score windows chose Romanian for the Medpark opening, but took 49.7 seconds for 120 seconds of audio on this laptop and still needs language-boundary and one-hour performance work. Public evaluation audio/reference text stayed outside Git. Keep this PBI OPEN for a known-language reference, code-switch/overlap review and a quality-safe window choice. ASR-only extrapolation is not the one-hour end-to-end gate.
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.
