# Target architecture and shared contracts

**Proposed implementation; none of the new paths below exist in the baseline.** Keep this repository and Svelte. Add one local Python service for meeting jobs, ASR/LLM adapters, SQLite, and delivery. Avoid a fleet of new microservices in 48 hours.

## One complete path

```mermaid
flowchart TD
    WEB[Svelte browser UI] --> API[Local FastAPI service]
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

## Reuse / change / add

| Existing asset | Plan |
|---|---|
| Svelte project, CSS, UI components | Reuse build system and useful visual primitives; add meeting pages with HTTP API |
| Tauri source picker/capture | Keep available; add durable recording only after upload P0 works |
| Native Whisper | Keep as existing caption capability/possible later CPU adapter; new batch worker first |
| SQLite/history ideas | Reuse patterns; separate meeting database so old history/schema are not accidentally migrated |
| Overlay and appearance settings | Leave intact; not on the competition's critical path |
| Model downloader | Reuse checksum lessons; new offline manifest/preflight governs the meeting pipeline |
| Meeting API, jobs, LLM, minutes, mail | New implementation |

Recommended page: `/meetings`. It works in an ordinary browser and can also be opened in Tauri. Any shared layout/titlebar must guard native imports and calls in browser mode. Existing caption route can remain available; no need to rewrite the overlay or change frameworks.

## Proposed additions and ownership

```text
src/routes/meetings/                 # Dev B: home, setup, upload, progress, minutes
src/lib/components/meetings/         # Dev B: reusable meeting UI
src/lib/api/meetings.ts              # Dev B: HTTP client, no Tauri dependency
contracts/meeting.schema.json        # Dev A owns; both approve changes
services/meeting/
  pyproject.toml + lockfile          # Dev A: pinned Python environment
  api.py                            # Dev A: meeting/job/profile endpoints
  contracts.py                      # Dev A: strict validated models
  jobs.py + pipeline.py             # Dev A: persistent states, stage orchestration
  storage.py                        # Dev A: SQLite transactions and assets
  adapters/asr.py + llm.py           # Dev A: runtime-specific code
  decisions.py                      # Dev A: final state and validation
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
| Event | ID, item ID, kind `propose/confirm/amend/reject/cancel`, sequence, payload, evidence; acceptance assigned by validator |
| MoM snapshot | Meeting ID, revision, decisions/actions, unresolved items, source/model revisions, canonical content hash |
| Delivery | Snapshot ID/hash, configured recipient-group version, stable delivery key/Message-ID, attempt count and SMTP status |

**P0 state:** accepted actions and rejected/unresolved items, with source references. Handle explicit final owner/date corrections across the whole meeting. **P1 expansion:** complete event history and interactive before/after evidence. Do not implement last-mention-wins: a later suggestion does not override a confirmed decision.

API proposal (freeze exact JSON with fixtures at H0–H2):

| Route | Behavior |
|---|---|
| `POST /api/meetings` | Validates metadata and configured recipient group; creates draft |
| `POST /api/meetings/{id}/audio` | Bounded upload; safe decode; durable asset + hash |
| `POST /api/meetings/{id}/jobs` | Validates profile/assets, freezes config, queues processing |
| `GET /api/jobs/{id}` | State/stage/elapsed/errors; polling is enough initially |
| `GET /api/meetings/{id}` | Meeting, timed transcript, latest minutes, delivery status |
| `GET /api/profiles` | Installed profile/model choices, backend compatibility and readiness |
| `GET /api/meetings/{id}/audio` | Authorized range/playback from stored asset; not arbitrary file paths |
| `PATCH /api/meetings/{id}/review` | Later: versioned correction and dependent-result invalidation |
| `PATCH /api/meetings/{id}/speakers/{cluster}` | Later: explicit cluster-to-participant mapping |

Job states: `queued -> decoding -> transcribing -> extracting -> validating -> rendering -> delivering -> complete`; any stage can enter `failed`, with a retry from a valid checkpoint. `needs_review` applies only where publication cannot proceed under policy. Distinguish job failure from delivery failure; SMTP retries must not rerun ASR.

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

</details>
