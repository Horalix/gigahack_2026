# FeelSay

Windows desktop captions with local speech recognition and a movable subtitle overlay.

## Use

1. Install the Windows setup package and open FeelSay.
2. Choose **Select Source**: system playback, a microphone, or a supported application.
3. Press **Start**. First use downloads and verifies a 142 MB multilingual speech model; subsequent captions work offline.
4. Drag the subtitle box to move it; drag its edges to resize. Its corner control changes text size, colors, opacity, and transcript saving immediately.
5. Press **Stop** to release capture and recognition resources.

**Settings** contains appearance presets, fonts, colors, opacity, always-on-top and click-through behavior, language, English translation, and transcript history. Changes apply to the running session. Language changes apply to the next recognition update.

System audio follows the playback device selected when Start is pressed. If Windows changes that device, FeelSay stops and asks you to start again. Applications routed to another output may need that output selected in Windows, or application capture. Application capture requires Windows build 20348 or newer and includes the selected process and its child processes. Protected or inaccessible audio may not be capturable. Application lists are choices, not live screenshot previews.

Recognition runs on the CPU, with up to four threads and no GPU requirement. Accuracy depends on the language, recording quality, overlapping voices, and available CPU time. English translation is optional; original plus translation performs two recognition passes. Reliable speaker identification is not shipped.

## Optional transcripts and privacy

Saving is **off by default**. Enable or disable it in Settings or the overlay corner control without restarting captions. Only finalized speech captured after enabling is eligible for saving. Enabling begins a fresh recognition segment; disabled speech is never backfilled.

Settings > Transcripts provides history, viewing, copying, TXT/SRT/VTT/JSON export, and individual deletion. Files include session timing, source labels, finalized text, and translation when available. Transcript saving stops with a visible notice at 100 sessions or 64 MiB of database data. Exports have a separate 64 MiB limit. Delete older sessions to free capacity, then enable saving again.

Audio and transcript content are not uploaded. The network is used to obtain the speech model. Settings, model files, and transcripts live under `%APPDATA%/app.feelsay.desktop`. The native overlay uses a temporary current-caption file, held with Windows delete-on-close protection and removed when capture stops or the owning process exits; it is not transcript history. SQLite secure deletion and deletion of FeelSay-managed exports prevent deleted history from remaining accessible in the application. Copies made elsewhere, clipboard history, OS backups, and forensic recovery from storage are outside the application's deletion controls.

Click-through makes the overlay controls inaccessible by mouse; turn it off in Settings. Optional shortcuts are Ctrl+Shift+C (captions), Ctrl+Shift+O (overlay visibility), and Ctrl+Shift+X (click-through), when another application has not reserved them.

## Build on Windows

End users need no Python, FFmpeg, CUDA, compiler, or manually installed speech model. WebView2 is installed by the installer if missing. Developer prerequisites are Node.js 22+, Rust/Cargo, Visual Studio Build Tools with Desktop development with C++, Windows SDK, CMake, and LLVM/libclang.

```powershell
npm ci
$env:LIBCLANG_PATH = 'C:/Program Files/LLVM/bin'
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows-build.ps1 -Task package
```

The helper discovers installed Visual Studio and SDK headers. `LIBCLANG_PATH` must contain `libclang.dll`. LLVM and CMake are build dependencies only. Generated Windows bindings are required; do not set `WHISPER_DONT_GENERATE_BINDINGS`.

Installers are generated under `src-tauri/target/release/bundle/nsis` and `bundle/msi`. Builds are currently unsigned. No release is automatically published.

## Validation

```powershell
npm run check
npm run test:ui
npm run test:native-overlay # after building the Windows executable
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows-build.ps1 -Task test
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows-build.ps1 -Task lint
```

UI tests use an isolated headless Edge profile on Windows and mock native IPC boundaries. Rust tests exercise persistence and signal processing. A separate ignored test accepts controlled WAV/model fixtures; it never plays audio or captures the desktop. See [project status](docs/PROJECT_STATUS.md), [engineering notes](docs/ENGINEERING_NOTES.md), and [installer verification](docs/installer-smoke-test.md) for evidence and remaining native checks. A successful package build is not proof of live audio capture or clean-machine installation.

Controlled native checks have also exercised installed builds, process and explicit-output audio capture, live transcript consent, exports/deletion, and repeated Start/Stop sessions. Microphone, clean-machine setup, interactive overlay movement/menu behavior, and broader speech accuracy remain release-verification limits.

For controlled recognition checks, set `FEELSAY_TEST_MODEL` to the pinned base-model file and `FEELSAY_TEST_WAV` to the official whisper.cpp `samples/jfk.wav`, then run the Windows helper with `-Task fixtures -Release`. Optional `FEELSAY_TEST_REPETITIONS=120` exercises repeated segments in one model session with saving off and on. It processes prerecorded samples without playing or capturing audio.
