import uuid

from services.meeting.tests.test_access import logged_in
from services.meeting.tests.test_jobs import client, meeting, short_wav


def test_owner_purge_removes_managed_audio_and_incomplete_capture(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    meeting_id = meeting(api)
    uploaded = api.post(f"/api/meetings/{meeting_id}/audio",
                        files={"file": ("recording.wav", short_wav(), "audio/wav")})
    assert uploaded.status_code == 201, uploaded.text
    source_key = uploaded.json()["storageKey"]
    store = api.app.state.store
    source_path = store.resolve_key(source_key)
    assert source_path.exists()

    capture = api.post(f"/api/meetings/{meeting_id}/captures", json={"contentType": "audio/wav"}).json()
    chunk = api.put(f"/api/captures/{capture['id']}/chunks/0", content=short_wav(),
                    headers={"Content-Type": "audio/wav"})
    assert chunk.status_code == 200
    assert store.capture_chunk_path(capture["id"], 0).exists()

    result = api.delete(f"/api/meetings/{meeting_id}")
    assert result.status_code == 200, result.text
    assert result.json() == {"ok": True, "pendingFileCleanup": 0}
    assert api.get(f"/api/meetings/{meeting_id}").status_code == 404
    assert not source_path.exists()
    assert not store.capture_chunk_path(capture["id"], 0).exists()
    with store.connect() as db:
        audit = db.execute("SELECT subject_type,subject_id,action FROM deletion_audit WHERE subject_id=?",
                           (meeting_id,)).fetchone()
        assert tuple(audit) == ("meeting", meeting_id, "purge_requested")
        assert db.execute("SELECT COUNT(*) FROM meetings WHERE id=?", (meeting_id,)).fetchone()[0] == 0


def test_purge_is_owner_only_and_blocked_while_job_is_active(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    meeting_id = meeting(api)
    uploaded = api.post(f"/api/meetings/{meeting_id}/audio",
                        files={"file": ("recording.wav", short_wav(), "audio/wav")})
    assert uploaded.status_code == 201
    asset = uploaded.json()
    store = api.app.state.store
    job_id, now = str(uuid.uuid4()), "2026-09-27T00:00:00Z"
    with store.transaction() as db:
        db.execute("""INSERT INTO jobs(id,organization_id,meeting_id,asset_id,state,stage,profile_id,
            model_config_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (job_id, asset["organizationId"], meeting_id, asset["id"], "running", "transcribe", "laptop8", "{}", now, now))

    result = api.delete(f"/api/meetings/{meeting_id}")
    assert result.status_code == 409 and result.json()["code"] == "MEETING_PROCESSING"
    assert api.get(f"/api/meetings/{meeting_id}").status_code == 200

    org = store.installation_organization()
    api.app.state.auth.create_user(org, "outsider", "correct horse battery staple", "clinician")
    outsider, login = logged_in(api.app, "outsider")
    assert login.status_code == 200
    assert outsider.delete(f"/api/meetings/{meeting_id}").status_code == 404
