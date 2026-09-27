import hashlib

from services.meeting import decisions
from services.meeting.adapters import asr
from services.meeting.jobs import run_once
from services.meeting.rendering import render_minutes_html
from services.meeting.tests.test_access import PASSWORD, logged_in
from services.meeting.tests.test_jobs import client, meeting, short_wav


def ready_meeting(api, monkeypatch):
    meeting_id = meeting(api)
    asset = api.post(f"/api/meetings/{meeting_id}/audio",
                     files={"file": ("synthetic.wav", short_wav(), "audio/wav")}).json()
    store = api.app.state.store
    organization_id = store.installation_organization()
    job = store.create_or_get_job(meeting_id, organization_id, asset["id"],
                                  {"profile_id": "test", "models": {"asr": {"path": "synthetic"}}})

    def recognize(_decoded, _asset, _config, progress=None):
        return {"segments": [{"id": "segment-artifact", "transcriptRevision": 1, "startMs": 0,
                               "endMs": 500, "text": "<script>transcript</script>", "language": "ro",
                               "origin": "asr", "words": []}], "metrics": {"wallSeconds": 0.01}}

    def decide(segments, _meeting, _job, _work, progress=None):
        if progress:
            progress()
        return {"transcriptRevision": segments[0]["transcript_revision"], "modelAlias": "test-llm",
                "items": [{"id": "action-1", "kind": "action", "text": "<img src=x onerror=alert(1)>",
                           "status": "proposed", "ownerLabel": None, "originalDateExpression": None,
                           "taskEvidence": [{"segmentId": "segment-artifact", "startMs": 0,
                                             "quote": "<svg onload=alert(1)>", "endMs": 50}],
                           "ownerEvidence": [], "dateEvidence": []}], "requiresHumanReview": True}

    monkeypatch.setattr(asr, "transcribe_audio", recognize)
    monkeypatch.setattr(decisions, "extract_decisions", decide)
    assert run_once(store, "artifact-test-worker")
    return meeting_id


def test_renderer_preserves_unicode_and_marks_unresolved_fields():
    long_text = "Romanian: ăâîșț. Русский: пациент. " * 400
    output = render_minutes_html(
        {"id": "meeting-1", "title": "Consultation", "recordedAt": "2026-09-27T09:00:00Z",
         "timeZone": "Europe/Warsaw", "outputLanguage": "ro", "transcriptRevision": 4},
        [{"startMs": 0, "language": "ro", "text": long_text}],
        {"items": [{"kind": "action", "text": "Follow up", "ownerLabel": None,
                    "originalDateExpression": None, "taskEvidence": []}]},
        reviewer="clinician", approved_at="2026-09-27T09:10:00Z")
    assert b"\xc8\x99" in output and "Русский".encode() in output
    assert b"Unassigned" in output and b"No deadline stated" in output
    assert b"No supporting excerpt was supplied" in output
    assert long_text.encode() in output
    no_actions = render_minutes_html({"id": "meeting-2", "title": "Empty"}, [], {"items": []},
                                     reviewer="clinician", approved_at="now")
    assert b"No decisions or follow-up actions were identified" in no_actions


def test_approved_html_is_escaped_checksummed_and_superseded_on_correction(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    meeting_id = ready_meeting(api, monkeypatch)
    detail = api.get(f"/api/meetings/{meeting_id}").json()
    assert detail["artifact"] is None
    assert api.post(f"/api/meetings/{meeting_id}/artifacts", json={
        "transcriptRevision": 1, "confirmHumanReview": False}).status_code == 422

    approved = api.post(f"/api/meetings/{meeting_id}/artifacts", json={
        "transcriptRevision": 1, "confirmHumanReview": True})
    assert approved.status_code == 201, approved.text
    artifact = approved.json()["artifact"]
    assert artifact["status"] == "ready" and artifact["transcriptRevision"] == 1
    assert "Synthetic test meeting" not in artifact["storageKey"]
    organization_id = api.app.state.store.installation_organization()
    api.app.state.auth.create_user(organization_id, "artifact-outsider", PASSWORD, "clinician")
    outsider, login = logged_in(api.app, "artifact-outsider")
    assert login.status_code == 200
    assert outsider.get(f"/api/artifacts/{artifact['id']}/content").status_code == 404
    content = api.get(f"/api/artifacts/{artifact['id']}/content")
    assert content.status_code == 200 and "attachment" in content.headers["content-disposition"]
    assert hashlib.sha256(content.content).hexdigest() == artifact["sha256"]
    assert b"Clinician reviewed" in content.content and b"test-admin" in content.content
    assert b"&lt;script&gt;transcript&lt;/script&gt;" in content.content
    assert b"&lt;img src=x onerror=alert(1)&gt;" in content.content
    assert b"<script>transcript</script>" not in content.content
    assert b"https://" not in content.content

    correction = api.put(f"/api/meetings/{meeting_id}/segments/segment-artifact", json={
        "transcriptRevision": 1, "text": "Corrected safe transcript"})
    assert correction.status_code == 200
    assert api.get(f"/api/artifacts/{artifact['id']}/content").status_code == 404
    assert api.get(f"/api/meetings/{meeting_id}").json()["artifact"] is None


def test_artifact_approval_rejects_a_stale_revision(tmp_path, monkeypatch):
    api = client(tmp_path, monkeypatch)
    meeting_id = ready_meeting(api, monkeypatch)
    response = api.post(f"/api/meetings/{meeting_id}/artifacts", json={
        "transcriptRevision": 2, "confirmHumanReview": True})
    assert response.status_code == 409
    assert api.get(f"/api/meetings/{meeting_id}").json()["artifact"] is None
