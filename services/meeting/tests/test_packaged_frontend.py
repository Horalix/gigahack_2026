from fastapi.testclient import TestClient

from services.meeting import api as meeting_api


def test_packaged_frontend_and_api_share_loopback_origin(tmp_path, monkeypatch):
    frontend = tmp_path / "build"
    frontend.mkdir()
    (frontend / "index.html").write_text("<main>Notavra</main>", encoding="utf-8")
    (frontend / "app.js").write_text("window.ready = true", encoding="utf-8")
    monkeypatch.setattr(meeting_api, "FRONTEND_DIR", frontend)

    origin = "http://127.0.0.1:8000"
    client = TestClient(meeting_api.create_app(tmp_path / "data"), base_url=origin,
                        headers={"Origin": origin})

    assert client.get("/").text == "<main>Notavra</main>"
    assert client.get("/app.js").text == "window.ready = true"
    setup = client.post("/api/auth/setup", json={
        "username": "first-admin", "password": "correct horse battery staple",
    })
    assert setup.status_code == 201, setup.text
    assert "samesite=strict" in setup.headers["set-cookie"].lower()
    assert client.get("/api/auth/me").status_code == 200
