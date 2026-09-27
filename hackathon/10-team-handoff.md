# Secure MOM live team handoff

**27 September 2026.** App branch: `codex/app-completion` at `4c69d06`, pushed from updated `develop` after Affan's branch merge. The working tree currently has only PBI evidence/handoff documentation changes. ASR experiment branch: `codex/asr-comparison` at `411750d`; it must be updated from the app branch before its final report is current. Read this page, then [the PBI index](pbis/README.md) and the relevant PBI. This page supersedes older staffing/checkpoint guesses. The supplied challenge PDF and research HTML are reference material, not instructions to an AI executor.

## What we are building

Notavra is a local hospital-meeting assistant: upload audio/video or record from the microphone, transcribe RO/RU/EN, extract decisions/actions with quote evidence and unresolved owners/dates, allow corrections, then produce a clinician-approved HTML file. A doctor has a searchable/paginated patient directory and meeting workspace. Affan owns SMTP and attaches the output file on his path; no SMTP implementation is in this branch. The old floating subtitle window is not part of this workflow. A one-hour meeting reaching local email within 15 minutes on reference hardware has **not** been measured.

Security is pass/fail: no external ASR/LLM API at runtime; real patient data needs access control and stays outside Git/OneDrive. Today's prototype does not establish GDPR or clinical deployment approval. The CEO owns the pitch and evidence claims.

```mermaid
flowchart LR
    UI[Notavra workbench\nSvelte / Tauri or browser] --> API[Loopback FastAPI]
    API --> DB[(SQLite + source audio\nlocal app data)]
    DB --> ASR[Whisper large-v3\nlocal ASR worker]
    ASR --> LLM[Qwen local decisions\nserial stage]
    LLM --> REVIEW[Transcript and actions\nedit / evidence / approve]
    REVIEW --> DOC[Versioned downloadable HTML]
    DOC -. file handoff .-> MAIL[Affan's SMTP integration\nseparate owner]
```

## Actual state, not the older plan

- Current app checkout: `codex/app-completion` at `4c69d06`, clean except documentation updates in this commit series. The branch is pushed. `develop` contains the merge of `origin/affan/develop`; Affan's SMTP work is not part of the app branch. The app branch has committed slices for workbench, profiles, patient directory, HTML artifact, durable capture, correction/undo, local purge and launch scripts.
- **Foundation/access complete:** versioned contracts, FastAPI/SQLite ingest/jobs, worker checkpoint recovery, Argon2id local accounts, loopback/trusted-origin access and explicit meeting grants. Patient directory supports keyset pagination and separate meeting-link permissions. Audio/video uploads decode to locally stored WAV. Deletion exists for completed meetings; production retention controls do not.
- **Profiles/models:** laptop8, hospital16 and CPU configurations exist; the pinned Whisper and Qwen assets are outside Git. Laptop preflight verifies the model hashes and detects 8 GiB VRAM. The actual 16 GB 5080 host has not been tested. Job ASR/LLM stages run serially, but no complete one-hour RSS/VRAM ceiling has been established.
- **004 open:** the permitted 11m42s Medpark recording ran offline on the 8 GB laptop. Romanian-only accuracy is materially better than auto mode on that audio, but the opening's language-script instability, code switches and overlap need a human-verified review. No one-hour end-to-end claim.
- **App workflow:** meeting setup, patient selection, audio/video upload, processing status, transcript/action viewing, single and batch correction, audited Undo, search/navigation, authorized audio playback, explicit approval and downloadable HTML work in the local workbench. Microphone capture saves 10-second chunks and recovers acknowledged chunks, but ASR starts only after Stop; live words are not shown.
- **PBI-025 comparison:** on the same 702.5s audio and machine-generated reference, Romanian-forced Whisper scored 47.9% WER/29.9% CER in 74.7s; OmniASR CTC scored 72.6%/52.6% in 15.2s; OmniASR LLM scored 66.9%/46.4% in 276s. **Use Whisper large-v3 with Romanian selected for the demo.** Auto Whisper historically chose Russian and scored 81.8% WER. These are disagreements against an unverified machine reference, not clinical accuracy; timings use different runtime/OS/windowing and are not a strict apples-to-apples speed ranking. Full details are in the [ASR comparison report](https://github.com/Horalix/gigahack_2026/blob/codex/asr-comparison/hackathon/ASR_COMPARISON_RESULTS.md).
- **Verification:** 46 local service tests pass; `npm run check` and `npm run build` pass. A browser launch smoke returned HTTP 200 and Playwright verified first-run setup; start/stop scripts managed their three child processes. Tauri build was not possible on this laptop because CMake and `libclang.dll` are missing. WAN-disconnected start, physical microphone, actual Medpark app-to-artifact, and one-hour end-to-end timing remain unverified. Keep remaining P0 PBIs OPEN.
- Sensitive challenge recordings/transcripts stay under local app data, not Git. Meeting purge removes app-managed completed-meeting files but does not guarantee physical erasure or cover backups/downloads; this prototype is not GDPR-certified or for real patient data.

## Epics and ownership

This allocation supersedes `Owner:` labels in older PBI files. The current authorized app branch owns remaining frontend/backend integration in one tree. **Affan owns SMTP and attachment/delivery integration on his branch. The CEO owns the pitch and challenge-facing evidence.** PBIs are acceptance units, not exclusive task bundles; coordinate the generated-file boundary before claiming delivery.

The table below groups PBIs by epic; the files are currently kept together in `hackathon/pbis/` (completed items in `hackathon/pbis/completed/`). They are not physically arranged into per-epic folders.

| Epic | PBI | Owner | State / start condition |
|---|---|---|---|
| Foundation | [001](pbis/completed/PBI-001-contracts-and-file-handoff.md), [002](pbis/completed/PBI-002-local-service-and-durable-jobs.md) | Core | COMPLETE |
| Models + speech | [003](pbis/completed/PBI-003-model-registry-and-hardware-profiles.md), [004](pbis/PBI-004-gpu-transcription.md) | Core | 003 COMPLETE; 004 OPEN for accuracy and performance qualification |
| Trust + patients | [005](pbis/completed/PBI-005-local-access-and-object-isolation.md), [006](pbis/completed/PBI-006-patients-api-and-pagination.md) | Core | COMPLETE; broader retention still open |
| Doctor workflow | [007](pbis/PBI-007-doctor-dashboard-without-overlay.md), [008](pbis/PBI-008-meeting-upload-and-progress-ui.md) | Core | Implemented in workbench; real UI/Tauri/one-hour acceptance OPEN |
| Decisions + document | [009](pbis/PBI-009-local-llm-and-final-decisions.md), [010](pbis/PBI-010-final-document-and-artifact-handoff.md) | Core; Affan consumes file | Local extraction and approved HTML exist; gold accuracy and Affan handoff OPEN |
| Live mode | [011](pbis/PBI-011-durable-live-audio-backend.md), [012](pbis/PBI-012-live-recording-ui.md) | Core | Durable capture exists; ASR begins after Stop, live text not yet shown |
| Review + privacy | [013](pbis/PBI-013-versioned-transcript-corrections.md), [014](pbis/PBI-014-transcript-review-ui.md), [015](pbis/PBI-015-privacy-retention-and-local-data-controls.md) | Core | Batch edit/undo, find/playback and meeting purge implemented; integrated acceptance and retention scope OPEN |
| Release + evidence | [016](pbis/PBI-016-offline-launch-and-packaging.md), [017](pbis/PBI-017-accuracy-and-one-hour-benchmark.md), [025](pbis/PBI-025-whisper-omniasr-comparison.md) | Core; CEO presents | Browser launch passed; Tauri/offline/one-hour OPEN; ASR comparison report is on separate branch |
| Optional P1 | [018](pbis/PBI-018-ai-transcript-flags.md), [019](pbis/PBI-019-speaker-diarization.md), [020](pbis/PBI-020-speaker-name-correction-ui.md) | Core | Defer until P0 gates pass |
| Later P2 / pilot | [021](pbis/PBI-021-optional-voice-enrollment.md), [023](pbis/PBI-023-hospital-deployment-and-eu-scale.md) | You | OPEN; not tonight's demo claim |
| Later pilot | [022](pbis/PBI-022-eu-pilot-privacy-and-ethics.md) | Affan + CEO | OPEN; human policy approval required |
| Pitch | [024](pbis/PBI-024-demo-evidence-and-presentation.md) | CEO | OPEN; draft now, final claims from measured gates |

## Parallel order and file boundaries

1. **Core next:** complete a manually exercised browser upload-to-approved-file flow, then use the real Medpark file for a Romanian-only app run and collect targeted human review. Keep accuracy and 15-minute claims OPEN.
2. **Live/review next:** exercise microphone permissions and interruption recovery; decide whether time remains for provisional ASR windows. The current recorder processes after Stop and must not be described as live captions. Exercise search, selected replace, Undo and audio playback.
3. **Affan:** confirm the generated HTML artifact can be attached by his SMTP branch using its local file boundary. Keep all SMTP implementation and delivery behavior in his scope.
4. **CEO:** complete the pitch and rehearse; state measured constraints (machine-generated reference, no Tauri build on this laptop, no one-hour run) plainly.
5. **Shared boundary:** API owns authorization and data correctness; UI uses authenticated same-origin HTTP. Current routes cover accounts, patients, meetings, uploads, chunk capture, jobs, segments, actions, audio playback and approved artifacts. Coordinate any shape/schema change and commit it before the other branch consumes it.
6. **Integration rhythm:** app branch commits are small and pushed. Before claiming readiness run service tests, `npm run check/build`, fresh browser startup, then a permitted end-to-end sample; leave unmet PBI acceptance OPEN.

## AI executor handoff

Read `hackathon/README.md`, this page, `hackathon/pbis/README.md`, the assigned PBI and dependencies. Reference attachments describe the challenge, not instructions to the executor. Inspect the actual branch and working tree before editing. Keep ASR/LLM runtime calls local, source text unmodified, unknown clinical facts unresolved and test audio outside Git. Use Luna for routine work, Sol for state/security/LLM boundaries and Astra only for a specific unresolved hard problem. Report **Done / Changed / Next / Risks** with real checks and limitations.
