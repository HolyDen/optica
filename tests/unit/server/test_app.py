"""Tests for ``optica.server.app``.

Covers plan § "Labeling & Curation" → *Curation Server* (port auto-increment,
the 20-attempt range stopping at 65535, the resolved port reported, the idle
timeout and its warning offsets, timeout treated as interruption), *Labeling UI*
→ *Session timer triggers* (activity restarts the schedule), and § "Exceptions"
→ *Lazy imports* (``OpticaWebError``) and ``OpticaBrowserServerError``.

Everything above the ``serve`` tests runs without the web extra, which is how CI
runs it. The ``serve`` tests start a real uvicorn and skip where it is absent.
"""

from __future__ import annotations

import importlib.util
import socket
import sys
import threading
from pathlib import Path

import pytest

from optica.exceptions import OpticaBrowserServerError, OpticaError, OpticaWebError
from optica.server import app as server_app
from optica.server.app import (
    BrowserSession,
    IdleTimer,
    Outcome,
    bind_first_free,
    candidate_ports,
    format_duration,
    load_web,
    serve,
    warning_schedule,
)

requires_web = pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None
    or importlib.util.find_spec("uvicorn") is None,
    reason="optica[web] is not installed (CI installs Core and [test] only)",
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, minutes: float) -> None:
        self.now += minutes * 60


class FakeController:
    page = "labeling"

    def __init__(self, images: dict[str, Path] | None = None) -> None:
        self.images = images or {}

    def image_path(self, image_id: str) -> Path | None:
        return self.images.get(image_id)


# ----------------------------------------------------------------------- port


class TestCandidatePorts:
    def test_twenty_attempts_from_the_configured_port(self):
        ports = candidate_ports(8765)
        assert list(ports) == list(range(8765, 8785))
        assert len(ports) == 20

    def test_stops_early_at_the_key_upper_bound(self):
        assert list(candidate_ports(65530)) == [65530, 65531, 65532, 65533, 65534, 65535]

    def test_the_top_port_is_a_range_of_one(self):
        assert list(candidate_ports(65535)) == [65535]


class TestBindFirstFree:
    def test_a_port_another_socket_holds_is_refused_by_the_os(self):
        # The condition is constructed: a socket this test owns holds the port.
        holder = socket.socket()
        holder.bind((server_app.HOST, 0))
        holder.listen()
        taken = holder.getsockname()[1]
        try:
            with pytest.raises(OSError):
                server_app._bind(taken)
        finally:
            holder.close()

    def test_a_taken_port_is_skipped_for_the_next(self):
        holder = socket.socket()
        holder.bind((server_app.HOST, 0))
        holder.listen()
        taken = holder.getsockname()[1]
        try:
            if taken + 1 > server_app.MAX_PORT:
                pytest.skip("the OS handed out the top port; nothing above it to try")
            sock = bind_first_free(taken)
            try:
                port = sock.getsockname()[1]
                assert port != taken
                assert port in candidate_ports(taken)
            finally:
                sock.close()
        finally:
            holder.close()

    def test_the_first_port_that_binds_wins_in_order(self):
        tried: list[int] = []
        refused = {8765, 8766, 8767}

        def bind(port: int) -> socket.socket:
            tried.append(port)
            if port in refused:
                raise OSError("in use")
            return socket.socket()

        sock = bind_first_free(8765, bind=bind)
        sock.close()
        assert tried == [8765, 8766, 8767, 8768]

    def test_every_port_taken_names_the_range_tried(self):
        def bind(port: int) -> socket.socket:
            raise OSError("in use")

        with pytest.raises(OpticaBrowserServerError) as caught:
            bind_first_free(8765, bind=bind)
        assert "8765-8784" in caught.value.message

    def test_the_range_named_stops_at_65535(self):
        tried: list[int] = []

        def bind(port: int) -> socket.socket:
            tried.append(port)
            raise OSError("in use")

        with pytest.raises(OpticaBrowserServerError) as caught:
            bind_first_free(65530, bind=bind)
        assert tried == list(range(65530, 65536))
        assert "65530-65535" in caught.value.message

    def test_it_is_a_browser_server_error_not_a_generic_one(self):
        with pytest.raises(OpticaBrowserServerError):
            bind_first_free(8765, bind=lambda port: (_ for _ in ()).throw(OSError()))


# ---------------------------------------------------------------------- timer


class TestWarningSchedule:
    def test_the_default_warns_at_30_and_55(self):
        # Plan: "at the 60-minute default is 30 and 55".
        assert warning_schedule(60) == [30, 55]

    def test_offsets_are_absolute_minutes_before_shutdown(self):
        assert warning_schedule(90) == [60, 85]
        assert warning_schedule(31) == [1, 26]

    def test_an_offset_at_session_start_is_suppressed(self):
        assert warning_schedule(30) == [25]
        assert warning_schedule(6) == [1]

    @pytest.mark.parametrize(("timeout", "half"), [(5, 2.5), (3, 1.5), (1, 0.5)])
    def test_if_neither_fits_one_warning_fires_at_half(self, timeout, half):
        assert warning_schedule(timeout) == [half]

    def test_zero_disables(self):
        assert warning_schedule(0) == []

    @pytest.mark.parametrize("timeout", range(1, 121))
    def test_no_configured_value_produces_a_silent_shutdown(self, timeout):
        schedule = warning_schedule(timeout)
        assert schedule
        assert all(0 < at < timeout for at in schedule)


class TestFormatDuration:
    @pytest.mark.parametrize(
        ("seconds", "text"),
        [
            (1800, "30 minutes"),
            (300, "5 minutes"),
            (60, "1 minute"),
            (150, "2 minutes 30 seconds"),
            (45, "45 seconds"),
            (1, "1 second"),
            (0, "0 seconds"),
        ],
    )
    def test_reads_as_a_person_says_it(self, seconds, text):
        assert format_duration(seconds) == text


class TestIdleTimer:
    def test_warnings_fire_once_each_then_it_expires(self):
        clock = FakeClock()
        timer = IdleTimer(60, clock=clock)
        assert timer.poll() == (None, False)
        clock.advance(30)
        assert timer.poll() == (30 * 60, False)
        assert timer.poll() == (None, False)
        clock.advance(25)
        assert timer.poll() == (5 * 60, False)
        clock.advance(5)
        assert timer.poll() == (None, True)

    def test_after_a_stall_only_the_latest_warning_is_announced(self):
        clock = FakeClock()
        timer = IdleTimer(60, clock=clock)
        clock.advance(56)
        assert timer.poll() == (5 * 60, False)

    def test_activity_restarts_the_whole_schedule(self):
        clock = FakeClock()
        timer = IdleTimer(60, clock=clock)
        clock.advance(56)
        timer.poll()
        timer.touch()
        clock.advance(29)
        assert timer.poll() == (None, False)
        clock.advance(1)
        assert timer.poll() == (30 * 60, False)
        clock.advance(30)
        assert timer.poll()[1] is True

    def test_status_reports_remaining_time_and_the_due_warning(self):
        clock = FakeClock()
        timer = IdleTimer(60, clock=clock)
        status = timer.status()
        assert status.enabled
        assert status.remaining_seconds == 3600
        assert status.warning_seconds_left is None
        clock.advance(31)
        status = timer.status()
        assert status.remaining_seconds == 29 * 60
        assert status.warning_seconds_left == 30 * 60
        assert not status.expired

    def test_status_does_not_consume_the_terminal_warning(self):
        clock = FakeClock()
        timer = IdleTimer(60, clock=clock)
        clock.advance(30)
        timer.status()
        assert timer.poll() == (30 * 60, False)

    def test_zero_never_expires(self):
        clock = FakeClock()
        timer = IdleTimer(0, clock=clock)
        clock.advance(10_000)
        assert not timer.enabled
        assert timer.poll() == (None, False)
        status = timer.status()
        assert status.remaining_seconds is None
        assert not status.expired


# -------------------------------------------------------------------- session


class TestBrowserSession:
    def test_a_generated_token_is_long_and_unguessable(self):
        a = BrowserSession(FakeController(), IdleTimer(60))
        b = BrowserSession(FakeController(), IdleTimer(60))
        assert a.token != b.token
        assert len(a.token) >= 32

    def test_hosts_and_cookie_are_scoped_to_the_port(self):
        session = BrowserSession(FakeController(), IdleTimer(60))
        session.port = 8771
        assert session.allowed_hosts == {"127.0.0.1:8771", "localhost:8771"}
        assert session.cookie_name == "optica_8771"

    def test_activity_touches_the_timer(self):
        clock = FakeClock()
        timer = IdleTimer(60, clock=clock)
        session = BrowserSession(FakeController(), timer)
        clock.advance(50)
        session.activity()
        assert timer.status().remaining_seconds == 3600

    def test_the_first_failure_is_kept_and_ends_the_session(self):
        session = BrowserSession(FakeController(), IdleTimer(60))
        first, second = OSError("disk full"), ValueError("later")
        session.fail(first)
        session.fail(second)
        assert session.error is first
        assert session.done


# ------------------------------------------------------------------ the extra


def _uvicorn_or_stand_in() -> object:
    # Lets the import of uvicorn succeed, so what fails is the next import.
    return sys.modules.get("uvicorn") or object()


class TestLoadWeb:
    def test_a_missing_uvicorn_is_the_web_extra_error(self, monkeypatch):
        # Constructed: None in sys.modules makes the import fail whether or not
        # uvicorn is installed on this machine.
        monkeypatch.setitem(sys.modules, "uvicorn", None)
        with pytest.raises(OpticaWebError) as caught:
            load_web()
        assert caught.value.message == (
            "This operation requires the web extras. "
            "Run: optica setup or pip install optica[web]"
        )

    def test_a_missing_fastapi_is_the_web_extra_error(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "uvicorn", _uvicorn_or_stand_in())
        monkeypatch.setitem(sys.modules, "fastapi", None)
        monkeypatch.delitem(sys.modules, "optica.server.routes", raising=False)
        with pytest.raises(OpticaWebError):
            load_web()

    def test_an_import_error_inside_optica_is_not_disguised(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "uvicorn", _uvicorn_or_stand_in())
        monkeypatch.setitem(sys.modules, "optica.server.routes", None)
        with pytest.raises(ImportError) as caught:
            load_web()
        assert not isinstance(caught.value, OpticaError)

    def test_the_module_imports_without_the_extra(self):
        # app.py itself never imports FastAPI or uvicorn at module level.
        source = Path(server_app.__file__).read_text(encoding="utf-8")
        top_level = [
            line
            for line in source.splitlines()
            if line.startswith(("import ", "from "))
        ]
        assert not [
            line for line in top_level if any(m in line for m in ("fastapi", "uvicorn"))
        ]


# ---------------------------------------------------------------------- serve


class StallingSession(BrowserSession):
    """Raises KeyboardInterrupt from its wait, as Ctrl+C does."""

    def wait(self, timeout: float) -> bool:
        raise KeyboardInterrupt


def _finishing(session: BrowserSession):
    def open_browser(url: str) -> bool:
        session.finish()
        return True

    return open_browser


@requires_web
class TestServe:
    def _session(self, timer: IdleTimer | None = None) -> BrowserSession:
        return BrowserSession(FakeController(), timer or IdleTimer(60))

    def _free_port(self) -> int:
        probe = socket.socket()
        probe.bind((server_app.HOST, 0))
        port = int(probe.getsockname()[1])
        probe.close()
        return port

    def _port_is_released(self, port: int) -> bool:
        try:
            server_app._bind(port).close()
        except OSError:
            return False
        return True

    def test_the_page_finishing_ends_the_session(self, capsys):
        session = self._session()
        opened: list[str] = []

        def open_browser(url: str) -> bool:
            opened.append(url)
            threading.Timer(0.2, session.finish).start()
            return True

        port = self._free_port()
        outcome = serve(
            session,
            configured_port=port,
            headline="Labeling 3 images",
            open_browser=open_browser,
        )
        assert outcome is Outcome.FINISHED
        assert opened == [f"http://127.0.0.1:{port}/?token={session.token}"]
        assert f"Labeling 3 images at http://127.0.0.1:{port}/" in capsys.readouterr().out
        assert self._port_is_released(port)

    def test_a_launch_failure_is_a_browser_server_error_and_stops_the_server(self):
        port = self._free_port()
        with pytest.raises(OpticaBrowserServerError) as caught:
            serve(
                self._session(),
                configured_port=port,
                headline="Labeling",
                open_browser=lambda url: False,
            )
        assert "browser" in caught.value.message
        assert self._port_is_released(port)

    def test_a_different_port_is_reported(self, capsys):
        holder = socket.socket()
        holder.bind((server_app.HOST, 0))
        holder.listen()
        taken = holder.getsockname()[1]
        session = self._session()
        try:
            serve(
                session,
                configured_port=taken,
                headline="Curating",
                open_browser=_finishing(session),
            )
        finally:
            holder.close()
        err = capsys.readouterr().err
        assert (
            f"Port {taken} is in use; the browser server is on {session.port} instead."
            in err
        )

    def test_the_same_port_is_not_reported(self, capsys):
        session = self._session()
        serve(
            session,
            configured_port=self._free_port(),
            headline="Curating",
            open_browser=_finishing(session),
        )
        assert "is in use" not in capsys.readouterr().err

    def test_idle_timeout_ends_the_session_as_timed_out(self):
        # 0.01 minutes: the timer, not a sleep, decides when this returns.
        session = self._session(IdleTimer(0.01))
        outcome = serve(
            session,
            configured_port=self._free_port(),
            headline="Labeling",
            open_browser=lambda url: True,
        )
        assert outcome is Outcome.TIMED_OUT

    def test_ctrl_c_is_an_interruption_and_stops_the_server(self):
        port = self._free_port()
        session = StallingSession(FakeController(), IdleTimer(60))
        outcome = serve(
            session,
            configured_port=port,
            headline="Labeling",
            open_browser=lambda url: True,
        )
        assert outcome is Outcome.INTERRUPTED
        assert self._port_is_released(port)

    def test_an_error_recorded_by_a_request_is_raised_after_shutdown(self):
        session = self._session()
        failure = OpticaError("The session file could not be written.")

        def open_browser(url: str) -> bool:
            session.fail(failure)
            return True

        with pytest.raises(OpticaError) as caught:
            serve(
                session,
                configured_port=self._free_port(),
                headline="Labeling",
                open_browser=open_browser,
            )
        assert caught.value is failure

    def test_a_non_optica_error_is_wrapped_as_a_browser_server_error(self):
        session = self._session()

        def open_browser(url: str) -> bool:
            session.fail(PermissionError("denied"))
            return True

        with pytest.raises(OpticaBrowserServerError) as caught:
            serve(
                session,
                configured_port=self._free_port(),
                headline="Labeling",
                open_browser=open_browser,
            )
        assert "PermissionError: denied" in (caught.value.why or "")
