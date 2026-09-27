import io
import subprocess
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi.testclient import TestClient

from services.meeting.api import create_app
from services.meeting.storage import Storage


def short_wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\0\0" * 16000)
    return buffer.getvalue()


def client(tmp_path, monkeypatch) -> TestClient:
    from services.meeting.adapters import llm

    monkeypatch.setattr("services.meeting.api.host_gpu_memory_gb", lambda: 16.0)
    monkeypatch.setattr("services.meeting.api.host_gpu_free_memory_gb", lambda: 12.0)
    monkeypatch.setattr("services.meeting.api.host_available_memory_gb", lambda: 12.0)
    monkeypatch.setattr("services.meeting.cuda_runtime.configure_cuda_dll_search", lambda: (True, None))
    runtime = tmp_path / "llama-server.exe"
    runtime.touch()
    monkeypatch.setattr(llm, "_runtime_path", lambda _model: runtime)
    app = create_app(tmp_path)
    org_id = app.state.store.installation_organization()
    app.state.auth.create_user(org_id, "test-admin", "correct horse battery staple", "administrator", bootstrap=True)
    api = TestClient(app, headers={"Origin": "http://localhost:1420"})
    login = api.post("/api/auth/login", json={"username": "test-admin", "password": "correct horse battery staple"})
    assert login.status_code == 200, login.text
    return api


def meeting(api: TestClient) -> str:
    response = api.post("/api/meetings", json={
        "contractVersion": "1.0", "title": "Synthetic test meeting",
        "recordedAt": "2026-09-26T09:00:00Z", "timeZone": "Europe/Chisinau",
        "outputLanguage": "en", "patientLinkIds": [],
    })
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_upload_is_durable_and_filename_is_generated(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    meeting_id = meeting(api)
    response = api.post(f"/api/meetings/{meeting_id}/audio",
        files={"file": ("../../patient-name.wav", short_wav(), "audio/wav")})
    assert response.status_code == 201, response.text
    asset = response.json()
    assert asset["durationMs"] == 1000
    assert "patient-name" not in asset["storageKey"]
    store = Storage(tmp_path)
    assert store.resolve_key(asset["storageKey"]).exists()
    org_id = store.installation_organization()
    assert store.resolve_key(store.latest_asset(meeting_id, org_id)["decoded_key"]).exists()
    assert store.latest_asset(meeting_id, org_id)["id"] == asset["id"]
    playback = api.get(f"/api/meetings/{meeting_id}/audio")
    assert playback.status_code == 200 and playback.headers["content-type"].startswith("audio/wav")
    assert len(playback.content) > 44
    anonymous = TestClient(api.app, headers={"Origin": "http://localhost:1420"})
    assert anonymous.get(f"/api/meetings/{meeting_id}").status_code == 401


def test_recovered_decoder_error_is_visible_after_reload(tmp_path, monkeypatch):
    from services.meeting import media

    original_run = media._run

    def recovered_frame(args, timeout):
        result = original_run(args, timeout)
        if args[0] == "ffmpeg":
            result.stderr = b"synthetic recoverable frame error"
        return result

    monkeypatch.setattr(media, "_run", recovered_frame)
    api = client(tmp_path, monkeypatch)
    meeting_id = meeting(api)
    response = api.post(f"/api/meetings/{meeting_id}/audio",
        files={"file": ("synthetic.wav", short_wav(), "audio/wav")})
    assert response.status_code == 201, response.text
    assert "decoder reported" in response.json()["decodeWarning"]
    saved = api.get(f"/api/meetings/{meeting_id}")
    assert saved.json()["asset"]["decodeWarning"] == response.json()["decodeWarning"]


def test_duplicate_api_job_start_keeps_one_job(tmp_path, monkeypatch):
    from services.meeting import models

    api = client(tmp_path, monkeypatch)
    meeting_id = meeting(api)
    upload = api.post(f"/api/meetings/{meeting_id}/audio",
        files={"file": ("synthetic.wav", short_wav(), "audio/wav")})
    assert upload.status_code == 201, upload.text
    monkeypatch.setattr(models, "resolve_profile", lambda profile_id, **kwargs: {"profile_id": "laptop8", "models": {"asr": {"path": "synthetic"}, "llm": {"path": "synthetic"}}})
    monkeypatch.setattr(models, "validate_assets", lambda config, kinds: None)
    first = api.post(f"/api/meetings/{meeting_id}/jobs", json={"profileId": "laptop8"})
    second = api.post(f"/api/meetings/{meeting_id}/jobs", json={"profileId": "laptop8"})
    assert first.status_code == second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["modelConfig"]["profile_id"] == "laptop8"


def test_new_job_freezes_selected_model_settings(tmp_path, monkeypatch):
    from services.meeting import models

    monkeypatch.setattr(models, "validate_assets", lambda config, kinds: None)
    api = client(tmp_path, monkeypatch)
    meeting_id = meeting(api)
    def upload_and_start(beam_size, runtime):
        uploaded = api.post(f"/api/meetings/{meeting_id}/audio",
            files={"file": ("synthetic.wav", short_wav(), "audio/wav")})
        assert uploaded.status_code == 201, uploaded.text
        monkeypatch.setenv("MOM_ASR_BEAM_SIZE", str(beam_size))
        monkeypatch.setenv("MOM_LLM_RUNTIME", runtime)
        return api.post(f"/api/meetings/{meeting_id}/jobs",
            json={"profileId": "laptop8", "asrModelAlias": "whisper-large-v3-local",
                  "language": "ro" if beam_size == 3 else "auto"})

    first = upload_and_start(3, "cuda12")
    second = upload_and_start(4, "cuda13")
    assert first.status_code == second.status_code == 202
    assert first.json()["id"] != second.json()["id"]
    assert first.json()["modelConfig"]["models"]["asr"]["beam_size"] == 3
    assert second.json()["modelConfig"]["models"]["asr"]["beam_size"] == 4
    assert first.json()["modelConfig"]["models"]["asr"]["language"] == "ro"
    assert second.json()["modelConfig"]["models"]["asr"]["language"] == "auto"
    assert first.json()["modelConfig"]["models"]["llm"]["runtime"] == "cuda12"
    assert second.json()["modelConfig"]["models"]["llm"]["runtime"] == "cuda13"
    stored = api.get(f"/api/jobs/{first.json()['id']}")
    assert stored.json()["modelConfig"]["models"]["asr"]["beam_size"] == 3


def test_reprocessing_same_asr_segment_ids_creates_a_new_revision(tmp_path, monkeypatch):
    from services.meeting.adapters import asr
    from services.meeting import decisions, models
    from services.meeting.jobs import run_once

    api = client(tmp_path, monkeypatch)
    meeting_id = meeting(api)
    upload = api.post(f"/api/meetings/{meeting_id}/audio",
        files={"file": ("synthetic.wav", short_wav(), "audio/wav")})
    assert upload.status_code == 201, upload.text
    monkeypatch.setattr(models, "resolve_profile", lambda profile_id, **kwargs: {
        "profile_id": profile_id, "models": {"asr": {"path": "synthetic"}, "llm": {"path": "synthetic"}}})
    monkeypatch.setattr(models, "validate_assets", lambda config, kinds: None)
    monkeypatch.setattr(asr, "transcribe_audio", lambda *args, **kwargs: {"segments": [{
        "id": "stable-source-segment", "transcriptRevision": 1, "startMs": 0, "endMs": 500,
        "text": "Original words", "language": "en", "origin": "asr", "words": [],
    }], "metrics": {}})
    monkeypatch.setattr(decisions, "extract_decisions", lambda segments, *args, **kwargs: {
        "transcriptRevision": segments[0]["transcript_revision"], "modelAlias": "test-llm",
        "items": [], "requiresHumanReview": True,
    })

    first_job = api.post(f"/api/meetings/{meeting_id}/jobs", json={"profileId": "laptop8"}).json()
    store = api.app.state.store
    assert run_once(store, "worker-first")
    first_segment = api.get(f"/api/meetings/{meeting_id}").json()["segments"][0]
    correction = api.put(f"/api/meetings/{meeting_id}/segments/{first_segment['id']}", json={
        "transcriptRevision": first_segment["transcriptRevision"], "text": "Corrected words",
    })
    assert correction.status_code == 200, correction.text

    second_job = api.post(f"/api/meetings/{meeting_id}/jobs", json={"profileId": "laptop8"}).json()
    assert second_job["id"] != first_job["id"]
    assert run_once(store, "worker-second")
    updated = api.get(f"/api/meetings/{meeting_id}").json()["segments"][0]
    assert updated["id"] != first_segment["id"]
    assert updated["text"] == "Original words"
    assert updated["transcriptRevision"] == first_segment["transcriptRevision"] + 2


def test_16gb_profile_is_rejected_on_8gb_gpu(tmp_path, monkeypatch):
    import services.meeting.api as api_module
    api = client(tmp_path, monkeypatch)
    meeting_id = meeting(api)
    uploaded = api.post(f"/api/meetings/{meeting_id}/audio",
        files={"file": ("synthetic.wav", short_wav(), "audio/wav")})
    assert uploaded.status_code == 201
    monkeypatch.setattr(api_module, "host_gpu_memory_gb", lambda: 8)
    response = api.post(f"/api/meetings/{meeting_id}/jobs", json={"profileId": "hospital16"})
    assert response.status_code == 422
    assert response.json()["code"] == "PROFILE_INCOMPATIBLE"


def test_low_available_ram_refuses_job_before_queueing(tmp_path, monkeypatch):
    import services.meeting.api as api_module
    api = client(tmp_path, monkeypatch)
    meeting_id = meeting(api)
    uploaded = api.post(f"/api/meetings/{meeting_id}/audio",
        files={"file": ("synthetic.wav", short_wav(), "audio/wav")})
    assert uploaded.status_code == 201
    monkeypatch.setattr(api_module, "host_available_memory_gb", lambda: 2.5)
    response = api.post(f"/api/meetings/{meeting_id}/jobs", json={"profileId": "laptop8", "language": "ro"})
    assert response.status_code == 503
    assert response.json()["code"] == "SYSTEM_MEMORY_LOW"
    with api.app.state.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM jobs WHERE state = 'queued'").fetchone()[0] == 0


def test_low_free_vram_refuses_job_before_queueing(tmp_path, monkeypatch):
    import services.meeting.api as api_module
    api = client(tmp_path, monkeypatch)
    meeting_id = meeting(api)
    uploaded = api.post(f"/api/meetings/{meeting_id}/audio",
        files={"file": ("synthetic.wav", short_wav(), "audio/wav")})
    assert uploaded.status_code == 201
    monkeypatch.setattr(api_module, "host_gpu_free_memory_gb", lambda: 3.0)
    response = api.post(f"/api/meetings/{meeting_id}/jobs", json={"profileId": "laptop8", "language": "ro"})
    assert response.status_code == 503
    assert response.json()["code"] == "GPU_MEMORY_LOW"
    with api.app.state.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM jobs WHERE state = 'queued'").fetchone()[0] == 0


def test_no_audio_and_invalid_source_are_rejected(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    meeting_id = meeting(api)
    video = tmp_path / "silent.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=32x32:r=1:d=1",
                    "-an", "-c:v", "mpeg4", str(video)], check=True)
    response = api.post(f"/api/meetings/{meeting_id}/audio",
        files={"file": ("silent.mp4", video.read_bytes(), "video/mp4")})
    assert response.status_code == 422
    assert response.json()["code"] == "NO_AUDIO_TRACK"
    assert Storage(tmp_path).latest_asset(meeting_id, Storage(tmp_path).installation_organization()) is None


def test_video_with_multiple_audio_tracks_requires_selection(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    meeting_id = meeting(api)
    video = tmp_path / "two-audio-tracks.mp4"
    subprocess.run([
        "ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=32x32:r=1:d=1",
        "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
        "-map", "0:v", "-map", "1:a", "-map", "2:a", "-t", "1", "-c:v", "mpeg4",
        "-c:a", "aac", str(video),
    ], check=True)
    first = api.post(f"/api/meetings/{meeting_id}/audio",
        files={"file": ("video.mp4", video.read_bytes(), "video/mp4")})
    assert first.status_code == 422, first.text
    assert first.json()["code"] == "AUDIO_TRACK_REQUIRED"
    second_index = first.json()["details"]["trackIndices"].split(",")[1]
    chosen = api.post(f"/api/meetings/{meeting_id}/audio?audio_track_index={second_index}",
        files={"file": ("video.mp4", video.read_bytes(), "video/mp4")})
    assert chosen.status_code == 201, chosen.text
    assert chosen.json()["audioTrackIndex"] == int(second_index)
    assert chosen.json()["mediaType"] == "video/mp4"


def test_size_limit_and_write_failure_leave_no_source(tmp_path, monkeypatch):
    import services.meeting.api as api_module
    monkeypatch.setattr(api_module, "MAX_UPLOAD_BYTES", 64)
    api = client(tmp_path, monkeypatch)
    meeting_id = meeting(api)
    response = api.post(f"/api/meetings/{meeting_id}/audio",
        files={"file": ("x.wav", short_wav(), "audio/wav")})
    assert response.status_code == 413
    assert list((tmp_path / "assets" / meeting_id).glob("*")) == []
    monkeypatch.setattr(api_module, "MAX_UPLOAD_BYTES", 2 * 1024 * 1024 * 1024)

    def failed_record(*args):
        raise OSError("synthetic database storage failure")

    monkeypatch.setattr(api.app.state.store, "create_asset", failed_record)
    failed = api.post(f"/api/meetings/{meeting_id}/audio",
        files={"file": ("synthetic.wav", short_wav(), "audio/wav")})
    assert failed.status_code == 507
    assert list((tmp_path / "assets" / meeting_id).glob("*")) == []


def test_claims_are_unique_and_expired_worker_resumes(tmp_path):
    from services.meeting.auth import AuthService
    store = Storage(tmp_path)
    org_id = store.installation_organization()
    actor = AuthService(store).create_user(org_id, "test-clinician", "correct horse battery staple", "clinician", bootstrap=True)
    meeting_row = store.create_meeting(actor, {"title": "Synthetic", "recordedAt": "2026-09-26T09:00:00Z",
        "timeZone": "Europe/Chisinau", "outputLanguage": "en"})
    asset_id = "asset-test"
    store.create_asset(meeting_row["id"], org_id, {"id": asset_id, "source_key": "assets/source",
        "source_sha256": "a" * 64, "decoded_key": "assets/decoded", "duration_ms": 1000,
        "source_offset_ms": 0, "size_bytes": 100, "media_type": "audio/wav", "audio_track_index": 0,
        "kind": "audio"})
    config = {"profile_id": "laptop8", "models": {"asr": {"path": "fixture"}}}
    first = store.create_or_get_job(meeting_row["id"], org_id, asset_id, config)
    assert store.create_or_get_job(meeting_row["id"], org_id, asset_id, config)["id"] == first["id"]
    claimed = store.claim_job("worker-a")
    assert claimed["id"] == first["id"]
    assert store.claim_job("worker-b") is None
    with store.transaction() as db:
        db.execute("UPDATE jobs SET lease_until=? WHERE id=?", (time.time() - 1, first["id"]))
    resumed = store.claim_job("worker-b")
    assert resumed["id"] == first["id"]
    assert resumed["attempts"] == 2
    assert store.finish_job(first["id"], "worker-a", "ready") is False
    assert store.finish_job(first["id"], "worker-b", "failed", "MODEL_NOT_READY", "Local model missing")
    assert store.retry_job(first["id"], org_id)["state"] == "queued"
    assert store.get_job(first["id"], org_id)["error_code"] is None


def test_parallel_workers_cannot_claim_the_same_gpu_job(tmp_path):
    from services.meeting.auth import AuthService
    store = Storage(tmp_path)
    org_id = store.installation_organization()
    actor = AuthService(store).create_user(org_id, "test-clinician", "correct horse battery staple", "clinician", bootstrap=True)
    row = store.create_meeting(actor, {"title": "Synthetic",
        "recordedAt": "2026-09-26T09:00:00Z", "timeZone": "Europe/Chisinau", "outputLanguage": "en"})
    store.create_asset(row["id"], org_id, {"id": "asset-parallel", "source_key": "assets/source",
        "source_sha256": "a" * 64, "decoded_key": "assets/decoded", "duration_ms": 1000,
        "source_offset_ms": 0, "size_bytes": 100, "media_type": "audio/wav",
        "audio_track_index": 0, "kind": "audio"})
    store.create_or_get_job(row["id"], org_id, "asset-parallel", {"profile_id": "test"})
    barrier = Barrier(2)

    def claim(owner):
        barrier.wait()
        return Storage(tmp_path).claim_job(owner)

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim, ["worker-a", "worker-b"]))
    assert sum(item is not None for item in claims) == 1


def test_worker_reuses_durable_transcript_after_commit_failure(tmp_path, monkeypatch):
    from services.meeting.adapters import asr
    from services.meeting import decisions
    from services.meeting.jobs import run_once

    api = client(tmp_path, monkeypatch)
    meeting_id = meeting(api)
    upload = api.post(f"/api/meetings/{meeting_id}/audio",
        files={"file": ("synthetic.wav", short_wav(), "audio/wav")},
    )
    assert upload.status_code == 201, upload.text
    asset = upload.json()
    store = api.app.state.store
    org_id = store.installation_organization()
    config = {"profile_id": "test", "models": {"asr": {"path": "synthetic"}}}
    job = store.create_or_get_job(meeting_id, org_id, asset["id"], config)
    calls = []

    def recognize(decoded, asset_row, config_row, progress):
        calls.append(1)
        return {"segments": [{"id": "segment-test", "transcriptRevision": 1, "startMs": 0,
                 "endMs": 500, "text": "Synthetic speech", "language": "en", "origin": "asr",
                 "words": []}], "metrics": {"wallSeconds": 0.01}}

    def decide(segments, meeting_row, job_row, work_dir, progress=None):
        if progress:
            progress()
        return {"transcriptRevision": segments[0]["transcript_revision"], "modelAlias": "test-llm",
                "items": [], "requiresHumanReview": True}

    monkeypatch.setattr(asr, "transcribe_audio", recognize)
    monkeypatch.setattr(decisions, "extract_decisions", decide)
    original_save = store.save_segments

    def fail_commit(*args):
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(store, "save_segments", fail_commit)
    assert run_once(store, "worker-before-restart")
    assert store.get_job(job["id"], org_id)["state"] == "failed"
    assert store.resolve_key(asset["storageKey"]).is_file()
    assert list(tmp_path.rglob("*.transcript.json"))
    assert api.get(f"/api/meetings/{meeting_id}").json()["latestJob"] == {
        "id": job["id"], "state": "failed", "stage": "transcribe", "errorCode": "PROCESSING_FAILED",
    }
    monkeypatch.setattr(store, "save_segments", original_save)
    retry = api.post(f"/api/jobs/{job['id']}/retry")
    assert retry.status_code == 202 and retry.json()["state"] == "queued"
    assert run_once(store, "worker-after-restart")
    assert store.get_job(job["id"], org_id)["state"] == "ready"
    assert len(store.get_segments(meeting_id, org_id)) == 1
    assert len(calls) == 1
    meeting_response = api.get(f"/api/meetings/{meeting_id}")
    assert meeting_response.status_code == 200
    assert meeting_response.json()["decisions"]["modelAlias"] == "test-llm"


def test_transcript_correction_is_audited_and_invalidates_old_decisions(tmp_path, monkeypatch):
    from services.meeting.adapters import asr
    from services.meeting import decisions
    from services.meeting.jobs import run_once

    api = client(tmp_path, monkeypatch)
    meeting_id = meeting(api)
    upload = api.post(f"/api/meetings/{meeting_id}/audio", files={"file": ("synthetic.wav", short_wav(), "audio/wav")})
    asset = upload.json()
    store = api.app.state.store
    org_id = store.installation_organization()
    job = store.create_or_get_job(meeting_id, org_id, asset["id"], {"profile_id": "test", "models": {"asr": {"path": "synthetic"}}})
    monkeypatch.setattr(asr, "transcribe_audio", lambda *args, **kwargs: {"segments": [{
        "id": "segment-editable", "transcriptRevision": 1, "startMs": 0, "endMs": 500,
        "text": "Original words", "language": "en", "origin": "asr", "words": [],
    }], "metrics": {}})
    monkeypatch.setattr(decisions, "extract_decisions", lambda segments, *args, **kwargs: {
        "transcriptRevision": segments[0]["transcript_revision"], "modelAlias": "test-llm", "items": [], "requiresHumanReview": True,
    })
    assert run_once(store, "worker-edit-test")
    updated = api.put(f"/api/meetings/{meeting_id}/segments/segment-editable", json={
        "transcriptRevision": 1, "text": "Corrected words",
    })
    assert updated.status_code == 200, updated.text
    assert updated.json()["text"] == "Corrected words"
    result = api.get(f"/api/meetings/{meeting_id}").json()
    assert result["meeting"]["transcriptRevision"] == 2
    assert result["segments"][0]["transcriptRevision"] == 2
    assert result["decisions"] is None
    with store.connect() as db:
        history = db.execute("SELECT old_text,new_text,from_revision,to_revision FROM segment_revisions").fetchone()
    assert tuple(history) == ("Original words", "Corrected words", 1, 2)
    stale = api.put(f"/api/meetings/{meeting_id}/segments/segment-editable", json={
        "transcriptRevision": 1, "text": "Stale edit",
    })
    assert stale.status_code == 409
