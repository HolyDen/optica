"""User text that the output stream cannot encode, through the real entry point.

Covers plan § "Coding Style" → *Error handling* ("raw tracebacks never reach end
users") for text Optica does not control the characters of: class names, paths,
Open Images display names. A status glyph has an ASCII stand-in and keeps it
(``utils/logging.py:Markers``); a class name in a script with no ASCII
equivalent has none, so the stream itself must degrade to an escape rather than
raise.

**The non-encodable stream is constructed, never assumed.** Each test builds it
explicitly in a child process — ``PYTHONIOENCODING=ascii:strict`` for stdout,
which Python applies to pipes on every platform, and a strict ASCII
``TextIOWrapper`` swapped in for stderr, whose handler Python otherwise forces
to ``backslashreplace``. Nothing depends on the runner's code page, so the
outcome is identical on all three runners. See ``notes/build-log.md``
§ "Unencodable user text on stdout".
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from optica.exceptions import ExitCode

# "Black cat": no ASCII equivalent exists, so there is nothing to transliterate to.
# Two characters, deliberately: a single character is blocklisted by the plan
# ("single characters or lone numbers"), which stops fetch at the CLIP entry
# check before any class name is printed — a test using one would pass or fail
# without ever reaching the encoding path.
BLACK_CAT = "黑猫"
ESCAPED = BLACK_CAT.encode("ascii", "backslashreplace")  # b"\\u9ed1\\u732b"


@pytest.fixture
def child_env(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ)
    env.update({"HOME": str(home), "USERPROFILE": str(home)})
    env["PYTHONIOENCODING"] = "ascii:strict"
    return env


def _run(body: str, env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[bytes]:
    source = textwrap.dedent(body)
    # ASCII-only child source: how a non-ASCII command-line argument is encoded
    # differs between Windows and POSIX, and that must not be what varies here.
    assert source.isascii(), "child source must be ASCII"
    return subprocess.run(
        [sys.executable, "-c", source],
        env=env,
        cwd=cwd,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )


def test_the_escape_is_what_the_assertions_expect():
    assert ESCAPED == b"\\u9ed1\\u732b"


def test_the_child_stdout_really_is_strict_ascii(child_env, tmp_path):
    # The control: without it, a runner whose streams already escaped would make
    # the tests below pass vacuously.
    result = _run(
        "import sys; print(sys.stdout.encoding, sys.stdout.errors)", child_env, tmp_path
    )
    assert result.stdout.strip() == b"ascii strict"


def test_the_name_is_not_blocklisted():
    # The other control: the stdout test must reach the line that prints it.
    from optica.input.classes import class_name_problem, is_blocklisted

    assert class_name_problem(BLACK_CAT) is None
    assert not is_blocklisted(BLACK_CAT)


def test_a_class_name_with_no_ascii_equivalent_does_not_break_stdout(child_env, tmp_path):
    result = _run(
        f"""
        import sys
        from optica.cli.main import app
        sys.argv = ["optica", "fetch", "-c", {BLACK_CAT + ",dog"!a}, "--dry-run"]
        app()
        """,
        child_env,
        tmp_path,
    )
    assert result.returncode == ExitCode.SUCCESS, result.stderr
    assert b"Classes: " + ESCAPED + b", dog" in result.stdout
    assert b"unexpected error" not in result.stderr
    assert b"Traceback" not in result.stderr


def test_an_error_naming_that_class_does_not_break_stderr(child_env, tmp_path):
    # Python forces the interpreter's own stderr to `backslashreplace` whatever
    # PYTHONIOENCODING says, so stderr is only safe while nobody replaces it.
    # Replace it here, as an embedding application or a harness would.
    result = _run(
        f"""
        import io, sys
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="ascii", errors="strict", line_buffering=True
        )
        from optica.cli.main import app
        sys.argv = ["optica", "fetch", "-c", {BLACK_CAT!a}, "--yes"]
        app()
        """,
        child_env,
        tmp_path,
    )
    # One class is below the minimum: an OpticaError whose message names it.
    assert result.returncode == ExitCode.ERROR
    assert b"Got: " + ESCAPED in result.stderr
    assert b"Traceback" not in result.stderr
