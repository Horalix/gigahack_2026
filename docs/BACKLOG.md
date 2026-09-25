# Product Backlog

Historical planning record. Completion checkboxes here are not release evidence; current implementation and validation are tracked in [project status](PROJECT_STATUS.md).

Priority levels:

- **P0**: Required before real captioning can be trusted.
- **P1**: MVP core feature.
- **P2**: MVP polish or important expansion.
- **P3**: Post-MVP.

## P0-001: Stabilize Current Overlay And Settings

**Goal:** Make the existing overlay/settings foundation reliable before adding capture.

**Tasks:**

- Manually test all five profiles.
- Verify autosave status under quick edits.
- Verify live overlay updates for font, colors, opacity, outline, geometry, and click-through.
- Verify visual placement helper still works with click-through enabled.
- Fix any overlay lifecycle regressions.
- Update failing docs or tests if behavior changes.

**Acceptance:**

- No duplicate or orphan overlay processes.
- Settings persist after restart.
- Running overlay updates without Stop/Start.

## P0-002: Replace Mock Meter With Real Microphone Level Meter

**Goal:** Prove real audio input capture lifecycle without ASR.

**Tasks:**

- Enumerate and select microphone devices through the existing source model.
- Start a real microphone capture preview.
- Emit real `audio-level` events.
- Stop capture cleanly on Stop, source change, overlay close, and app exit.
- Keep mock meter only as fallback/debug path.

**Acceptance:**

- Devices tab can select a real microphone.
- Meter reacts to microphone input.
- No capture thread remains after Stop/app close.

## P0-003: Audio Capture Service Architecture

**Goal:** Create the capture foundation that ASR can consume safely.

**Tasks:**

- Define `AudioCaptureProvider`, `AudioCaptureSession`, and PCM frame event types.
- Normalize sample format, channel count, and sample rate.
- Add bounded queues/ring buffers.
- Add timestamps.
- Ensure capture callbacks never block.

**Acceptance:**

- Capture service can produce normalized PCM frames.
- Backpressure behavior is explicit and tested.
- UI only receives high-level status/events, not raw audio.

## P1-004: Windows System Audio Capture Preview

**Goal:** Capture system audio on Windows without ASR.

**Tasks:**

- Implement WASAPI loopback capture for default output device.
- Wire `Entire System` source to system loopback.
- Emit real audio levels from system audio.
- Handle no-output-device and device-change failures gracefully.

**Acceptance:**

- Playing audio in another app moves the meter.
- Stop/app close releases the loopback session.

## P1-005: Source Selection To Capture Wiring

**Goal:** Make selected source determine capture behavior.

**Tasks:**

- Map microphone sources to microphone capture.
- Map output/system sources to loopback capture.
- Keep app/window sources disabled or clearly marked unsupported until app-specific capture exists.
- Show clear capture status: ready, starting, active, error.

**Acceptance:**

- User sees only useful capture states.
- Unsupported sources do not silently pretend to work.

## P1-006: Voice Activity Detection

**Goal:** Reduce wasted ASR work by detecting speech before transcription.

**Tasks:**

- Add VAD stage after capture normalization.
- Emit speech/silence status.
- Gate downstream ASR chunks on speech.
- Keep thresholds configurable internally first.

**Acceptance:**

- Silence does not produce transcription work.
- Speech state is visible in debug/status events.

## P1-007: Local ASR Prototype

**Goal:** Produce first real local captions.

**Tasks:**

- Integrate a lightweight Whisper-based runtime.
- Add one default local model preset.
- Feed VAD-approved audio chunks into ASR.
- Emit provisional caption events.
- Display recognized text in the overlay.

**Acceptance:**

- Microphone or system audio produces real caption text.
- No translation yet.
- Stop cleans up capture and ASR workers.

## P1-008: Caption Stabilization

**Goal:** Make live captions readable instead of flickery.

**Tasks:**

- Separate provisional and committed caption text.
- Add simple text replacement/stabilization policy.
- Handle line wrapping and max visible lines.
- Clear stale captions after silence/session stop.

**Acceptance:**

- Caption text updates feel stable.
- Overlay remains readable during continuous speech.

## P1-009: Model Management MVP

**Goal:** Make local model usage user-manageable.

**Tasks:**

- Add installed model metadata.
- Add default model path/config.
- Add model selection UI.
- Add checksum verification for bundled/downloaded models.
- Show disk size and active model.

**Acceptance:**

- User can see which ASR model is active.
- Missing model state is clear and recoverable.

## P1-010: Transcript Storage MVP

**Goal:** Save local transcripts when enabled.

**Tasks:**

- Add SQLite schema for sessions and segments.
- Add transcript saving toggle.
- Save timestamps, source summary, original text, and final segment state.
- Keep saving disabled by default until UX is ready.

**Acceptance:**

- A caption session can be stored locally.
- No transcript is saved when saving is disabled.

## P1-011: Transcript Export

**Goal:** Let users export saved sessions.

**Tasks:**

- Add transcript history view.
- Export TXT, SRT, VTT, and JSON.
- Include timestamps.
- Handle empty/partial sessions.

**Acceptance:**

- Saved transcript exports open correctly in common tools.

## P2-012: Translation Mode MVP

**Goal:** Add first translation path.

**Tasks:**

- Add mode selector: captions only, translate, original + translation.
- Use Whisper translate-to-English if supported by selected model.
- Display translated text in overlay.
- Store translated text in transcript segments.

**Acceptance:**

- Non-English speech can produce English captions in translation mode.
- Captions-only mode remains unchanged.

## P2-013: Original Plus Translation Overlay

**Goal:** Support two-line subtitles.

**Tasks:**

- Add overlay layout for original line above translation.
- Add profile setting for dual-line mode styling.
- Keep readability at common overlay sizes.

**Acceptance:**

- Original and translated lines are visually distinct and readable.

## P2-014: Application Audio Capture Research And Prototype

**Goal:** Determine reliable Windows app-specific capture path.

**Tasks:**

- Investigate Windows application loopback support.
- Prototype app/window source capture where available.
- Keep fallback to system audio.
- Document unsupported cases clearly.

**Acceptance:**

- App-specific capture either works for supported apps or is clearly scoped out.

## P2-015: Source Picker Polish

**Goal:** Make source selection feel native and trustworthy.

**Tasks:**

- Improve Windows app/window enumeration filtering.
- Add real app icons where feasible.
- Add real or better placeholder thumbnails.
- Improve unavailable/unsupported labels.

**Acceptance:**

- Source picker shows user-facing apps without obvious junk windows.

## P2-016: Hotkeys And Tray Controls

**Goal:** Make the utility easier to control while in other apps.

**Tasks:**

- Add global Start/Stop hotkey.
- Add show/hide overlay hotkey.
- Add click-through toggle hotkey.
- Add tray menu with Start/Stop and Settings.

**Acceptance:**

- User can control captions without returning to the main window.

## P2-017: Performance Presets

**Goal:** Give users simple quality/performance choices.

**Tasks:**

- Add Low Resource, Balanced, Accuracy, and Custom presets.
- Map presets to model, VAD, chunking, and worker settings.
- Show estimated resource impact.

**Acceptance:**

- User can choose performance behavior without technical tuning.

## P2-018: Error Handling And Recovery Pass

**Goal:** Make failures understandable and recoverable.

**Tasks:**

- Replace raw backend errors with user-safe messages.
- Add recovery actions for missing devices, failed capture, missing models, and permission issues.
- Add structured logs for debugging.

**Acceptance:**

- Common failures explain what happened and what to do next.

## P2-019: Packaging Polish

**Goal:** Make the Windows app feel installable and real.

**Tasks:**

- Add final app icon.
- Verify MSI/NSIS metadata.
- Add version display.
- Add installer smoke test checklist.
- Prepare code-signing notes.

**Acceptance:**

- Built installer has correct name, icon, and metadata.

## P3-020: Speaker Or Source Labels

**Goal:** Identify where captions came from when multiple sources exist.

**Tasks:**

- Add source labels to segments.
- Display optional label in overlay.
- Store labels in transcript.

**Acceptance:**

- Multi-source sessions can distinguish source labels.

## P3-021: Diarization

**Goal:** Add optional speaker-turn detection.

**Tasks:**

- Evaluate local diarization options.
- Add opt-in high-resource mode.
- Store speaker labels per segment.
- Expose uncertainty clearly.

**Acceptance:**

- Speaker labels can be generated without blocking normal captions.

## P3-022: Local Text Translation Engine

**Goal:** Support language-to-language translation beyond Whisper English translation.

**Tasks:**

- Evaluate local translation models.
- Add translation worker separate from ASR.
- Add model management for translation models.
- Support original-to-target language pairs.

**Acceptance:**

- Translation works for selected non-English target languages locally.

## P3-023: Custom Vocabulary And Corrections

**Goal:** Improve recognition for names and domain terms.

**Tasks:**

- Add correction dictionary.
- Add custom vocabulary settings.
- Apply post-ASR corrections safely.

**Acceptance:**

- User can improve repeated terms without model retraining.

## P3-024: Cross-Platform Capture Adapters

**Goal:** Expand beyond Windows while preserving architecture.

**Tasks:**

- Add macOS ScreenCaptureKit adapter.
- Add Linux PipeWire adapter.
- Keep unsupported source types clearly labeled.
- Maintain shared capture interface.

**Acceptance:**

- macOS/Linux builds compile and expose platform-appropriate capture capabilities.

## P3-025: Mobile Conversation Mode

**Goal:** Start mobile roadmap separately from desktop overlay UX.

**Tasks:**

- Define mobile-specific UX.
- Reuse shared speech core.
- Prototype microphone conversation translation.
- Add split-screen conversation layout.

**Acceptance:**

- Mobile direction is validated without forcing desktop UX onto mobile.
