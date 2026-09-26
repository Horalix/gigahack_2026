# Project status

## Done

- Replaced mock production capture and external-command recognition with real Windows adapters and embedded CPU Whisper.
- Implemented optional local finalized transcripts, live consent controls, bounded background storage, full history, copying, four export formats, and secure app-managed deletion.
- Simplified the main window and Settings, added compact native overlay controls, no-activation behavior, DPI handling, persistent geometry and parent-process cleanup.
- Built MSI and NSIS installers. Inspected the rebuilt executable: no separate Visual C++ runtime dependency remains.
- Passed 39 Rust tests, three native renderer regressions, four headless UI flows, strict Clippy, formatting checks, and Svelte checking without warnings. The final real-model fixture also passed.
- Recognized controlled prerecorded speech. Shorter encoder windows reduced processing for an 11-second streaming fixture from 7.92 seconds to 1.37 seconds on this machine; this is computation time, not end-to-end live caption delay.
- Rendered native normal-size and 280-by-110 overlays invisibly, with foreground-focus assertions and visual inspection.
- The extended fixture passed 120 cycles each with saving off/on: about 44 minutes of repeated audio processed in 193.8 seconds. Off/on processing took 95.034/96.168 seconds (about 1.2% difference). Peak test-process working set was 343.1 MiB on an Intel i9-12900H. This excludes the full WebView UI and is not a live-caption latency or diverse-speech accuracy measurement.
- Ran the actual official-model download/repair test. Its process ended and its owned directory was removed, consistent with reaching cleanup after checksum, cache reuse and reload assertions. The terminal result was lost during context compaction, so no exit-code claim is recorded.
- Installed and uninstalled NSIS and MSI packages on the current Windows machine. Installed Settings downloaded the model with the expected checksum. Restart preserved appearance settings and did not restore deleted history.
- Passed ten real application-capture and ten explicit-output loopback Start/Stop cycles, with finalized speech and overlay cleanup. Another controlled process was excluded from application capture. Closing the selected player produced recovery instructions and stopped the overlay; reselection worked.
- Native live consent saved only the enabled phrase from a three-phrase recording. View, clipboard copy, all exports, active-session deletion, and original/translation metadata worked. Original user data was restored and temporary installations/apps removed.

## Changed

- Hackathon PBI-002 now has a separate FastAPI/SQLite service: generated-name WAV/video ingest, FFmpeg track selection, source preservation, transactional single-GPU job claims, expired-lease recovery, checkpointed transcript commits and deny-by-default synthetic-only access hook. Real synthetic English speech reached `transcript_ready` after a simulated worker expiry on the RTX 3070 Ti; this does not verify multilingual large-v3 accuracy.
- Hackathon PBI-003 is complete: pinned large-v3 and Qwen GGUF passed local SHA-256 checks; large-v3 ran on the 8 GB laptop GPU and Qwen loaded with its embedded template on a local CPU runtime. PBI-004 remains open: the permitted 11m42s Medpark recording produced timed words in 101.5 seconds of ASR work, but a composite exposed language/script instability and overlap lost one voice. The remote 16 GB host and one-hour end-to-end path are untested. See `hackathon/10-team-handoff.md` for current team ownership and evidence.
- Completed hackathon PBI-001 on the current `noomy/freepalestine` checkout: added versioned Secure MOM record schemas, synthetic contract/output fixtures and documented semantic validation plus Affan's still-pending artifact format/handoff decision. This is additive planning/integration scaffolding; it does not change or complete the caption app.
- Native checks fixed four defects: overbroad source filtering, a borrowed PROPVARIANT destructor causing heap corruption, stale/empty caption rendering crashing the overlay, and missing titlebar-dragging permission.
- Removed repeated randomized decoding retries for short live chunks. A recognition-state reuse experiment was discarded because its timing benefit was not clear. Native timing remains fixture-specific; broader latency and accuracy evaluation is still needed.
- Latest additions include model-download progress, playback-device-change handling, recognition-error propagation, startup race guards, export-folder access, writer-overload persistence, and repeated prerecorded segment checks.
- Appearance edits now use serialized field patches; scratch captions use Windows delete-on-close protection. Both changes pass dedicated regression tests. Installers were rebuilt after the production changes.
- README and overlay documentation now describe implemented behavior; historical backlog/summary documents are explicitly labeled as planning records.

## Next

- Qualify PBI-004 against known-language references and review the code-switch window choice; then finish PBI-005 access and PBI-009 grounded decisions while Affan builds the PBI-010 artifact renderer.
- Complete the remaining controlled checks in `installer-smoke-test.md`: native mouse/menu interaction, mixed-DPI/fullscreen behavior, live microphone, clean-machine installation, and broader speech accuracy/latency.

## Risks

- Only controlled test audio and application data are authorized. Do not capture live microphone/ambient audio or inspect unrelated private applications.
- Default-output capture was not used because another audio session was active. An idle NVIDIA output endpoint exercised the real WASAPI loopback adapter without changing the default device. Live microphone and clean-machine checks remain explicitly deferred.
- Windows packages are unsigned. Product completion is not yet proven. The Computer Use native pipe is unavailable after reset/retry; installed WebView tests used a process-local debugging interface, but native mouse interaction remains unverified.
- The goal is blocked on the remaining native mouse/menu checks. The unavailable helper persisted across the resumed validation continuations and was rechecked after cleanup; a working Windows interaction connection or controlled manual results are needed to close those gates.
