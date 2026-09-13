"""Y/N prompts, and the flags that answer or suppress them.

Implements plan § "Global flags" (``--yes``, ``--force``) and § "Error handling
and prompt conventions", plus the settled point that a **declined prompt exits
3** while ``click.Abort`` exits ``130``.

``typer.confirm(..., abort=True)`` is never used anywhere in Optica: it raises
``Abort`` both for a declined prompt and for an interrupt, which would return
``130`` where the exit-code table requires ``3``. :func:`confirm_or_abort` is the
replacement, and it is the only place the decline-to-exit mapping is written.

Prompts live here rather than in :mod:`optica.utils.logging` because ``--quiet``
must never reach them: it silences progress and status output only, and a prompt
that fired with nothing on screen would block on stdin invisibly.
"""

from __future__ import annotations

import sys
from enum import StrEnum

import typer

from optica.exceptions import ExitCode, OpticaError, OpticaValidationError

__all__ = [
    "CLASS_PROMPT",
    "PromptCategory",
    "ask_class_names",
    "confirm",
    "confirm_or_abort",
    "is_interactive",
]

CLASS_PROMPT = "  Which classes? Comma-separated, e.g. cat,dog"
"""The class-name prompt. Its example shows the comma, so a list is written one
way whether typed as a flag or at a prompt."""


def ask_class_names() -> str:
    """Ask for class names and return the raw answer, trimmed.

    The caller has already decided a prompt can fire — a terminal, and no
    ``--yes`` — and splits the answer on commas exactly as it splits ``-c``.
    One function, so the global handler's redirect and a command body that finds
    ``--classes`` absent ask the same question.
    """
    answer: str = typer.prompt(CLASS_PROMPT, default="", show_default=False)
    return answer.strip()


class PromptCategory(StrEnum):
    """Which flag, if any, answers a prompt.

    The split is the plan's: ``--yes`` answers choice and safety prompts and
    never touches destructive ones, while ``--force`` *suppresses* safety
    prompts rather than answering them.
    """

    CHOICE = "choice"
    """An ordinary decision. ``--yes`` answers **Y** — not the default."""

    SAFETY = "safety"
    """Fires when an explicit instruction may produce an unintended outcome.
    ``--yes`` answers it with the continue option; ``--force`` suppresses it."""

    DESTRUCTIVE = "destructive"
    """Loses data. Neither ``--yes`` nor ``--force`` touches it — each such
    prompt carries its own dedicated flag (``--overwrite`` for ``dataset/``) or
    must be answered interactively."""


if sys.platform == "win32":

    def _is_console(stream: object) -> bool:
        """Whether ``stream`` is a real Windows console, not merely a character device.

        On Windows ``isatty()`` is True for the ``NUL`` device — ``</dev/null``,
        ``subprocess.DEVNULL`` — because it is a character device, so
        ``isatty()`` alone would treat "no stdin at all" as a terminal. A console
        is the one character device ``GetConsoleMode`` succeeds on.
        """
        import ctypes
        import msvcrt
        from ctypes import wintypes

        try:
            handle = msvcrt.get_osfhandle(stream.fileno())  # type: ignore[attr-defined]
        except (AttributeError, OSError, ValueError):
            return False
        kernel32 = ctypes.windll.kernel32
        kernel32.GetConsoleMode.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        )
        kernel32.GetConsoleMode.restype = wintypes.BOOL
        mode = wintypes.DWORD()
        return bool(kernel32.GetConsoleMode(handle, ctypes.byref(mode)))

else:

    def _is_console(stream: object) -> bool:
        """On POSIX ``isatty()`` already answers this: ``/dev/null`` is not a tty."""
        return True


def is_interactive() -> bool:
    """Whether a prompt can actually be answered.

    False when stdin is not a terminal — a pipeline, a container build, a
    redirect from ``/dev/null``, or a test — in which case a prompt would block
    invisibly, or read end-of-file and look like an interrupt, rather than being
    answered.
    """
    try:
        if not sys.stdin.isatty():
            return False
    except (AttributeError, ValueError):  # detached or closed stdin
        return False
    return _is_console(sys.stdin)


def confirm(
    question: str,
    *,
    default: bool = True,
    category: PromptCategory = PromptCategory.CHOICE,
    assume_yes: bool = False,
    force: bool = False,
    non_interactive_error: type[OpticaError] = OpticaValidationError,
    non_interactive_why: str | None = None,
    non_interactive_fix: str | list[str] | None = None,
) -> bool:
    """Ask a Y/N question and return the answer.

    Both answers continue the run. Where **N** ends it, use
    :func:`confirm_or_abort` instead, so the exit code stays ``3``.

    Args:
        question: The question, without the ``[Y/n]`` suffix.
        default: The answer taken on a bare Enter. Note that ``--yes`` answers
            **Y** regardless of this — it is "answers Y", not "accepts
            defaults".
        category: Which flag may answer or suppress this prompt.
        assume_yes: The ``--yes`` flag.
        force: The ``--force`` flag.
        non_interactive_error: Exception class raised when no prompt can fire
            and no flag answered it. Defaults to
            :class:`~optica.exceptions.OpticaValidationError`; a caller passes
            its own subsystem's class, since a hard error's class is the
            subsystem whose contract it violates.
        non_interactive_why: One-sentence explanation for that error.
        non_interactive_fix: Fix instruction, or several, for that error.

    Returns:
        The answer.

    Raises:
        OpticaError: Of ``non_interactive_error``'s class, when the prompt
            cannot fire and no flag answers it.
    """
    if category is PromptCategory.SAFETY and force:
        # --force suppresses safety prompts, taking the continue option. It does
        # not suppress warnings, and does not reach destructive prompts.
        return True

    if assume_yes and category is not PromptCategory.DESTRUCTIVE:
        return True

    if not is_interactive():
        raise non_interactive_error(
            question,
            why=non_interactive_why
            or "This needs an answer, and there is no terminal to ask on.",
            fix=non_interactive_fix or [],
        )

    return typer.confirm(question, default=default)


def confirm_or_abort(
    question: str,
    *,
    default: bool = True,
    category: PromptCategory = PromptCategory.CHOICE,
    assume_yes: bool = False,
    force: bool = False,
    non_interactive_error: type[OpticaError] = OpticaValidationError,
    non_interactive_why: str | None = None,
    non_interactive_fix: str | list[str] | None = None,
) -> None:
    """Ask a Y/N question where **N** ends the run, and exit ``3`` if declined.

    Takes the same arguments as :func:`confirm`.

    Raises:
        typer.Exit: With :attr:`~optica.exceptions.ExitCode.ABORTED` when the
            answer is N. Optica handles the decline itself rather than letting
            ``Abort`` do it, so that ``130`` stays reserved for an interrupt.
        OpticaError: When the prompt cannot fire and no flag answers it.
    """
    if not confirm(
        question,
        default=default,
        category=category,
        assume_yes=assume_yes,
        force=force,
        non_interactive_error=non_interactive_error,
        non_interactive_why=non_interactive_why,
        non_interactive_fix=non_interactive_fix,
    ):
        raise typer.Exit(code=ExitCode.ABORTED)
