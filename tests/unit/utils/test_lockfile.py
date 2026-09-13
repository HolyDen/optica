"""The global lock file.

Covers Implementation Note 2 — hard-block on a live PID, silent cleanup on a
dead one — and plan § "Known Constraints" → *Global lock file*.
"""

from __future__ import annotations

import json
import os

import pytest

from optica.exceptions import OpticaError
from optica.utils import lockfile


@pytest.fixture(autouse=True)
def _home(fake_home):
    """Every test in this file writes to a throwaway ``~/.optica/``."""
    return fake_home


class TestPidLiveness:
    """Liveness must never signal the process it is asking about."""

    def test_this_process_is_live(self):
        assert lockfile.pid_is_live(os.getpid()) is True

    def test_an_impossible_pid_is_not_live(self):
        assert lockfile.pid_is_live(-1) is False
        assert lockfile.pid_is_live(0) is False


class TestOutOfRangePid:
    """A PID wider than the platform's own type answers False, never raises.

    The lock file is plain JSON that a user can hand-edit and a crash can
    truncate, so these values are reachable input. Unguarded, POSIX
    ``os.kill`` raises ``OverflowError`` above 2**31-1 and the ctypes call
    raises ``ArgumentError`` above 2**32-1 — both before any error check runs,
    and both escaping as a raw traceback.
    """

    @pytest.mark.parametrize(
        "pid",
        [
            2**31 - 1,  # the POSIX ceiling itself
            2**31,  # one past it: OverflowError, unguarded
            4_000_000_000,  # the value CI failed on
            2**32 - 1,  # the Windows ceiling itself
            2**32,  # one past it: ctypes ArgumentError, unguarded
            2**63,
            10**30,  # far wider than any C integer type
        ],
    )
    def test_answers_without_raising(self, pid):
        assert lockfile.pid_is_live(pid) is False

    def test_the_bound_is_the_platform_s_own(self):
        import sys

        expected = 2**32 - 1 if sys.platform == "win32" else 2**31 - 1
        assert expected == lockfile._MAX_PID

    def test_a_hand_edited_lock_file_is_treated_as_stale(self):
        # The end-to-end shape of the same bug: a nonsense PID in the file must
        # read as "no live lock", not as a traceback.
        lockfile.lock_path().write_text(
            json.dumps({"pid": 10**30, "command": "optica run", "run_id": "r"}),
            encoding="utf-8",
        )
        assert lockfile.read_lock() is None
        assert not lockfile.lock_path().exists()

    def test_a_lock_file_with_an_out_of_range_pid_does_not_block(self):
        lockfile.lock_path().write_text(
            json.dumps({"pid": 2**40, "command": "optica run", "run_id": "r"}),
            encoding="utf-8",
        )
        with lockfile.acquire_lock("optica fetch") as info:
            assert info.command == "optica fetch"


class TestAcquire:
    def test_writes_pid_command_and_run_id(self):
        with lockfile.acquire_lock("optica run") as info:
            stored = json.loads(lockfile.lock_path().read_text(encoding="utf-8"))
        assert stored["pid"] == os.getpid()
        assert stored["command"] == "optica run"
        assert stored["run_id"] == info.run_id

    def test_releases_on_exit(self):
        with lockfile.acquire_lock("optica fetch"):
            assert lockfile.lock_path().exists()
        assert not lockfile.lock_path().exists()

    def test_releases_even_when_the_command_fails(self):
        with pytest.raises(RuntimeError), lockfile.acquire_lock("optica train"):
            raise RuntimeError("boom")
        assert not lockfile.lock_path().exists()


class TestHardBlock:
    """The plan's message, line for line."""

    def test_a_live_lock_blocks(self, monkeypatch):
        lockfile.lock_path().write_text(
            json.dumps({"pid": 48291, "command": "optica run", "run_id": "abc123"}),
            encoding="utf-8",
        )
        monkeypatch.setattr(lockfile, "pid_is_live", lambda pid: True)
        with pytest.raises(OpticaError) as caught:
            lockfile.acquire_lock("optica train")
        exc = caught.value
        assert exc.message == "Optica is already running in another terminal."
        assert exc.why == "Command: optica run (PID 48291)"
        assert exc.fix == [
            "Wait for it to complete, or terminate it before running a new command."
        ]

    def test_the_blocking_command_is_reported_not_the_blocked_one(self, monkeypatch):
        lockfile.lock_path().write_text(
            json.dumps({"pid": 1, "command": "optica curate", "run_id": "r"}),
            encoding="utf-8",
        )
        monkeypatch.setattr(lockfile, "pid_is_live", lambda pid: True)
        with pytest.raises(OpticaError) as caught:
            lockfile.acquire_lock("optica export")
        assert "optica curate" in (caught.value.why or "")


class TestStaleCleanup:
    """A dead PID is silent cleanup, then proceed."""

    def test_dead_pid_is_removed_and_the_command_runs(self, monkeypatch, capsys):
        lockfile.lock_path().write_text(
            json.dumps({"pid": 999999, "command": "optica run", "run_id": "r"}),
            encoding="utf-8",
        )
        monkeypatch.setattr(lockfile, "pid_is_live", lambda pid: False)
        with lockfile.acquire_lock("optica fetch"):
            pass
        assert capsys.readouterr().out == ""

    def test_corrupt_lock_is_treated_as_stale(self):
        lockfile.lock_path().write_text("{not json", encoding="utf-8")
        assert lockfile.read_lock() is None
        assert not lockfile.lock_path().exists()

    def test_lock_missing_a_field_is_treated_as_stale(self):
        lockfile.lock_path().write_text(json.dumps({"pid": 1}), encoding="utf-8")
        assert lockfile.read_lock() is None

    def test_no_lock_at_all_is_not_an_error(self):
        assert lockfile.read_lock() is None


class TestExemptCommands:
    """``config --view``, ``config --set`` and ``--version`` never take it."""

    @pytest.mark.parametrize(
        "command", ["config --view", "config --set", "--version"]
    )
    def test_the_three_exempt_commands(self, command):
        assert command in lockfile.EXEMPT_COMMANDS

    @pytest.mark.parametrize(
        "command",
        ["run", "train", "fetch", "export", "curate", "label", "setup"],
    )
    def test_write_commands_are_not_exempt(self, command):
        assert command not in lockfile.EXEMPT_COMMANDS


class TestPlanValuesStillToImplement:
    """Wiring the lock into the commands themselves."""

    @pytest.mark.parametrize(
        "argv",
        [
            ["fetch", "-c", "cat,dog", "--yes"],
            ["config", "--clear-staging"],
        ],
    )
    def test_fetch_takes_the_lock(self, argv, monkeypatch, project_dir, capsys):
        """The blocked list.

        run, train, fetch, export, curate, label, setup, config --init and
        config --clear-staging. Pass 2 wires the two it builds: a live lock held
        by another run blocks both before they touch the network or staging.
        """
        from optica.cli.main import app
        from optica.exceptions import ExitCode

        lockfile.lock_path().write_text(
            json.dumps({"pid": 4242, "command": "optica run", "run_id": "r"}),
            encoding="utf-8",
        )
        monkeypatch.setattr(lockfile, "pid_is_live", lambda pid: True)
        assert app.invoke_guarded(argv) == ExitCode.ERROR
        assert "already running" in capsys.readouterr().err

    @pytest.mark.skip(reason="stub - pass 5")
    def test_setup_takes_the_lock(self):
        """`optica setup` is on the blocked list."""
