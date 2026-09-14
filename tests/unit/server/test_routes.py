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


# ------------------------------------------------------------------ labeling


class TestLabelingRoutes:
    """The labeling page's routes over a real controller and session file.

    Covers plan § *Labeling UI* → *Session timer triggers*: assignment, Back or
    Next, and toggling auto-advance reset the timer; reading state does not.
    """

    @pytest.fixture
    def labeling(self, tmp_path: Path, clock: FakeClock) -> tuple[TestClient, object]:
        from optica.input.sessions import LabelingSession, SourceType
        from optica.server.labeling import LabelingController

        folder = tmp_path / "images"
        folder.mkdir()
        images = []
        for i in range(12):
            path = folder / f"IMG_{i:04d}.jpg"
            path.write_bytes(bytes([i]) * 8)
            images.append(path.resolve())
        session_file = LabelingSession.new(
            tmp_path / "home", folder, SourceType.FOLDER, ["cat", "dog"]
        )
        controller = LabelingController(session_file, images)
        browser = BrowserSession(controller, IdleTimer(60, clock=clock), token="t" * 32)
        browser.port = PORT
        client = TestClient(create_app(browser), base_url=BASE)
        assert (
            client.get(f"/?token={browser.token}", follow_redirects=False).status_code
            == 303
        )
        return client, browser

    def test_the_page_is_served(self, labeling):
        client, _ = labeling
        response = client.get("/")
        assert response.status_code == 200
        assert "<title>Optica — Label</title>" in response.text
        assert response.headers["cache-control"] == "no-store"
        assert client.get("/static/labeling.js").status_code == 200

    def test_state_is_not_activity(self, labeling, clock):
        client, _ = labeling
        clock.now += 40 * 60
        body = client.get("/api/label/state").json()
        assert body["position"] == "1 of 12"
        assert body["widget"] == "radio"
        assert client.get("/api/heartbeat").json()["remaining_seconds"] == 20 * 60

    @pytest.mark.parametrize(
        ("path", "payload"),
        [
            ("/api/label/assign", {"index": 0, "class": "cat"}),
            ("/api/label/next", {"index": 0}),
            ("/api/label/back", {"index": 1}),
            ("/api/label/auto-advance", {"enabled": False}),
        ],
    )
    def test_each_decision_is_activity(self, labeling, clock, path, payload):
        client, _ = labeling
        clock.now += 40 * 60
        assert client.post(path, json=payload).status_code == 200
        assert client.get("/api/heartbeat").json()["remaining_seconds"] == 3600

    def test_assign_is_written_to_the_session_file_before_it_returns(self, labeling):
        import json

        client, browser = labeling
        body = client.post("/api/label/assign", json={"index": 0, "class": "dog"}).json()
        assert body["index"] == 1
        stored = json.loads(browser.controller.session.path.read_text(encoding="utf-8"))
        assert list(stored["entries"].values()) == [{"state": "labeled", "class": "dog"}]

    @pytest.mark.parametrize(
        "payload",
        [
            {"index": 0},
            {"class": "cat"},
            {"index": "0", "class": "cat"},
            {"index": True, "class": "cat"},
            {"index": 0, "class": "bird"},
            {"index": 99, "class": "cat"},
        ],
    )
    def test_a_malformed_assignment_is_a_400_and_changes_nothing(self, labeling, payload):
        client, browser = labeling
        response = client.post("/api/label/assign", json=payload)
        assert response.status_code == 400
        assert browser.controller.session.entries == {}
        assert not browser.done

    def test_a_body_that_is_not_json_is_a_400(self, labeling):
        client, _ = labeling
        response = client.post(
            "/api/label/next", content=b"index=0", headers={"content-type": "text/plain"}
        )
        assert response.status_code == 400

    def test_finish_while_gated_is_blocked_and_the_session_continues(self, labeling):
        client, browser = labeling
        body = client.post("/api/label/finish", json={"confirmed": True}).json()
        assert body["status"] == "blocked"
        assert body["hint"] == (
            "Every class needs at least 5 images. cat needs 5 more, dog needs 5 more."
        )
        assert not browser.done

    def test_finish_asks_then_hands_back_to_the_terminal(self, labeling):
        client, browser = labeling
        for i in range(10):
            client.post(
                "/api/label/assign", json={"index": i, "class": "cat" if i < 5 else "dog"}
            )
        first = client.post("/api/label/finish", json={"confirmed": False}).json()
        assert first["status"] == "confirm"
        assert first["message"] == (
            "2 images will not be included: 0 skipped, 2 not yet reached."
        )
        assert not browser.done
        second = client.post("/api/label/finish", json={"confirmed": True}).json()
        assert second["status"] == "finished"
        assert browser.done


# ------------------------------------------------------------------ curation


class TestCurationRoutes:
    """The curation page's routes over a real controller and ``curation.json``.

    Covers plan § *Curation Server*: the timer resets on image select or
    deselect, tab switch and Fetch More; reading state does not. Every toggle
    is written before the response returns.
    """

    @pytest.fixture
    def curation(self, fake_home: Path, clock: FakeClock) -> tuple[TestClient, object]:
        from optica.input.curation import load_view, open_session
        from optica.input.fetch import ClassFetchReport
        from optica.server.curation import CurationController

        for name in ("cat", "dog"):
            folder = fake_home / ".optica" / "staging" / name
            folder.mkdir(parents=True)
            for i in range(1, 13):
                (folder / f"{i:04d}.jpg").write_bytes(f"{name}{i}".encode())

        def fetcher(name: str, count: int, on_image: object) -> ClassFetchReport:
            return ClassFetchReport(name, count)

        controller = CurationController(
            load_view(), open_session(), 50, reload=load_view, fetch_more=fetcher
        )
        browser = BrowserSession(controller, IdleTimer(60, clock=clock), token="c" * 32)
        browser.port = PORT
        client = TestClient(create_app(browser), base_url=BASE)
        response = client.get(f"/?token={browser.token}", follow_redirects=False)
        assert response.status_code == 303
        return client, browser

    def test_the_page_is_served(self, curation):
        client, _ = curation
        response = client.get("/")
        assert response.status_code == 200
        assert "<title>Optica — Curate</title>" in response.text
        assert client.get("/static/curation.js").status_code == 200

    def test_state_is_not_activity(self, curation, clock):
        client, _ = curation
        clock.now += 40 * 60
        body = client.get("/api/curate/state").json()
        assert body["navigation"] == "tabs"
        assert [c["name"] for c in body["classes"]] == ["cat", "dog"]
        assert client.get("/api/heartbeat").json()["remaining_seconds"] == 20 * 60

    @pytest.mark.parametrize(
        ("path", "payload"),
        [
            ("/api/curate/select", {"class": 0, "image": 0, "selected": False}),
            ("/api/curate/select-all", {"class": 1, "selected": False}),
            ("/api/curate/active", {"class": 1}),
            ("/api/curate/fetch-more", {"class": 0}),
        ],
    )
    def test_each_decision_is_activity(self, curation, clock, path, payload):
        client, _ = curation
        clock.now += 40 * 60
        assert client.post(path, json=payload).status_code == 200
        assert client.get("/api/heartbeat").json()["remaining_seconds"] == 3600

    def test_a_toggle_is_written_before_it_returns(self, curation, fake_home):
        import json

        client, _ = curation
        client.post(
            "/api/curate/select", json={"class": 1, "image": 3, "selected": False}
        )
        stored = json.loads(
            (fake_home / ".optica" / "staging" / "curation.json").read_text(
                encoding="utf-8"
            )
        )
        assert [Path(p).name for p in stored["deselected"]["dog"]] == ["0004.jpg"]

    @pytest.mark.parametrize(
        "payload",
        [
            {"class": 0, "image": 0},
            {"class": 0, "image": 0, "selected": "no"},
            {"class": True, "image": 0, "selected": False},
            {"class": 0, "image": 99, "selected": False},
            {"class": 5, "image": 0, "selected": False},
        ],
    )
    def test_a_malformed_toggle_is_a_400(self, curation, payload):
        client, browser = curation
        assert client.post("/api/curate/select", json=payload).status_code == 400
        assert browser.controller.session.deselected == {}

    def test_confirm_blocked_by_a_class_with_nothing_selected(self, curation):
        client, browser = curation
        client.post("/api/curate/select-all", json={"class": 0, "selected": False})
        body = client.post("/api/curate/confirm").json()
        assert body["status"] == "blocked"
        assert body["hint"] == "Select at least one image in cat to confirm."
        assert not browser.done

    def test_confirm_hands_back_to_the_terminal(self, curation):
        client, browser = curation
        assert client.post("/api/curate/confirm").json()["status"] == "finished"
        assert browser.done
