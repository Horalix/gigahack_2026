# Local meeting service

Run from the repository root with Python 3.11 and FFmpeg/FFprobe on `PATH`. Create a dedicated virtual environment outside the OneDrive checkout, then install the pinned environment with its Python: `python -m pip install -r services/meeting/requirements.lock`. The system Python already has unrelated package conflicts, so use the isolated environment for a repeatable run. Runtime models are prepared separately by PBI-003 and must be local before transcription starts.

For **synthetic development only**, set `MOM_SYNTHETIC_DEV=1`, then start `python -m uvicorn services.meeting.api:app --host 127.0.0.1 --port 8000` and `python -m services.meeting.jobs` in separate terminals. The temporary API hook requires `X-Demo-Principal: synthetic-demo` from loopback. Without that opt-in, meeting endpoints deny access. PBI-005 replaces the hook with actual local authentication and object permissions before real data is used.

`MOM_DATA_DIR` optionally selects a directory outside Git and OneDrive. By default the database and recordings use the OS local application-data folder. The source upload stays intact; an audio-only, mono 16 kHz WAV derivative is created for ASR. Audio/video media are probed by FFprobe and decoded by FFmpeg. The source filename is ignored. If a file has multiple audio tracks, pass its FFprobe stream index as `audio_track_index` when uploading.

The API stores jobs; it does not run inference inside the request. The worker claims one GPU job transactionally, renews a lease, and resumes expired claims after a process stops. The transcription checkpoint is written and synced before committing transcript rows. A `ready` job and `transcript_ready` meeting in this slice mean the **transcript** is available; later PBIs add structured minutes and final artifacts. No mail implementation is present.

Current HTTP routes: `GET /api/health`, `GET /api/profiles`, `POST /api/meetings`, `GET /api/meetings/{id}`, `POST /api/meetings/{id}/audio`, `POST /api/meetings/{id}/jobs`, `GET /api/jobs/{id}`, and `POST /api/jobs/{id}/retry`. The [versioned record contract](../../contracts/README.md) defines payload meanings. A new job accepts `profileId`, `asrModelAlias`, and `llmModelAlias`; its resolved choices are frozen in `modelConfig`. Profile listing shows file presence, while job start verifies the selected ASR asset digest. API errors use safe codes and request IDs; they do not echo audio or transcript text.

The explicit limits are 2 GiB upload size, six hours media duration, tested FFmpeg containers/codecs and a bounded decoder process timeout. Unsupported, corrupt, missing-audio and ambiguous multi-track files produce visible errors. These limits are implementation bounds, not a claim that every possible video can be decoded safely on every machine.

If FFmpeg recovers audio despite damaged frames, the asset includes `decodeWarning`. The source stays intact so a reviewer can check for missing speech.
