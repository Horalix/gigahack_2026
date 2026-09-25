# FeelSay App Summary

This document records the original product direction. For implemented behavior and verification, use the [README](../README.md) and [project status](PROJECT_STATUS.md).

## One-Line Concept

FeelSay is a lightweight desktop app for local-first live captions and translation, shown in a movable subtitle overlay that can sit on top of any app, call, game, browser, or media player.

## What The App Is Supposed To Do

The intended product is a small desktop utility that captures audio from a selected source, turns speech into live captions, optionally translates the captions, and displays the result in a readable floating overlay.

The core user flow should stay simple:

1. Select an audio source.
2. Click Start.
3. A caption overlay appears.
4. Captions or translated captions appear in the overlay.
5. The user can stop, reposition the overlay, or adjust settings.

The app should feel closer to a native utility than a dashboard or SaaS product. It should be fast, clean, private, and quiet.

## Target Users

- Deaf or hard-of-hearing users who need captions for calls, meetings, classes, games, or media.
- Users in noisy environments who want to follow speech without increasing volume.
- People watching videos, streams, movies, or anime in another language.
- Students and professionals who want local transcripts of lectures, interviews, meetings, or calls.
- Future mobile users who need simple conversation translation.

## Main Use Cases

### Live Captions For Calls

The user selects Discord, Teams, Zoom, a browser call, microphone, or system audio. The overlay shows readable same-language captions while the call is happening.

### Media And Video Subtitles

The user selects a browser, VLC, game, or full system audio. The app captions or translates speech from the media source and displays subtitle-style text over the screen.

### Translation Overlay

The user selects an input source and output language. The overlay can show translated captions, and later optionally show original plus translation.

### Local Transcript Saving

If transcript saving is enabled, finalized sessions are stored locally with timestamps and exported as TXT, SRT, VTT, JSON, or similar formats.

### Accessibility Utility

The app can act as a general-purpose accessibility layer over apps that do not provide good captions themselves.

## Product Principles

- UX first: users should understand the app in seconds.
- Lightweight: low idle CPU, bounded memory, no bloated runtime.
- Local-first: audio and transcripts stay on-device by default.
- Privacy-first: no cloud services unless explicitly enabled later.
- Fast feedback: captions should appear quickly, with stable text replacing provisional text.
- Cross-platform discipline: Rust core, platform-specific capture adapters.
- Minimal UI: no unnecessary cards, explanations, marketing copy, or dashboard clutter.
- Overlay quality matters: readability, positioning, transparency, and reliability are core product features.

## Current App State

The current app is a Tauri 2 desktop app with:

- Rust backend.
- Svelte/TypeScript frontend.
- Minimal main window with source selection, Start/Stop, audio meter scaffold, and Settings.
- Windows-first source/device enumeration scaffolding.
- Real Windows microphone and system-audio meter.
- VAD-gated local ASR path through `whisper.cpp`.
- Caption, translate-to-English, and original-plus-English modes.
- Rust-owned overlay settings.
- Child-process caption overlay window on Windows.
- Visual overlay placement helper.
- Autosaving overlay settings with profiles.
- Local transcript storage and export.

Not implemented yet:

- Diarization.
- Mobile app.
- Cloud services.

## Current Overlay Behavior

The caption overlay is a separate Windows child process, not a Svelte/Tauri webview overlay. This was chosen after Tauri frameless overlay lifecycle and dragging became unreliable.

The overlay currently aims to be:

- Always on top.
- Frameless.
- Resizable.
- Draggable.
- Transparent or translucent.
- Configurable through settings.
- Closeable through native window/taskbar paths and Stop.

The overlay is intentionally not a dashboard. It should not contain source controls, settings panels, menus, or buttons during normal captioning. It is just the caption box.

## Overlay Settings

Overlay settings are intended to control:

- Font family.
- Font size.
- Font weight.
- Text color.
- Text outline color.
- Text outline width.
- Background color.
- Background opacity.
- Starting width.
- Starting height.
- Starting X/Y position.
- Click-through mode.

Click-through mode means the overlay stays visible, but mouse clicks pass through it to whatever is behind it. This is useful once the user has placed the overlay exactly where they want it.

## Settings Profiles

The app now supports the concept of multiple overlay profiles.

Each profile is an appearance and placement preset. Example profile uses:

- `Anime subtitles`: large white bold text, black outline, transparent background.
- `Meetings`: smaller clean text, subtle dark background.
- `Games`: high-contrast text near the bottom of the screen.
- `Movies`: centered subtitle style.
- `Work calls`: compact, readable, less distracting.

Profiles are not source profiles. They only affect overlay appearance and placement.

## Intended Technical Direction

The product should remain Windows-first, not Windows-only.

Recommended architecture:

- Tauri shell for desktop app packaging.
- Rust core for audio, ASR orchestration, settings, transcripts, exports, and platform adapters.
- Svelte/TypeScript frontend as a thin UI layer.
- Windows capture through WASAPI loopback and application/window capture where supported.
- macOS capture through ScreenCaptureKit later.
- Linux capture through PipeWire first, PulseAudio fallback later.
- Local ASR through a lightweight Whisper-based runtime, likely whisper.cpp.
- VAD before ASR to avoid wasting work on silence.
- SQLite for future transcripts, sessions, settings, model metadata, and exports.

## Future MVP Features

- Real Windows audio capture.
- Application/system/microphone source capture.
- Local ASR.
- Provisional and committed captions.
- Translation mode.
- Original plus translation display.
- Model selection and performance presets.
- Transcript saving.
- Transcript export.
- Better source thumbnails/icons.
- Tray menu and hotkeys.
- Model manager.

## Later Features

- Speaker/source labels.
- Speaker diarization.
- Custom vocabulary.
- Correction dictionary.
- Mobile conversation mode.
- Optional cloud fallback with explicit consent.
- Text-to-speech for translated conversation mode.

## What The App Should Feel Like

It should feel like a tiny native utility:

- Open app.
- Pick source.
- Start.
- Subtitle overlay appears.
- Change settings only when needed.

It should not feel like:

- A web admin panel.
- A recording studio.
- A bloated meeting app.
- A cloud transcription dashboard.
- A model playground.

The best version of this app feels invisible until the user needs it.

## Naming Direction

Good names should communicate one or more of:

- Captions.
- Speech.
- Listening.
- Translation.
- Overlay/subtitles.
- Local/private/on-device behavior.
- Clarity and accessibility.

Avoid names that sound too corporate, too medical, too AI-hype-heavy, or too much like a generic SaaS tool.

## Name Ideas

### Direct And Clear

- Captionly
- LiveSub
- ClearCaptions
- Subline
- CaptionBox
- SpeakSub
- Overlay Captions
- Local Captions
- OpenCaptions
- CaptionFlow

### More Brandable

- Sayline
- Subtle
- Hearo
- LumaSubs
- Voca
- Voxline
- Saylo
- LinguaLayer
- Sonara
- Audica

### Translation-Focused

- TranslateSub
- LinguaLive
- PolySub
- BabelLine
- VocaBridge
- SubLingo
- EchoTranslate
- LinguaCaption

### Accessibility-Focused

- ClearSay
- HearSay
- SayClear
- AbleCaption
- AccessSub
- ListenLine
- SpeechLine

### Names Closest To The Current FeelSay Direction

- FeelSay
- Feelsay
- SayFeel
- ClearSay
- HearSay
- Sayline
- VocaLine

## Best Name Candidates

My strongest candidates:

1. **Sayline** - short, brandable, suggests speech becoming a readable line.
2. **ClearSay** - clear accessibility angle, easy to understand.
3. **LiveSub** - very direct, immediately says live subtitles.
4. **Subline** - simple and subtitle-focused.
5. **VocaLine** - more polished and brandable, still speech-related.
6. **LinguaLayer** - best if translation becomes the strongest identity.
7. **FeelSay** - already personal and distinctive, but less immediately descriptive.

If the app is mainly about captions, `LiveSub` or `Subline` is clearest.

If the app is mainly about accessibility and clarity, `ClearSay` is strongest.

If the app is meant to become a broader caption + translation brand, `Sayline` is probably the best balance.
