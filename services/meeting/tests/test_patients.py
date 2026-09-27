import uuid

from services.meeting.api import create_app
from services.meeting.tests.test_access import ORIGIN, PASSWORD, logged_in, make_meeting, setup_app


def create_patient(api, name="Ștefan Popescu", reference="MP-123"):
    response = api.post("/api/patients", json={"displayName": name, "hospitalReference": reference})
    assert response.status_code == 201, response.text
    return response.json()["patient"]


def test_patient_search_pagination_and_cursor_filter_binding(tmp_path):
    app, _ = setup_app(tmp_path)
    api, _ = logged_in(app)
    store = app.state.store
    actor = store.get_user_by_username("owner")
    with store.transaction() as db:
        for index in range(1005):
            name = f"Patient {index:04d}"
            db.execute("""INSERT INTO patients
                (id,organization_id,display_name,search_name,hospital_reference,search_reference,status,created_by,created_at,updated_at)
                VALUES(?,?,?,?,? ,?,'active',?,?,?)""",
                (str(uuid.uuid4()), actor["organization_id"], name, name.casefold(), f"REF-{index:04d}",
                 f"ref-{index:04d}", actor["id"], "2026-09-27T00:00:00Z", "2026-09-27T00:00:00Z"))
    first = api.get("/api/patients?limit=100").json()
    assert first["total"] == 1005 and first["hasMore"] and len(first["patients"]) == 100
    last = first
    while last["hasMore"]:
        last = api.get("/api/patients", params={"limit": 100, "cursor": last["nextCursor"]}).json()
    assert len(last["patients"]) == 5 and last["patients"][-1]["displayName"] == "Patient 1004"
    assert api.get("/api/patients?q=REF-0500").json()["total"] == 1
    assert api.get("/api/patients", params={"q": "Patient", "cursor": first["nextCursor"]}).status_code == 422
    assert api.get("/api/patients", params={"q": "%' OR 1=1 --"}).json()["total"] == 0


def test_patient_access_is_scoped_and_link_does_not_grant_meeting_access(tmp_path):
    app, org_id = setup_app(tmp_path)
    owner, _ = logged_in(app)
    second = app.state.auth.create_user(org_id, "other-clinician", PASSWORD, "clinician")
    other, login = logged_in(app, "other-clinician")
    assert login.status_code == 200
    patient = create_patient(owner)
    assert other.get("/api/patients").json()["total"] == 0
    assert other.get(f"/api/patients/{patient['id']}").status_code == 404

    meeting_id = make_meeting(owner)
    assert owner.post(f"/api/patients/{patient['id']}/meetings/{meeting_id}").status_code == 201
    details = owner.get(f"/api/patients/{patient['id']}").json()["patient"]
    assert [meeting["id"] for meeting in details["meetings"]] == [meeting_id]
    assert other.get(f"/api/meetings/{meeting_id}").status_code == 404

    assert owner.post(f"/api/meetings/{meeting_id}/grants", json={
        "userId": second["id"], "permission": "viewer"}).status_code == 201
    shared = other.get(f"/api/patients/{patient['id']}").json()["patient"]
    assert [meeting["id"] for meeting in shared["meetings"]] == [meeting_id]
    assert other.get("/api/patients").json()["total"] == 1
    assert other.patch(f"/api/patients/{patient['id']}", json={"status": "inactive"}).status_code == 404


def test_patient_create_edit_unicode_search_and_meeting_creation_link(tmp_path):
    app, _ = setup_app(tmp_path)
    api, _ = logged_in(app)
    patient = create_patient(api)
    assert api.get("/api/patients?q=șTEFAN").json()["patients"][0]["id"] == patient["id"]
    updated = api.patch(f"/api/patients/{patient['id']}", json={
        "displayName": "Иван Петров", "hospitalReference": None, "status": "inactive"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["patient"]["hospitalReference"] is None
    assert api.get("/api/patients?q=иван").json()["total"] == 1
    meeting = api.post("/api/meetings", json={
        "title": "Linked consultation", "recordedAt": "2026-09-27T09:00:00Z",
        "timeZone": "Europe/Warsaw", "outputLanguage": "ro", "patientLinkIds": [patient["id"]],
    })
    assert meeting.status_code == 201, meeting.text
    assert meeting.json()["patientLinkIds"] == [patient["id"]]
    assert api.get(f"/api/meetings/{meeting.json()['id']}").json()["meeting"]["patientLinkIds"] == [patient["id"]]
    second_copy = create_patient(api, "Иван Петров", "MP-124")
    duplicates = api.get("/api/patients", params={"q": "иван"}).json()["patients"]
    assert len(duplicates) == 2 and duplicates[0]["id"] < duplicates[1]["id"]
    restarted = create_app(tmp_path)
    restarted_api, login = logged_in(restarted)
    assert login.status_code == 200
    assert restarted_api.get(f"/api/patients/{second_copy['id']}").status_code == 200


def test_invalid_patient_link_rolls_back_new_meeting(tmp_path):
    app, _ = setup_app(tmp_path)
    api, _ = logged_in(app)
    response = api.post("/api/meetings", json={
        "title": "No link", "recordedAt": "2026-09-27T09:00:00Z", "timeZone": "Europe/Warsaw",
        "outputLanguage": "ro", "patientLinkIds": ["unknown"],
    })
    assert response.status_code == 422
    assert api.get("/api/meetings").json()["total"] == 0
