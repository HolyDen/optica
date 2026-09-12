"""The ``classify`` command group.

Implements plan § "CLI Layer & Conventions" → *Commands* and the *CLI Flag
Reference (V1)*.

**Fully self-contained** — all classify-specific logic lives here, so this module
is the clean template for a future ``cli/detect.py``. ``main.py`` registers the
group and the flat aliases and knows nothing about what is in it.

Pass 1 builds the command surface: every flag the reference assigns to each
command, the global flags in either position, the comma value separator, config
resolution before the command acts, and the global lock. The stage bodies
themselves arrive with their own passes — fetch and the input layer in pass 2,
the browser in pass 3, training and export in pass 4.
"""

from __future__ import annotations

from pathlib import Path

import typer

from optica.cli import GlobalState, get_state, split_values
from optica.config.defaults import MODELS, MODES, SOURCES
from optica.exceptions import OpticaError, OpticaValidationError
from optica.utils.lockfile import acquire_lock

__all__ = ["classify_app"]

classify_app = typer.Typer(
    name="classify",
    help="Image classification: fetch, label, curate, train, export.",
    no_args_is_help=True,
)

# --- Shared option definitions -------------------------------------------
#
# Declared once so that the flag reference has exactly one implementation per
# row, and so that a later pass changing a help string changes it everywhere.

_Verbose = typer.Option(False, "--verbose", help="Add detail to progress output.")
_Quiet = typer.Option(False, "--quiet", help="Suppress progress and status output.")
_Yes = typer.Option(False, "--yes", "-y", help="Answer Y to every Y/N prompt in scope.")
_Force = typer.Option(False, "--force", "-f", help="Bypass safety prompts only.")
_DryRun = typer.Option(
    False, "--dry-run", help="Print what would happen without executing."
)
_Overwrite = typer.Option(
    False,
    "--overwrite",
    help="Authorize the dataset/ overwrite prompt unattended.",
)
_Classes = typer.Option(
    None,
    "--classes",
    "-c",
    help='Class names, comma-separated. Quote per value: --classes "orange cat",dog',
)
_Dataset = typer.Option(
    Path("./dataset"), "--dataset", "-d", help="Organized dataset folder."
)
_Output = typer.Option(
    Path("./optica-output"), "--output", "-o", help="Container folder for run outputs."
)


def _globals(
    state: GlobalState,
    *,
    verbose: bool,
    quiet: bool,
    yes: bool,
    force: bool,
    dry_run: bool = False,
) -> GlobalState:
    """Fold a command's copy of the global flags into the run's state."""
    return state.merge(
        verbose=verbose, quiet=quiet, yes=yes, force=force, dry_run=dry_run
    )


def _not_yet(stage: str) -> OpticaError:
    """Return the error a not-yet-built stage raises.

    Pass 1 ships the command surface; each stage's body lands in its own pass.
    The message is a plain statement rather than an apology, and it exits ``1``
    like any other :class:`~optica.exceptions.OpticaError`. ``options`` is not
    used: that field lists a fixed-value flag's valid values, and borrowing it
    for a build note would put the wrong thing under "Valid options".
    """
    return OpticaError(
        f"{stage} is not available in this build.",
        why="Optica's command surface is complete; this stage's implementation "
        "is not yet part of the installed version.",
        fix="Run: optica --version to see which version you have.",
    )


def _check_mode(mode: str | None, allowed: tuple[str, ...], command: str) -> str | None:
    """Validate ``--mode`` against the values this command accepts.

    Fixed-value flags always list valid options in their errors, and include the
    default where one applies — the values are listed **per command**, since
    ``fetch`` accepts a narrower set than ``run``.
    """
    if mode is None or mode in allowed:
        return mode
    raise OpticaValidationError(
        f"--mode {mode} is not valid for optica {command}.",
        why=f"optica {command} accepts only these modes.",
        options=list(allowed),
    )


@classify_app.command()
def fetch(
    ctx: typer.Context,
    classes: list[str] | None = _Classes,
    source: str | None = typer.Option(
        None, "--source", "-s", help="flickr, open-datasets"
    ),
    images_per_class: int | None = typer.Option(
        None, "--images-per-class", "-i", help="Images per class to fetch."
    ),
    dataset: Path = _Dataset,
    mode: str | None = typer.Option(None, "--mode", help="curate, clip"),
    clip_threshold: float | None = typer.Option(
        None, "--clip-threshold", help="CLIP confidence threshold for clip mode."
    ),
    overwrite: bool = _Overwrite,
    verbose: bool = _Verbose,
    quiet: bool = _Quiet,
    yes: bool = _Yes,
    force: bool = _Force,
    dry_run: bool = _DryRun,
) -> None:
    """Fetch images for each class from a remote source."""
    state = _globals(
        get_state(ctx),
        verbose=verbose,
        quiet=quiet,
        yes=yes,
        force=force,
        dry_run=dry_run,
    )
    # `--mode label` is a hard error here: fetch is remote acquisition, and
    # label mode takes local input.
    _check_mode(mode, ("curate", "clip"), "fetch")
    state.config(
        overrides={
            "default_source": source,
            "images_per_class": images_per_class,
            "default_mode": mode,
            "clip_threshold": clip_threshold,
        },
        flag_names={
            "default_source": "--source",
            "images_per_class": "--images-per-class",
            "default_mode": "--mode",
            "clip_threshold": "--clip-threshold",
        },
    )
    with acquire_lock("optica fetch"):
        split_values(classes)
        raise _not_yet("optica fetch")


@classify_app.command()
def label(
    ctx: typer.Context,
    classes: list[str] | None = _Classes,
    folder: Path | None = typer.Option(
        None, "--folder", help="Flat folder of images to label."
    ),
    manifest: Path | None = typer.Option(
        None, "--manifest", help="CSV or JSON manifest file."
    ),
    dataset: Path = _Dataset,
    overwrite: bool = _Overwrite,
    verbose: bool = _Verbose,
    quiet: bool = _Quiet,
    yes: bool = _Yes,
    force: bool = _Force,
) -> None:
    """Label a flat folder of images in the browser."""
    state = _globals(get_state(ctx), verbose=verbose, quiet=quiet, yes=yes, force=force)
    state.config()
    with acquire_lock("optica label"):
        split_values(classes)
        raise _not_yet("optica label")


@classify_app.command()
def curate(
    ctx: typer.Context,
    classes: list[str] | None = _Classes,
    dataset: Path = _Dataset,
    overwrite: bool = _Overwrite,
    verbose: bool = _Verbose,
    quiet: bool = _Quiet,
    yes: bool = _Yes,
    force: bool = _Force,
) -> None:
    """Review fetched images in the browser and keep the good ones."""
    state = _globals(get_state(ctx), verbose=verbose, quiet=quiet, yes=yes, force=force)
    state.config()
    with acquire_lock("optica curate"):
        # `--classes` is warned and ignored here: curate reads the fetched
        # staging structure rather than a class list.
        split_values(classes)
        raise _not_yet("optica curate")


@classify_app.command()
def train(
    ctx: typer.Context,
    classes: list[str] | None = _Classes,
    model: str | None = typer.Option(None, "--model", help="Backbone architecture."),
    epochs: int | None = typer.Option(None, "--epochs", "-e", help="Training epochs."),
    batch_size: int | None = typer.Option(None, "--batch-size", help="Images per batch."),
    no_augmentation: bool = typer.Option(
        False, "--no-augmentation", help="Disable all data augmentation."
    ),
    dataset: Path = _Dataset,
    manifest: Path | None = typer.Option(
        None, "--manifest", help="A fully labeled manifest file."
    ),
    output: Path = _Output,
    overwrite: bool = _Overwrite,
    verbose: bool = _Verbose,
    quiet: bool = _Quiet,
    yes: bool = _Yes,
    force: bool = _Force,
    dry_run: bool = _DryRun,
) -> None:
    """Train a classifier on an organized dataset."""
    state = _globals(
        get_state(ctx),
        verbose=verbose,
        quiet=quiet,
        yes=yes,
        force=force,
        dry_run=dry_run,
    )
    if model is not None and model not in MODELS:
        raise OpticaValidationError(
            f"--model {model} is not a known architecture.",
            options=list(MODELS),
            default="efficientnet-small",
        )
    state.config(
        overrides={
            "default_model": model,
            "epochs": epochs,
            "batch_size": batch_size,
            "augmentation": False if no_augmentation else None,
        },
        flag_names={
            "default_model": "--model",
            "epochs": "--epochs",
            "batch_size": "--batch-size",
            "augmentation": "--no-augmentation",
        },
    )
    with acquire_lock("optica train"):
        split_values(classes)
        raise _not_yet("optica train")


@classify_app.command()
def export(
    ctx: typer.Context,
    checkpoint_rank: list[str] | None = typer.Option(
        None,
        "--checkpoint-rank",
        "--checkpoint",
        help="Checkpoint rank(s) to export, comma-separated. Absence prompts.",
    ),
    output: Path = _Output,
    verbose: bool = _Verbose,
    quiet: bool = _Quiet,
    yes: bool = _Yes,
    force: bool = _Force,
    dry_run: bool = _DryRun,
) -> None:
    """Export a trained checkpoint."""
    state = _globals(
        get_state(ctx),
        verbose=verbose,
        quiet=quiet,
        yes=yes,
        force=force,
        dry_run=dry_run,
    )
    state.config()
    with acquire_lock("optica export"):
        # Absence is *not* rank 1: it raises the checkpoint selection prompt,
        # which `--yes` answers with rank 1.
        split_values(checkpoint_rank)
        raise _not_yet("optica export")


@classify_app.command()
def run(
    ctx: typer.Context,
    classes: list[str] | None = _Classes,
    source: str | None = typer.Option(
        None, "--source", "-s", help="flickr, open-datasets"
    ),
    images_per_class: int | None = typer.Option(
        None, "--images-per-class", "-i", help="Images per class to fetch."
    ),
    mode: str | None = typer.Option(None, "--mode", help="label, curate, clip"),
    clip_threshold: float | None = typer.Option(
        None, "--clip-threshold", help="CLIP confidence threshold for clip mode."
    ),
    model: str | None = typer.Option(None, "--model", help="Backbone architecture."),
    epochs: int | None = typer.Option(None, "--epochs", "-e", help="Training epochs."),
    batch_size: int | None = typer.Option(None, "--batch-size", help="Images per batch."),
    no_augmentation: bool = typer.Option(
        False, "--no-augmentation", help="Disable all data augmentation."
    ),
    checkpoint_rank: list[str] | None = typer.Option(
        None,
        "--checkpoint-rank",
        "--checkpoint",
        help="Checkpoint rank(s) to export, comma-separated. Absence prompts.",
    ),
    folder: Path | None = typer.Option(
        None, "--folder", help="Flat folder of images to label."
    ),
    manifest: Path | None = typer.Option(
        None, "--manifest", help="CSV or JSON manifest file."
    ),
    dataset: Path = _Dataset,
    output: Path = _Output,
    overwrite: bool = _Overwrite,
    verbose: bool = _Verbose,
    quiet: bool = _Quiet,
    yes: bool = _Yes,
    force: bool = _Force,
    dry_run: bool = _DryRun,
) -> None:
    """Run the full workflow: fetch, curate or label, train, export."""
    state = _globals(
        get_state(ctx),
        verbose=verbose,
        quiet=quiet,
        yes=yes,
        force=force,
        dry_run=dry_run,
    )
    _check_mode(mode, MODES, "run")
    if source is not None and source not in SOURCES:
        raise OpticaValidationError(
            f"--source {source} is not a known source.",
            options=list(SOURCES),
            default="open-datasets",
        )
    state.config(
        overrides={
            "default_source": source,
            "images_per_class": images_per_class,
            "default_mode": mode,
            "clip_threshold": clip_threshold,
            "default_model": model,
            "epochs": epochs,
            "batch_size": batch_size,
            "augmentation": False if no_augmentation else None,
        },
        flag_names={
            "default_source": "--source",
            "images_per_class": "--images-per-class",
            "default_mode": "--mode",
            "clip_threshold": "--clip-threshold",
            "default_model": "--model",
            "epochs": "--epochs",
            "batch_size": "--batch-size",
            "augmentation": "--no-augmentation",
        },
    )
    with acquire_lock("optica run"):
        split_values(classes)
        split_values(checkpoint_rank)
        raise _not_yet("optica run")
