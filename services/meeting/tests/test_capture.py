from fastapi.testclient import TestClient

from services.meeting.api import create_app
from services.meeting.tests.test_access import logged_in
from services.meeting.tests.test_jobs import client, meeting, short_wav


def test_live_preview_returns_only_owned_source_timed_segments(tmp_path, monkeypatch):
    from services.meeting import models

    api = client(tmp_path, monkeypatch)
    meeting_id = meeting(api)
    capture_id = api.post(f"/api/meetings/{meeting_id}/captures", json={"contentType": "audio/wav"}).json()["id"]
    monkeypatch.setattr(models, "resolve_profile", lambda *_args, **_kwargs: {
        "profile_id": "laptop8", "limits": {"min_available_ram_gb": 4},
        "models": {"asr": {"device": "cpu", "path": "synthetic"}},
    })
    monkeypatch.setattr(models, "validate_assets", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("services.meeting.adapters.asr.transcribe_audio", lambda _path, asset, _config: {
        "segments": [
            {"id": "inside", "startMs": asset["source_offset_ms"], "endMs": asset["duration_ms"], "text": "Bună ziua", "language": "ro"},
            {"id": "outside", "startMs": asset["source_offset_ms"] + 500, "endMs": asset["duration_ms"], "text": "overlap duplicate", "language": "ro"},
        ],
        "metrics": {"wallSeconds": 0.2},
    })

    response = api.post(f"/api/captures/{capture_id}/preview?profileId=laptop8&language=ro&start_ms=0&ownershipStartMs=0&ownershipEndMs=600",
                        content=short_wav(), headers={"Content-Type": "audio/wav"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert [segment["id"] for segment in body["segments"]] == ["inside"]
    assert body["segments"][0]["startMs"] == 0
    assert body["ownershipEndMs"] == 600
    assert list((tmp_path / "temporary").glob("*.wav")) == []
    assert api.put(f"/api/captures/{capture_id}/chunks/0", content=short_wav(),
                   headers={"Content-Type": "audio/wav"}).status_code == 200
    sealed = api.post(f"/api/captures/{capture_id}/seal", json={"expectedSequenceCount": 1})
    assert sealed.status_code == 200, sealed.text
    from services.meeting.adapters.asr import asr_configuration_hash
    config = models.resolve_profile("laptop8", overrides={"asr": {"language": "ro"}})
    windows = api.app.state.store.get_capture_preview_windows(
        sealed.json()["asset"]["id"], api.app.state.store.installation_organization(), asr_configuration_hash(config))
    assert len(windows) == 1 and windows[0]["segments"][0]["text"] == "Bună ziua"


def test_live_preview_rejects_wrong_audio_format(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    meeting_id = meeting(api)
    capture_id = api.post(f"/api/meetings/{meeting_id}/captures", json={"contentType": "audio/webm"}).json()["id"]
    response = api.post(f"/api/captures/{capture_id}/preview?profileId=laptop8&language=ro&start_ms=0&ownershipStartMs=0&ownershipEndMs=1000",
                        content=b"not a wav", headers={"Content-Type": "audio/wav"})
    assert response.status_code == 422
    assert response.json()["code"] == "PREVIEW_AUDIO_INVALID"


def test_final_asr_reuses_valid_live_window_and_transcribes_only_gap(tmp_path, monkeypatch):
    import wave
    from services.meeting.adapters import asr
    from services.meeting.pipeline import _transcribe_with_capture_previews

    decoded = tmp_path / "source.wav"
    with wave.open(str(decoded), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\0\0" * (3 * 16000))
    config = {"models": {"asr": {"language": "ro", "path": "synthetic", "device": "cpu",
                                    "compute_type": "float32", "beam_size": 5, "batch_size": 1,
                                    "word_timestamps": True}}}

    class PreviewStore:
        root = tmp_path

        def get_capture_preview_windows(self, asset_id, organization_id, fingerprint):
            assert asset_id == "asset-1" and organization_id == "org-1"
            assert fingerprint == asr.asr_configuration_hash(config)
            return [{"start_ms": 0, "ownership_end_ms": 1000, "segments": [{
                "id": "duplicate-window-id", "startMs": 0, "endMs": 900, "text": "preview words",
                "language": "ro", "origin": "asr", "words": [],
            }], "wall_seconds": 1.5, "peak_gpu_memory_mib": 3000}]

    calls = []

    def fake_transcribe(path, asset, _config, progress=None):
        with wave.open(str(path), "rb") as audio:
            calls.append((asset["source_offset_ms"], audio.getnframes() // 16000))
        if progress:
            progress(asset["duration_ms"])
        return {"segments": [{"id": "duplicate-window-id", "transcriptRevision": 1,
                               "startMs": asset["source_offset_ms"], "endMs": asset["duration_ms"],
                               "text": "tail words", "language": "ro", "origin": "asr", "words": []}],
                "metrics": {"audioDurationMs": 3000, "wallSeconds": 3.0,
                            "peakGpuMemoryMiBObserved": 3200}}

    monkeypatch.setattr(asr, "transcribe_audio", fake_transcribe)
    updates = []
    result = _transcribe_with_capture_previews(
        PreviewStore(), {"id": "job-1", "organization_id": "org-1"},
        {"id": "asset-1", "duration_ms": 3000, "source_offset_ms": 0}, decoded, config, updates.append)
    assert calls == [(1000, 2)]
    assert [segment["text"] for segment in result["segments"]] == ["preview words", "tail words"]
    assert len({segment["id"] for segment in result["segments"]}) == 2
    assert result["metrics"]["livePreviewWindowsReused"] == 1
    assert result["metrics"]["livePreviewCoverageMs"] == 1000
    assert result["metrics"]["uncoveredGapCount"] == 1
    assert result["metrics"]["wallSeconds"] == 4.5
    assert updates == [1000, 3000]
    assert list((tmp_path / "runtime-tmp" / "live-asr").glob("*.wav")) == []


def test_ordered_capture_persists_chunks_and_seals_valid_media(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    meeting_id = meeting(api)
    wav = short_wav()
    started = api.post(f"/api/meetings/{meeting_id}/captures", json={"contentType": "audio/wav"})
    assert started.status_code == 201, started.text
    capture_id = started.json()["id"]

    stored = api.put(f"/api/captures/{capture_id}/chunks/0", content=wav,
                     headers={"Content-Type": "audio/wav"})
    assert stored.status_code == 200 and stored.json()["nextSequence"] == 1
    duplicate = api.put(f"/api/captures/{capture_id}/chunks/0", content=wav,
                        headers={"Content-Type": "audio/wav"})
    assert duplicate.status_code == 200 and duplicate.json()["idempotent"] is True
    assert api.put(f"/api/captures/{capture_id}/chunks/2", content=b"later",
                   headers={"Content-Type": "audio/wav"}).status_code == 409

    # The durable chunk and sequence survive an API process restart.
    restarted = TestClient(create_app(tmp_path), headers={"Origin": "http://localhost:1420"})
    login = restarted.post("/api/auth/login", json={"username": "test-admin", "password": "correct horse battery staple"})
    assert login.status_code == 200
    state = restarted.get(f"/api/captures/{capture_id}").json()
    assert state["state"] == "capturing" and state["nextSequence"] == 1
    assert state["receivedBytes"] == len(wav)
    assert restarted.post(f"/api/captures/{capture_id}/seal", json={"expectedSequenceCount": 2}).status_code == 409

    sealed = restarted.post(f"/api/captures/{capture_id}/seal", json={"expectedSequenceCount": 1})
    assert sealed.status_code == 200, sealed.text
    asset = sealed.json()["asset"]
    assert asset["durationMs"] == 1000 and asset["sha256"]
    store = restarted.app.state.store
    assert store.resolve_key(asset["storageKey"]).read_bytes() == wav
    assert restarted.get(f"/api/captures/{capture_id}").json()["state"] == "sealed"
    repeated = restarted.post(f"/api/captures/{capture_id}/seal", json={"expectedSequenceCount": 1})
    assert repeated.status_code == 200 and repeated.json()["asset"]["id"] == asset["id"]


def test_capture_and_chunks_require_explicit_meeting_access(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    meeting_id = meeting(api)
    capture_id = api.post(f"/api/meetings/{meeting_id}/captures", json={"contentType": "audio/wav"}).json()["id"]
    organization_id = api.app.state.store.installation_organization()
    api.app.state.auth.create_user(organization_id, "capture-outsider", "correct horse battery staple", "clinician")
    outsider, login = logged_in(api.app, "capture-outsider")
    assert login.status_code == 200
    assert outsider.get(f"/api/captures/{capture_id}").status_code == 404
    assert outsider.put(f"/api/captures/{capture_id}/chunks/0", content=short_wav(),
                        headers={"Content-Type": "audio/wav"}).status_code == 404
