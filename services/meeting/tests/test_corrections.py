import json
import uuid

from services.meeting.tests.test_access import logged_in, make_meeting, setup_app
from services.meeting.storage import timestamp


def transcript_fixture(api, meeting_id):
    me = api.get("/api/auth/me").json()["user"]
    store = api.app.state.store
    asset_id, job_id = str(uuid.uuid4()), str(uuid.uuid4())
    created = timestamp()
    with store.transaction() as db:
        db.execute("""INSERT INTO assets(id,organization_id,meeting_id,source_key,source_sha256,decoded_key,
            duration_ms,source_offset_ms,size_bytes,media_type,audio_track_index,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (asset_id, me["organizationId"], meeting_id, "assets/source", "a" * 64, "assets/audio.wav",
             2000, 0, 4, "audio/wav", 0, created))
        db.execute("""INSERT INTO jobs(id,organization_id,meeting_id,asset_id,state,stage,profile_id,
            model_config_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (job_id, me["organizationId"], meeting_id, asset_id, "ready", "complete", "cpu", "{}", created, created))
        for index, text in enumerate(("Maria ia <5 mg pe zi", "control peste două săptămâni")):
            db.execute("""INSERT INTO segments(id,organization_id,meeting_id,asset_id,job_id,transcript_revision,
                start_ms,end_ms,text,language,origin,words_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (f"segment-{index}", me["organizationId"], meeting_id, asset_id, job_id, 1,
                 index * 1000, (index + 1) * 1000, text, "ro", "asr", json.dumps([]), created))
        db.execute("UPDATE meetings SET transcript_revision=1 WHERE id=?", (meeting_id,))
    return me


def test_batch_correction_is_atomic_and_undo_is_a_new_audited_revision(tmp_path):
    app, _ = setup_app(tmp_path)
    api, login = logged_in(app)
    assert login.status_code == 200
    meeting_id = make_meeting(api)
    me = transcript_fixture(api, meeting_id)

    corrected = api.put(f"/api/meetings/{meeting_id}/segments", json={
        "transcriptRevision": 1,
        "corrections": [
            {"segmentId": "segment-0", "text": "Maria ia 5 mg pe zi"},
            {"segmentId": "segment-1", "text": "control peste două săptămâni."},
        ],
    })
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["transcriptRevision"] == 2
    assert [row["text"] for row in corrected.json()["segments"]] == [
        "Maria ia 5 mg pe zi", "control peste două săptămâni.",
    ]

    # The second edit cannot partially apply if a passage ID is wrong.
    failed = api.put(f"/api/meetings/{meeting_id}/segments", json={
        "transcriptRevision": 2,
        "corrections": [
            {"segmentId": "segment-0", "text": "Must roll back"},
            {"segmentId": "missing", "text": "Not present"},
        ],
    })
    assert failed.status_code == 409
    assert api.get(f"/api/meetings/{meeting_id}").json()["segments"][0]["text"] == "Maria ia 5 mg pe zi"

    undone = api.post(f"/api/meetings/{meeting_id}/transcript/undo", json={"transcriptRevision": 2})
    assert undone.status_code == 200, undone.text
    assert undone.json()["transcriptRevision"] == 3
    assert [row["text"] for row in undone.json()["segments"]] == [
        "Maria ia <5 mg pe zi", "control peste două săptămâni",
    ]
    stale = api.post(f"/api/meetings/{meeting_id}/transcript/undo", json={"transcriptRevision": 2})
    assert stale.status_code == 409

    with app.state.store.connect() as db:
        history = db.execute("SELECT editor_id,from_revision,to_revision,old_text,new_text FROM segment_revisions \
            WHERE meeting_id=? ORDER BY created_at,id", (meeting_id,)).fetchall()
    assert len(history) == 4
    assert all(row["editor_id"] == me["id"] for row in history)
    assert {(row["from_revision"], row["to_revision"]) for row in history} == {(1, 2), (2, 3)}


def test_stale_batch_is_rejected_without_partial_revision(tmp_path):
    app, _ = setup_app(tmp_path)
    api, _ = logged_in(app)
    meeting_id = make_meeting(api)
    transcript_fixture(api, meeting_id)
    response = api.put(f"/api/meetings/{meeting_id}/segments", json={
        "transcriptRevision": 99,
        "corrections": [{"segmentId": "segment-0", "text": "Stale"}],
    })
    assert response.status_code == 409
    assert api.get(f"/api/meetings/{meeting_id}").json()["meeting"]["transcriptRevision"] == 1


def test_reviewer_role_cannot_edit_even_with_editor_meeting_grant(tmp_path):
    app, organization_id = setup_app(tmp_path)
    owner, _ = logged_in(app)
    meeting_id = make_meeting(owner)
    transcript_fixture(owner, meeting_id)
    reviewer = app.state.auth.create_user(organization_id, "reviewer", "correct horse battery staple", "reviewer")
    assert owner.post(f"/api/meetings/{meeting_id}/grants", json={
        "userId": reviewer["id"], "permission": "editor",
    }).status_code == 201
    reviewer_api, login = logged_in(app, "reviewer")
    assert login.status_code == 200
    edited = reviewer_api.put(f"/api/meetings/{meeting_id}/segments/segment-0", json={
        "transcriptRevision": 1, "text": "Should stay read only",
    })
    assert edited.status_code == 403 and edited.json()["code"] == "ROLE_READ_ONLY"
