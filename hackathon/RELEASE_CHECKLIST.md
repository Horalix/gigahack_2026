# Notavra release checklist

**State: demo candidate; not a clinical release.** Update this file after each final rehearsal. A checked code test does not substitute for a hardware or human-review gate.

## Verified in this checkout

- [x] Doctor dashboard, searchable/paginated patient directory, meeting creation and local audio/video upload are implemented.
- [x] Local authentication, meeting access checks, durable jobs/capture chunks, retry/checkpoint handling and meeting purge are implemented.
- [x] Local Whisper and Qwen inference produce a transcript and evidence-linked decisions that require human review.
- [x] Transcript edits, bulk replacement, undo, search and source-audio passage seeking are implemented.
- [x] Approval creates a revisioned, checksummed HTML artifact.
- [x] Laptop ASR batch 2 passed two identical runs on the same 702.549s Romanian WAV; WER 51.64%, CER 35.28% against the saved machine reference.
- [x] `python -m pytest services/meeting/tests -q`: 54 passed.
- [x] `npm run test:ui`: 5 passed, including mocked provisional words during microphone capture and correction/undo invalidation behavior.
- [x] `npm run check`: 0 errors/warnings; `npm run build`: passed.
- [x] `scripts/hackathon/preflight.ps1 -ProfileId laptop8`: passed on this RTX 3070 Ti laptop.
- [x] One real 20-second Romanian sample window passed through local preview API on the 3070 Ti in 14.42s including request/model setup; temporary audio was removed and VRAM returned to 0 MiB.

## Must remain disclosed as open

- [ ] Full one-hour upload-to-approved-file timing at or below 15 minutes. Last integrated run projected to 20.0 minutes/hour at its then-current profile; a standalone batch-2 ASR probe plus the earlier LLM run projects to 12.2, but the app has not been retimed end to end under batch 2. No one-hour test has been completed.
- [ ] RTX 5080 / 16 GB host test. `hospital16` batch 4 and CUDA 13 are configured but not physically verified here.
- [ ] WAN-disconnected launch and external-egress observation on the final demo build.
- [ ] Physical microphone recording, permission-loss and user-visible preview-lag behavior on the demo device. Mocked UI plus one real sample-window API test pass, but no ambient/microphone run has been performed.
- [ ] Human review of Romanian transcription, medical terms, negation, names, numbers and extracted actions. The Microsoft share page was inaccessible; the saved reference is machine-generated.
- [ ] Integrated real-audio browser/Tauri manual review of search, passage playback, edit, reprocess, approval and artifact download after the latest branch commits.
- [ ] Packaged release build and fresh-machine install. Tauri dev launch and service health were previously verified; that does not prove packaging.
- [ ] Affan confirms his SMTP path can attach the generated file; his delivery implementation is outside this branch.

## Privacy and release boundary

- Use synthetic patient details and only the challenge recording whose use was authorized. Keep transcripts, references, model weights and credentials outside Git and synced folders.
- This prototype is local-first and has local access controls. It is not GDPR-certified, clinically validated, or approved for real patient care. Purge does not prove physical erasure of backups, SSD snapshots or downloaded copies.
- Before presenting, confirm no private transcript, API key, model file or patient data is staged: `git status --short` and `git diff --cached --name-only`.
