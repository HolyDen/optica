"""The ``optica config`` command.

Implements plan § "Configuration" — ``--init``, ``--set``, ``--view`` and
``--global``.

``--clear-staging`` is **not** registered yet: the plan puts its deletion logic
in the Input Manager, which pass 2 builds, and ``cli/config.py`` delegates to it
rather than reimplementing it. The flag arrives with the Input Manager.

Prompt dispositions here are the plan's, and they differ within the one command
— which is why ``--yes`` is registered per prompt rather than per command
(Implementation Note 11). The **create** confirmation is non-destructive and
``--yes`` answers it; the **overwrite** confirmation is destructive and ``--yes``
never touches it.
"""

from __future__ import annotations

import typer

from optica.cli import get_state
from optica.config.defaults import API_KEYS
from optica.config.manager import ConfigManager
from optica.exceptions import OpticaConfigError, OpticaValidationError
from optica.utils import logging as olog
from optica.utils.lockfile import acquire_lock
from optica.utils.prompts import PromptCategory, confirm_or_abort

__all__ = ["config"]


def config(
    ctx: typer.Context,
    key: str | None = typer.Option(
        None, "--set", help="Set a config key: optica config --set epochs 20"
    ),
    value: str | None = typer.Argument(None, help="The value, when using --set."),
    init: bool = typer.Option(
        False, "--init", help="Create a project-local .optica.toml."
    ),
    view: bool = typer.Option(
        False, "--view", help="Show the resolved config with source annotations."
    ),
    use_global: bool = typer.Option(
        False, "--global", help="Force --set to write the global config."
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Add detail to output."),
    quiet: bool = typer.Option(False, "--quiet", help="Suppress status output."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Answer Y to Y/N prompts."),
    force: bool = typer.Option(False, "--force", "-f", help="Bypass safety prompts."),
) -> None:
    """Manage Optica's settings."""
    state = get_state(ctx).merge(verbose=verbose, quiet=quiet, yes=yes, force=force)
    manager = ConfigManager()

    requested = (("--set", key), ("--init", init), ("--view", view))
    chosen = [name for name, given in requested if given]
    if len(chosen) > 1:
        raise OpticaValidationError(
            f"{' and '.join(chosen)} cannot be combined.",
            why="Each does a different thing to a different file.",
            fix="Run one at a time.",
        )
    if not chosen:
        raise OpticaValidationError(
            "optica config needs one of --set, --init or --view.",
            why="On its own it has nothing to do.",
            fix=[
                "Run: optica config --view          to see the resolved settings",
                "Run: optica config --set epochs 20 to change one",
                "Run: optica config --init          to create a project-local file",
            ],
        )

    if view:
        _view(manager)
        return
    if key is not None:
        _set(manager, key, value, use_global=use_global)
        return
    # `--init` writes a file, so unlike --view and --set it takes the lock.
    with acquire_lock("optica config --init"):
        _init(manager, assume_yes=state.yes)


def _view(manager: ConfigManager) -> None:
    """Print the resolved config with source annotations.

    An API key renders masked but keeps its normal annotation: *"is Optica using
    the key from my environment or the stale one in my global config?"* is the
    question people actually hit, and it is answerable without disclosing a
    character.
    """
    rows = manager.view()
    width = max(len(row.key) for row in rows)
    for row in rows:
        if not row.is_set:
            annotation = "(not set)"
        elif row.at_default:
            annotation = f"{row.source.value} (unset)"
        else:
            annotation = row.source.value
        olog.out_console.print(
            f"{row.key:<{width}} = {row.value}"
            f"  [dim]# {annotation}[/dim]"
        )


def _set(
    manager: ConfigManager, key: str, value: str | None, *, use_global: bool
) -> None:
    """Write one key, reporting the file written to."""
    if value is None:
        raise OpticaConfigError(
            f"--set {key} needs a value.",
            why="A key on its own does not say what to set it to.",
            fix=f"Run: optica config --set {key} <value>",
        )
    target, parsed = manager.set_key(key, value, use_global=use_global)
    shown = "••••••••" if key in API_KEYS else parsed
    # The path is always reported: a file the user did not know appeared is the
    # outcome this reporting exists to prevent.
    olog.success(f"{key} = {shown}  ->  {target}")


def _init(manager: ConfigManager, *, assume_yes: bool) -> None:
    """Create ``.optica.toml``, prompting first.

    A first-run command must not write to the filesystem silently.
    """
    if manager.project_path.exists():
        olog.out_console.print(f"{manager.project_path.name} already exists.")
        olog.out_console.print(
            "Use optica config --set to modify individual settings, "
            "or overwrite the file entirely."
        )
        # Destructive: `--yes` never answers this one, on the same command where
        # it answers the create prompt above.
        confirm_or_abort(
            "Overwrite?",
            default=False,
            category=PromptCategory.DESTRUCTIVE,
            non_interactive_error=OpticaConfigError,
            non_interactive_why="Overwriting a config file needs an explicit answer.",
            non_interactive_fix="Delete the file first, or run this in a terminal.",
        )
    else:
        confirm_or_abort(
            f"Create {manager.project_path.name} in the current directory?",
            default=True,
            category=PromptCategory.CHOICE,
            assume_yes=assume_yes,
            non_interactive_error=OpticaConfigError,
            non_interactive_why="Creating a file needs an answer.",
            non_interactive_fix="Re-run with --yes, or run this in a terminal.",
        )

    path = manager.init_project()
    olog.success(f"Created {path}")


def register(app: typer.Typer) -> None:
    """Attach ``optica config`` to ``app``.

    A function rather than a decorator at import time, so that ``main.py``
    decides the command's name and this module stays importable on its own.
    """
    app.command(name="config")(config)
