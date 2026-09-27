from fastapi.testclient import TestClient

from services.meeting.api import create_app
from services.meeting.tests.test_access import logged_in
from services.meeting.tests.test_jobs import client, meeting, short_wav


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
