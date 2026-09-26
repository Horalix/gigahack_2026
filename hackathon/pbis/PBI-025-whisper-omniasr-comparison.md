# PBI-025: Reproduce a fair Whisper versus OmniASR comparison

Parent: `hackathon/pbis/README.md` — Core inference / evaluation epic  
Status: OPEN — planned, no OmniASR run performed  
Priority: P0 — bounded model-selection experiment  
Owner: Core/backend developer; CEO may verify reference passages  
Recommended model: **GPT-6 Luna**  
Recommended reasoning: **High**  
Depends on: completed 003; consumes 004 baseline; supplies evidence to 017

## Human summary

Compare the same audio against the same saved reference, with frozen settings. Test Whisper with Romanian explicitly selected as well as automatic mode; a comparison only against its previously wrong language choice is insufficient. Test OmniASR CTC 1B on the laptop first, then its language-conditioned LLM 1B variant. Repeat suitable candidates on the 16 GB machine when access is available. Report speed, memory and reference disagreement separately. Keep the existing app working while doing this in isolated benchmark scripts.

The Microsoft transcript is the user's comparison source. It is machine-generated, not independently verified ground truth. Use it now; label scores accordingly. A human review improves confidence but must not block the automated comparison.

## Source of truth and inspected files

- User authorizes use of the Medpark recording and saving/reusing the shared Microsoft transcript locally: https://playground.microsoft.ai/share/c7b9dc9c-d2af-4535-8d9e-e88f0b54e446
- `services/meeting/adapters/asr.py`: current faster-whisper implementation. Hardcodes `language=None`, `multilingual=True`, VAD on, previous-text conditioning off; uses full iterator consumption and word timestamps.
- `services/meeting/models.py`, `models/manifest.json`, `config/profiles/laptop8.json`, `config/profiles/hospital16.json`: current local assets/configuration. Resolve the existing pinned Whisper directory from these; do not download another copy.
- `services/meeting/pyproject.toml`, `services/meeting/requirements.lock`: application dependency versions; do not change these for the experiment.
- `hackathon/pbis/PBI-004-gpu-transcription.md`, `PBI-017-accuracy-and-one-hour-benchmark.md`, `docs/ENGINEERING_NOTES.md`: previous evidence and known decoding warning.
- Official OmniASR [models](https://github.com/facebookresearch/omnilingual-asr), [inference guide](https://github.com/facebookresearch/omnilingual-asr/blob/main/src/omnilingual_asr/models/inference/README.md), [pipeline](https://github.com/facebookresearch/omnilingual-asr/blob/main/src/omnilingual_asr/models/inference/pipeline.py), [dependencies](https://github.com/facebookresearch/omnilingual-asr/blob/main/pyproject.toml).
- [fairseq2 installation matrix](https://github.com/facebookresearch/fairseq2#installation): exact PyTorch/CUDA ABI compatibility matters. OmniASR currently constrains fairseq2 to 0.5.2–0.6.0; do not install an incompatible latest release.

## Verified local inputs (26 September 2026)

Use these existing files. No tracked M4A/WAV/MP3 was found on the inspected merged `develop` checkout; do not assume Affan's copy exists.

| Input | Absolute location | SHA-256 |
|---|---|---|
| Full original, 58,841,746 bytes | `C:/Users/neuma/Downloads/Medpark_audio.m4a` | `86976c7d42dc6676fe3f35fe4b969a6f7fe32b7ee9d6cc63c169c14f3cde17f8` |
| Previously decoded full WAV | `C:/Users/neuma/AppData/Local/SecureMOM/evaluation/medpark-decoded.wav` | `6c8bdc04676470b02b20f77c5c5a0d2dc3ed7b213fdafffc9b5e44a2d9a81b62` |
| Saved Microsoft reference, 10,420 bytes | `C:/Users/neuma/AppData/Local/SecureMOM/evaluation/medpark-microsoft-reference.txt` | `49ef9ec13d9f70e181bf171d421db4e30598e74b28c285a2a9c22ccf57242eb5` |
| Historical Whisper output | `%LOCALAPPDATA%/SecureMOM/evaluation/medpark-full.large-v3.json` | Read/hash at execution |
| Historical scoring metadata | `%LOCALAPPDATA%/SecureMOM/evaluation/medpark-reference-comparison.json` | Read/hash at execution |

The WAV duration previously measured 702.635 s (about 11m42s). Check actual channels, sample rate, sample count and duration before using it. A recoverable ALAC frame error was reported while decoding the source; preserve this caveat equally for all candidates. The separately present `Medpark_audio_first_quarter.m4a` is not the full recording.

Use `%LOCALAPPDATA%/SecureMOM/evaluation/pbi025/` for inputs manifest, runs, transcripts, chunks, private review files and reports. Keep the existing reference immutable; do not overwrite it with a model output or human correction. No recordings, reference text, hypotheses or medical terms go into Git. Portable manifests use logical filenames plus hashes; actual local paths live in the private manifest.

The share page was not accessible through the web-fetch tool during planning. This does not block execution: the saved reference hash matches the previously recorded extraction. If the saved file is missing, use a browser to retrieve only the transcript from the exact share page, excluding UI labels, speakers and timestamps; save provenance and a new hash. Do not silently substitute another reference.

## Files to create during execution

Create these only after reading this PBI; these are proposed files, not existing commands:

- `evaluation/asr_compare.py`: stdlib CLI orchestration, input checks, chunk creation, isolated worker invocation, score/report commands.
- `evaluation/asr_compare_worker.py`: one model per process; imports model packages only inside the selected backend.
- `evaluation/asr_metrics.py`: deterministic normalization, WER/CER, report aggregation.
- `evaluation/asr_compare.matrix.json`: exact named configurations below; no private paths.
- `evaluation/test_asr_compare.py`: synthetic scoring/manifest/failure tests.
- `evaluation/ASR_COMPARISON.md`: tested setup and exact commands, including native/WSL path mapping.
- `evaluation/asr_compare.runtime.lock.json`: actual source commit, package versions, wheel/index provenance, model/tokenizer hashes, OS/runtime; populate from observed preparation, never invent pins.
- `hackathon/ASR_COMPARISON_RESULTS.md`: public-safe numeric results and decision, no transcript excerpts.

Update only this PBI and its index status on completion. Do not modify production ASR, model profiles, schemas, UI, SMTP or application dependencies in this PBI. Model promotion is a separate reviewed change under 004 after these results exist.

## Fixed comparison design

### A. Common-input experiment (primary model comparison)

1. Reuse the verified full decoded WAV. If it is not 16 kHz mono PCM16, create one derivative outside Git and freeze its hash; use that same derivative for every candidate.
2. Split by PCM sample index into consecutive **25.000-second**, non-overlapping windows, with a final shorter window. Keep all samples including silence. No denoising, source separation, VAD removal, gain tuning or overlap deduplication. Each model receives byte-identical windows in identical order.
3. Batch size 1; load once, process every window, concatenate returned text with a single space, then unload by process exit. Save each raw window result and its absolute sample/time interval.
4. Do not use the reference, glossary or another recognizer's output as model prompts. No post-ASR spelling fixes or LLM rewriting. Score original output.
5. Fixed boundaries can split words. Disclose this limitation. This experiment controls input context; the separate deployment baseline below measures Whisper's actual workflow.

| Run ID | Model | Language setting | Precision / decoding |
|---|---|---|---|
| `w-auto-common` | Existing pinned faster-whisper large-v3 | `language=None`, `multilingual=True` | CUDA `int8_float16`, beam 5 |
| `w-ro-common` | Same Whisper | `language="ro"`, `multilingual=False` | Same |
| `o-ctc1-common` | `omniASR_CTC_1B_v2` | None; CTC has no language conditioning | CUDA BF16, official greedy CTC |
| `o-llm1-ro-common` | `omniASR_LLM_1B_v2` (standard, not Unlimited) | `lang=["ron_Latn"]` per one-item batch | CUDA BF16; record official beam configuration |
| `o-llm1-auto-common` | Same Omni LLM | No language hint | Same |
| `o-ctc3-common` | `omniASR_CTC_3B_v2` | None | 16 GB host only; CUDA BF16 |

Common Whisper settings: `task="transcribe"`, `vad_filter=False`, `condition_on_previous_text=False`, `word_timestamps=True`, `temperature=0.0`; consume the full iterator. Use `WhisperModel`, not the batched wrapper. No hidden language override in the Romanian run. Preserve and record remaining runtime defaults. Beam numbers are backend-specific; do not claim equivalent search algorithms.

Omni API: `ASRInferencePipeline(model_card=..., device="cuda", dtype=torch.bfloat16)` then `transcribe([waveform_input], batch_size=1, lang=["ron_Latn"])` for conditioned LLM only. A waveform input is `{"waveform": <float32 mono samples>, "sample_rate": 16000}`. Scale PCM16 once to float32. For CTC/automatic mode omit `lang`. Record actual configuration and detect unsupported options rather than silently dropping them.

Check BF16 support first. If unavailable, mark that row incompatible; optionally run an explicitly named FP16 row, never reuse the original ID. Do not load 3B CTC on the 8 GB laptop or try 7B models in this bounded experiment.

### B. Actual Whisper deployment baselines (separate table)

- `w-auto-native`: new full-file run through the existing `transcribe_audio` adapter/config, preserving current VAD settings and metrics.
- `w-ro-native`: benchmark-local direct Whisper call on that same full WAV, matching deployment options except `language="ro"`, `multilingual=False`.
- Keep both separate from common-input results. The historical 101.5-second output is context only; it is not a new matched run.
- Do not compare old Windows timings to new WSL Omni timings as a pure model-speed claim. Run a Whisper common-input control in the same OS/runtime environment as Omni, using the same asset bytes and recorded backend version. Report deployment versus WSL overhead separately.

## Runtime preparation and offline execution

1. Check `git status`, active branch and HEAD. Work on a fresh `codex/asr-comparison` branch from the user's integrated `develop` if no other feature work is present. Preserve unrelated edits.
2. Inventory GPU name/UUID, driver, total/free VRAM, RAM, OS, Python, FFmpeg, available disk and WSL distributions. Do not install/reconfigure WSL or NVIDIA drivers as an incidental fix. Laptop should be plugged in; record power mode and other GPU processes. Do not terminate unrelated workloads.
3. Known native Python: `C:/Users/neuma/AppData/Local/Programs/Python/Python311/python.exe`; FFmpeg/ffprobe found on PATH. The service `.venv` did not exist at planning. Check where current faster-whisper imports succeed; do not assume a virtualenv path.
4. Use an isolated environment under ignored `.tools` or Linux user storage. For Omni, prefer existing WSL/Linux with a supported fairseq2 wheel. Consult the official **0.6** compatibility row, not latest fairseq2. Candidate combination to resolve and verify: Python 3.11/3.12, PyTorch/torchaudio 2.8.0 CUDA 12.8, fairseq2 0.6.0, an immutable Omni source revision compatible with that range. This is a preparation candidate, not a tested installation claim. Verify import, `pip check`, CUDA tensor operations and a 25-second model smoke before proceeding. Record the successful exact lock and reproducible install commands.
5. A native Windows failure to obtain a compatible fairseq2 wheel is an environment blocker, not evidence against the model. If no existing compatible runtime is available, still build/scoring-test the harness and run Whisper; report Omni blocked with the exact error. Do not spend the day building fairseq2 from source. Two targeted setup fixes, then escalate only the specific blocker to Sol.
6. Prepare/download public model/tokenizer files online before timing. Reuse existing Whisper assets. Pin upstream source/revision and compute SHA-256 for every downloaded artifact; record whether hashes are locally observed or publisher-verified. Cache files outside Git. Do not touch the source audio during downloads or upload it anywhere.
7. Timed workers use prepared assets only. A cache miss fails rather than downloading. Record the enforcement/observation used for offline execution; an environment flag alone is not proof of host-wide isolation. Never disable the user's network globally. A private namespace/local-only sandbox may be used where already supported.
8. Run only one GPU worker at a time. Put full audio/model copies on Linux storage if using WSL; verify hashes after copying and exclude copy time from inference but report preparation time. `C:/...` maps to `/mnt/c/...` for initial access. Do not place live application databases in this experiment.
9. Run one unscored 25-second smoke per prepared model. Then full runs in matrix order. If a worker errors/OOMs, save failure and partial artifacts, mark incomplete, and continue independent rows. One retry for a clearly transient error; no silent precision/batch changes. Cap a full Medpark worker at 30 minutes; timeout is a measured failure, not an empty transcript.
10. Repeat each completed candidate once in a fresh worker, model files cached. Record both timings/output hashes; do not call this a true disk-cold benchmark. Never average transcript metrics across repetitions as though they are independent recordings.

For the remote 16 GB machine, prepare a portable bundle of harness/config and hashes; obtain the host/path from the user only if not already configured. Use permitted synthetic/public audio for the remote setup check. Transfer the Medpark recording/reference only with explicit authorization covering that remote host. Missing access/transfer authorization marks 16 GB NOT RUN; local work proceeds.

## CLI contract Luna must implement, then execute

The following commands **do not exist yet**. Their exact interface is the implementation target. Run from the repository root with the appropriate prepared Python interpreter. The stdlib harness invokes model workers through the interpreter supplied in the private manifest, allowing separate dependency environments.

```powershell
$benchRoot = Join-Path $env:LOCALAPPDATA 'SecureMOM/evaluation/pbi025'
python evaluation/asr_compare.py prepare --root $benchRoot --audio 'C:/Users/neuma/Downloads/Medpark_audio.m4a' --decoded 'C:/Users/neuma/AppData/Local/SecureMOM/evaluation/medpark-decoded.wav' --reference 'C:/Users/neuma/AppData/Local/SecureMOM/evaluation/medpark-microsoft-reference.txt'
python evaluation/asr_compare.py doctor --root $benchRoot
python -m pytest evaluation/test_asr_compare.py -q
python evaluation/asr_compare.py run --root $benchRoot --suite laptop8 --repeat 2
python evaluation/asr_compare.py score --root $benchRoot
python evaluation/asr_compare.py report --root $benchRoot --public-output hackathon/ASR_COMPARISON_RESULTS.md
```

Implement `run --id <run-id>` for retries/single cases, and `--suite hospital16` for same-host controls plus 3B CTC. A doctor failure for one backend must not prevent running another. `prepare` is idempotent: validate existing hashes, never overwrite changed inputs, emit actionable errors. Store progress/checkpoint per completed window; a resumed correctness run is labeled resumed and is not a clean timing trial.

## Scoring: exact rules

- Preserve raw reference/output. Normalize separate scoring copies using Unicode NFKC, casefold, then replace every character whose Unicode category does not begin L, M or N with a space; collapse whitespace. Apply identically to both sides.
- Retain Romanian diacritics and Cyrillic. No transliteration, stemming, synonym matching, translation, number-word conversion or medical spelling correction. Report sensitivity to this normalization; numeric formatting differences may still count as errors.
- WER = `(substitutions + deletions + insertions) / reference_words`; CER is Levenshtein distance over normalized non-space characters / reference characters. Use one tested edit-distance implementation and a stable backtrace tie-break. Report counts and denominators. WER may exceed 100%; do not call `1-WER` clinical accuracy or clamp it into a flattering score.
- The saved TXT is already transcript-only; inspect its format locally, never apply a generic regex that removes spoken numbers as timestamps. Do not expose its text in public logs/reports.
- Score the full concatenated hypothesis against the full saved reference. Do not align arbitrary reference word slices to timed clips. Historical 81.8% disagreement may differ under a new normalization; record the reason, never force a match.
- Label the primary column **WER versus Microsoft machine reference (unverified)**. Empty reference fails scoring; an empty completed hypothesis yields deletion errors, while a crashed/incomplete run gets no official score.
- Generate a private diff report for human review. Optional human layer: before inspecting candidate outputs, a fluent reviewer checks the fixed intervals 0–60 s, 300–360 s and the final 60 s; records exact timestamps and transcription in a new versioned file. Unintelligible spans have explicit exclusions applied consistently to every candidate. No human availability means NOT VERIFIED, not blocked automated work.
- Critical-term review uses reviewer-frozen occurrences with time/context and accepted spelling variants. Count correctly preserved terms, negations, drug/dose/unit mentions and minority-language words separately, with numerator/denominator. Never let a model write its own answer key. If this annotation is unavailable, report NOT SCORED.
- The mostly Romanian Medpark sample does not qualify Russian, English or code-switching. Existing composites may be diagnostic, but must have a verified timed reference and provenance before scored claims. Do not invent multilingual test data or label synthetic switching as natural conversation performance.

## Timing, memory and output schema

For each run save JSON with: run ID, suite, git SHA, hardware/OS, model/runtime hashes and versions, frozen options, audio/reference/chunk hashes, reference verification state, completed/expected windows, per-window text and absolute intervals, output hashes, errors, metrics and scoring normalizer version.

Measure process wall time including startup/model load/inference/serialization/exit; also report separate model-load and inference times. Synchronize CUDA around inference timing where applicable; consume lazy outputs before stopping. Model download is preparation, never hidden inside inference. Report `RTF = worker_wall_seconds / audio_seconds` and `speedup = 1/RTF`.

Sample GPU total used memory and process-tree RSS periodically (target 200–500 ms); record pre-run GPU baseline and sampling interval. On WSL or Windows where attribution is unavailable, label device totals honestly. Peak minus baseline is an estimate, not exact process VRAM. Measure worker cleanup and verify no owned GPU worker survives exit.

The reference duration is about 703 seconds, not an hour. Any `RTF * 3600` number is **ASR-only extrapolation**. The 900-second challenge gate includes decode, ASR, optional alignment/diarization, LLM, artifact and Affan's delivery; it remains PBI-017. Provisional selection budget: ASR RTF <=0.15 (9 minutes/hour extrapolated), leaving 6 minutes for other stages. This is a screening budget, not measured acceptance.

The standard Omni pipeline returns strings, not word timings. Store only known chunk intervals and `timingGranularity="chunk"`; never synthesize word timestamps. Report this integration gap beside its score. Likewise preserve raw formatting; punctuation restoration is separate work. A text benchmark winner is not yet a drop-in application replacement.

## Decision rule and bounded follow-up

1. Publish every attempted row, including failures. Rank common-input rows only within the same hardware/runtime cohort; show native deployment baselines separately.
2. A **provisional candidate** needs full completion without OOM, >=5 percentage points lower reference WER than the better matched Whisper common-input mode, and ASR RTF <=0.15 on its actual target device. This threshold is a project decision, not statistical significance.
3. A human-reviewed critical-term/negation regression prevents promotion even if aggregate WER improves. Without human review, state provisional only. One recording cannot establish general superiority.
4. If no Omni candidate passes, retain Whisper and preserve results. No automatic production switch. If a candidate passes, report exact model/runtime/config and timestamp/language-control work needed under PBI-004.
5. CTC cannot honor a forced-language dropdown. Language conditioning belongs to Omni LLM or Whisper. Automatic mode does not prove accurate switches within a sentence. Keep both facts visible in the recommendation.

## Targeted tests and acceptance

- Synthetic identical text => WER/CER 0; `a b c` versus `a x c d` => one substitution and insertion, WER 2/3; empty hypothesis => WER 1; empty reference rejected; Unicode diacritics/Cyrillic preserved; punctuation/case ignored.
- Input/hash mismatch rejected; chunk sample coverage exact without gaps/duplication; full iterator consumed; failed/resumed runs excluded from clean timing rankings; private text absent from public report.
- Commands above work after documented preparation, and successful workers repeat offline from prepared caches.
- PBI COMPLETE only when harness/tests and real laptop Whisper/Omni CTC 1B plus Omni LLM 1B Romanian/auto results exist, or an explicit user-approved reduction of scope is recorded. A model run failing/OOMing with complete diagnostic evidence is a valid negative experiment; inability to install Omni leaves model comparison INCOMPLETE.
- Optional remote rows and human annotations may remain NOT RUN/NOT VERIFIED with an honest local provisional result. PBI-004/017 are not automatically closed by finishing this experiment.

## Completion record

- Commit / changed files: pending
- Runtime preparation and reproducible commands: pending
- Attempted/completed/failed model runs: pending
- Source/reference hashes and local report paths: pending
- Accuracy, speed, memory and human-review limitations: pending
- Recommendation and follow-up under 004/017: pending

## Copy-paste executor prompt

Read `hackathon/pbis/PBI-025-whisper-omniasr-comparison.md` and the backlog index. Execute PBI-025 using GPT-6 Luna with High reasoning. The PBI defines the model matrix, existing private inputs and hashes, runtime isolation, CLI to implement, scoring and decision rules. Implement the small benchmark harness, prepare compatible isolated runtimes, run the real available local comparisons, and save private outputs outside Git plus a public-safe numeric report. Do not change production models/UI/SMTP or claim human-verified accuracy from the Microsoft transcript. Continue independent work if an environment/remote dependency is missing; report exact blockers. Update the PBI completion record. Do not start other PBIs.
