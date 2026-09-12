"""Progress bars.

Covers the `utils/progress.py` slot in plan § "Code Structure" and the verbosity
rule in § "Coding Style": a progress bar is progress output, so ``--quiet``
silences it.
"""

from __future__ import annotations

from optica.utils import logging as olog
from optica.utils.progress import progress_bar, spinner


class TestQuiet:
    def test_progress_bar_is_disabled_under_quiet(self):
        olog.set_verbosity(olog.Verbosity.QUIET)
        with progress_bar("Fetching", total=10) as bar:
            assert bar.disable is True

    def test_progress_bar_is_enabled_at_normal(self):
        with progress_bar("Fetching", total=10) as bar:
            assert bar.disable is False

    def test_spinner_is_disabled_under_quiet(self):
        olog.set_verbosity(olog.Verbosity.QUIET)
        with spinner("Resolving") as spin:
            assert spin.disable is True


class TestUsableEitherWay:
    """A call site never needs an ``if quiet`` branch."""

    def test_a_task_exists_even_when_disabled(self):
        olog.set_verbosity(olog.Verbosity.QUIET)
        with progress_bar("Fetching", total=3) as bar:
            assert len(bar.tasks) == 1
            bar.advance(bar.tasks[0].id)

    def test_advance_reaches_completion(self):
        with progress_bar("Fetching", total=3) as bar:
            task = bar.tasks[0].id
            for _ in range(3):
                bar.advance(task)
            assert bar.tasks[0].completed == 3

    def test_spinner_has_no_total(self):
        with spinner("Resolving") as spin:
            assert spin.tasks[0].total is None
