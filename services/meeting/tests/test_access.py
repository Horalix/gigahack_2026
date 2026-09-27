import time

from fastapi.testclient import TestClient

from services.meeting.api import create_app
from services.meeting.auth import SESSION_COOKIE


ORIGIN = "http://localhost:1420"
PASSWORD = "correct horse battery staple"


def setup_app(tmp_path, username="owner", role="clinician"):
    app = create_app(tmp_path)
    org_id = app.state.store.installation_organization()
    app.state.auth.create_user(org_id, username, PASSWORD, role, bootstrap=True)
    return app, org_id


def logged_in(app, username="owner", password=PASSWORD, *, origin=ORIGIN, base_url="http://testserver"):
    api = TestClient(app, base_url=base_url, headers={"Origin": origin})
    response = api.post("/api/auth/login", json={"username": username, "password": password})
    return api, response


def make_meeting(api, title="Private meeting"):
    response = api.post("/api/meetings", json={
        "contractVersion": "1.0", "title": title, "recordedAt": "2026-09-26T09:00:00Z",
        "timeZone": "Europe/Chisinau", "outputLanguage": "ro", "patientLinkIds": [],
    })
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_auth_required_and_demo_header_is_not_a_bypass(tmp_path, monkeypatch):
    app, _ = setup_app(tmp_path)
    monkeypatch.setenv("MOM_SYNTHETIC_DEV", "1")
    api = TestClient(app, headers={"Origin": ORIGIN, "X-Demo-Principal": "synthetic-demo"})
    assert api.get("/api/profiles").status_code == 401
    assert api.post("/api/meetings", json={}).status_code == 401


def test_first_run_setup_and_searchable_meeting_list(tmp_path):
    api = TestClient(create_app(tmp_path), headers={"Origin": ORIGIN})
    assert api.get("/api/health").json()["setupRequired"] is True
    setup = api.post("/api/auth/setup", json={"username": "first-admin", "password": PASSWORD})
    assert setup.status_code == 201, setup.text
    assert api.get("/api/auth/me").json()["user"]["role"] == "administrator"
    for title in ("Romanian clinic", "Russian clinic"):
        assert api.post("/api/meetings", json={
            "title": title, "recordedAt": "2026-09-26T09:00:00Z", "timeZone": "Europe/Warsaw",
            "outputLanguage": "ro", "patientLinkIds": [],
        }).status_code == 201
    result = api.get("/api/meetings?q=Romanian&limit=1&offset=0").json()
    assert result["total"] == 1
    assert [meeting["title"] for meeting in result["meetings"]] == ["Romanian clinic"]
    assert api.post("/api/auth/setup", json={"username": "other-admin", "password": PASSWORD}).status_code == 409


def test_login_cookie_logout_and_expiry(tmp_path):
    app, _ = setup_app(tmp_path)
    api, response = logged_in(app)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert f"{SESSION_COOKIE}=" in cookie
    assert "httponly" in cookie and "samesite=strict" in cookie and "secure" not in cookie
    assert api.get("/api/auth/me").json()["user"]["username"] == "owner"

    token = api.cookies[SESSION_COOKIE]
    token_hash = __import__("hashlib").sha256(token.encode("ascii")).hexdigest()
    with app.state.store.transaction() as db:
        db.execute("UPDATE auth_sessions SET expires_at=? WHERE token_hash=?", (time.time() - 1, token_hash))
    assert api.get("/api/auth/me").status_code == 401

    api2, login = logged_in(app)
    assert login.status_code == 200
    assert api2.post("/api/auth/logout").status_code == 200
    assert api2.get("/api/auth/me").status_code == 401


def test_secure_cookie_is_enabled_on_https(tmp_path):
    app, _ = setup_app(tmp_path)
    _, response = logged_in(app, base_url="https://testserver")
    assert response.status_code == 200
    assert "secure" in response.headers["set-cookie"].lower()


def test_admin_can_provision_and_suspend_accounts_but_clinicians_cannot(tmp_path):
    app, _ = setup_app(tmp_path, role="administrator")
    admin, _ = logged_in(app)
    created = admin.post("/api/users", json={
        "username": "new-clinician", "password": PASSWORD, "role": "clinician",
    })
    assert created.status_code == 201, created.text
    account = created.json()["user"]
    listed = admin.get("/api/users").json()["users"]
    assert all("password" not in user and "password_hash" not in user for user in listed)

    clinician, login = logged_in(app, "new-clinician")
    assert login.status_code == 200
    assert clinician.get("/api/users").status_code == 403
    suspended = admin.patch(f"/api/users/{account['id']}", json={"active": False})
    assert suspended.status_code == 200
    assert clinician.get("/api/auth/me").status_code == 401
    assert admin.post("/api/auth/login", json={"username": "new-clinician", "password": PASSWORD}).status_code == 401


def test_admin_provisioned_accounts_do_not_get_implicit_meeting_access(tmp_path):
    app, org_id = setup_app(tmp_path)
    owner, _ = logged_in(app)
    admin = app.state.auth.create_user(org_id, "config-admin", PASSWORD, "administrator")
    admin_api, login = logged_in(app, "config-admin")
    assert login.status_code == 200
    meeting_id = make_meeting(owner)

    assert admin_api.get(f"/api/meetings/{meeting_id}").status_code == 404
    assert admin_api.get("/api/users").status_code == 200
    assert owner.post(f"/api/meetings/{meeting_id}/grants", json={
        "userId": admin["id"], "permission": "viewer",
    }).status_code == 201
    assert admin_api.get(f"/api/meetings/{meeting_id}").status_code == 200
    assert admin_api.get(f"/api/meetings/{meeting_id}/grants").status_code == 403
    assert admin_api.post(f"/api/meetings/{meeting_id}/audio", files={
        "file": ("empty.wav", b"", "audio/wav"),
    }).status_code == 403


def test_grants_are_owner_managed_and_revocable(tmp_path):
    app, org_id = setup_app(tmp_path)
    owner, _ = logged_in(app)
    reviewer = app.state.auth.create_user(org_id, "reviewer", PASSWORD, "reviewer")
    reviewer_api, login = logged_in(app, "reviewer")
    assert login.status_code == 200
    meeting_id = make_meeting(owner)
    assert reviewer_api.get(f"/api/meetings/{meeting_id}").status_code == 404
    assert reviewer_api.get("/api/jobs/unknown").status_code == 404

    grant = owner.post(f"/api/meetings/{meeting_id}/grants", json={
        "userId": reviewer["id"], "permission": "viewer",
    })
    assert grant.status_code == 201
    assert reviewer_api.get(f"/api/meetings/{meeting_id}").status_code == 200
    assert reviewer_api.post(f"/api/meetings/{meeting_id}/jobs", json={"profileId": "laptop8"}).status_code == 403
    assert owner.delete(f"/api/meetings/{meeting_id}/grants/{reviewer['id']}").status_code == 200
    assert reviewer_api.get(f"/api/meetings/{meeting_id}").status_code == 404


def test_login_errors_are_generic_and_origin_is_required(tmp_path):
    app, _ = setup_app(tmp_path)
    api = TestClient(app)
    missing_origin = api.post("/api/auth/login", json={"username": "owner", "password": PASSWORD})
    assert missing_origin.status_code == 403

    api = TestClient(app, headers={"Origin": ORIGIN})
    wrong = api.post("/api/auth/login", json={"username": "unknown-user", "password": PASSWORD})
    known_wrong = api.post("/api/auth/login", json={"username": "owner", "password": "wrong password here"})
    assert wrong.status_code == known_wrong.status_code == 401
    assert wrong.json()["message"] == known_wrong.json()["message"]
    assert "unknown-user" not in wrong.text


def test_remote_clients_and_untrusted_origins_are_rejected(tmp_path):
    app, _ = setup_app(tmp_path)
    remote = TestClient(app, client=("192.0.2.10", 12345), headers={"Origin": ORIGIN})
    assert remote.get("/api/health").status_code == 403
    local_bad_origin = TestClient(app, headers={"Origin": "https://attacker.invalid"})
    assert local_bad_origin.get("/api/health").status_code == 403


def test_owner_must_grant_to_an_account_in_this_installation(tmp_path):
    app, _ = setup_app(tmp_path)
    owner, _ = logged_in(app)
    meeting_id = make_meeting(owner)
    missing = owner.post(f"/api/meetings/{meeting_id}/grants", json={
        "userId": "foreign-user-id", "permission": "viewer",
    })
    assert missing.status_code == 404
    assert owner.get(f"/api/meetings/{meeting_id}/grants").json()["grants"][0]["permission"] == "owner"
