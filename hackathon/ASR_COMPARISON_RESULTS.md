# ASR comparison — Romanian Medpark sample

**Recommendation: keep Whisper large-v3 as the app ASR. Do not switch to OmniASR for the demo.** On the same saved 11m43s WAV and Microsoft-generated reference, Romanian-forced Whisper had the lowest text disagreement. Omni CTC was much faster but substantially worse; Omni LLM was also worse and missed the one-hour speed target.

## Results

| Candidate | Romanian control | WER vs saved reference | CER | Wall time for 702.5s audio | ASR-only extrapolation to 1h | Peak GPU used observed |
|---|---|---:|---:|---:|---:|---:|
| Whisper large-v3, historical app run | Forced `ro`; `int8_float16`, beam 5, whole-file, word timestamps | **47.9%** (873/1,824 word edits) | **29.9%** | **74.7s** | **6.4 min** | 3,293 MiB |
| Whisper large-v3, current app `laptop8` | Forced `ro`; `float16`, beam 5, batch 1, whole-file, word timestamps | **51.8%** (945/1,824) | **33.3%** (2,414/7,256 chars) | **118.6s** | **10.1 min** | 5,275 MiB |
| OmniASR CTC 1B v2, WSL | No language conditioning supported; 24 sequential 30s windows, BF16 | 72.6% (1,325/1,824) | 52.6% | 15.2s | 1.3 min | 2,989 MiB |
| OmniASR LLM 1B v2, WSL | Forced `ron_Latn`; 24 sequential 30s windows, BF16 | 66.9% (1,221/1,824) | 46.4% | 276.0s | 23.6 min | 5,603 MiB |

The current app Whisper score is 15.1 percentage points lower WER than the language-conditioned Omni LLM, and 20.8 points lower than Omni CTC. The historical `int8_float16` Whisper run scored 3.9 points better than the current FP16 profile, but that precision failed a real 60-second inference smoke on the pinned local CUDA stack; the current profile therefore uses FP16. The controlled WSL Whisper-window run was stopped after more than 12 minutes without completing; its timing is not reported as a completed run. Timings are descriptive, not a strict speed ranking: Whisper ran natively on Windows; Omni ran under WSL, and windowing differed. All completed candidates used the same audio and saved Romanian reference with the same scoring normalizer.

## How to read this

- These are **WER/CER disagreement scores against an unverified Microsoft machine transcript**, not measured clinical accuracy. The provided share page could not be independently retrieved during this run; the saved transcript was used as supplied. A fluent Romanian reviewer should verify clinical terms, negation, doses, names, and code-switches before making accuracy claims.
- The current app `laptop8` upload-to-worker run completed ASR and local decision extraction on the 11m42.5s sample: 166 transcript segments and 35 evidence-linked items requiring human review. Current ASR wall time was 118.6s. Its one-hour ASR-only extrapolation is 10.1 minutes, leaving about 4.9 minutes for decode, decision extraction, review, and artifact creation. The complete app workflow has not been timed on a one-hour recording, so the 15-minute end-to-end target is unverified.
- A later run on the original 702.635s M4A used forced-Romanian FP16 and produced 191 segments in 138.676s. Its first LLM pass failed because the verbose final response exceeded the output limit. After switching reconciliation to select source-validated event indexes (the service reconstructs exact text/evidence), a checkpoint retry completed in 95.68s with 20 decisions, all requiring human review. The measured ASR + successful LLM stage sum is **234.4s**, a linear **20.0 min/hour projection**. This is not a full cold upload-to-approved-file timing and does not meet the 15-minute/hour target. A separate 6,000-byte experimental batch took 121.21s and returned 31 review items; it did not improve speed, so production remains at 3,200 bytes.
- An automated browser journey then uploaded the actual M4A through the app, recovered from an unsupported LLM evidence candidate using the saved checkpoint, displayed 182 transcript passages and 18 review-required decisions, and generated/downloaded the HTML file after exercising the approval checkbox. The checkbox was automated; this does not represent clinician review or alter the ASR comparison scores.
- Romanian forcing matters: the historical Auto run selected Russian and scored 81.8% WER under this normalizer, while forcing Romanian in the app gave 47.9%. Keep the explicit language selector and select Romanian when known.
- Omni CTC has no forced-language input in the tested standard pipeline; Omni LLM accepts the Romanian code but has poor measured agreement and higher VRAM. Neither is a drop-in app backend today: the app adapter supports faster-whisper and word-level timestamps; Omni returned untimed window text.
- VRAM is the peak device-wide `nvidia-smi` reading, not process-attributed memory. The current Whisper value includes other processes; it is not attributable to Notavra alone. Omni LLM completed on the 8 GB laptop GPU, but its 5,603 MiB is also device-wide. No RTX 5080/16 GB run was made because that host was not accessible from this checkout. The 16 GB profile and CUDA 13 runtime remain unverified.
- First Omni LLM setup also downloaded about 8.49 GB of weights. Its first 30s smoke took 807.8s wall including the cache miss; the full cached run reported 132.6s load plus 136.0s inference. Do not include model download in the advertised processing time; provision and verify model files before offline demo.

## Reproduction record

- Input: mono 16 kHz PCM16 WAV, 702.549s; SHA-256 `6c8bdc04676470b02b20f77c5c5a0d2dc3ed7b213fdafffc9b5e44a2d9a81b62`.
- Reference: saved transcript, SHA-256 `49ef9ec13d9f70e181bf171d421db4e30598e74b28c285a2a9c22ccf57242eb5`; 1,824 normalized reference words and 7,256 characters.
- Normalization: Unicode NFKC, case-fold; preserve Unicode letters, marks and numbers; punctuation/symbols become spaces; collapse whitespace. No medical correction or transliteration.
- Laptop: NVIDIA RTX 3070 Ti Mobile, 8 GB VRAM, 24 GB system RAM. Whisper used the app's configured local model and adapter. Omni ran in WSL with Python 3.12, PyTorch 2.8.0+cu128, fairseq2 0.6 and BF16. The private full hypotheses and run JSON remain outside Git under `%LOCALAPPDATA%\SecureMOM\evaluation` and `/home/neuma/.cache/notavra-pbi025`.
- No transcript text is included in this report because the source audio is clinical challenge data.

## Decision and next work

Use Whisper large-v3 for the demo, with Romanian explicitly selected for Romanian-only input. The current verified laptop setting is FP16, batch 1, beam 5; do not use the historical `int8_float16` setting until it passes inference on the pinned CUDA runtime. Keep Auto available for unknown language, but make Romanian the contest default. Do not switch to either tested OmniASR model: both had substantially higher disagreement on this sample, and the Omni LLM also misses the ASR speed budget. Revisit only with Romanian medical adaptation and the same frozen human-reviewed test set.

Before claiming medical transcription quality, have a fluent reviewer annotate a consented reference and critical medical terms. Before claiming the 15-minute end-to-end gate, time the complete one-hour workflow with LLM extraction and artifact delivery. Repeat the benchmark on the 16 GB workstation when available. This report is a single-recording model-selection result, not a production validation.
