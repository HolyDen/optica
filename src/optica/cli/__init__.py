"""The command-line interface, and the state its commands share.

A thin entry point: it maps commands to components and holds no business logic
(plan § "CLI Layer & Conventions").

``GlobalState`` and the value-separator helper live here rather than in
``main.py`` so that ``main.py`` can import ``classify.py`` to register it while
``classify.py`` reads the shared state — importing them from ``main`` would make
that a cycle. ``main.py`` re-exports both, so a caller need not know.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import typer

from optica.utils import logging as olog

if TYPE_CHECKING:
    from optica.config.manager import ConfigManager, ResolvedConfig

__all__ = ["GlobalState", "get_state", "split_values"]


def split_values(raw: list[str] | None) -> list[str]:
    """Expand a repeated, comma-separated flag into its values.

    Plan § *Value separator — comma, everywhere*: every multi-value flag accepts
    comma-separated values, a repeated flag is equally valid, and the two
    compose — ``-c cat -c dog,bird`` yields three classes. Values are trimmed of
    surrounding whitespace.

    Click does none of this itself: it hands back ``["cat", "dog,bird"]``
    unchanged (see ``notes/verified.md`` § "Click's restriction of variable-length
    ``nargs``"), so the splitting, the trimming and the composition are all
    Optica's own work and this is where they happen.

    Empty segments are dropped, so a trailing comma is not a value.

    Args:
        raw: The values Click parsed, or None when the flag was not given.

    Returns:
        The individual values, in the order they were written.
    """
    values: list[str] = []
    for item in raw or []:
        values.extend(part.strip() for part in item.split(",") if part.strip())
    return values


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
    _resolved: ResolvedConfig | None = None

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

    def config(
        self,
        manager: ConfigManager | None = None,
        overrides: dict[str, object] | None = None,
        flag_names: dict[str, str] | None = None,
    ) -> ResolvedConfig:
        """Resolve the configuration for this run, once.

        Called at the top of each command body, which is before that command
        does anything — the enforcement point plan § "Error handling and prompt
        conventions" asks for, so a bad value in ``.optica.toml`` errors rather
        than misbehaving silently.
        """
        if self._resolved is None or overrides:
            from optica.config.manager import ConfigManager as _ConfigManager

            self._resolved = (manager or _ConfigManager()).resolve(
                overrides=overrides, flag_names=flag_names
            )
        return self._resolved


def get_state(ctx: typer.Context) -> GlobalState:
    """Return the run's :class:`GlobalState`, creating it if needed."""
    root = ctx.find_root()
    if not isinstance(root.obj, GlobalState):
        root.obj = GlobalState(argv=list(sys.argv[1:]))
    state: GlobalState = root.obj
    return state
