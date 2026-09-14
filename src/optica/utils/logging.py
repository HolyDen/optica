"""Rich user-facing output, verbosity, and the standard error rendering.

Implements plan § "Coding Style" → *Logging* and *Error handling*.

Two rules from the plan shape this module:

- ``--verbose``/``--quiet`` **govern progress and status output only**. Warnings,
  safety prompts and errors display at every level (Implementation Note 19), so
  :func:`warn` and :func:`render_error` never consult the verbosity level.
- Output reports actual detected values, never internal registry keys. That is a
  rule for callers; this module only gives them somewhere to write.

Prompts deliberately live in :mod:`optica.utils.prompts` rather than here: the
verbosity switch must never reach them.
"""

from __future__ import annotations

import logging
import sys
from enum import IntEnum
from typing import TYPE_CHECKING, Final, TextIO

from rich.console import Console

if TYPE_CHECKING:
    from optica.exceptions import OpticaError

__all__ = [
    "Markers",
    "Verbosity",
    "detail",
    "err_console",
    "get_verbosity",
    "incomplete",
    "markers_for",
    "out_console",
    "protect_streams",
    "render_error",
    "set_verbosity",
    "status",
    "success",
    "warn",
]


class Verbosity(IntEnum):
    """How much progress and status output to emit.

    Ordered, so a caller can write ``if get_verbosity() >= Verbosity.VERBOSE``.
    """

    QUIET = 0
    NORMAL = 1
    VERBOSE = 2


_verbosity: Verbosity = Verbosity.NORMAL

# `soft_wrap=True` on both: Rich otherwise word-wraps at an assumed 80 columns
# whenever the stream is not a terminal — a pipe, a redirect, a CI log — and
# folds any token longer than the remaining width, inserting a newline *inside*
# it. Paths and commands are the tokens that get long, and those are exactly the
# ones plan § "Error handling and prompt conventions" requires to stay
# copy-paste-ready. Soft wrapping emits the line whole and lets the terminal
# wrap it for display, so nothing is broken mid-token.
out_console: Final = Console(soft_wrap=True)
"""Progress and status output. Silenced by ``--quiet``."""

err_console: Final = Console(stderr=True, soft_wrap=True)
"""Warnings, prompts and errors. Never silenced."""


def set_verbosity(level: Verbosity) -> None:
    """Set the global output level.

    Called once by the CLI's global callback, which accepts ``--verbose`` and
    ``--quiet`` in either position.
    """
    global _verbosity
    _verbosity = level


def get_verbosity() -> Verbosity:
    """Return the current global output level."""
    return _verbosity


class Markers:
    """The four status glyphs, resolved against one stream's encoding.

    The plan's output format uses ``✕`` (error), ``✗`` (incomplete),
    ``✓`` (success) and ``⚠`` (warning). On a Windows console with a
    non-UTF-8 codepage, writing any of them to ``stdout`` raises
    ``UnicodeEncodeError`` — through Rich as well as through ``print``, since
    Rich writes to the same stream — which would put a raw traceback in front of
    a user who did nothing unusual. Each glyph is therefore tested once against
    the target encoding and replaced with an ASCII stand-in only where it cannot
    be encoded.

    Attributes:
        error: Marks a hard error.
        fail: Marks an incomplete or failed step.
        ok: Marks a completed step.
        warn: Marks a warning.
    """

    _FALLBACKS: Final[dict[str, str]] = {
        "✕": "X",
        "✗": "x",
        "✓": "+",
        "⚠": "!",
    }

    def __init__(self, encoding: str | None) -> None:
        self.error = self._resolve("✕", encoding)
        self.fail = self._resolve("✗", encoding)
        self.ok = self._resolve("✓", encoding)
        self.warn = self._resolve("⚠", encoding)

    @classmethod
    def _resolve(cls, glyph: str, encoding: str | None) -> str:
        if not encoding:
            return cls._FALLBACKS[glyph]
        try:
            glyph.encode(encoding)
        except (UnicodeEncodeError, LookupError):
            return cls._FALLBACKS[glyph]
        return glyph


def markers_for(console: Console) -> Markers:
    """Return the marker set usable on ``console``'s stream."""
    stream: TextIO | None = getattr(console, "file", None)
    return Markers(getattr(stream, "encoding", None))


def status(message: str) -> None:
    """Print a progress or status line. Suppressed by ``--quiet``."""
    if _verbosity >= Verbosity.NORMAL:
        out_console.print(message)


def detail(message: str) -> None:
    """Print an extra-detail line. Shown only under ``--verbose``."""
    if _verbosity >= Verbosity.VERBOSE:
        out_console.print(message)


def success(message: str) -> None:
    """Print a completion line. Suppressed by ``--quiet``."""
    if _verbosity >= Verbosity.NORMAL:
        marks = markers_for(out_console)
        out_console.print(f"[bold green]{marks.ok}[/bold green] {message}")


def incomplete(message: str) -> None:
    """Print an ``✗ X incomplete — reason`` completion line to stderr.

    Unlike :func:`success`, never silenced: an incomplete step exits ``3``, and
    the line is the only record an unattended run has of why.
    """
    marks = markers_for(err_console)
    err_console.print(f"[bold red]{marks.fail}[/bold red] {message}")


def warn(message: str, *, why: str | None = None, fix: str | None = None) -> None:
    """Print a warning to stderr.

    Displays at **every** verbosity level: ``--quiet`` silences progress and
    status output only, and ``--force`` suppresses safety *prompts* rather than
    warnings.
    """
    marks = markers_for(err_console)
    err_console.print(f"[bold yellow]{marks.warn}[/bold yellow] {message}")
    for line in (why, fix):
        if line:
            err_console.print(f"  {line}")


def render_error(exc: OpticaError) -> None:
    """Print an :class:`~optica.exceptions.OpticaError` in the standard shape.

    The three-line structure plan § "Coding Style" requires — what went wrong,
    why in one sentence, how to fix with a specific command — plus the valid
    options and default that fixed-value-flag errors must additionally list.

    Always goes to stderr, and never consults the verbosity level.
    """
    marks = markers_for(err_console)
    err_console.print(f"[bold red]{marks.error}[/bold red] {exc.message}")
    if exc.why:
        err_console.print(f"  {exc.why}")
    for line in exc.fix:
        err_console.print(f"  {line}")
    if exc.options:
        err_console.print(f"  Valid options: {', '.join(exc.options)}")
    if exc.default is not None:
        err_console.print(f"  Default: {exc.default}")


_NON_RAISING: Final = frozenset(
    {"backslashreplace", "replace", "ignore", "xmlcharrefreplace", "namereplace"}
)


def protect_streams(*streams: object) -> None:
    """Make text a stream cannot encode degrade to an escape instead of raising.

    The **second** of two mechanisms for characters a stream cannot encode, and
    they solve different problems. :class:`Markers` handles the four status
    glyphs, which each have a good ASCII stand-in (``✓`` becomes ``+``); it runs
    first, so a glyph never reaches the stream unencodable. This handles
    everything else Optica prints — class names, paths, Open Images display
    names — which is the user's text and has no stand-in: there is nothing to
    transliterate a class name in a non-Latin script to. For that text an escape
    (a backslash-u code per character) is the only honest rendering, and it beats
    a failed command.

    Only the error handler changes; the encoding is kept. A stream already on a
    non-raising handler, or one that cannot be reconfigured (a caller's own
    object), is left alone.

    Called by the CLI entry point only. The Python API never reconfigures a
    caller's streams: a library that changed its host process's stdout on import
    or on call would be reaching into state it does not own.

    Args:
        streams: The streams to protect. Defaults to ``sys.stdout`` and
            ``sys.stderr``.
    """
    for stream in streams or (sys.stdout, sys.stderr):
        if getattr(stream, "errors", None) in _NON_RAISING:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(errors="backslashreplace")
        except (ValueError, OSError):  # a closed or detached stream
            continue


def get_logger(name: str) -> logging.Logger:
    """Return the standard-library logger for internal debug output.

    Rich handles everything user-facing; :mod:`logging` is per-module and
    internal, as plan § "Coding Style" splits them.
    """
    return logging.getLogger(name)


def configure_stdlib_logging(level: Verbosity) -> None:
    """Point the internal :mod:`logging` tree at stderr at a matching level.

    Internal debug output is not user-facing output, so it is wired separately
    from the Rich consoles and stays on stderr regardless.
    """
    mapping = {
        Verbosity.QUIET: logging.ERROR,
        Verbosity.NORMAL: logging.WARNING,
        Verbosity.VERBOSE: logging.DEBUG,
    }
    logging.basicConfig(
        level=mapping[level],
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
        force=True,
    )
