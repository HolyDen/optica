"""Every exit code, observed from a real process.

Covers the exit-code table in plan § "Exceptions" and pass 1's milestone: each
of ``0``, ``1``, ``2``, ``3`` and ``130`` is reachable.

The unit tests call ``invoke_guarded`` and read its return value; these run the
installed console script — or the app through a fresh interpreter — and read the
process's actual status, which is what a CI job or a container build branches on.
"""

from __future__ import annotations

import json
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


_TORCH_STACK = ("torch", "torchvision", "timm", "sklearn", "open_clip")
"""Top-level import names of the torch stack and the CLIP extra."""

_HIDE_TORCH = f"""
import importlib.util
_HIDDEN = {_TORCH_STACK!r}

class _Hide:
    # Wraps a finder so the torch stack is not found, exactly as on a machine
    # where it was never installed: find_spec gives None, import raises
    # ModuleNotFoundError.
    def __init__(self, inner):
        self.inner = inner
    def find_spec(self, name, path=None, target=None):
        if name.partition(".")[0] in _HIDDEN:
            return None
        return self.inner.find_spec(name, path, target)
    def __getattr__(self, attr):
        return getattr(self.inner, attr)

sys.meta_path[:] = [_Hide(finder) for finder in sys.meta_path]
for _name in _HIDDEN:
    assert importlib.util.find_spec(_name) is None, f"failed to hide {{_name}}"
"""


def _shadow_torch(fake_root: Path) -> str:
    """Return a patch that puts a recording fake of the torch stack first.

    Each fake package prints the stack that imported it, so a failure names the
    importer.
    """
    for name in _TORCH_STACK:
        package = fake_root / name
        package.mkdir(parents=True)
        (package / "__init__.py").write_text(
            "import sys, traceback\n"
            f"sys.stderr.write('FAKE {name} IMPORTED BY:\\n')\n"
            "traceback.print_stack()\n",
            encoding="utf-8",
        )
    return f"""
import importlib.util
sys.path.insert(0, {str(fake_root)!r})
for _name in {_TORCH_STACK!r}:
    _spec = importlib.util.find_spec(_name)
    assert _spec is not None and _spec.origin.startswith({str(fake_root)!r}), (
        f"failed to shadow {{_name}}: {{_spec}}"
    )
"""


def _drive_and_report_modules(argv: list[str], *, patch: str, report: Path) -> str:
    """Like :func:`_drive`, and write the torch-stack modules loaded at exit."""
    return f"""
{patch}
import json
from optica.cli.main import app
sys.argv = ["optica"] + {argv!r}
try:
    app()
finally:
    Path({str(report)!r}).write_text(json.dumps(sorted(
        m for m in sys.modules if m.partition(".")[0] in {_TORCH_STACK!r}
    )), encoding="utf-8")
"""


class TestMilestone:
    """`pip install -e .` then `optica --version`, with no torch installed.

    Neither test reads whether this machine has torch. Each constructs the
    torch condition it needs inside the subprocess and asserts the construction
    took before driving the app, so the result is the same on a machine with the
    torch stack installed (the pass 4 venv) and one without it (CI).
    """

    def test_version_runs_with_the_torch_stack_absent(self, workspace):
        result = _run_script(_drive(["--version"], patch=_HIDE_TORCH), workspace)
        assert result.returncode == ExitCode.SUCCESS, result.stderr
        assert "optica" in result.stdout

    def test_version_never_imports_the_torch_stack(self, workspace, tmp_path):
        # The torch stack is made present — a fake that shadows any real one —
        # so an import guarded by `except ImportError` is caught too: it would
        # succeed here and load the fake.
        report = tmp_path / "loaded.json"
        script = _drive_and_report_modules(
            ["--version"], patch=_shadow_torch(tmp_path / "fake"), report=report
        )
        result = _run_script(script, workspace)
        assert result.returncode == ExitCode.SUCCESS, result.stderr
        assert json.loads(report.read_text(encoding="utf-8")) == [], result.stderr

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
