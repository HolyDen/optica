"""Tests for ``optica.server.routes`` — the routes both pages share.

Covers plan § "Labeling & Curation" → *Curation Server* ("Keep Session Active",
the browser half of the timeout warnings; localhost only) and the images both
pages show. The page-specific routes are tested with their pages.

Two guards the plan does not spell out are tested here because they are what
makes "localhost only" hold inside the user's own browser: the ``Host`` check
and the session cookie (``notes/build-log.md`` § "Browser session key").

Needs the web extra; skipped where it is absent, which includes CI.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from optica.server.app import BrowserSession, IdleTimer
from optica.server.routes import create_app

PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class FakeController:
    page = "labeling"

    def __init__(self, images: dict[str, Path] | None = None) -> None:
        self.images = images or {}
        self.raise_on_image: BaseException | None = None

    def image_path(self, image_id: str) -> Path | None:
        if self.raise_on_image is not None:
            raise self.raise_on_image
        return self.images.get(image_id)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def controller(tmp_path: Path) -> FakeController:
    image = tmp_path / "cat.jpg"
    image.write_bytes(b"\xff\xd8\xff\xe0 jpeg-ish")
    return FakeController({"0": image})


@pytest.fixture
def session(controller: FakeController, clock: FakeClock) -> BrowserSession:
    browser = BrowserSession(controller, IdleTimer(60, clock=clock), token="k" * 32)
    browser.port = PORT
    return browser


@pytest.fixture
def client(session: BrowserSession) -> TestClient:
    return TestClient(create_app(session), base_url=BASE)


@pytest.fixture
def authed(client: TestClient, session: BrowserSession) -> TestClient:
    response = client.get(f"/?token={session.token}", follow_redirects=False)
    assert response.status_code == 303
    return client


class TestHostCheck:
    def test_a_foreign_host_is_refused(self, session):
        client = TestClient(create_app(session), base_url=f"http://evil.example:{PORT}")
        assert client.get("/static/shared.js").status_code == 403

    def test_the_right_host_on_the_wrong_port_is_refused(self, session):
        client = TestClient(create_app(session), base_url="http://127.0.0.1:9999")
        assert client.get("/static/shared.js").status_code == 403

    def test_localhost_by_name_is_accepted(self, session):
        client = TestClient(create_app(session), base_url=f"http://localhost:{PORT}")
        assert client.get("/static/shared.js").status_code == 200


class TestSessionKey:
    def test_the_api_refuses_a_request_without_the_cookie(self, client):
        response = client.get("/api/heartbeat")
        assert response.status_code == 403
        assert "Open the link from the terminal" in response.json()["error"]

    def test_the_page_refuses_a_visit_without_the_key(self, client):
        response = client.get("/")
        assert response.status_code == 403
        assert "Open the link from your terminal" in response.text

    def test_a_wrong_key_is_refused(self, client):
        assert client.get("/?token=wrong", follow_redirects=False).status_code == 403

    def test_the_right_key_becomes_a_strict_http_only_cookie(self, client, session):
        response = client.get(f"/?token={session.token}", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/"
        cookie = response.headers["set-cookie"]
        assert cookie.startswith(f"optica_{PORT}={session.token}")
        assert "HttpOnly" in cookie
        assert "SameSite=strict" in cookie

    def test_with_the_cookie_the_api_answers(self, authed):
        assert authed.get("/api/heartbeat").status_code == 200

    def test_static_files_need_no_key(self, client):
        # They carry no session data; the page itself and the API do.
        response = client.get("/static/shared.css")
        assert response.status_code == 200
        assert "text/css" in response.headers["content-type"]


class TestHeartbeat:
    def test_reports_the_timer(self, authed, clock):
        body = authed.get("/api/heartbeat").json()
        assert body == {
            "timeout_enabled": True,
            "remaining_seconds": 3600,
            "warning_seconds_left": None,
            "ended": False,
        }
        clock.now += 30 * 60
        body = authed.get("/api/heartbeat").json()
        assert body["warning_seconds_left"] == 30 * 60
        assert body["remaining_seconds"] == 30 * 60

    def test_polling_is_not_activity(self, authed, clock):
        clock.now += 40 * 60
        authed.get("/api/heartbeat")
        assert authed.get("/api/heartbeat").json()["remaining_seconds"] == 20 * 60

    def test_reports_ended_once_the_session_is_done(self, authed, session):
        session.finish()
        assert authed.get("/api/heartbeat").json()["ended"] is True

    def test_api_responses_are_never_cached(self, authed):
        assert authed.get("/api/heartbeat").headers["cache-control"] == "no-store"


class TestKeepSessionActive:
    def test_restarts_the_idle_timer(self, authed, clock):
        clock.now += 56 * 60
        assert authed.get("/api/heartbeat").json()["warning_seconds_left"] == 5 * 60
        assert authed.post("/api/keepalive").json() == {"ok": True}
        body = authed.get("/api/heartbeat").json()
        assert body["remaining_seconds"] == 3600
        assert body["warning_seconds_left"] is None


class TestImages:
    def test_an_image_is_served_by_id(self, authed, controller):
        response = authed.get("/api/image/0")
        assert response.status_code == 200
        assert response.content == controller.images["0"].read_bytes()

    def test_an_unknown_id_is_not_found(self, authed):
        assert authed.get("/api/image/7").status_code == 404

    def test_a_path_is_never_an_id(self, authed, tmp_path):
        secret = tmp_path / "secret.txt"
        secret.write_text("not an image", encoding="utf-8")
        assert authed.get(f"/api/image/{secret}").status_code == 404
        assert authed.get("/api/image/../../secret.txt").status_code == 404

    def test_an_id_whose_file_has_gone_is_not_found(self, authed, controller):
        controller.images["0"].unlink()
        assert authed.get("/api/image/0").status_code == 404


class TestFailures:
    def test_a_handler_error_ends_the_session_and_is_kept_for_the_terminal(
        self, authed, controller, session
    ):
        controller.raise_on_image = OSError("disk gone")
        response = authed.get("/api/image/0")
        assert response.status_code == 500
        assert response.json()["ended"] is True
        assert isinstance(session.error, OSError)
        assert session.done
