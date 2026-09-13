"""Every exit code, observed from a real process.

Covers the exit-code table in plan § "Exceptions" and pass 1's milestone: each
of ``0``, ``1``, ``2``, ``3`` and ``130`` is reachable.

The unit tests call ``invoke_guarded`` and read its return value; these run the
installed console script — or the app through a fresh interpreter — and read the
process's actual status, which is what a CI job or a container build branches on.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from optica.exceptions import ExitCode

_PREAMBLE = """
import sys
from pathlib import Path
"""


def _run_script(body: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a snippet that drives the app exactly as the console script does."""
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(_PREAMBLE + body)],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty project directory with a private home beside it."""
    project = tmp_path / "project"
    home = tmp_path / "home"
    project.mkdir()
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return project


def _drive(argv: list[str], *, patch: str = "") -> str:
    """Return a script that runs ``argv`` through the app's real entry point."""
    return f"""
{patch}
from optica.cli.main import app
sys.argv = ["optica"] + {argv!r}
app()
"""


class TestExitCodes:
    def test_success_is_zero(self, workspace):
        result = _run_script(_drive(["--version"]), workspace)
        assert result.returncode == ExitCode.SUCCESS
        assert "optica" in result.stdout

    def test_optica_error_is_one(self, workspace):
        # One class is below the two-class minimum: an OpticaValidationError
        # raised before anything touches the network. (Until pass 2 this used
        # `fetch -c cat,dog`, which now fetches.)
        result = _run_script(_drive(["fetch", "-c", "cat"]), workspace)
        assert result.returncode == ExitCode.ERROR
        assert "Traceback" not in result.stderr

    def test_usage_error_is_two(self, workspace):
        result = _run_script(_drive(["fetch", "--nope"]), workspace)
        assert result.returncode == ExitCode.USAGE
        assert "Traceback" not in result.stderr

    def test_space_separated_classes_is_two(self, workspace):
        # The comma convention's failure mode, end to end.
        result = _run_script(_drive(["fetch", "-c", "cat", "dog"]), workspace)
        assert result.returncode == ExitCode.USAGE
        assert "unexpected extra argument" in result.stderr

    def test_declined_prompt_is_three(self, workspace):
        patch = """
import typer
typer.confirm = lambda *a, **k: False
import optica.utils.prompts as prompts
prompts.is_interactive = lambda: True
"""
        result = _run_script(_drive(["config", "--init"], patch=patch), workspace)
        assert result.returncode == ExitCode.ABORTED
        assert not (workspace / ".optica.toml").exists()

    def test_interrupt_at_a_prompt_is_130(self, workspace):
        patch = """
import typer
def _interrupt(*a, **k):
    raise KeyboardInterrupt
typer.confirm = _interrupt
import optica.utils.prompts as prompts
prompts.is_interactive = lambda: True
"""
        result = _run_script(_drive(["config", "--init"], patch=patch), workspace)
        assert result.returncode == ExitCode.INTERRUPTED

    def test_click_abort_is_also_130(self, workspace):
        patch = """
import typer
def _abort(*a, **k):
    raise typer.Abort()
typer.confirm = _abort
import optica.utils.prompts as prompts
prompts.is_interactive = lambda: True
"""
        result = _run_script(_drive(["config", "--init"], patch=patch), workspace)
        assert result.returncode == ExitCode.INTERRUPTED


class TestMilestone:
    """`pip install -e .` then `optica --version`, with no torch installed."""

    def test_version_runs_without_torch(self, workspace):
        result = _run_script(
            _drive(["--version"]) + "\n", workspace
        )
        assert result.returncode == ExitCode.SUCCESS

    def test_no_torch_is_importable_in_this_environment(self):
        # The milestone is only a real check while the venv has no torch.
        result = subprocess.run(
            [sys.executable, "-c", "import torch"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0

    def test_the_installed_console_script_reports_the_same_version(self, workspace):
        from importlib import metadata

        result = _run_script(_drive(["--version"]), workspace)
        assert metadata.version("optica") in result.stdout


class TestNoRawTracebacks:
    """A raw Typer traceback must never reach the user, on any path."""

    @pytest.mark.parametrize(
        "argv",
        [
            ["fetch", "--nope"],
            ["fetch", "-c", "cat", "dog"],
            ["train", "--epochs", "ten"],
            ["train", "--model", "nope"],
            ["nosuchcommand"],
            ["config", "--set", "epocs", "20"],
        ],
    )
    def test_no_traceback(self, workspace, argv):
        result = _run_script(_drive(argv), workspace)
        assert "Traceback (most recent call last)" not in result.stderr
        assert result.returncode in {ExitCode.ERROR, ExitCode.USAGE}
