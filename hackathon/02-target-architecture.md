# Target architecture and shared contracts

**Proposed implementation; none of the new paths below exist in the baseline.** Keep this repository and Svelte. Add one local Python service for meeting jobs, ASR/LLM adapters, SQLite, and delivery. Avoid a fleet of new microservices in 48 hours.

## One complete path

```mermaid
flowchart TD
    UPLOAD[Audio or video upload] --> WEB[Svelte browser UI]
    MIC[Live microphone + provisional transcript] --> WEB
    WEB --> API[Local FastAPI service]
    TAURI[Optional existing Windows capture client] --> API
    API --> AUDIO[Durable source audio + meeting metadata]
    AUDIO --> JOB[Persistent job queue]
    JOB --> ASR[Local ASR adapter]
    ASR --> TRANSCRIPT[Original timed transcript]
    TRANSCRIPT --> LLM[Local LLM: structured candidates]
    LLM --> CHECK[Schema + evidence + date/owner checks]
    CHECK --> STATE[Final decisions and action state]
    STATE --> RENDER[Deterministic HTML / text minutes]
    RENDER --> OUTBOX[Transactional delivery outbox]
    OUTBOX --> SMTP[Local SMTP / Mailpit]
    TRANSCRIPT -. after P0 .-> SPEAKERS[Optional diarization and name mapping]
    SPEAKERS -.-> STATE
    CHECK -->|Ambiguous item| REVIEW[Focused review or explicit unresolved field]
    REVIEW --> STATE
```

Inference may run in child processes to release VRAM cleanly. API stays responsive while jobs run. Use one GPU job at a time; a durable audio file survives worker failures. LAN UI/API/mail are local network traffic; no external endpoints or inference fallback.

## Required input modes

| Mode | Behavior | Timing |
|---|---|---|
| Audio upload | Accept tested WAV/MP3/M4A/FLAC formats; decode locally, retain source, index audio | 60-minute source: upload start to local email <=900 seconds |
| Video upload | Accept tested MP4/WebM containers; select the speech track, extract audio locally without video inference | Same target, including upload/demux/decode; record source size and transfer time |
| Live microphone | Start/Stop, timer/level, persisted-recording status, provisional timed transcript, then final minutes/email | Measure ongoing ASR lag and Stop-to-email separately; target <=900 seconds after a 60-minute meeting |

Format support is a tested codec/container matrix, not a promise that every file with those extensions decodes. Reject no-audio/corrupt media clearly; let the user choose among multiple audio tracks. No vision model is required. Long files are streamed to disk/decoded in bounded buffers, not loaded completely into RAM. Local video upload size can dominate wall time; benchmark a representative video as well as audio.

Browser capture on the demo host uses `localhost`; LAN browser microphones need trusted HTTPS. Persist sequenced, acknowledged recording chunks continuously before inference. MediaRecorder chunks may depend on earlier container headers: reassemble/demux the ordered stream; do not assume every blob is an independent WAV. Retry duplicates idempotently, detect missing sequences, and limit buffered unacknowledged bytes. If durable recording cannot continue, stop with a visible error rather than pretending audio was saved.

Live ASR consumes completed speech windows from the durable recording, with overlap/padding and stable source offsets. Emit replaceable provisional segments; keep final transcript revisions separate. On the 8 GB GPU, ASR owns the device during capture; final LLM extraction runs after Stop and ASR completion. Reuse valid completed ASR windows, finish any tail/backlog, then reconcile the whole meeting. A second full hour of ASR is not the default finalization step. Inference failure may delay the transcript but must not stop healthy recording.

References: [MediaRecorder chunk behavior](https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder/start), [microphone secure-context requirements](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia). Browser permission denial, device removal, page close, and server loss need explicit UI states. Guaranteed recording after browser closure is outside the browser MVP; a native capture client can add that later.

## Reuse / change / add

| Existing asset | Plan |
|---|---|
| Svelte project, CSS, UI components | Reuse build system and useful visual primitives; add meeting pages with HTTP API |
| Tauri source picker/capture | Reuse if needed for native capture; required browser live mode follows first upload integration and persists audio independently |
| Native Whisper | Keep as existing caption capability/possible later CPU adapter; new batch worker first |
| SQLite/history ideas | Reuse patterns; separate meeting database so old history/schema are not accidentally migrated |
| Overlay and appearance settings | Leave intact; not on the competition's critical path |
| Model downloader | Reuse checksum lessons; new offline manifest/preflight governs the meeting pipeline |
| Meeting API, jobs, LLM, minutes, mail | New implementation |

Recommended page: `/meetings`. It works in an ordinary browser and can also be opened in Tauri. Any shared layout/titlebar must guard native imports and calls in browser mode. Existing caption route can remain available; no need to rewrite the overlay or change frameworks.

## Proposed additions and ownership

```text
src/routes/meetings/                 # Dev B: home, setup, upload/record, progress, minutes
src/lib/components/meetings/         # Dev B: reusable meeting UI
src/lib/api/meetings.ts              # Dev B: HTTP client, no Tauri dependency
contracts/meeting.schema.json        # Dev A owns; both approve changes
services/meeting/
  pyproject.toml + lockfile          # Dev A: pinned Python environment
  api.py                            # Dev A: meeting/job/profile endpoints
  contracts.py                      # Dev A: strict validated models
  jobs.py + pipeline.py             # Dev A: persistent states, stage orchestration
  storage.py                        # Dev A: SQLite transactions and assets
  capture.py                        # Dev B with A: chunk ingest, assembly, recording state
  adapters/asr.py + llm.py           # Dev A: runtime-specific code
  decisions.py                      # Dev A: final state and validation
  review.py                         # Dev A: versioned edits, bounded issues, invalidation
  models.py                         # Dev A: manifest/profile resolution
  rendering.py + templates/          # Dev B: deterministic minutes
  delivery.py                       # Dev B: local SMTP outbox worker
  speakers.py                       # Dev A: later optional diarization/enrollment
  tests/                            # Owning developer: targeted tests
config/profiles/                     # Dev A: laptop8, hospital16, cpu
config/recipient-groups.json         # Dev B: synthetic/local recipients
models/manifest.json                 # Dev A: artifact hashes and local paths
scripts/hackathon/                   # Dev B: prepare, preflight, launch, smoke
evaluation/                         # Dev A metrics; CEO gold labels and reports
artifacts/                          # Ignored recordings/outputs; never commit real data
```

Names describe boundaries, not a demand to create every file before the first result. Start with the few modules required for the vertical slice. Dev A owns schema migrations; Dev B uses the storage interface for delivery transactions.

<details>
<summary><strong>Developer / AI appendix: shared contracts and implementation rules</strong></summary>

## Contract to freeze before parallel development

All times are integer milliseconds relative to the original asset; meeting date/timezone resolves relative dates. IDs are stable strings. Preserve Unicode, original text, and source audio. Version contracts and results.

| Object | Required fields / behavior |
|---|---|
| Meeting | `id`, title, recording date/timezone, selected type, suggested type, output language, participant list, recipient group ID, status |
| AudioAsset | `id`, meeting ID, local storage key, SHA-256, duration, channels, sample rate; source retained |
| Job | ID, meeting ID, state, current stage, error code, frozen resolved model config, timestamps, artifact references |
| Segment | ID, revision, asset ID, start/end, original text, optional words/language spans, nullable speaker cluster ID |
| Action | ID, task, nullable owner and due date, original date expression, status, independent task/owner/date evidence references |
| Evidence | Segment ID + revision + exact quote + start/end; validate reference and source bounds |
| ReviewIssue / TranscriptEdit | Exact revision/span, optional suggestions, disposition, actor and batch provenance; see [review contract](07-transcript-review.md) |
| Event | ID, item ID, kind `propose/confirm/amend/reject/cancel`, sequence, payload, evidence; acceptance assigned by validator |
| MoM snapshot | Meeting ID, revision, decisions/actions, unresolved items, source/model revisions, canonical content hash |
| Delivery | Snapshot ID/hash, configured recipient-group version, stable delivery key/Message-ID, attempt count and SMTP status |

**P0 state:** accepted actions and rejected/unresolved items, with source references. Handle explicit final owner/date corrections across the whole meeting. **P1 expansion:** complete event history and interactive before/after evidence. Do not implement last-mention-wins: a later suggestion does not override a confirmed decision.

API proposal (freeze exact JSON with fixtures at H0–H2):

| Route | Behavior |
|---|---|
| `POST /api/meetings` | Validates metadata and configured recipient group; creates draft |
| `POST /api/meetings/{id}/audio` | Bounded audio/video upload; safe audio decode; durable source + hash |
| `POST /api/meetings/{id}/recordings` | Create live recording session with selected MIME/codec and sequence state |
| `PUT /api/recordings/{id}/chunks/{sequence}` | Idempotent ordered chunk ingest; acknowledge only after durable write |
| `POST /api/recordings/{id}/stop` | Seal recording after final chunk acknowledgment; finalize existing job |
| `POST /api/meetings/{id}/jobs` | Validates profile/assets, freezes config, queues processing |
| `GET /api/jobs/{id}` | State/stage/elapsed/errors; polling is enough initially |
| `GET /api/meetings/{id}` | Meeting, timed transcript, latest minutes, delivery status |
| `GET /api/profiles` | Installed profile/model choices, backend compatibility and readiness |
| `GET /api/meetings/{id}/audio` | Authorized range/playback from stored asset; not arbitrary file paths |
| `PATCH /api/meetings/{id}/review` | Later: versioned correction and dependent-result invalidation |
| `PATCH /api/meetings/{id}/speakers/{cluster}` | Later: explicit cluster-to-participant mapping |

Job states: `queued -> decoding -> transcribing -> extracting -> validating -> rendering -> delivering -> complete`; any stage can enter `failed`, with a retry from a valid checkpoint. `needs_review` applies only where publication cannot proceed under policy. Distinguish job failure from delivery failure; SMTP retries must not rerun ASR.

Live recording state is independent: `starting -> recording -> stopping -> sealed`, or `interrupted`. ASR can be processing or failed while capture remains healthy. Poll the meeting for provisional segments initially; a new socket protocol is unnecessary for the MVP.

## AI implementation rules

- Decode arbitrary user files in a bounded subprocess with format, duration, and size limits. Keep paths generated by the server. Do not trust uploaded filenames.
- Run blocking inference off the API event loop. Save stage artifacts atomically and record completion only afterward.
- Chunk transcripts by timed segments with bounded overlap; extract compact candidates; reconcile all candidates globally so a late correction is not lost.
- LLM receives transcript as untrusted data and has no tools. It cannot choose recipients, invoke external URLs, set `verified`, or issue clinical orders.
- Validate output shape, cited segments/quotes, date interpretation, and explicit commitments. Structural validation alone does not prove semantic truth. Unknown owner/date stays null; ambiguous dose stays unresolved.
- Render official minutes from accepted state, escaping text. Do not ask another unconstrained generation pass to rewrite approved facts.
- Delivery transaction binds snapshot hash and recipient group. SMTP timeout after submission is ambiguous: retain stable IDs, show uncertain status, avoid promising exactly-once delivery.
- Access: loopback single-operator demo first. If opening to LAN, require local authentication and meeting-scoped checks on media/export routes. Keep ports narrow, browser assets local, and inference servers on loopback. Do not claim hospital production readiness.
- Source edits or speaker changes increment revision and invalidate affected extracted fields/snapshots. A distributed snapshot remains immutable; a correction creates a superseding version.
- Manual transcript editing/undo is P0; bounded AI error flags are P1. Follow [07](07-transcript-review.md) for keyboard UX, bulk replacement, Unicode spans, stale-edit conflicts, evidence rebuild and delivery races. Unaccepted suggestions never enter authoritative text.

</details>
