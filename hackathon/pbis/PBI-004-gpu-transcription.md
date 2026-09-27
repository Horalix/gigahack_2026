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

- Commit / changed files: commit `820f1a9` on `noomy/freepalestine`; `services/meeting/adapters/asr.py`, checkpoint integration in `pipeline.py`, aligned API records/schema and `tests/test_asr_contract.py`. PBI stays OPEN for accuracy qualification.
- Commands and observed behavior: complete iterator consumption, source-bounded timing, words, local-only model loading, CUDA compute-type checks, progress and model errors are implemented. The pinned large-v3 ran on the RTX 3070 Ti with `int8_float16`, beam 5, batch 1 and word timestamps. The permitted 702.5-second Medpark WAV produced 193 segments and 1,207 word spans in 101.5 seconds of ASR work (108.3 seconds including startup/checksum); observed total GPU usage peaked at 3,293 MiB. Controlled English and negation sentences were transcribed exactly; two seconds of silence returned no segments. The 17 focused service/registry tests pass.
- Acceptance evidence / limitations: Medpark output contains Cyrillic and Romanian script, but no clinician-reviewed reference establishes medical accuracy. A controlled two-voice overlap lost the second voice. In a composite containing identical Medpark opening PCM followed by a later Romanian section, changing only the English suffix changed the opening output from Cyrillic to Romanian Latin; shorter 10/15-second windows restored Cyrillic but also changed wording, so no quality improvement is claimed. The user confirmed the first 25 seconds are Romanian; the Cyrillic rendition is wrong. Testing the full first 120 seconds with and without VAD at 30/15-second windows still rendered the start in Cyrillic, so changing those switches alone does not fix it. A public [Google FLEURS-R](https://huggingface.co/datasets/google/fleurs-r) CC-BY-4.0 RO/RU plus [whisper.cpp JFK](https://github.com/ggml-org/whisper.cpp/blob/master/samples/jfk.wav) English composite showed that the default VAD-compressed 30-second pass misrendered the first Russian clip and dropped the English ending; pause-bounded decode clips recovered the three scripts. A prototype combining VAD clips into language-score windows chose Romanian for the Medpark opening, but took 49.7 seconds for 120 seconds of audio on this laptop and still needs language-boundary and one-hour performance work. Public evaluation audio/reference text stayed outside Git. The Microsoft transcript comparison is now recorded below. Keep this PBI OPEN for a human-verified reference, code-switch/overlap review and a quality-safe window choice. ASR-only extrapolation is not the one-hour end-to-end gate.
- Provisional comparison added 2026-09-26: the user-provided [Microsoft AI share transcript](https://playground.microsoft.ai/share/c7b9dc9c-d2af-4535-8d9e-e88f0b54e446) was extracted locally and compared with `C:\Users\neuma\AppData\Local\SecureMOM\evaluation\medpark-full.large-v3.json` (702.635 seconds; duration matches the page's 11:42). After NFKC/casefold and punctuation removal, excluding timestamps, speaker labels, and UI text: 1,788 reference words; 1,212 Whisper words; 865 substitutions, 587 deletions, 11 insertions; WER **81.8%** (18.2% token agreement). Whole-file Whisper language metadata was `ru`, while the opening reference is Romanian and the user previously confirmed the first 25 seconds are Romanian. This quantifies severe disagreement, not definitive accuracy: the Microsoft transcript is also machine-generated, contains visibly uncertain medical words and automatic language labels, and has no independent human verification. The raw reference stays outside Git at `%LOCALAPPDATA%\SecureMOM\evaluation\medpark-microsoft-reference.txt`; hashes and scoring metadata are in `medpark-reference-comparison.json` beside it. Human-verified reference and targeted code-switch/overlap review are still required; keep this PBI OPEN.
- Current app-profile rerun (27 September): forced Romanian, faster-whisper/CTranslate2 pinned version, FP16, beam 5, batch 1, full iterator and word timestamps. On the 702.549s WAV it produced 166 segments in **118.6s**, with **51.8% WER** (945/1,824) and **33.3% CER** (2,414/7,256) against the same saved Microsoft reference. Device-wide peak was 5,275 MiB while other repository processes were running, so this is not process-attributed. Full app transcript stays outside Git. This profile runs reliably; the historical `int8_float16` profile scored lower disagreement but failed the current pinned stack's short GPU inference check. PBI remains OPEN for a human-verified reference and code-switch/overlap assessment.
- Move to `hackathon/pbis/completed/` only after acceptance passes; update index links and this record. Do not mark complete based on mocked success alone.
