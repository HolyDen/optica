"""The browser server's lifecycle: port, idle timer, threads and shutdown.

Implements plan § "Labeling & Curation" → *Curation Server* (the port rule, the
idle timeout and its two warnings, interruption), the terminal half of *Labeling
UI* → *Session timer triggers*, and § "Exceptions" → *Lazy imports* for the
``optica[web]`` extra.

Both pages run through one server — ``optica label`` and ``optica curate`` differ
only in the page controller they hand to :func:`serve` — which is why its failure
class, :class:`~optica.exceptions.OpticaBrowserServerError`, names the subsystem
rather than a caller.

**Nothing in this module imports FastAPI or uvicorn at module level.** Everything
here that is logic rather than wiring — the port rule, the warning schedule, the
idle timer — is therefore importable and testable in a Core install, which is
what CI is (plan § "Version-bound strategy": no CI leg installs the web extra).
:func:`load_web` is the one place the extra is imported, and it re-raises a
missing extra as :class:`~optica.exceptions.OpticaWebError`.

Threads: uvicorn runs in a worker thread, where it installs no signal handlers
(``notes/verified.md`` § "uvicorn 0.53.0 can run in a worker thread"), so Ctrl+C
reaches the main thread, which is the one waiting in :func:`serve`.
"""

from __future__ import annotations

import os
import secrets
import socket
import sys
import threading
import time
import webbrowser
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Protocol

from optica.exceptions import OpticaBrowserServerError, OpticaError, OpticaWebError
from optica.utils import logging as olog
from optica.utils import prompts

if TYPE_CHECKING:
    from types import ModuleType

__all__ = [
    "HOST",
    "MAX_PORT",
    "PORT_ATTEMPTS",
    "STATIC_DIR",
    "WARNING_OFFSETS_MINUTES",
    "BrowserSession",
    "IdleTimer",
    "Outcome",
    "PageController",
    "TimerStatus",
    "bind_first_free",
    "candidate_ports",
    "format_duration",
    "load_web",
    "serve",
    "warning_schedule",
]

HOST: Final = "127.0.0.1"
"""Localhost only in V1: bound to the loopback address, never network-exposed."""

PORT_ATTEMPTS: Final = 20
"""Ports tried, counting the configured one, before giving up."""

MAX_PORT: Final = 65535
"""``curation_port``'s own upper bound, where auto-increment stops early."""

WARNING_OFFSETS_MINUTES: Final = (30, 5)
"""Warnings fire this many minutes **before shutdown** — absolute, not
proportional: five minutes is how long a person needs to respond, which is a
property of the user and not a fraction of the session."""

STATIC_DIR: Final = Path(__file__).resolve().parent / "static"
"""The two pages and their shared JS and CSS. Vanilla, no build step."""

_WEB_MODULES: Final = frozenset({"fastapi", "starlette", "uvicorn"})
_STARTUP_TIMEOUT_SECONDS: Final = 10.0
_POLL_SECONDS: Final = 0.25


# ------------------------------------------------------------------ the extra


def load_web() -> tuple[ModuleType, Callable[[BrowserSession], Any]]:
    """Import uvicorn and the route factory, or raise the missing-extra error.

    The lazy import the optional-extras architecture rests on: a raw
    ``ImportError`` never reaches the user. Only an import failure *of the extra
    itself* is translated — an ``ImportError`` raised from inside Optica's own
    route module is a bug, and is left to surface as one.

    Returns:
        ``(uvicorn, create_app)``.

    Raises:
        OpticaWebError: When FastAPI, Starlette or uvicorn is not installed.
    """
    try:
        import uvicorn

        from optica.server.routes import create_app
    except ImportError as exc:
        if (exc.name or "").partition(".")[0] in _WEB_MODULES:
            raise OpticaWebError() from exc
        raise
    return uvicorn, create_app


# ----------------------------------------------------------------------- port


def candidate_ports(configured: int) -> range:
    """The ports tried: the configured one and the next, up to 20 in all.

    Stops early at 65535 rather than wrapping.
    """
    return range(configured, min(configured + PORT_ATTEMPTS, MAX_PORT + 1))


def _bind(port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if sys.platform == "win32":
            # Without this, a later process setting SO_REUSEADDR could bind over
            # Optica's port on Windows. See notes/verified.md.
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            # On POSIX this reuses a port the previous run left in TIME_WAIT and
            # still refuses a port another program is listening on.
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((HOST, port))
    except BaseException:
        sock.close()
        raise
    return sock


def bind_first_free(
    configured: int, *, bind: Callable[[int], socket.socket] = _bind
) -> socket.socket:
    """Bind the first free port from ``configured``, and return the bound socket.

    The socket itself is handed to uvicorn, so the port found free is the port
    served — there is no window between checking a port and binding it.

    Args:
        configured: ``curation_port``.
        bind: Binds one port or raises ``OSError``. Injected by tests.

    Raises:
        OpticaBrowserServerError: When every port in the range is taken, naming
            the range tried.
    """
    ports = candidate_ports(configured)
    for port in ports:
        try:
            return bind(port)
        except OSError:
            continue
    span = f"{ports[0]}" if len(ports) == 1 else f"{ports[0]}-{ports[-1]}"
    raise OpticaBrowserServerError(
        f"No free port for the browser server: {span} are all in use.",
        why=f"Optica tries {len(ports)} port{'s' if len(ports) != 1 else ''} "
        f"starting from curation_port ({configured}).",
        fix=[
            "Close whatever is using those ports, or start from another one:",
            "optica config --set curation_port 9000",
        ],
    )


# ---------------------------------------------------------------------- timer


def warning_schedule(timeout_minutes: float) -> list[float]:
    """Minutes after the last activity at which a warning fires.

    Warnings sit at fixed offsets from shutdown — 30 and 5 minutes before it, so
    30 and 55 at the 60-minute default. An offset that would fall at or before
    session start is suppressed; if neither fits, a single warning fires at half
    the timeout, so **no configured value produces a silent shutdown**. A
    timeout of ``0`` disables the timer and has no warnings.
    """
    if timeout_minutes <= 0:
        return []
    fitting = [
        timeout_minutes - before
        for before in WARNING_OFFSETS_MINUTES
        if timeout_minutes - before > 0
    ]
    return fitting or [timeout_minutes / 2]


def format_duration(seconds: float) -> str:
    """``30 minutes``, ``2 minutes 30 seconds``, ``45 seconds``."""
    total = max(0, round(seconds))
    minutes, rest = divmod(total, 60)
    parts = []
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if rest or not minutes:
        parts.append(f"{rest} second{'s' if rest != 1 else ''}")
    return " ".join(parts)


@dataclass(frozen=True)
class TimerStatus:
    """The idle timer, as the browser's heartbeat reports it.

    Attributes:
        enabled: False when ``curation_timeout_minutes`` is ``0``.
        remaining_seconds: Until shutdown, or None when disabled.
        warning_seconds_left: When a warning is due in this idle period, the
            time before shutdown that warning announced; otherwise None.
        expired: Whether the timeout has passed.
    """

    enabled: bool
    remaining_seconds: float | None
    warning_seconds_left: float | None
    expired: bool


class IdleTimer:
    """The session's idle timeout. Thread-safe.

    Any qualifying activity calls :meth:`touch`, which restarts the whole
    schedule. What qualifies differs by page — the page controllers decide —
    and "Keep Session Active" and a terminal keypress qualify on both.

    Args:
        timeout_minutes: ``curation_timeout_minutes``; ``0`` disables.
        clock: Seconds, monotonic. Injected by tests.
    """

    def __init__(
        self, timeout_minutes: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._timeout = timeout_minutes * 60
        self._schedule = [minutes * 60 for minutes in warning_schedule(timeout_minutes)]
        self._clock = clock
        self._lock = threading.Lock()
        self._last = clock()
        self._fired = 0

    @property
    def enabled(self) -> bool:
        """Whether a timeout is configured at all."""
        return self._timeout > 0

    @property
    def timeout_seconds(self) -> float:
        """The configured timeout."""
        return self._timeout

    def touch(self) -> None:
        """Record activity: the schedule restarts from now."""
        with self._lock:
            self._last = self._clock()
            self._fired = 0

    def _due(self, elapsed: float) -> int:
        return sum(1 for at in self._schedule if elapsed >= at)

    def poll(self) -> tuple[float | None, bool]:
        """What the terminal should announce since the last poll.

        Returns:
            ``(warning_seconds_left, expired)`` — the newest warning that became
            due since the previous poll, if any (after a long stall only the
            latest is worth printing), and whether the session has timed out.
        """
        with self._lock:
            if not self.enabled:
                return None, False
            elapsed = self._clock() - self._last
            due = self._due(elapsed)
            warning = None
            if due > self._fired:
                warning = self._timeout - self._schedule[due - 1]
                self._fired = due
            return warning, elapsed >= self._timeout

    def status(self) -> TimerStatus:
        """The timer's state, for the browser."""
        with self._lock:
            if not self.enabled:
                return TimerStatus(False, None, None, False)
            elapsed = self._clock() - self._last
            due = self._due(elapsed)
            warning = self._timeout - self._schedule[due - 1] if due else None
            return TimerStatus(
                True,
                max(0.0, self._timeout - elapsed),
                warning,
                elapsed >= self._timeout,
            )


# --------------------------------------------------------------- key presses


if sys.platform == "win32":

    def _watch_keys(stop: threading.Event, on_key: Callable[[], None]) -> None:
        import msvcrt

        while not stop.wait(0.1):
            while msvcrt.kbhit():
                msvcrt.getwch()
                on_key()

else:

    def _watch_keys(stop: threading.Event, on_key: Callable[[], None]) -> None:
        import select
        import termios
        import tty

        fd = sys.stdin.fileno()
        saved = termios.tcgetattr(fd)
        try:
            # cbreak, not raw: a key arrives without Enter, and Ctrl+C still
            # raises SIGINT in the main thread.
            tty.setcbreak(fd)
            while not stop.is_set():
                ready, _, _ = select.select([fd], [], [], 0.1)
                if ready:
                    os.read(fd, 1024)
                    on_key()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)


@contextmanager
def _key_watcher(on_key: Callable[[], None]) -> Iterator[None]:
    """Reset the idle timer on a terminal keypress, for the ``with`` block.

    Only where there is a terminal to press keys in.
    """
    # TODO(test): a real keypress in a real console resets the timer — needs a
    # console, which no test runner provides.
    if not prompts.is_interactive():
        yield
        return
    stop = threading.Event()
    watcher = threading.Thread(
        target=_watch_keys, args=(stop, on_key), name="optica-keys", daemon=True
    )
    watcher.start()
    try:
        yield
    finally:
        stop.set()
        watcher.join(timeout=1)


# ------------------------------------------------------------------- session


class PageController(Protocol):
    """What a page gives the shared routes. Each page adds routes of its own."""

    @property
    def page(self) -> str:
        """The page's HTML file stem under ``static/``: ``labeling`` or ``curation``."""
        ...

    def image_path(self, image_id: str) -> Path | None:
        """The file behind an image ID, or None.

        Images are served **by ID from the session's own list, never by path**,
        so the server cannot be asked for an arbitrary file.
        """
        ...


class Outcome(StrEnum):
    """How a browser session handed control back to the terminal."""

    FINISHED = "finished"
    TIMED_OUT = "timed out"
    INTERRUPTED = "interrupted"


class BrowserSession:
    """What the routes and the terminal share for one server run.

    Args:
        controller: The page.
        timer: The idle timer.
        token: The session secret. Generated when not given.
    """

    def __init__(
        self,
        controller: PageController,
        timer: IdleTimer,
        *,
        token: str | None = None,
    ) -> None:
        self.controller = controller
        self.timer = timer
        self.token = token or secrets.token_urlsafe(24)
        self.port = 0
        self.error: BaseException | None = None
        self._done = threading.Event()

    @property
    def cookie_name(self) -> str:
        """Per port: cookies on ``127.0.0.1`` are shared across ports."""
        return f"optica_{self.port}"

    @property
    def allowed_hosts(self) -> frozenset[str]:
        """``Host`` values the server answers.

        Anything else is refused, which is what stops a page on another site
        from reaching this server by pointing its own hostname at 127.0.0.1.
        """
        return frozenset({f"{HOST}:{self.port}", f"localhost:{self.port}"})

    def activity(self) -> None:
        """A qualifying event: restart the idle timer."""
        self.timer.touch()

    def finish(self) -> None:
        """The page is done; the terminal takes over."""
        self._done.set()

    def fail(self, exc: BaseException) -> None:
        """Record an error raised while handling a request, and end the session.

        A write that failed must not be survivable in silence: the terminal
        re-raises it once the server has stopped.
        """
        if self.error is None:
            self.error = exc
        self._done.set()

    @property
    def done(self) -> bool:
        """Whether the page finished or failed."""
        return self._done.is_set()

    def wait(self, timeout: float) -> bool:
        """Wait up to ``timeout`` seconds for the session to end."""
        return self._done.wait(timeout)


def serve(
    session: BrowserSession,
    *,
    configured_port: int,
    headline: str,
    open_browser: Callable[[str], bool] | None = None,
) -> Outcome:
    """Run the browser server until the page finishes, times out or is interrupted.

    Staging is preserved on every ending: a page writes each decision through
    its session file as it happens, so there is nothing to save at the end.

    Args:
        session: The shared state, holding the page controller and idle timer.
        configured_port: ``curation_port``.
        headline: What the terminal says is happening, e.g. ``Labeling 200
            images``.
        open_browser: Opens a URL, returning whether a browser was launched.
            Defaults to :func:`webbrowser.open`.

    Returns:
        How the session ended.

    Raises:
        OpticaWebError: When the web extra is missing.
        OpticaBrowserServerError: No free port, the server failed to start, or
            no browser could be launched.
        OpticaError: Re-raised when handling a request failed, such as a session
            file that could not be written.
    """
    uvicorn, create_app = load_web()
    sock = bind_first_free(configured_port)
    session.port = sock.getsockname()[1]
    if session.port != configured_port:
        # Otherwise a user who set 8765 and landed on 8771 learns it only from
        # the browser's address bar.
        olog.warn(
            f"Port {configured_port} is in use; the browser server is on "
            f"{session.port} instead."
        )
    config = uvicorn.Config(
        create_app(session),
        log_config=None,
        access_log=False,
        lifespan="off",
        timeout_graceful_shutdown=2,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [sock]},
        name="optica-browser-server",
        daemon=True,
    )
    try:
        thread.start()
        _wait_for_startup(server, thread)
        url = f"http://{HOST}:{session.port}/?token={session.token}"
        olog.status(f"{headline} at {url}")
        if session.timer.enabled:
            olog.status(
                "  Progress is saved as you go. The session closes after "
                f"{format_duration(session.timer.timeout_seconds)} without activity; "
                "Ctrl+C stops it now."
            )
        else:
            olog.status("  Progress is saved as you go. Ctrl+C stops the session.")
        # Looked up at call time, not bound as a default, so the test harness's
        # guard against launching a real browser reaches it.
        launch = open_browser or webbrowser.open
        if not launch(url):
            raise OpticaBrowserServerError(
                "Could not open a web browser.",
                why="No browser could be launched from this environment.",
                fix="Set the BROWSER environment variable to your browser's command "
                "and run the command again.",
            )
        outcome = _wait_for_end(session, thread)
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
    if session.error is not None:
        if isinstance(session.error, OpticaError):
            raise session.error
        raise OpticaBrowserServerError(
            "The browser session failed while handling a request.",
            why=f"{type(session.error).__name__}: {session.error}",
            fix="Your progress up to the failure is saved; run the command again "
            "to resume.",
        ) from session.error
    return outcome


def _wait_for_startup(server: Any, thread: threading.Thread) -> None:
    deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
    while not server.started:
        if not thread.is_alive():
            raise OpticaBrowserServerError(
                "The browser server failed to start.",
                why="uvicorn stopped during startup.",
                fix="Run again with --verbose to see why.",
            )
        if time.monotonic() > deadline:
            raise OpticaBrowserServerError(
                "The browser server did not start in time.",
                why=f"It was not accepting connections after "
                f"{_STARTUP_TIMEOUT_SECONDS:.0f} seconds.",
                fix="Run the command again.",
            )
        time.sleep(0.05)


def _wait_for_end(session: BrowserSession, thread: threading.Thread) -> Outcome:
    try:
        with _key_watcher(session.activity):
            while not session.wait(_POLL_SECONDS):
                warning, expired = session.timer.poll()
                if expired:
                    return Outcome.TIMED_OUT
                if warning is not None:
                    olog.warn(
                        f"The browser session closes in {format_duration(warning)} "
                        "without activity.",
                        fix="Press any key here, or Keep Session Active in the browser, "
                        "to keep it open.",
                    )
                if not thread.is_alive():
                    raise OpticaBrowserServerError(
                        "The browser server stopped unexpectedly.",
                        why="Its thread exited while the session was open.",
                        fix="Your progress is saved; run the command again to resume.",
                    )
            return Outcome.FINISHED
    except KeyboardInterrupt:
        return Outcome.INTERRUPTED
