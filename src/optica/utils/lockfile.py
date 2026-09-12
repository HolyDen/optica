"""The global lock file, ``~/.optica/optica.lock``.

Implements Implementation Note 2: only one write command runs at a time, and a
second is hard-blocked while the first holds the lock. The lock holds a PID, the
command name and a run ID.

A lock whose PID is no longer alive is cleaned up silently and the command
proceeds — that is the crash-recovery path, and it must not ask the user
anything.

**Liveness is not checked with ``os.kill(pid, 0)``.** That is the POSIX idiom,
but on Windows :func:`os.kill` maps every signal except the console-control ones
onto ``TerminateProcess``, so the "harmless" probe would kill the process it was
asking about. The Windows branch opens a query-only handle instead.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Final

from optica.exceptions import OpticaError

__all__ = [
    "EXEMPT_COMMANDS",
    "LockInfo",
    "acquire_lock",
    "lock_path",
    "optica_home",
    "pid_is_live",
    "read_lock",
    "release_lock",
]

EXEMPT_COMMANDS: frozenset[str] = frozenset(
    {"config --view", "config --set", "--version"}
)
"""Commands that never take the lock (Implementation Note 2).

They are read-only or write only a config key, and ``config --set`` in
particular has to run *before* ``optica setup`` ever has.
"""


@dataclass(frozen=True)
class LockInfo:
    """The contents of a held lock.

    Attributes:
        pid: The process holding it.
        command: The command name, as the user typed it.
        run_id: The run this lock belongs to, linking it to that run's log.
    """

    pid: int
    command: str
    run_id: str


def optica_home() -> Path:
    """Return ``~/.optica/``, creating it if needed."""
    home = Path.home() / ".optica"
    home.mkdir(parents=True, exist_ok=True)
    return home


def lock_path() -> Path:
    """Return the path of the global lock file."""
    return optica_home() / "optica.lock"


# The widest PID the platform's own API can represent. A value outside it is
# not a process that has ended -- it is a number that was never a PID, and both
# branches below raise on one rather than returning an answer: POSIX `os.kill`
# takes a signed 32-bit `pid_t`, and ctypes converts to a 32-bit DWORD. A lock
# file is a plain JSON file a user can hand-edit and a crash can truncate, so an
# out-of-range PID is reachable input, not a theoretical one.
_MAX_PID: Final = 2**32 - 1 if sys.platform == "win32" else 2**31 - 1


def _is_plausible_pid(pid: int) -> bool:
    """Whether ``pid`` is a number the platform could have issued as a PID."""
    return 0 < pid <= _MAX_PID


if sys.platform == "win32":

    def pid_is_live(pid: int) -> bool:
        """Whether a process with this PID is currently running.

        Opens a query-only handle rather than signalling: on Windows
        :func:`os.kill` maps every ordinary signal onto ``TerminateProcess``, so
        the POSIX ``kill(pid, 0)`` idiom would kill the process it is asking
        about.

        ``argtypes`` and ``restype`` are declared rather than inferred. Inferred,
        ctypes converts the PID to a signed C ``int`` and truncates the returned
        ``HANDLE`` to 32 bits, which is wrong on 64-bit Windows and silently so.
        """
        if not _is_plausible_pid(pid):
            return False

        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        still_active = 259

        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        )
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return bool(code.value == still_active)
        finally:
            kernel32.CloseHandle(handle)

else:

    def pid_is_live(pid: int) -> bool:
        """Whether a process with this PID is currently running.

        Signal 0 performs the error checks without sending anything.
        """
        if not _is_plausible_pid(pid):
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            # Someone else's process, which means it exists.
            return True
        except OSError:
            return False
        return True


def read_lock() -> LockInfo | None:
    """Return the held lock, or None if there is none worth honouring.

    A lock file that is missing, unreadable, or held by a dead PID all give
    None; the stale file is deleted on the way, silently, as the plan requires.
    """
    path = lock_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        # A corrupt lock is indistinguishable from a crashed run, and treating
        # it as held would wedge the user out of their own machine.
        path.unlink(missing_ok=True)
        return None

    try:
        info = LockInfo(
            pid=int(raw["pid"]), command=str(raw["command"]), run_id=str(raw["run_id"])
        )
    except (KeyError, TypeError, ValueError):
        path.unlink(missing_ok=True)
        return None

    if not pid_is_live(info.pid):
        path.unlink(missing_ok=True)
        return None
    return info


def release_lock() -> None:
    """Remove the lock file if this process holds it."""
    path = lock_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if raw.get("pid") == os.getpid():
        path.unlink(missing_ok=True)


class _HeldLock:
    """Context manager returned by :func:`acquire_lock`."""

    def __init__(self, info: LockInfo) -> None:
        self.info = info

    def __enter__(self) -> LockInfo:
        return self.info

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        release_lock()


def acquire_lock(command: str, run_id: str | None = None) -> _HeldLock:
    """Take the global lock, or raise if another live run holds it.

    Args:
        command: The command name as the user typed it, e.g. ``optica run``. It
            is reported back to whoever is blocked, so it must be their
            vocabulary rather than an internal key.
        run_id: The run this lock belongs to. Generated if omitted.

    Returns:
        A context manager that releases the lock on exit.

    Raises:
        OpticaError: When another live process holds the lock.
    """
    held = read_lock()
    if held is not None:
        raise OpticaError(
            "Optica is already running in another terminal.",
            why=f"Command: {held.command} (PID {held.pid})",
            fix="Wait for it to complete, or terminate it before running a new command.",
        )

    info = LockInfo(
        pid=os.getpid(), command=command, run_id=run_id or uuid.uuid4().hex[:12]
    )
    lock_path().write_text(
        json.dumps(
            {"pid": info.pid, "command": info.command, "run_id": info.run_id}, indent=2
        ),
        encoding="utf-8",
    )
    return _HeldLock(info)
