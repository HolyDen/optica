"""``optica label`` and ``optica curate`` over a real socket.

Covers pass 3's milestone — *both start, serve their page, and write back through
their session files* — plan § "Labeling & Curation" → *Curation Server* (the
port rule, "localhost only", the resolved port reported, the idle timeout
treated as an interruption) and *Staging shapes* (every decision written to its
session file as it happens), and *Terminal-side completion for browser steps*.

The unit tests reach these commands with ``serve`` replaced, or reach the routes
through an in-process test client. Here nothing is replaced but the browser: the
command runs in a worker thread exactly as the console script runs it, uvicorn
binds a real port, and an HTTP client plays the page — opening the tokened link
the command printed, reading the page and its scripts, and sending the page's
requests. The browser launch is replaced by a function that hands the URL to the
test; everything after it is real.

Each test constructs the port it uses (``curation_port`` in ``.optica.toml``,
chosen free by binding it) and a short idle timer, so a failing test ends in
seconds instead of holding a server for the default hour.

Needs the web extra; skipped where it is absent, which includes CI. The
stored *form* of a deselection is deliberately not asserted here — it is under
review (``notes/build-log.md``, option B).
"""

from __future__ import annotations

import importlib.util
import json
import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest
from PIL import Image

from optica.cli.main import app
from optica.exceptions import ExitCode
from optica.input.sessions import labeling_dir
from optica.server import app as server_app

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None
    or importlib.util.find_spec("uvicorn") is None,
    reason="optica[web] is not installed (CI installs Core and [test] only)",
)

_WAIT = 20.0


def _free_port() -> int:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = int(probe.getsockname()[1])
    probe.close()
    return port


def _images(folder: Path, count: int, *, names: str = "IMG_{:04d}.jpg") -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(count):
        path = folder / names.format(i + 1)
        Image.new("RGB", (150, 150), ((i * 41) % 256, (i * 67) % 256, 120)).save(
            path, "JPEG"
        )
        paths.append(path)
    return paths


@dataclass
class Running:
    """A command running in a worker thread, and the URL it asked a browser to open."""

    thread: threading.Thread
    url_ready: threading.Event = field(default_factory=threading.Event)
    url: str = ""
    code: int | None = None

    def wait_for_url(self) -> str:
        assert self.url_ready.wait(_WAIT), "the command never tried to open a browser"
        return self.url

    def wait_for_exit(self) -> int:
        self.thread.join(_WAIT)
        assert not self.thread.is_alive(), "the command did not hand back"
        assert self.code is not None
        return self.code


@pytest.fixture
def workspace(
    fake_home: Path, project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    port = _free_port()
    (project_dir / ".optica.toml").write_text(
        f"curation_port = {port}\n", encoding="utf-8"
    )
    # A 0.1-minute idle timeout — long enough for a test's requests, each of
    # which resets it, short enough that a failing test cannot hang for an hour.
    monkeypatch.setattr(
        "optica.cli.classify.IdleTimer", lambda minutes: server_app.IdleTimer(0.1)
    )
    return project_dir


@pytest.fixture
def launch(monkeypatch: pytest.MonkeyPatch) -> Iterator[object]:
    started: list[Running] = []

    def run(argv: list[str]) -> Running:
        running = Running(thread=threading.Thread(target=lambda: None))

        def fake_browser(url: str, *args: object, **kwargs: object) -> bool:
            running.url = url
            running.url_ready.set()
            return True

        # Overrides the suite's autouse guard for this test only: the one
        # replaced piece. A real tab never opens.
        monkeypatch.setattr("webbrowser.open", fake_browser)

        def target() -> None:
            running.code = app.invoke_guarded(argv)

        running.thread = threading.Thread(target=target, daemon=True)
        running.thread.start()
        started.append(running)
        return running

    yield run
    for running in started:
        running.thread.join(_WAIT)


@contextmanager
def _client(url: str) -> Iterator[httpx.Client]:
    """A client that has opened the tokened link, as the browser would."""
    origin = url.split("/?", 1)[0]
    with httpx.Client(base_url=origin, timeout=10.0) as client:
        opened = client.get(url, follow_redirects=True)
        assert opened.status_code == 200, opened.text
        yield client


# -------------------------------------------------------------------- label


class TestLabelOverASocket:
    def test_starts_serves_its_page_and_writes_through_the_session_file(
        self, workspace, launch, fake_home, capsys
    ):
        _images(workspace / "images", 10)
        running = launch(["label", "--folder", "images", "-c", "cat,dog"])
        url = running.wait_for_url()
        port = int(url.split(":")[2].split("/")[0])
        assert url.startswith(f"http://127.0.0.1:{port}/?token=")

        with _client(url) as client:
            page = client.get("/")
            assert "<title>Optica — Label</title>" in page.text
            for asset in ("shared.js", "shared.css", "labeling.js"):
                assert client.get(f"/static/{asset}").status_code == 200
            state = client.get("/api/label/state").json()
            assert state["position"] == "1 of 10"
            assert state["widget"] == "radio"

            for index in range(3):
                client.post("/api/label/assign", json={"index": index, "class": "cat"})
            # Written through the session file, before Finish, over the wire.
            [stored] = sorted(labeling_dir(fake_home).glob("*.json"))
            entries = json.loads(stored.read_text(encoding="utf-8"))["entries"]
            assert [e["class"] for e in entries.values()] == ["cat", "cat", "cat"]

            for index in range(3, 5):
                client.post("/api/label/assign", json={"index": index, "class": "cat"})
            for index in range(5, 10):
                client.post("/api/label/assign", json={"index": index, "class": "dog"})
            finished = client.post("/api/label/finish", json={"confirmed": False}).json()
            assert finished["status"] == "finished"

        assert running.wait_for_exit() == ExitCode.SUCCESS
        out = capsys.readouterr().out
        assert f"Labeling 10 images at http://127.0.0.1:{port}/?token=" in out
        assert "Labeling complete — 10 images labeled across 2 classes" in out
        dataset = workspace / "dataset"
        assert {d.name: len(list(d.iterdir())) for d in dataset.iterdir()} == {
            "cat": 5,
            "dog": 5,
        }
        assert list(labeling_dir(fake_home).glob("*.json")) == []

    def test_only_the_tokened_link_opens_it(self, workspace, launch):
        _images(workspace / "images", 6)
        running = launch(["label", "--folder", "images", "-c", "cat,dog"])
        url = running.wait_for_url()
        origin = url.split("/?", 1)[0]
        port = origin.rsplit(":", 1)[1]
        with httpx.Client(base_url=origin, timeout=10.0) as stranger:
            assert stranger.get("/").status_code == 403
            assert stranger.get("/api/label/state").status_code == 403
            assert (
                stranger.get("/", headers={"Host": f"evil.example:{port}"}).status_code
                == 403
            )
            assert (
                stranger.post(
                    "/api/label/assign", json={"index": 0, "class": "cat"}
                ).status_code
                == 403
            )
        # The legitimate page still works, then the idle timer ends the session.
        with _client(url) as client:
            assert client.get("/api/label/state").status_code == 200
        assert running.wait_for_exit() == ExitCode.ABORTED

    def test_idle_timeout_hands_back_as_incomplete_and_keeps_progress(
        self, workspace, launch, fake_home, capsys
    ):
        _images(workspace / "images", 6)
        running = launch(["label", "--folder", "images", "-c", "cat,dog"])
        with _client(running.wait_for_url()) as client:
            client.post("/api/label/assign", json={"index": 0, "class": "dog"})
        assert running.wait_for_exit() == ExitCode.ABORTED
        err = capsys.readouterr().err
        assert "Labeling incomplete — the session closed after 6 seconds" in err
        [stored] = sorted(labeling_dir(fake_home).glob("*.json"))
        assert len(json.loads(stored.read_text(encoding="utf-8"))["entries"]) == 1
        assert not (workspace / "dataset").exists()

    def test_a_taken_port_moves_to_the_next_and_says_so(self, workspace, launch, capsys):
        configured = int(
            (workspace / ".optica.toml").read_text(encoding="utf-8").split("=")[1]
        )
        holder = socket.socket()
        holder.bind(("127.0.0.1", configured))
        holder.listen()
        try:
            _images(workspace / "images", 6)
            running = launch(["label", "--folder", "images", "-c", "cat,dog"])
            url = running.wait_for_url()
            assert f"127.0.0.1:{configured}/" not in url
            assert running.wait_for_exit() == ExitCode.ABORTED
        finally:
            holder.close()
        assert f"Port {configured} is in use; the browser server is on" in (
            capsys.readouterr().err
        )


# ------------------------------------------------------------------- curate


class TestCurateOverASocket:
    def test_starts_serves_its_page_and_writes_through_curation_json(
        self, workspace, launch, fake_home, capsys
    ):
        staging = fake_home / ".optica" / "staging"
        _images(staging / "cat", 12, names="{:04d}.jpg")
        _images(staging / "dog", 12, names="{:04d}.jpg")
        running = launch(["curate"])
        url = running.wait_for_url()

        with _client(url) as client:
            assert "<title>Optica — Curate</title>" in client.get("/").text
            assert client.get("/static/curation.js").status_code == 200
            state = client.get("/api/curate/state").json()
            assert state["navigation"] == "tabs"
            assert client.get(f"/api/image/{state['images'][0]['id']}").status_code == 200

            for image in (0, 1):
                client.post(
                    "/api/curate/select",
                    json={"class": 0, "image": image, "selected": False},
                )
            # Written through curation.json before Confirm, over the wire.
            stored = json.loads((staging / "curation.json").read_text(encoding="utf-8"))
            assert len(stored["deselected"]["cat"]) == 2
            client.post("/api/curate/active", json={"class": 1})
            assert (
                json.loads((staging / "curation.json").read_text(encoding="utf-8"))[
                    "active_class"
                ]
                == "dog"
            )
            assert client.post("/api/curate/confirm").json()["status"] == "finished"

        assert running.wait_for_exit() == ExitCode.SUCCESS
        out = capsys.readouterr().out
        assert "Curating 24 images across 2 classes at http://127.0.0.1:" in out
        assert "Curation complete — 22 images selected across 2 classes" in out
        dataset = workspace / "dataset"
        assert {d.name: len(list(d.iterdir())) for d in dataset.iterdir()} == {
            "cat": 10,
            "dog": 12,
        }
        assert not (staging / "curation.json").exists()
