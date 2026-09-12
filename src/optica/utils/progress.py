"""Rich progress bars.

Implements the `utils/progress.py` slot in plan § "Code Structure".

A progress bar is progress output, so ``--quiet`` silences it and ``--verbose``
does not change it — the verbosity rule in plan § "Coding Style" applies here
exactly as it does to status lines. Under ``--quiet`` the caller still gets a
context manager and a task handle, so no call site needs an ``if quiet`` branch.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)

from optica.utils.logging import Verbosity, get_verbosity, out_console

__all__ = ["progress_bar", "spinner"]


@contextmanager
def progress_bar(description: str, total: int) -> Iterator[Progress]:
    """Show a counted progress bar for a step of known length.

    Args:
        description: What the step is doing, in the user's vocabulary.
        total: The number of units of work.

    Yields:
        A started :class:`rich.progress.Progress` carrying one task. Disabled —
        but still usable — under ``--quiet``.
    """
    quiet = get_verbosity() <= Verbosity.QUIET
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeRemainingColumn(),
        console=out_console,
        disable=quiet,
        transient=False,
    )
    with progress:
        progress.add_task(description, total=total)
        yield progress


@contextmanager
def spinner(description: str) -> Iterator[Progress]:
    """Show an indeterminate spinner for a step of unknown length.

    Args:
        description: What the step is doing.

    Yields:
        A started :class:`rich.progress.Progress` carrying one task.
    """
    quiet = get_verbosity() <= Verbosity.QUIET
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=out_console,
        disable=quiet,
        transient=True,
    )
    with progress:
        progress.add_task(description, total=None)
        yield progress
