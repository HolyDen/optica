"""Typer application entry point, and the global exception handler.

Implements plan § "CLI Layer & Conventions" → *Error handling and prompt
conventions*, and Implementation Note 1. **The handler is the first thing built
in the implementation** — it is a hard sequencing prerequisite, because every
other flag decision's error behaviour executes through it.

The plan spells the mechanism ``app.exception_handler()``. That method does not
exist: ``typer.Typer`` exposes exactly ``add_typer``, ``callback`` and
``command``, and ``exception_handler`` is FastAPI's API, not Typer's. The
behaviour the plan specifies is implemented in full by :class:`OpticaTyper`
below, which overrides ``__call__`` so that Click propagates exceptions here
instead of printing them and exiting itself; see ``notes/build-log.md``
§ "The global exception handler's mechanism".

There is no ``click`` to import from, either: typer 0.27.2 vendors Click as the
private ``typer._click`` and declares no dependency on it. The vendored classes
are the only ones Typer ever raises, so they are what the handler catches — a
separately installed Click would supply a second, unrelated ``UsageError`` and
the catch would silently stop firing.

``main.py`` registers the task group and the flat aliases and holds nothing
classify-specific, which is what makes ``cli/classify.py`` the template for a
future ``cli/detect.py``.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from importlib import metadata
from typing import Any, Final, NoReturn

import typer
from typer._click.exceptions import (
    BadOptionUsage,
    MissingParameter,
    NoArgsIsHelpError,
    UsageError,
)

from optica.exceptions import ExitCode, OpticaError
from optica.utils import logging as olog
from optica.utils.prompts import is_interactive

__all__ = ["GlobalState", "OpticaTyper", "app", "get_state"]

_CLASSES_OPTS: Final = frozenset({"--classes", "-c"})
"""The one flag whose "given with no value" case redirects to a prompt rather
than to an error (plan § *Flag (no value) behavior*)."""


@dataclass
class GlobalState:
    """Flags that apply to the whole run, wherever on the line they appear.

    ``--verbose``, ``--quiet``, ``--yes``/``-y``, ``--force``/``-f`` and
    ``--dry-run`` are accepted in either position, so each is declared both on
    the root callback and on every command; :meth:`merge` folds the two
    sightings together. ``--force`` is registered globally from V1 — the same
    pattern as the display flags — so that safety prompts added to commands
    later need no flag re-registration.
    """

    verbose: bool = False
    quiet: bool = False
    yes: bool = False
    force: bool = False
    dry_run: bool = False
    argv: list[str] = field(default_factory=list)

    def merge(
        self,
        *,
        verbose: bool = False,
        quiet: bool = False,
        yes: bool = False,
        force: bool = False,
        dry_run: bool = False,
    ) -> GlobalState:
        """Fold a command's own sighting of the global flags into this state."""
        self.verbose = self.verbose or verbose
        self.quiet = self.quiet or quiet
        self.yes = self.yes or yes
        self.force = self.force or force
        self.dry_run = self.dry_run or dry_run
        self.apply()
        return self

    def apply(self) -> None:
        """Push the display flags into the output layer.

        ``--verbose`` wins over ``--quiet`` when both are given: it adds detail
        rather than unlocking messages ``--quiet`` withheld, so the louder of
        the two is never the surprising choice.
        """
        level = olog.Verbosity.NORMAL
        if self.verbose:
            level = olog.Verbosity.VERBOSE
        elif self.quiet:
            level = olog.Verbosity.QUIET
        olog.set_verbosity(level)
        olog.configure_stdlib_logging(level)


def get_state(ctx: typer.Context) -> GlobalState:
    """Return the run's :class:`GlobalState`, creating it if needed."""
    if not isinstance(ctx.obj, GlobalState):
        ctx.obj = GlobalState()
    return ctx.obj


def _version() -> str:
    """Return the installed distribution version.

    Read from installed metadata rather than from a literal, so ``pyproject.toml``
    stays the single source of truth for the version and the two cannot drift.
    """
    try:
        return metadata.version("optica")
    except metadata.PackageNotFoundError:  # running from a source tree, uninstalled
        return "unknown"


class OpticaTyper(typer.Typer):
    """A Typer app whose every invocation passes through the global handler.

    ``Typer.__call__`` forwards to the Click group, so passing
    ``standalone_mode=False`` makes Click return exit codes and re-raise
    exceptions instead of printing and exiting on its own. That is what gives
    this class somewhere to stand.

    The catch is ``UsageError`` **at the base**, deliberately not a named list:
    every parser error Typer raises subclasses it, and a list would go stale the
    moment a new subclass is added. ``Abort`` is not a ``UsageError`` and is
    handled separately, joining SIGINT at ``130``.
    """

    def __call__(self, *args: Any, **kwargs: Any) -> NoReturn:
        """Run the command line and exit with the code the handler chose."""
        argv = kwargs.pop("args", None)
        argv = list(argv) if argv is not None else list(sys.argv[1:])
        raise SystemExit(self.invoke_guarded(argv, **kwargs))

    def invoke_guarded(self, argv: list[str], _retry: bool = True, **kwargs: Any) -> int:
        """Run ``argv`` and return the exit code, raising nothing.

        Args:
            argv: The command line, without the program name.
            _retry: Whether a redirect-to-prompt may re-run the command. Set
                False on the second attempt so a prompt can never loop.
            **kwargs: Passed through to Click's ``main``.

        Returns:
            The process exit code.
        """
        try:
            result = super().__call__(args=argv, standalone_mode=False, **kwargs)
        except UsageError as exc:
            return self._handle_usage_error(exc, argv, _retry=_retry, **kwargs)
        except typer.Abort:
            # Reserved for an interrupt at a prompt. A *declined* prompt is
            # Optica's own business and exits 3; see utils/prompts.py.
            olog.err_console.print("Aborted.")
            return int(ExitCode.INTERRUPTED)
        except OpticaError as exc:
            olog.render_error(exc)
            if olog.get_verbosity() >= olog.Verbosity.VERBOSE and exc.__cause__:
                olog.err_console.print_exception()
            return int(ExitCode.ERROR)
        except Exception as exc:  # noqa: BLE001 - a raw traceback must never surface
            self._handle_unexpected(exc)
            return int(ExitCode.ERROR)
        # `standalone_mode=False` returns an int only where the command exited
        # explicitly: `--help`, `--version`, `typer.Exit(...)`, or a
        # KeyboardInterrupt, which Typer turns into exit code 130 itself.
        return int(result) if isinstance(result, int) else int(ExitCode.SUCCESS)

    def _handle_usage_error(
        self, exc: UsageError, argv: list[str], *, _retry: bool, **kwargs: Any
    ) -> int:
        """Render a parser error, or redirect it to a prompt where one applies.

        The fallback hierarchy the plan states: try prompt, then a clean wrapped
        error, and **never** a raw Typer traceback.
        """
        if isinstance(exc, NoArgsIsHelpError):
            # Not a mistake to report: its message *is* the help text, and the
            # framework's own exit code for it is 2. Print it plainly.
            olog.err_console.print(exc.format_message())
            return int(exc.exit_code)

        if _retry:
            filled = self._redirect_to_classes_prompt(exc, argv)
            if filled is not None:
                return self.invoke_guarded(filled, _retry=False, **kwargs)

        marks = olog.markers_for(olog.err_console)
        olog.err_console.print(
            f"[bold red]{marks.error}[/bold red] {exc.format_message()}"
        )
        if exc.ctx is not None:
            hint = exc.ctx.help_option_names[0] if exc.ctx.help_option_names else "--help"
            olog.err_console.print(f"  Run: {exc.ctx.command_path} {hint}")
        # UsageError.exit_code is Click's own 2; the plan matches it rather than
        # contending for it, so the code comes from the exception, not from us.
        return int(exc.exit_code)

    def _redirect_to_classes_prompt(
        self, exc: UsageError, argv: list[str]
    ) -> list[str] | None:
        """Return ``argv`` with ``--classes`` filled in from a prompt, or None.

        ``--classes``/``-c`` given with no value is the one flag the plan sends
        to a prompt instead of to an error. The parser reports that as
        ``BadOptionUsage``; a ``--classes`` that is *absent* while required
        reports as ``MissingParameter``. Both are handled, since both are the
        same situation from the user's side.

        Returns None — leaving the caller to render the error — whenever the
        prompt cannot or must not fire: a different flag, no terminal, or
        ``--yes``, which errors rather than hanging on a prompt it cannot
        answer.
        """
        if not self._is_classes_error(exc, argv):
            return None
        if "--yes" in argv or "-y" in argv or not is_interactive():
            return None

        marks = olog.markers_for(olog.err_console)
        olog.err_console.print(
            f"[bold yellow]{marks.warn}[/bold yellow] No class names given."
        )
        answer = typer.prompt(
            "  Which classes? Comma-separated, e.g. cat,dog",
            default="",
            show_default=False,
        ).strip()
        if not answer:
            return None

        filled = [arg for arg in argv if arg not in _CLASSES_OPTS]
        return [*filled, "--classes", answer]

    @staticmethod
    def _is_classes_error(exc: UsageError, argv: list[str]) -> bool:
        """Whether ``exc`` is ``--classes`` missing its value."""
        if isinstance(exc, BadOptionUsage):
            return exc.option_name in _CLASSES_OPTS
        if isinstance(exc, MissingParameter):
            param = exc.param
            opts = set(param.opts) if param is not None else set()
            return bool(opts & _CLASSES_OPTS)
        # A bare trailing `-c` with nothing after it can also surface as the
        # generic "unexpected extra argument" shape, so fall back to the line.
        return bool(argv) and argv[-1] in _CLASSES_OPTS

    @staticmethod
    def _handle_unexpected(exc: Exception) -> None:
        """Report a non-Optica exception without showing a traceback.

        Nothing should reach here. When something does, it is a bug in Optica
        rather than a mistake by the user, and the message says so — a raw
        traceback never reaches an end user, and ``--verbose`` is what adds one.
        """
        marks = olog.markers_for(olog.err_console)
        olog.err_console.print(
            f"[bold red]{marks.error}[/bold red] Optica hit an unexpected error: "
            f"{type(exc).__name__}: {exc}"
        )
        olog.err_console.print(
            "  This is a bug in Optica, not a problem with your input."
        )
        olog.err_console.print("  Re-run with --verbose to see the full traceback.")
        if olog.get_verbosity() >= olog.Verbosity.VERBOSE:
            olog.err_console.print_exception()


app = OpticaTyper(
    name="optica",
    help="A simple, powerful computer-vision toolkit.",
    no_args_is_help=True,
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        # Exempt from the global lock file, along with `config --view` and
        # `config --set` (Implementation Note 2).
        olog.out_console.print(f"optica {_version()}")
        raise typer.Exit(code=ExitCode.SUCCESS)


@app.callback()
def _root(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        help="Print the installed Optica version.",
        callback=_version_callback,
        is_eager=True,
    ),
    verbose: bool = typer.Option(
        False, "--verbose", help="Add detail to progress and status output."
    ),
    quiet: bool = typer.Option(
        False, "--quiet", help="Suppress progress and status output."
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Answer Y to every Y/N prompt in scope."
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Bypass safety prompts. Never destructive prompts."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print what would happen without executing."
    ),
) -> None:
    """Optica — image classification by transfer learning."""
    state = get_state(ctx)
    state.argv = list(sys.argv[1:])
    state.merge(
        verbose=verbose, quiet=quiet, yes=yes, force=force, dry_run=dry_run
    )
