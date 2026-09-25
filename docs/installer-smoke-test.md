# Windows release verification

Build with `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows-build.ps1 -Task package`.

Outputs:

- `src-tauri/target/release/bundle/nsis/FeelSay_0.1.0_x64-setup.exe`
- `src-tauri/target/release/bundle/msi/FeelSay_0.1.0_x64_en-US.msi`

Both formats have been generated locally. The executable uses embedded recognition and a static C++ runtime; dependency inspection must continue to show no `MSVCP140.dll`/`VCRUNTIME140.dll` requirement. The installer handles WebView2. Speech-model download requires a connection on first use; captions need no connection after setup. Packages are unsigned and have not been published.

## Safe automated checks

- Svelte/TypeScript checking and static production build.
- Headless isolated Edge UI tests with native IPC mocked: first Start/model setup, live transcript changes without capture restart, history view/export/delete, narrow Settings, and capture-error cleanup.
- Rust tests against actual local SQLite, including default-off, consent boundaries, finalized-only storage, exports, secure deletion, active-session deletion, storage errors and bounded writer behavior.
- Controlled prerecorded WAV recognition and repeated streaming segments. No playback and no unrelated audio capture.
- Hidden native rendering at normal and minimum overlay sizes, including separate original/translation text. The renderer asserts invisibility and unchanged foreground focus.

These checks do not prove live WASAPI capture or clean-machine installation.

## Recorded native checks (2026-09-06)

- Windows 11 build 26100, Intel i9-12900H; installed WebView2 already present. NSIS installation/uninstallation and MSI per-user installation/uninstallation returned exit code 0. MSI used `ALLUSERS=2 MSIINSTALLPERUSER=1`; this does not verify elevated per-machine installation or a clean PC.
- The installed Settings download completed, and the model SHA-256 matched the pinned value. Cached setup survived restarts.
- Ten application-capture and ten explicit-output loopback cycles recognized the prerecorded JFK fixture, finalized speech, stopped capture, and removed the overlay. Lifecycle repetition called the installed application's real Tauri commands; separate UI Start/Stop/source-selection flows also ran. No native IPC was mocked.
- Application capture excluded a second controlled player's speech (zero speech events, peak level about 0.000015). The default output had another active audio session, so system loopback used an idle NVIDIA endpoint and a controlled output-only player. No microphone or unrelated audio was captured; no default device was changed.
- Closing the selected application displayed recovery instructions and removed its overlay. Relaunching/reselecting the fixture recovered successfully.
- Saving enabled at 6.047 seconds and disabled at 13.039 seconds in a controlled three-phrase recording. Only the middle phrase, containing “lantern,” was saved; the “mango” and “cactus” phrases were excluded. Capture was not restarted.
- Actual view/copy/TXT/SRT/VTT/JSON actions worked. Deletion removed all four managed exports, cleared the viewer/history, and removed the fixture phrase from raw SQLite bytes. History stayed empty after restart. Deletion while capture continued left the overlay running.
- A live Original + English change saved original and translated fields on three finalized synthetic-English segments. This checks the translation path, not cross-language translation accuracy.
- Main-window minimize/maximize/restore worked. The titlebar dragging ACL rejection was fixed and its handler retested without errors. Live font changes reached the native settings service and persisted after restarting. Installed main/Settings screenshots were inspected.
- Native empty/stale rendering had crashed after the stale timeout; the fix now passes three hidden renderer regression tests. The process-loopback heap-corruption crash and overbroad source-title filtering were also reproduced and fixed.
- About 562 seconds of native lifecycle/consent testing were sampled: main-process peak working set 249.8 MiB; sum across its process tree peaked at 644.9 MiB. The sum can double-count shared pages and is not unique physical memory. This is one machine/fixture, not a broad resource guarantee.
- Automatic-language timing showed long/variable updates. Disabling repeated randomized decode retries reduced most observed first updates to about 3.4–3.7 seconds in the controlled fixture. Some probes overlapped prior results; no general end-to-end latency claim is made. A state-reuse experiment was discarded.
- Test applications/installations were removed, the original FeelSay data directory was restored intact, and the controlled clipboard text was cleared. Logs, generated fixtures and result files remain under ignored `.tools/native-validation`; they contain controlled test data only.

## Remaining manual checks in a controlled session

Do not execute these on an active user's desktop or against unrelated audio. Use a clean test machine/profile or a deliberately arranged session with controlled speech.

1. Install each package on clean Windows without developer tools or the Visual C++ redistributable. Check first WebView2 setup and elevated MSI installation. Current-machine per-user installation and uninstallation are recorded above.
2. Download the model through first Start. Check offline startup afterward and retry after an interrupted download. Verify repair recovers a corrupted model.
3. Caption a known recording through the default playback device; caption controlled microphone speech; caption a supported application's known recording on Windows build 20348+. Confirm another application's unrelated sound is excluded in application mode.
4. Run at least ten Start/Stop cycles for each source. Verify capture stops, model memory is released, no child remains after Quit, and a subsequent Start works.
5. Close the selected application, disconnect a selected device, and change the default playback device in the test environment. Confirm useful recovery instructions and successful retry. Check silence does not create endless invented captions.
6. Drag and resize the overlay across monitors, including mixed DPI and negative monitor coordinates. Verify wrapping, font/color/opacity changes, topmost toggle, click-through recovery, popup control interaction, no unwanted focus activation, and restored geometry after restart.
7. Toggle saving in both Settings and the live overlay. Speak distinct before/enabled/disabled phrases. Verify only finalized eligible speech appears in history; Stop must finish eligible pending speech. Inspect all export formats and delete a session while captions continue.
8. Check a sustained call-length fixture for accuracy, caption delay, CPU and working-set stability on an ordinary CPU-only PC. Include overlapping voices and the languages intended for release. Speaker identities must never be fabricated.
9. Delete history and confirm it is absent after restart and its app-managed exports are gone. Check quota recovery after deleting older sessions. External copies and OS backups remain outside app deletion.

## Release gates

Do not describe the release as production-verified until the native checks above are recorded with environment and results. Signing a public release requires trusted credentials and explicit publishing authorization; neither is part of the local build task.

## Requirement audit

| Requirement                                                       | Current evidence                                                                                                          | Remaining verification                                                           |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| Three-action main flow, Settings, readable source choices         | Four headless flows plus installed WebView source/Start/Stop/Settings checks and screenshots                              | Clean-machine WebView setup                                                      |
| System, microphone and supported application capture              | Real application and explicit-output loopback capture; ten cycles each; second-process exclusion                          | Live microphone and default-output selection with no unrelated audio active      |
| Embedded local recognition with no user tooling                   | Real prerecorded speech recognized; model checksum validation; installer binaries include the engine and C++ runtime      | First-use network/setup and repair on a clean machine                            |
| Stable finalized segments, silence handling and local translation | Prerecorded segment finalization; display boundary tests; final-only persistence; original/English engine modes           | Broader languages, noise, overlapping speech, and live audio-to-screen delay     |
| Lightweight pipeline and bounded storage                          | Bounded queues/quotas; CPU-only engine; prerecorded benchmark and sampled native process-tree working sets                | Broader hardware, sustained conversational audio and unique-memory measurements  |
| Movable/resizable borderless overlay and no focus theft           | Native styles/hit tests; hidden normal/minimum-size rendering; invisibility and foreground assertions; persisted geometry | Interactive movement, resizing, mixed-monitor DPI, fullscreen and popup behavior |
| Immediate full/compact appearance changes                         | Installed live font changes and restart persistence; field-patch concurrency tests; native control protocol               | Mouse-driven native compact-menu interaction                                     |
| Saving off by default, live consent, no backfill                  | Service tests plus three distinct spoken phrases through native capture; only enabled speech saved without restarting     | Mouse-driven compact toggle                                                      |
| Local history, useful metadata, view/copy/export/delete           | Installed view/copy/all exports/delete; native original/translation fields; byte-level deletion and restart checks        | File-manager integration and external-copy expectations                          |
| No unstable permanent history or hidden deleted copies            | Final-only DB writes; generation invalidation; managed export deletion; Windows scratch-file automatic-deletion test      | Independent backup/OS forensic recovery is outside app control                   |
| Persistence and common error recovery                             | Native source-close recovery, repeated Start/Stop, clean exit, settings/history restart checks; atomic writes             | Device disconnect/default-device switch                                          |
| Speaker honesty                                                   | Experimental speaker labels are disabled in normalized production settings                                                | Reliable speaker distinction intentionally deferred                              |
| Windows packaging, accurate docs, clean diff                      | NSIS/MSI per-user installation and uninstallation; final NSIS launch; dependency inspection; automated checks             | Clean-machine/elevated installation; unsigned packages; no publishing performed  |

The remaining checks are explicit limitations, not completed gates. No usable isolated Windows test environment was identified. The Computer Use helper failed with “native pipe is unavailable” after reset/retry; mouse-driven compact menus, drag/resize, fullscreen and mixed-DPI interactions therefore remain unverified. Native WebView automation covered the recorded flows above. Do not enable system features or use live microphone/ambient audio to close these gaps without appropriate authorization.
