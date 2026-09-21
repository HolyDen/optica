"""The ``classify`` command group.

Implements plan § "CLI Layer & Conventions" → *Commands* and the *CLI Flag
Reference (V1)*, and — from pass 2 — § "Input & Acquisition" as it reaches the
terminal: ``optica fetch`` end to end, the class-name prompt, and the terminal
side of the blocklist sequence.

**Fully self-contained** — all classify-specific logic lives here, so this module
is the clean template for a future ``cli/detect.py``. ``main.py`` registers the
group and the flat aliases and knows nothing about what is in it.

This layer maps commands to components and asks the questions; the decisions
are the Input Manager's. Prompts live here and nowhere in ``optica.input``,
which is what lets the Python API raise where the CLI asks.

Every command's body is here as of pass 5. ``run`` is the exception to this
module's self-containment in one direction only: it asks the top-level
resumption question and hands the pipeline to :func:`optica.run`, because the
sequence, the resume point and the completion lines belong to the API layer and
a second sequencer beside it would be free to drift.
"""

from __future__ import annotations

import json
import math
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any, Final

import typer

from optica import pipeline
from optica.api import simple as api
from optica.api.simple import report_training
from optica.cli import GlobalState, get_state, split_values
from optica.config.defaults import MODELS, MODES, SOURCES
from optica.config.manager import ResolvedConfig, Source
from optica.config.schema import OpticaConfig
from optica.exceptions import (
    ExitCode,
    OpticaCurationError,
    OpticaTrainingError,
    OpticaValidationError,
)
from optica.export import manager as export_manager
from optica.input import clip as clip_adapter
from optica.input import manager as input_manager
from optica.input.classes import (
    Overlap,
    ResolvedClass,
    is_blocklisted,
    normalize_class_names,
    require_min_classes,
    resolve_auto_classes,
)
from optica.input.curation import (
    CurationView,
    fetch_more,
    fetch_more_refusal,
    fetch_more_shortfall,
    load_view,
    materialize_selection,
    open_session,
    selected_counts,
    selection_warnings,
)
from optica.input.fetch import (
    CANDIDATE_SLACK,
    ClassFetchReport,
    Downloader,
    SourceContext,
    create_source,
    fetch_class,
    make_client,
    staged_classes,
    staged_images,
)
from optica.input.local import (
    copy_into_dataset,
    copy_note,
    load_organized_dataset,
    parse_manifest,
    preflight,
    require_flat_folder,
)
from optica.input.sessions import (
    CurationSession,
    LabelingSession,
    SourceType,
    load_labeling,
    staging_root,
)
from optica.input.validation import (
    HARD_FLOOR,
    SIZE_THRESHOLD,
    InPlaceReport,
    check_floor,
    check_floor_after_dedupe,
    find_duplicates,
    imbalanced_classes,
    inspect_in_place,
    md5_of,
    reasons_summary,
)
from optica.server.app import (
    BrowserSession,
    IdleTimer,
    Outcome,
    format_duration,
    load_web,
    serve,
)
from optica.server.curation import CurationController
from optica.server.labeling import LabelingController
from optica.training import checkpoints
from optica.training.engine import (
    EpochMetrics,
    allocate_phases,
    finetune_ratio_warning,
    phase2_skipped_by_one_epoch,
)
from optica.training.models import base_model_for
from optica.training.splits import split_counts, training_data_hash
from optica.training.trainer import (
    TrainingInterrupted,
    TrainPlan,
    TrainSettings,
)
from optica.training.trainer import train as run_training
from optica.utils import logging as olog
from optica.utils import prompts, workspace
from optica.utils.lockfile import acquire_lock
from optica.utils.mlstack import import_torch_stack, select_device
from optica.utils.progress import progress_bar

__all__ = ["TerminalClassPrompter", "classify_app"]

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


def _configured(resolved: ResolvedConfig, key: str) -> str | None:
    """A config value that was explicitly set in a file or the environment."""
    if resolved.sources.get(key) in (Source.DEFAULT, Source.FLAG):
        return None
    value = getattr(resolved.config, key)
    return str(value) if value is not None else None


# --- Classes ----------------------------------------------------------------


def _resolve_classes(
    raw: list[str] | None, command: str, state: GlobalState
) -> list[str]:
    """Resolve ``-c`` for a command that cannot infer classes.

    Absent, it surfaces the class-name prompt where a prompt can fire and raises
    a hard error where one cannot — under ``--yes``, or with no terminal. The
    trailing-``--classes`` case never reaches here: the parser raises
    ``BadOptionUsage`` for it and the global handler redirects it to the same
    prompt. Either way the names then go through both class-name rules, so a
    value the parser bound from a flag spelling (``--classes --yes``) is refused
    as a name.
    """
    values = split_values(raw)
    if not values:
        if state.yes or not prompts.is_interactive():
            raise input_manager.missing_classes_error(command)
        marks = olog.markers_for(olog.err_console)
        olog.err_console.print(
            f"[bold yellow]{marks.warn}[/bold yellow] No class names given."
        )
        values = split_values([prompts.ask_class_names()])
        if not values:
            raise input_manager.missing_classes_error(command)
    names = normalize_class_names(values)
    require_min_classes(names)
    return names


class TerminalClassPrompter:
    """The blocklist sequence's questions, asked in a terminal.

    Dispositions follow the ``--yes`` table: group-or-separate picks **Group**,
    the overlap warning picks **Y**, and the class-name confirmation is skipped
    for clean cases only. The user-definition prompt is absent from that table —
    no answer can be defaulted — so it fires wherever a prompt can, ``--yes`` or
    not, and raises ``OpticaValidationError`` where one cannot.

    Args:
        state: The run's global flags.
    """

    def __init__(self, state: GlobalState) -> None:
        self.state = state

    def define(self, name: str) -> list[str]:
        """Ask what a blocklisted name means, as concrete sub-terms."""
        if not prompts.is_interactive():
            raise OpticaValidationError(
                f"'{name}' needs a concrete definition before anything is fetched.",
                why=f"'{name}' does not name a searchable, visual thing, and there is "
                "no terminal to ask what it means.",
                fix="Replace it in --classes with concrete names, e.g. "
                "--classes cracked_screen,dented_case",
            )
        olog.warn(
            f"'{name}' is too abstract to search for.",
            why="Define it as one or more concrete, visual sub-terms.",
        )
        answer: str = typer.prompt(
            f"  What does '{name}' mean? Comma-separated, "
            "e.g. cracked_screen,dented_case",
            default="",
            show_default=False,
        )
        return split_values([answer])

    def group_or_separate(self, name: str, sub_terms: list[str]) -> bool:
        """Group the sub-terms into one class, or make each its own."""
        if self.state.yes:
            return True
        joined = ", ".join(sub_terms)
        return prompts.confirm(
            f"Keep {joined} together as one class '{name}'? (n makes each its own class)",
            default=True,
            non_interactive_fix="Re-run with --yes to group them.",
        )

    def accept_overlaps(self, overlaps: list[Overlap]) -> bool:
        """Warn about names that search into each other, and ask to continue."""
        for overlap in overlaps:
            olog.warn(
                f"'{overlap.inner}' overlaps '{overlap.outer}'.",
                why="A search for one also finds the other, so their images may mix.",
            )
        return prompts.confirm(
            "Continue with these names?",
            default=True,
            assume_yes=self.state.yes,
            non_interactive_fix="Re-run with --yes to continue, or rename the classes.",
        )

    def redefine_classes(self, current: list[str]) -> list[str]:
        """Re-open the class-list prompt."""
        olog.err_console.print(f"  Current classes: {', '.join(current)}")
        return split_values([prompts.ask_class_names()])

    def confirm(self, classes: list[ResolvedClass], *, clean: bool) -> bool:
        """Show the resolved class list and counts before any fetch."""
        if clean and self.state.yes:
            return True
        olog.err_console.print("Classes to fetch:")
        for cls in classes:
            if cls.grouped:
                olog.err_console.print(
                    f"  {cls.name}: {cls.per_query} images each for "
                    f"{', '.join(cls.queries)} ({cls.target} total)"
                )
            else:
                olog.err_console.print(f"  {cls.name}: {cls.target} images")
        return prompts.confirm(
            "Fetch these classes?",
            default=True,
            assume_yes=self.state.yes and clean,
            non_interactive_fix="Re-run with --yes to confirm unattended.",
        )


# --- fetch --------------------------------------------------------------------


def _report_fetch(
    reports: list[ClassFetchReport], source_name: str, *, final: bool = True
) -> None:
    """The completion block. Nothing about the fetch is silent.

    ``final=False`` where a stage follows the fetch — CLIP filtering — so the
    success line is that stage's to print.
    """
    for report in reports:
        note = ""
        if report.exhausted and report.shortfall:
            note = f" — {source_name} ran out of candidates ({report.shortfall} short)"
        olog.status(f"  {report.name}: {report.staged} images{note}")
    dead = sum(r.dead for r in reports)
    unreadable = sum(r.unreadable for r in reports)
    duplicates = sum(r.duplicates for r in reports)
    resized = sum(r.resized for r in reports)
    if dead or unreadable or duplicates:
        olog.detail(
            f"  Skipped {dead} dead links, {unreadable} unreadable downloads and "
            f"{duplicates} duplicates."
        )
    if resized:
        olog.warn(
            f"{resized} fetched images were smaller than 128px and were upscaled.",
            why="Upscaled images carry less detail than their size suggests.",
        )
    total = sum(r.staged for r in reports)
    if final:
        olog.success(f"Fetch complete — {total} images across {len(reports)} classes")
    else:
        olog.status(f"Fetched {total} candidate images across {len(reports)} classes")


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
    if clip_threshold is not None:
        # The plan's own messages for the three hard-error bands, per command.
        # Config load would reject the same values, but with its generic range
        # error, and it runs first, so the flag is checked here before it.
        input_manager.check_clip_threshold(clip_threshold, command="fetch")
    if source is not None and source not in SOURCES:
        raise OpticaValidationError(
            f"--source {source} is not a known source.",
            options=list(SOURCES),
            default="open-datasets",
        )
    resolved = state.config(
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
    config = resolved.config

    # --- Everything knowable at entry, before any prompt or download. ----
    resolved_mode = input_manager.resolve_mode(
        command="fetch",
        explicit=mode,
        configured=_configured(resolved, "default_mode"),
        local_input=False,
    )
    names = _resolve_classes(classes, "fetch", state)
    blocklisted = [name for name in names if is_blocklisted(name)]
    if resolved_mode.mode == "clip":
        threshold = input_manager.check_clip_threshold(
            config.clip_threshold, command="fetch"
        )
        input_manager.require_clip_extra()
        if threshold.warning:
            olog.warn(threshold.warning)
        if threshold.prompt:
            prompts.confirm_or_abort(
                threshold.prompt,
                default=True,
                assume_yes=state.yes,
                non_interactive_fix="Re-run with --yes to continue.",
            )
    elif blocklisted:
        # The grouped path scores images with CLIP after the fetch completes;
        # blocklist membership is knowable now, so the dependency is checked now
        # rather than after the run's work and quota are spent.
        input_manager.require_clip_extra()

    if state.dry_run:
        olog.status(resolved_mode.line)
        olog.status(f"Source: {config.default_source}")
        olog.status(f"Classes: {', '.join(names)}")
        olog.status(f"Images per class: {config.images_per_class}")
        if blocklisted:
            olog.status(f"Needs a definition first: {', '.join(blocklisted)}")
        if resolved_mode.mode == "clip":
            olog.status(
                f"Candidates per class: {config.images_per_class} x "
                f"{clip_adapter.OVERFETCH_FACTOR}, filtered at clip_threshold "
                f"{config.clip_threshold}"
            )
            olog.status(f"Destination: {dataset}")
        else:
            olog.status("Destination: ~/.optica/staging/")
        olog.status("Dry run — nothing was fetched or written.")
        return

    with acquire_lock("optica fetch"):
        _fetch_body(
            state, names, resolved_mode, resolved, dataset, overwrite=overwrite
        )


def _fetch_body(
    state: GlobalState,
    names: list[str],
    resolved_mode: input_manager.ResolvedMode,
    resolved: ResolvedConfig,
    dataset: Path,
    *,
    overwrite: bool,
) -> None:
    config = resolved.config
    clip_mode = resolved_mode.mode == "clip"
    if clip_mode:
        # Clip mode is the one fetch path that writes `dataset/`, so the
        # destination check runs first — before any request or prompt for work.
        _confirm_replace(
            state, dataset, "images kept by CLIP filtering", overwrite=overwrite
        )
    client = make_client()
    try:
        context = SourceContext(
            client=client, api_key=config.flickr_api_key, report=olog.status
        )
        source = create_source(config.default_source, context)
        # Unknown names and a missing key fail before any prompt asks for work.
        source.prepare([name for name in names if not is_blocklisted(name)])

        if config.default_source == "open-datasets" and input_manager.soft_cap_exceeded(
            config.images_per_class, config.max_open_datasets_per_class
        ):
            olog.warn(
                f"--images-per-class {config.images_per_class} is above the Open Images "
                f"courtesy limit of {config.max_open_datasets_per_class} per class.",
                why="Open Images is public infrastructure; large fetches load it for "
                "everyone.",
            )
            prompts.confirm_or_abort(
                "Continue anyway?",
                default=True,
                category=prompts.PromptCategory.SAFETY,
                assume_yes=state.yes,
                force=state.force,
                non_interactive_fix="Re-run with --yes to continue, or lower "
                "--images-per-class.",
            )

        _resume_or_start_fresh(state, names)

        plan = resolve_auto_classes(
            names, config.images_per_class, TerminalClassPrompter(state)
        )
        if not plan:
            raise typer.Exit(code=ExitCode.ABORTED)
        source.prepare([query for cls in plan for query in cls.queries])

        olog.status(resolved_mode.line)
        olog.status(f"Source: {source.display_name}")
        scorer: clip_adapter.ImageScorer | None = None
        if clip_mode or any(cls.grouped for cls in plan):
            # Loaded — its weights downloaded and verified — before any image is
            # fetched, so a load failure costs no quota.
            scorer = clip_adapter.load_clip(
                report=olog.status,
                quiet=olog.get_verbosity() <= olog.Verbosity.QUIET,
            )
        # Clip mode fetches twice the target, and keeps up to the target.
        fetch_plan = (
            [clip_adapter.overfetch(cls) for cls in plan] if clip_mode else plan
        )
        existing = {s.name: s.images for s in staged_classes()}
        needed = {
            query: math.ceil(
                max(0, cls.target - existing.get(cls.name, 0)) * CANDIDATE_SLACK
            )
            for cls in fetch_plan
            for query in cls.queries
        }
        source.warm({query: count for query, count in needed.items() if count})

        downloader = Downloader(client)
        reports: list[ClassFetchReport] = []
        for cls in fetch_plan:
            with progress_bar(f"Fetching {cls.name}", total=cls.target) as bar:
                task = bar.task_ids[0]
                bar.advance(task, existing.get(cls.name, 0))
                reports.append(
                    fetch_class(
                        cls, source, downloader, on_image=partial(bar.advance, task)
                    )
                )
        source_name = source.display_name
    finally:
        client.close()

    if scorer is None:
        _report_fetch(reports, source_name)
        return
    _report_fetch(reports, source_name, final=False)
    if clip_mode:
        _clip_into_dataset(plan, scorer, config.clip_threshold, dataset)
    else:
        grouped = [cls for cls in plan if cls.grouped]
        removed = _clip_grouped_staging(grouped, scorer, config.clip_threshold)
        total = sum(r.staged for r in reports) - removed
        olog.success(f"Fetch complete — {total} images across {len(reports)} classes")


def _clip_score(
    scorer: clip_adapter.ImageScorer,
    cls: ResolvedClass,
    threshold: float,
    *,
    keep: int | None,
) -> clip_adapter.ClipFilterReport:
    """Score one staged class against its prompts: its own name, or every sub-term."""
    images = staged_images(staging_root() / cls.name)
    class_prompts = [clip_adapter.prompt_for(query) for query in cls.queries]
    with progress_bar(f"Scoring {cls.name}", total=len(images)) as bar:
        scores = scorer.score(
            images, class_prompts, on_image=partial(bar.advance, bar.task_ids[0])
        )
    return clip_adapter.select_survivors(
        cls.name, list(zip(images, scores, strict=True)), threshold, keep
    )


def _report_clip(report: clip_adapter.ClipFilterReport) -> None:
    """One class's post-filter line — a shortfall is visible, never silent."""
    line = (
        f"  {report.name}: {report.candidates} scored, {report.passed} at or "
        f"above {report.threshold}, {report.kept} kept"
    )
    if report.unreadable:
        line += f" ({report.unreadable} could not be read)"
    olog.status(line)


def _clip_into_dataset(
    plan: list[ResolvedClass],
    scorer: clip_adapter.ImageScorer,
    threshold: float,
    dataset: Path,
) -> None:
    """Clip mode's ingest: score each class, keep the best, write ``dataset/``.

    Keeps up to each class's un-doubled target, best score first. Written into a
    hidden sibling and committed in one move once every class is done, so a
    failure leaves the old dataset exactly as it was; the destination check ran
    at command start. MD5 deduplication runs again within each class. The
    consumed staging is removed only after the commit, so a failure before it
    leaves the fetched images for a re-run to resume from.
    """
    partial_dir = input_manager.partial_destination(dataset)
    if partial_dir.exists():
        shutil.rmtree(partial_dir)
    olog.status(f"CLIP filtering at clip_threshold {threshold}:")
    reports: list[clip_adapter.ClipFilterReport] = []
    duplicates = 0
    try:
        for cls in plan:
            report = _clip_score(scorer, cls, threshold, keep=cls.target)
            folder = partial_dir / cls.name
            # Created even when nothing passed, so an empty class reaches
            # training's floor check by name instead of vanishing.
            folder.mkdir(parents=True, exist_ok=True)
            seen: set[str] = set()
            written = 0
            for path in report.kept_paths:
                data = path.read_bytes()
                digest = md5_of(data)
                if digest in seen:
                    duplicates += 1
                    continue
                seen.add(digest)
                (folder / path.name).write_bytes(data)
                written += 1
            report.kept = written
            reports.append(report)
            _report_clip(report)
    except BaseException:
        shutil.rmtree(partial_dir, ignore_errors=True)
        raise
    input_manager.commit_dataset(partial_dir, dataset)
    for cls in plan:
        shutil.rmtree(staging_root() / cls.name, ignore_errors=True)

    if duplicates:
        olog.status(f"  {duplicates} duplicate images removed.")
    short = [r for r in reports if r.shortfall]
    if short:
        olog.warn(
            "Fewer images than requested passed CLIP filtering: "
            + ", ".join(f"{r.name} kept {r.kept} of {r.target}" for r in short)
            + ".",
            why="Not an error — the imbalance warning and the 5-image floor decide "
            "at training whether the dataset is usable.",
        )
    kept = sum(r.kept for r in reports)
    olog.success(
        f"Fetch complete — {kept} images kept across {len(reports)} classes "
        f"in {dataset}"
    )


def _clip_grouped_staging(
    grouped: list[ResolvedClass],
    scorer: clip_adapter.ImageScorer,
    threshold: float,
) -> int:
    """The grouped path under curate: filter each group's staging by its sub-terms.

    Each image is scored against every sub-term and keeps the group's label. One
    that reaches the threshold on no sub-term is removed from staging — silently,
    per the deletion rule for auto-fetched images, with the count reported.
    Nothing is capped: a person selects from what remains.

    Returns:
        How many staged images were removed.
    """
    olog.status(f"CLIP filtering grouped classes at clip_threshold {threshold}:")
    removed = 0
    for cls in grouped:
        report = _clip_score(scorer, cls, threshold, keep=None)
        for path in report.rejected_paths:
            path.unlink(missing_ok=True)
        removed += len(report.rejected_paths)
        _report_clip(report)
    return removed


def _resume_or_start_fresh(state: GlobalState, names: list[str]) -> None:
    """The interrupted-fetch prompt, which belongs to ``optica fetch``.

    ``--yes`` picks Resume. Declining starts fresh for those classes, which
    deletes their ``.partial`` directories — the directory is the whole state.
    Staged classes not in this request are left alone and named, since
    curation will show them.
    """
    staged = staged_classes()
    requested = set(names)
    interrupted = [s for s in staged if s.partial and s.name in requested]
    others = sorted({s.name for s in staged if s.name not in requested})
    if others:
        olog.warn(
            f"Staging also holds images for {', '.join(others)}, which curation "
            "will show.",
            fix="To start clean: optica config --clear-staging",
        )
    if not interrupted:
        return
    olog.err_console.print("A previous fetch was interrupted:")
    for s in interrupted:
        olog.err_console.print(f"  {s.name}: {s.images} images so far")
    resume = prompts.confirm(
        "Resume it? (n starts fresh for these classes)",
        default=True,
        assume_yes=state.yes,
        non_interactive_fix="Re-run with --yes to resume.",
    )
    if not resume:
        for s in interrupted:
            shutil.rmtree(s.path)


# --- label, curate ------------------------------------------------------------


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
    config = state.config().config
    source = input_manager.require_single_input_source(folder, manifest)
    if source is input_manager.InputSource.FETCH:
        raise OpticaValidationError(
            "optica label needs a flat folder or a manifest to label.",
            why="Neither --folder nor --manifest was given.",
            fix=[
                "Label a folder: optica label --folder ./images -c cat,dog",
                "Label a manifest: optica label --manifest ./images.csv -c cat,dog",
            ],
        )
    # The whole of this command is the browser stage, so its dependency is
    # checked here — before any prompt spends the user's attention.
    load_web()
    target = _label_input(folder, manifest)
    names = _resolve_classes(classes, "label", state)
    with acquire_lock("optica label"):
        _label_body(state, config, target, names, dataset, overwrite=overwrite)


@dataclass(frozen=True)
class _LabelTarget:
    """What ``optica label`` labels: a flat folder or an unlabeled manifest."""

    flag: str
    path: Path
    files: list[Path]
    source_type: SourceType
    content_hash: str | None = None


def _label_input(folder: Path | None, manifest: Path | None) -> _LabelTarget:
    if folder is not None:
        files = require_flat_folder(folder)
        return _LabelTarget(
            "--folder", folder, [f.resolve() for f in files], SourceType.FOLDER
        )
    assert manifest is not None
    parsed = parse_manifest(manifest)
    # A fully labeled manifest is a hard error, not a correction pass.
    parsed.require_unlabeled_for_label()
    if parsed.duplicates_removed:
        olog.status(
            f"Manifest: {parsed.duplicates_removed} exact duplicate row"
            f"{'s' if parsed.duplicates_removed != 1 else ''} collapsed."
        )
    # Read only. The manifest is disposable input and never rewritten: its
    # content hash is part of the session ID, so writing to it would orphan the
    # user's labeling progress and silently start a blank session next time.
    return _LabelTarget(
        "--manifest",
        manifest,
        [row.path for row in parsed.rows],
        SourceType.MANIFEST,
        parsed.content_hash,
    )


def _open_labeling_session(
    state: GlobalState, target: _LabelTarget, names: list[str]
) -> LabelingSession:
    """Resume, adopt, or start fresh — before any image is read.

    ``-c`` is never part of the session ID, so a corrected class list finds the
    same session; a mismatch adds **Adopt** to the prompt. ``--yes`` picks
    Resume; adopting is never automatic.
    """
    fresh = LabelingSession.new(
        None, target.path, target.source_type, names, target.content_hash
    )
    if not fresh.path.exists():
        return fresh
    stored = load_labeling(fresh.path)
    labeled = sum(1 for e in stored.entries.values() if e.get("state") == "labeled")
    skipped = sum(1 for e in stored.entries.values() if e.get("state") == "skipped")
    olog.err_console.print(
        f"A labeling session for {stored.source} was found: {labeled} labeled, "
        f"{skipped} skipped (last saved {stored.updated})."
    )
    options = {"R": "Resume", "S": "Start fresh"}
    mismatch = stored.classes_disagree(names)
    if mismatch:
        olog.err_console.print(f"  Session classes: {', '.join(stored.classes)}")
        olog.err_console.print(f"  --classes:       {', '.join(names)}")
        options = {
            "R": f"Resume with {', '.join(stored.classes)}",
            "A": f"Adopt {', '.join(names)}",
            "S": "Start fresh",
        }
    choice = prompts.choose(
        "Resume this labeling session?",
        options,
        default="R",
        assume_yes="R" if state.yes else None,
        non_interactive_fix="Re-run with --yes to resume it.",
    )
    if choice == "S":
        fresh.path.unlink()
        return fresh
    if choice == "A":
        # Entries in a departing class return to the queue as not yet reached.
        departed = stored.adopt_classes(names)
        stored.save()
        if departed:
            olog.status(
                f"{departed} label{'s' if departed != 1 else ''} for removed classes "
                "returned to the queue."
            )
    elif mismatch:
        olog.status(f"Resuming with the session's classes: {', '.join(stored.classes)}")
    return stored


def _with_dataset(argv: list[str], value: str) -> str:
    """The invocation with ``--dataset`` set to ``value``, every other flag kept."""
    out: list[str] = []
    skip = False
    for arg in argv:
        if skip:
            skip = False
            continue
        if arg in ("--dataset", "-d"):
            skip = True
            continue
        if arg.startswith("--dataset="):
            continue
        out.append(arg)
    return "optica " + " ".join([*out, "--dataset", value])


def _confirm_replace(
    state: GlobalState, destination: Path, replaced_with: str, *, overwrite: bool
) -> None:
    """The ``dataset/`` overwrite prompt, at command start, before the browser opens.

    Keyed to the destination. Destructive: ``--yes`` and ``--force`` never answer
    it, ``--overwrite`` is the only unattended route past it, and its default is
    N. Nothing is deleted here — the old dataset is replaced only once the new
    one is complete.
    """
    counts = input_manager.destination_contents(destination)
    if counts is None:
        return
    if overwrite:
        olog.warn(f"{destination} will be replaced (--overwrite).")
        return
    if not prompts.is_interactive():
        raise input_manager.overwrite_refused(destination)
    for line in input_manager.describe_destination(destination, counts, replaced_with):
        olog.err_console.print(line)
    if prompts.confirm(
        "Continue? (n to exit)",
        default=False,
        category=prompts.PromptCategory.DESTRUCTIVE,
    ):
        return
    marks = olog.markers_for(olog.err_console)
    olog.err_console.print(f"[bold red]{marks.error}[/bold red] Aborted.")
    olog.err_console.print(
        f"  To train on your existing dataset: optica train --dataset {destination}"
    )
    olog.err_console.print("  To create a new dataset at a different path:")
    olog.err_console.print(f"  {_with_dataset(state.argv, './new-dataset')}")
    raise typer.Exit(code=ExitCode.ABORTED)


def _report_unreadable(reports: list[InPlaceReport], when: str) -> None:
    """User-provided files that could not be read: listed individually, untouched."""
    if not reports:
        return
    count = len(reports)
    olog.warn(
        f"{count} file{'s' if count != 1 else ''} could not be read {when} and "
        f"{'is' if count == 1 else 'are'} left out. The files are untouched."
    )
    for line in reasons_summary(reports):
        olog.err_console.print(f"  {line}")


def _label_body(
    state: GlobalState,
    config: OpticaConfig,
    target: _LabelTarget,
    names: list[str],
    dataset: Path,
    *,
    overwrite: bool,
) -> None:
    session = _open_labeling_session(state, target, names)
    _confirm_replace(state, dataset, f"labels from {target.flag}", overwrite=overwrite)

    readable, unreadable = preflight(target.files)
    _report_unreadable(unreadable, "before labeling")

    controller = LabelingController(session, readable, unreadable)
    browser = BrowserSession(controller, IdleTimer(config.curation_timeout_minutes))
    outcome = serve(
        browser,
        configured_port=config.curation_port,
        headline=f"Labeling {len(readable)} image{'s' if len(readable) != 1 else ''}",
    )
    if outcome is Outcome.TIMED_OUT:
        olog.incomplete(
            "Labeling incomplete — the session closed after "
            f"{format_duration(browser.timer.timeout_seconds)} without activity; "
            "progress is saved. Run the same command to resume."
        )
        raise typer.Exit(code=ExitCode.ABORTED)
    if outcome is Outcome.INTERRUPTED:
        olog.incomplete(
            "Labeling incomplete — interrupted; progress is saved. "
            "Run the same command to resume."
        )
        raise typer.Exit(code=ExitCode.INTERRUPTED)
    _materialize_labels(controller, dataset, unreadable)


def _materialize_labels(
    controller: LabelingController, dataset: Path, unreadable: list[InPlaceReport]
) -> None:
    """Copy labeled images into ``dataset/<class>/``, replacing what was there.

    Written into a hidden sibling first, so the checks run before anything the
    user already has is touched: a class that falls below the floor — through
    duplicates, or a file that only failed when fully decoded — leaves the old
    dataset as it was and the session file in place to resume.
    """
    items = controller.labeled_items()
    session = controller.session
    before = controller.counts()
    partial = input_manager.partial_destination(dataset)
    if partial.exists():
        shutil.rmtree(partial)
    olog.status(copy_note((path for path, _ in items), dataset))
    report = copy_into_dataset(items, partial)
    try:
        _report_unreadable(report.unreadable, "while copying")
        classes = {str(path): name for path, name in items}
        for bad in report.unreadable:
            before[classes[str(bad.path)]] -= 1
        check_floor(before)
        after = {name: report.copied.get(name, 0) for name in session.classes}
        check_floor_after_dedupe(before, after, resumable_session=True)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    input_manager.commit_dataset(partial, dataset)
    session.path.unlink(missing_ok=True)

    def plural(count: int, noun: str) -> str:
        return f"{count} {noun}{'s' if count != 1 else ''}"

    duplicates = sum(report.duplicates.values())
    if duplicates:
        olog.status(f"  {plural(duplicates, 'duplicate image')} removed.")
    if report.renamed:
        olog.status(
            f"  {plural(report.renamed, 'file')} renamed to avoid a name collision "
            "(_2, _3, …)."
        )
    if report.converted:
        olog.status(f"  {report.converted} converted to JPEG or PNG.")
    if report.resized:
        olog.warn(
            f"{plural(report.resized, 'image')} smaller than 128px "
            f"{'were' if report.resized != 1 else 'was'} upscaled.",
            why="Upscaled images carry less detail than their size suggests.",
        )
    skipped_files = len(unreadable) + len(report.unreadable)
    details = f"{report.total} images labeled across {len(session.classes)} classes"
    if skipped_files:
        details += (
            f" ({skipped_files} unreadable file{'s' if skipped_files != 1 else ''} "
            "left out)"
        )
    olog.success(f"Labeling complete — {details}")


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
    config = state.config().config
    if split_values(classes):
        # Curate reads the fetched staging structure rather than a class list.
        olog.warn(
            "--classes is ignored by optica curate.",
            why="Curation reviews the classes already fetched into staging.",
        )
    # The whole of this command is the browser stage; see `label`.
    load_web()
    with acquire_lock("optica curate"):
        view = load_view()
        if view.incomplete:
            # Reported and proceeded past: the resume prompt belongs to fetch.
            olog.warn(
                f"The fetch for {', '.join(view.incomplete)} did not finish; curating "
                "what was fetched.",
                fix="To finish it first: optica fetch --classes "
                + ",".join(view.incomplete),
            )
        _curate_body(state, config, view, dataset, overwrite=overwrite)


def _open_curation_session(state: GlobalState) -> CurationSession:
    """Resume the one curation session, or start fresh — before the browser opens.

    ``--yes`` picks Resume. Start fresh deletes ``curation.json`` — the state
    file — and keeps the fetched images, which are what there is to curate.
    """
    session = open_session()
    if not session.path.exists():
        return session
    deselected = sum(len(paths) for paths in session.deselected.values())
    noun = "image" if deselected == 1 else "images"
    olog.err_console.print(
        f"A curation session was found: {deselected} {noun} deselected "
        f"(last saved {session.updated})."
    )
    choice = prompts.choose(
        "Resume this curation session?",
        {"R": "Resume", "S": "Start fresh"},
        default="R",
        assume_yes="R" if state.yes else None,
        non_interactive_error=OpticaCurationError,
        non_interactive_fix="Re-run with --yes to resume it.",
    )
    if choice == "S":
        session.path.unlink()
        return CurationSession(session.path)
    return session


def _run_fetch_more(
    config: OpticaConfig,
    requests: dict[str, int],
    *,
    progress: bool,
    on_image: Callable[[], None] | None = None,
) -> list[ClassFetchReport]:
    """Fetch more for staged classes, through the Curation Adapter."""
    client = make_client()
    try:
        context = SourceContext(
            client=client, api_key=config.flickr_api_key, report=olog.status
        )
        source = create_source(config.default_source, context)
        source.prepare(list(requests))
        source.warm(
            {name: math.ceil(n * CANDIDATE_SLACK) for name, n in requests.items()}
        )
        downloader = Downloader(client)
        reports: list[ClassFetchReport] = []
        for name, count in requests.items():
            if not progress:
                reports.append(
                    fetch_more(name, count, source, downloader, on_image=on_image)
                )
                continue
            with progress_bar(f"Fetching {count} more for {name}", total=count) as bar:
                advance = partial(bar.advance, bar.task_ids[0])
                reports.append(
                    fetch_more(name, count, source, downloader, on_image=advance)
                )
        return reports
    finally:
        client.close()


def _mass_rejection(
    state: GlobalState,
    config: OpticaConfig,
    view: CurationView,
    session: CurationSession,
) -> tuple[str, CurationView]:
    """The post-Confirm mass-rejection prompt: F / C / A.

    Two independent triggers, each with its own message. **C** raises a second
    confirmation defaulting to N; N returns to F/C/A. ``--yes`` picks C, then Y.
    **F** fetches enough to restore ``images_per_class`` selected and reopens
    curation; when a fetch yields nothing new the prompt returns without F, so
    an exhausted source cannot loop.

    Returns:
        ``("C", view)`` to continue, ``("F", reloaded view)`` to reopen
        curation, or ``("A", view)`` to abort.
    """
    offer_fetch = True
    while True:
        selected = selected_counts(view, session)
        warnings = selection_warnings(view.fetched, selected)
        if not warnings:
            return "C", view
        for warning in warnings:
            olog.warn(warning.message)
        requests: dict[str, int] = {}
        for warning in warnings:
            name = warning.class_name
            count = fetch_more_shortfall(config.images_per_class, selected[name])
            if count > 0 and fetch_more_refusal(name) is None:
                requests[name] = count
        options = {"C": "Continue anyway", "A": "Abort"}
        if offer_fetch and requests:
            options = {"F": "Fetch more", **options}
        choice = prompts.choose(
            "Some classes have few images selected.",
            options,
            default="C",
            assume_yes="C" if state.yes else None,
            non_interactive_fix="Re-run with --yes to continue with the selection.",
        )
        if choice == "A":
            return "A", view
        if choice == "C":
            if prompts.confirm(
                "Continue with the current selection?",
                default=False,
                assume_yes=state.yes,
                non_interactive_fix="Re-run with --yes to continue.",
            ):
                return "C", view
            continue
        reports = _run_fetch_more(config, requests, progress=True)
        delivered = sum(report.delivered for report in reports)
        view = load_view()
        if delivered:
            olog.status(f"Fetched {delivered} more images; reopening curation.")
            return "F", view
        olog.warn("The source had no more images for those classes.")
        offer_fetch = False


def _curate_body(
    state: GlobalState,
    config: OpticaConfig,
    view: CurationView,
    dataset: Path,
    *,
    overwrite: bool,
) -> None:
    session = _open_curation_session(state)
    _confirm_replace(
        state, dataset, "images selected in curation", overwrite=overwrite
    )

    def browser_fetch(
        name: str, count: int, on_image: Callable[[], None]
    ) -> ClassFetchReport:
        [report] = _run_fetch_more(
            config, {name: count}, progress=False, on_image=on_image
        )
        return report

    while True:
        controller = CurationController(
            view,
            session,
            config.images_per_class,
            reload=load_view,
            fetch_more=browser_fetch,
        )
        browser = BrowserSession(controller, IdleTimer(config.curation_timeout_minutes))
        total = sum(view.fetched.values())
        outcome = serve(
            browser,
            configured_port=config.curation_port,
            headline=f"Curating {total} images across {len(view.images)} classes",
        )
        if outcome is Outcome.TIMED_OUT:
            olog.incomplete(
                "Curation incomplete — the session closed after "
                f"{format_duration(browser.timer.timeout_seconds)} without activity; "
                "selections are saved. Run optica curate to resume."
            )
            raise typer.Exit(code=ExitCode.ABORTED)
        if outcome is Outcome.INTERRUPTED:
            olog.incomplete(
                "Curation incomplete — interrupted; selections are saved. "
                "Run optica curate to resume."
            )
            raise typer.Exit(code=ExitCode.INTERRUPTED)
        choice, view = _mass_rejection(state, config, controller.view, session)
        if choice == "F":
            continue
        if choice == "A":
            olog.incomplete(
                "Curation incomplete — aborted; staging and selections are preserved."
            )
            raise typer.Exit(code=ExitCode.ABORTED)
        break
    _materialize_selection(view, session, dataset)


def _materialize_selection(
    view: CurationView, session: CurationSession, dataset: Path
) -> None:
    """Write the selection into ``dataset/<class>/``, replacing what was there.

    Into a hidden sibling first, as for labeling. Then rejected auto-fetched
    images are deleted from staging — silently, per the deletion rule — and
    ``curation.json`` with them, the session being complete.
    """
    selected = selected_counts(view, session)
    partial_dir = input_manager.partial_destination(dataset)
    if partial_dir.exists():
        shutil.rmtree(partial_dir)
    report = materialize_selection(view, session, partial_dir)
    try:
        # Only a class the selection put at or above the floor can *fall* below
        # it here; one already below it is the mass-rejection prompt's business,
        # answered with C, and training refuses it later.
        certified = {name: n for name, n in selected.items() if n >= HARD_FLOOR}
        after = {name: report.written.get(name, 0) for name in certified}
        check_floor_after_dedupe(certified, after)
    except BaseException:
        shutil.rmtree(partial_dir, ignore_errors=True)
        raise
    input_manager.commit_dataset(partial_dir, dataset)

    rejected = 0
    for name, paths in view.images.items():
        for path in paths:
            if not session.is_selected(name, str(path)):
                path.unlink(missing_ok=True)
                rejected += 1
    session.path.unlink(missing_ok=True)

    duplicates = sum(report.duplicates.values())
    if duplicates:
        noun = "image" if duplicates == 1 else "images"
        olog.status(f"  {duplicates} duplicate {noun} removed.")
    olog.detail(f"  {rejected} deselected images removed from staging.")
    written = sum(report.written.values())
    olog.success(
        f"Curation complete — {written} images selected across "
        f"{len(view.images)} classes"
    )


# --- train, export, run ---------------------------------------------------------


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
    resolved = state.config(
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
    requested = split_values(classes)
    if requested:
        requested = normalize_class_names(requested)
    if state.dry_run:
        _train_dry_run(resolved.config, dataset, manifest, output, requested)
        return
    with acquire_lock("optica train"):
        _train_body(
            state,
            resolved,
            requested,
            dataset=dataset,
            manifest=manifest,
            output=output,
            overwrite=overwrite,
        )


def _settings(config: OpticaConfig) -> TrainSettings:
    return TrainSettings(
        epochs=config.epochs,
        batch_size=config.batch_size,
        learning_rate=config.learning_rate,
        augmentation=config.augmentation,
        early_stopping=config.early_stopping,
        finetune_ratio=config.finetune_ratio,
        optimizer=config.optimizer,
        train_split=config.train_split,
        val_split=config.val_split,
        test_split=config.test_split,
        max_checkpoints=config.max_checkpoints,
    )


def _train_dry_run(
    config: OpticaConfig,
    dataset: Path,
    manifest: Path | None,
    output: Path,
    requested: list[str],
) -> None:
    """What ``optica train`` would do. Reads the dataset's shape; writes nothing."""
    if manifest is not None:
        parsed = parse_manifest(manifest)
        parsed.require_fully_labeled()
        counts: dict[str, int] = {}
        for row in parsed.rows:
            assert row.class_name is not None
            counts[row.class_name] = counts.get(row.class_name, 0) + 1
        olog.status(f"Dataset: {dataset} (materialized from --manifest {manifest})")
    else:
        counts = load_organized_dataset(dataset).counts
        olog.status(f"Dataset: {dataset}")
    if requested:
        input_manager.compare_classes(requested, sorted(counts))
        counts = {name: counts[name] for name in requested}
    settings = _settings(config)
    phase1, phase2 = allocate_phases(settings.epochs, settings.finetune_ratio)
    olog.status(
        f"Model: {config.default_model} ({base_model_for(config.default_model)})"
    )
    olog.status(
        f"Epochs: {settings.epochs} — {phase1} head warmup + {phase2} fine-tune"
    )
    olog.status(f"Batch size: {settings.batch_size}")
    olog.status("Split per class (train/val/test):")
    for name in sorted(counts):
        n_train, n_val, n_test = split_counts(
            counts[name], settings.val_split, settings.test_split
        ) if counts[name] >= 2 else (counts[name], 0, 0)
        olog.status(f"  {name}: {counts[name]} images → {n_train}/{n_val}/{n_test}")
    olog.status(f"Checkpoints: ./{checkpoints.CHECKPOINTS_DIR}/")
    olog.status(f"Training log: {output / 'logs'}")
    olog.status("Dry run — nothing was trained or written.")


def _ensure_output(state: GlobalState, output: Path) -> None:
    """``--output`` as a container for the project-local training log.

    For ``optica train`` the path is always a container — the log is the only
    thing written there, so the export table's name-versus-container question
    does not arise (``notes/build-log.md``). Absent: ``Create it? [Y/n]``, which
    ``--yes`` confirms. A file: a hard error.
    """
    if output.is_dir():
        return
    if output.exists():
        raise OpticaValidationError(
            f"--output {output} is a file, not a folder.",
            why="--output is the container for run outputs.",
            fix="Choose a folder path: optica train --output ./optica-output",
        )
    prompts.confirm_or_abort(
        f"--output {output} does not exist. Create it?",
        default=True,
        assume_yes=state.yes,
        non_interactive_fix="Re-run with --yes to create it.",
    )
    workspace.create_ignored(output)


_KADS_PENDING = Callable[[], None]


def _checkpoint_housekeeping(
    state: GlobalState, root: Path, max_checkpoints: int
) -> _KADS_PENDING:
    """The K/A/D/S prompt and the soft limit.

    Returns the action, run just before training: nothing is moved or deleted
    while a later check could still stop the run.
    """
    existing = checkpoints.rank(checkpoints.list_active(root))
    if not existing:
        return lambda: None
    olog.err_console.print(
        f"{len(existing)} checkpoint{'s' if len(existing) != 1 else ''} from earlier "
        f"runs in {root}/:"
    )
    for item in existing[:10]:
        olog.err_console.print(f"  {item.path.name}")
    if len(existing) > 10:
        olog.err_console.print(f"  (and {len(existing) - 10} more)")
    choice = prompts.choose(
        "What would you like to do?",
        {
            "K": "Keep all",
            "A": f"Archive all (moved to {checkpoints.CHECKPOINTS_DIR}/"
            f"{checkpoints.ARCHIVE_DIR}/<timestamp>/ before new training starts)",
            "D": "Delete all",
            "S": "Select — choose per checkpoint",
        },
        default="K",
        assume_yes="K" if state.yes else None,
        non_interactive_error=OpticaTrainingError,
        non_interactive_fix="Re-run with --yes to keep them.",
    )
    to_archive: list[checkpoints.Checkpoint] = []
    to_delete: list[checkpoints.Checkpoint] = []
    if choice == "A":
        to_archive = existing
    elif choice == "D":
        to_delete = existing
    elif choice == "S":
        for item in existing:
            pick = prompts.choose(
                item.path.name,
                {"K": "Keep", "A": "Archive", "D": "Delete"},
                default="K",
                non_interactive_error=OpticaTrainingError,
            )
            (to_archive if pick == "A" else to_delete if pick == "D" else []).append(item)
    kept = len(existing) - len(to_archive) - len(to_delete)
    limit = checkpoints.soft_limit(max_checkpoints)
    if kept > limit:
        olog.warn(
            f"{kept} checkpoints are kept in {root}/, more than {limit} "
            f"(3 x max_checkpoints).",
            why="Each run adds up to max_checkpoints more.",
            fix="Archive or delete some at the next prompt, or remove folders by hand.",
        )
        prompts.confirm_or_abort(
            "Continue?",
            default=True,
            assume_yes=state.yes,
            non_interactive_fix="Re-run with --yes to continue.",
        )

    def act() -> None:
        if to_archive:
            target = checkpoints.archive(to_archive, root, datetime.now())
            olog.status(f"Archived {len(to_archive)} checkpoints to {target}")
        if to_delete:
            checkpoints.delete(to_delete)
            olog.status(f"Deleted {len(to_delete)} checkpoints.")

    return act


def _resume_prompt(state: GlobalState, root: Path) -> checkpoints.Checkpoint | None:
    """Offer to continue the newest interrupted checkpoint. ``--yes``: Continue."""
    candidate = checkpoints.resumable(checkpoints.list_active(root))
    if candidate is None:
        return None
    total = candidate.info.get("config", {}).get("epochs", "?")
    at = _interrupted_at(candidate)
    olog.err_console.print(
        f"Training was interrupted at epoch {at} of {total} ({candidate.path.name})."
    )
    if prompts.confirm(
        "Continue from checkpoint?",
        default=True,
        assume_yes=state.yes,
        non_interactive_error=OpticaTrainingError,
        non_interactive_fix="Re-run with --yes to continue it.",
    ):
        return candidate
    return None


def _interrupted_at(candidate: checkpoints.Checkpoint) -> int:
    """The epoch the run was in when interrupted.

    Read from the run's log, which records it; ``checkpoint_info.json`` does not.
    Falls back to the checkpoint's own epoch.
    """
    raw = candidate.info.get("log_file")
    if isinstance(raw, str):
        try:
            data = json.loads(Path(raw).expanduser().read_text(encoding="utf-8"))
            return int(data["interrupted_at_epoch"])
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return candidate.epoch


def _materialize_manifest(
    state: GlobalState, manifest: Path, dataset: Path, *, overwrite: bool
) -> Callable[[], None]:
    """``train --manifest``: validate now, return the copy to run later.

    The manifest must be fully labeled. The ``dataset/`` destination check fires
    here, before any other prompt spends attention; the copy itself runs after
    every question is answered.
    """
    parsed = parse_manifest(manifest)
    parsed.require_fully_labeled()
    _confirm_replace(state, dataset, "images from --manifest", overwrite=overwrite)
    items = [(row.path, row.class_name) for row in parsed.rows if row.class_name]

    def copy() -> None:
        partial = input_manager.partial_destination(dataset)
        if partial.exists():
            shutil.rmtree(partial)
        olog.status(copy_note((path for path, _ in items), dataset))
        report = copy_into_dataset(items, partial)
        try:
            _report_unreadable(report.unreadable, "while copying")
            before: dict[str, int] = {}
            for _, name in items:
                before[name] = before.get(name, 0) + 1
            for bad in report.unreadable:
                owner = next(n for p, n in items if p == bad.path)
                before[owner] -= 1
            check_floor(before)
            check_floor_after_dedupe(
                before, {name: report.copied.get(name, 0) for name in before}
            )
        except BaseException:
            shutil.rmtree(partial, ignore_errors=True)
            raise
        input_manager.commit_dataset(partial, dataset)
        olog.status(f"Materialized {report.total} images into {dataset}")

    return copy


def _ingest_dataset(dataset: Path, names: list[str]) -> dict[str, list[Path]]:
    """Pre-flight and deduplicate ``--dataset`` in place, writing nothing.

    Unreadable files are excluded and listed; convertible formats are used as
    they stand; undersized images warn without being resized; byte-identical
    duplicates within a class are excluded from the run. Then the five-image
    floor, before and after deduplication.
    """
    organized = load_organized_dataset(dataset)
    unreadable: list[InPlaceReport] = []
    undersized = 0
    readable: dict[str, list[Path]] = {}
    for name in names:
        for path in organized.classes[name]:
            report = inspect_in_place(path)
            if not report.readable:
                unreadable.append(report)
                continue
            undersized += int(report.undersized)
            readable.setdefault(name, []).append(path)
        readable.setdefault(name, [])
    _report_unreadable(unreadable, "in the dataset")
    if undersized:
        them = 'they are' if undersized != 1 else 'it is'
        olog.warn(
            f"{undersized} image{'s are' if undersized != 1 else ' is'} smaller than "
            f"{SIZE_THRESHOLD}px and will be used as {them}.",
            why="--dataset is read in place, so nothing is resized; upscaled "
            "training inputs carry less detail than their size suggests.",
        )
    before = {name: len(paths) for name, paths in readable.items()}
    check_floor(before)
    unique: dict[str, list[Path]] = {}
    removed = 0
    for name, paths in readable.items():
        kept, duplicates = find_duplicates(paths)
        unique[name] = kept
        removed += len(duplicates)
    if removed:
        olog.status(
            f"{removed} duplicate image{'s' if removed != 1 else ''} left out of the run "
            "(the files are untouched)."
        )
    check_floor_after_dedupe(before, {name: len(p) for name, p in unique.items()})
    return unique


class _RichReporter:
    """Per-epoch progress bars and one status line per completed epoch."""

    def __init__(self) -> None:
        self._bar: Any = None
        self._context: Any = None

    def epoch_started(self, epoch: int, total: int, phase: int, batches: int) -> None:
        label = "head warmup" if phase == 1 else "fine-tune"
        self._context = progress_bar(f"Epoch {epoch}/{total} ({label})", total=batches)
        self._bar = self._context.__enter__()

    def batch_done(self) -> None:
        if self._bar is not None:
            self._bar.advance(self._bar.task_ids[0])

    def epoch_finished(self, metrics: EpochMetrics) -> None:
        if self._context is not None:
            self._context.__exit__(None, None, None)
            self._context = self._bar = None
        olog.status(
            f"  train loss {metrics.train_loss:.4f}  acc {metrics.train_accuracy:.3f}  "
            f"│ val loss {metrics.val_loss:.4f}  acc {metrics.val_accuracy:.3f}"
        )

    def close(self) -> None:
        if self._context is not None:
            self._context.__exit__(None, None, None)
            self._context = self._bar = None


def _train_body(
    state: GlobalState,
    resolved: ResolvedConfig,
    requested: list[str],
    *,
    dataset: Path,
    manifest: Path | None,
    output: Path,
    overwrite: bool,
) -> None:
    config = resolved.config
    project_root = Path.cwd()
    ckpt_root = project_root / checkpoints.CHECKPOINTS_DIR

    # --- Everything knowable before a question is asked. ------------------
    copy_manifest: Callable[[], None] | None = None
    if manifest is not None:
        copy_manifest = _materialize_manifest(
            state, manifest, dataset, overwrite=overwrite
        )
        names = sorted(parse_manifest(manifest).classes)
    else:
        names = sorted(load_organized_dataset(dataset).classes)
    subset = input_manager.compare_classes(requested, names) if requested else None
    # After the dataset checks, so a missing dataset is reported without the
    # seconds torch takes to import; before any question, so a missing stack is.
    import_torch_stack()
    _ensure_output(state, output)

    # --- Questions. --------------------------------------------------------
    resume = _resume_prompt(state, ckpt_root)
    housekeeping: Callable[[], None] = lambda: None  # noqa: E731
    if resume is None:
        housekeeping = _checkpoint_housekeeping(state, ckpt_root, config.max_checkpoints)
    if subset is not None:
        for line in subset.lines:
            olog.err_console.print(line)
        prompts.confirm_or_abort(
            subset.question,
            default=True,
            assume_yes=state.yes,
            non_interactive_fix="Re-run with --yes to train on the requested classes.",
        )
        names = sorted(requested)

    if copy_manifest is not None:
        copy_manifest()
    files = _ingest_dataset(dataset, names)

    if resume is not None:
        settings = TrainSettings.from_json(resume.info.get("config", {}))
        model_family = str(resume.info["model_family"])
        if sorted(resume.info.get("classes", [])) != sorted(files):
            raise OpticaTrainingError(
                "The dataset's classes no longer match the interrupted run.",
                why=f"Checkpoint: {', '.join(resume.info.get('classes', []))}. "
                f"Now: {', '.join(sorted(files))}.",
                fix="Answer n at the resume prompt to start a fresh run.",
            )
        if training_data_hash(dataset) != resume.info.get("training_data_hash"):
            raise OpticaTrainingError(
                "The dataset has changed since the interrupted run.",
                why="Resuming would re-split a different set of files under the same "
                "random_state, mixing training and validation images.",
                fix="Answer n at the resume prompt to start a fresh run.",
            )
        class_weights = bool(resume.info.get("class_weights_applied"))
        ignored = [
            flag
            for key, flag in resolved.flag_names.items()
            if resolved.sources.get(key) is Source.FLAG
        ]
        if ignored:
            olog.warn(
                f"Resuming with the interrupted run's settings; {', '.join(ignored)} "
                "ignored.",
                why="A resumed run continues the configuration it was started with.",
            )
    else:
        settings = _settings(config)
        model_family = config.default_model
        class_weights = _imbalance_prompt(state, files)
        warning = finetune_ratio_warning(settings.finetune_ratio)
        if warning:
            olog.warn(warning)
        if phase2_skipped_by_one_epoch(settings.epochs, settings.finetune_ratio):
            prompts.confirm_or_abort(
                "--epochs 1 leaves no epoch for fine-tuning, so Phase 2 is skipped. "
                "Continue?",
                default=True,
                assume_yes=state.yes,
                non_interactive_fix="Re-run with --yes to continue, or raise --epochs.",
            )

    device = select_device()
    if device.type == "cpu" and settings.batch_size > CPU_BATCH_LIMIT:
        smaller = 8
        olog.warn(
            f"Training on CPU with batch_size {settings.batch_size} may cause memory "
            "issues on modest hardware.",
            fix=f"Consider reducing: optica train --batch-size {smaller} or "
            f"optica config --set batch_size {smaller}",
        )
        prompts.confirm_or_abort(
            "Continue anyway? (n to adjust batch size)",
            default=True,
            category=prompts.PromptCategory.SAFETY,
            assume_yes=state.yes,
            force=state.force,
            non_interactive_error=OpticaTrainingError,
            non_interactive_fix="Re-run with --yes or --force to continue, or lower "
            "--batch-size.",
        )

    # --- Actions. ------------------------------------------------------------
    housekeeping()
    plan = TrainPlan(
        dataset_root=dataset,
        files=files,
        model_family=model_family,
        settings=settings,
        class_weights=class_weights,
        project_root=project_root,
        output=output,
        resume_from=resume,
    )
    olog.status(
        f"Training {model_family} on {sum(len(p) for p in files.values())} images "
        f"across {len(files)} classes ({_device_description(device)})"
    )
    reporter = _RichReporter()
    try:
        outcome = run_training(plan, reporter, device=device, on_status=olog.status)
    except TrainingInterrupted as interrupted:
        reporter.close()
        olog.incomplete(
            f"Training incomplete — interrupted at epoch {interrupted.at_epoch}/"
            f"{interrupted.total}; run optica train to continue from the last "
            "checkpoint."
        )
        raise typer.Exit(code=ExitCode.INTERRUPTED) from None
    finally:
        reporter.close()
    report_training(outcome, project_root)


CPU_BATCH_LIMIT = 16


def _device_description(device: Any) -> str:
    """Actual detected values, never internal shorthand."""
    if device.type == "cuda":
        import torch

        return f"CUDA GPU: {torch.cuda.get_device_name(device)}"
    if device.type == "mps":
        return "Apple silicon GPU (MPS)"
    return "CPU"


def _imbalance_prompt(state: GlobalState, files: dict[str, list[Path]]) -> bool:
    """The imbalance warning on a dataset the user brought: ``C``/``A`` only.

    Standalone ``optica train`` cannot fetch, so ``[F]`` is not offered. ``--yes``
    picks C. Returns whether class weighting was chosen.
    """
    counts = {name: len(paths) for name, paths in files.items()}
    imbalance = imbalanced_classes(counts)
    if imbalance is None:
        return False
    olog.warn("Class imbalance detected:")
    for name, count in imbalance.counts.items():
        olog.err_console.print(f"  {name}: {count} images")
    choice = prompts.choose(
        "Continue with automatic class weighting?",
        {"C": "Continue with auto class weighting", "A": "Abort"},
        default="C",
        assume_yes="C" if state.yes else None,
        non_interactive_error=OpticaTrainingError,
        non_interactive_fix="Re-run with --yes to continue with class weighting.",
    )
    if choice == "A":
        olog.incomplete("Training incomplete — aborted at the class-imbalance warning.")
        raise typer.Exit(code=ExitCode.ABORTED)
    return True


@classify_app.command()
def export(
    ctx: typer.Context,
    checkpoint_rank: list[str] | None = typer.Option(
        None,
        "--checkpoint-rank",
        "--checkpoint",
        help="Checkpoint rank(s) to export, comma-separated. Absence prompts.",
    ),
    output: str = typer.Option(
        "./optica-output",
        "--output",
        "-o",
        # A str, not a Path: Path drops the trailing slash that decides whether a
        # multi-component path is a container.
        help="Container folder for run outputs.",
    ),
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
    # Absence is *not* rank 1: it raises the checkpoint selection prompt, which
    # `--yes` answers with rank 1.
    values = split_values(checkpoint_rank)
    if state.dry_run:
        _export_dry_run(values, output)
        return
    with acquire_lock("optica export"):
        _export_body(state, values, output)


def _export_dry_run(values: list[str], output: str) -> None:
    """What ``optica export`` would write. No prompt, no torch, nothing written."""
    project_root = Path.cwd()
    ranked = export_manager.ranked_checkpoints(project_root)
    ranks = export_manager.parse_ranks(values, len(ranked)) if values else None
    olog.status("Checkpoints, best first:")
    for item in ranked:
        olog.status(_ranked_line(item))
    if ranks is None:
        olog.status("Rank: not given — the selection prompt would ask; --yes picks 1")
        ranks = [1]
    situation = export_manager.classify_output(output)
    olog.status(f"Output: {output} ({_SITUATION_TEXT[situation]})")
    moment = datetime.now().replace(microsecond=0)
    for rank in ranks:
        info = ranked[rank - 1].checkpoint.info
        name = export_manager.folder_name(
            str(info.get("model_family")),
            int(info.get("num_classes", 0)),
            moment,
            rank,
            with_rank=rank != 1 or len(ranks) > 1,
        )
        olog.status(
            f"  rank {rank} -> {name}/: model.pt, class_names.json, "
            "model_info.json, usage_examples.md"
        )
    olog.status("Dry run — nothing was exported or written.")


_SITUATION_TEXT: dict[export_manager.OutputSituation, str] = {
    export_manager.OutputSituation.CONTAINER: "existing folder",
    export_manager.OutputSituation.IS_FILE: "a file — this would be an error",
    export_manager.OutputSituation.CREATE: "does not exist — would ask to create it",
    export_manager.OutputSituation.NAME_OR_CONTAINER: (
        "does not exist — would ask: export name or container"
    ),
}


def _ranked_line(item: export_manager.Ranked) -> str:
    info = item.checkpoint.info
    test = info.get("test_accuracy")
    test_text = f"{test:.3f}" if isinstance(test, int | float) else "n/a"
    return (
        f"  {item.rank}  {item.checkpoint.path.name}   val_accuracy "
        f"{item.checkpoint.val_accuracy:.3f}   test_accuracy {test_text}   "
        f"run {item.checkpoint.run_id}"
    )


def _with_output(argv: list[str], value: str) -> str:
    """The invocation with ``--output`` set to ``value``, every other flag kept."""
    out: list[str] = []
    skip = False
    for arg in argv:
        if skip:
            skip = False
            continue
        if arg in ("--output", "-o"):
            skip = True
            continue
        if arg.startswith("--output="):
            continue
        out.append(arg)
    return "optica " + " ".join([*out, "--output", value])


def _resolve_export_output(state: GlobalState, raw: str) -> tuple[Path, str | None]:
    """``--output`` per the plan's table: ``(container, export name or None)``.

    Asked before anything is written.
    """
    situation = export_manager.classify_output(raw)
    path = Path(raw)
    if situation is export_manager.OutputSituation.IS_FILE:
        raise OpticaValidationError(
            f"--output {raw} is a file, not a folder.",
            why="--output is the container for run outputs.",
            fix=_with_output(state.argv, "./optica-output"),
        )
    if situation is export_manager.OutputSituation.CREATE:
        prompts.confirm_or_abort(
            f"--output {raw} does not exist. Create it?",
            default=True,
            assume_yes=state.yes,
            non_interactive_fix="Re-run with --yes to create it.",
        )
        workspace.create_ignored(path)
    elif situation is export_manager.OutputSituation.NAME_OR_CONTAINER:
        as_container = raw.rstrip("/" + chr(92)) + "/"
        if state.yes or not prompts.is_interactive():
            raise OpticaValidationError(
                f"--output {raw} does not exist, and it could name a folder to create "
                "or the export itself.",
                why="Several path components with no trailing slash are ambiguous, and "
                "--yes cannot choose between two different results.",
                fix=[
                    "To create it as a container, add a trailing slash:",
                    _with_output(state.argv, as_container),
                    f"To use {path.name} as the export's name inside {path.parent}, run "
                    "without --yes in a terminal and answer N.",
                ],
            )
        choice = prompts.choose(
            f"--output {raw} does not exist.",
            {
                "N": f"Name — export as {path.name}/ inside {path.parent}/",
                "C": f"Container — create {raw} and export into it",
                "A": "Abort",
            },
            default="C",
        )
        if choice == "A":
            raise typer.Exit(code=ExitCode.ABORTED)
        if choice == "N":
            workspace.create_ignored(path.parent)
            export_manager.require_writable(path.parent)
            return path.parent, path.name
        workspace.create_ignored(path)
    export_manager.require_writable(path)
    return path, None


def _selection_prompt(
    state: GlobalState, ranked: list[export_manager.Ranked]
) -> list[int]:
    """The export checkpoint selection prompt. ``--yes`` picks rank 1.

    Accepts several ranks, comma-separated; an invalid answer is explained and
    asked again.
    """
    if state.yes:
        return [1]
    if not prompts.is_interactive():
        raise OpticaValidationError(
            "Which checkpoint to export needs an answer, and there is no terminal to "
            "ask on.",
            why="Without --checkpoint-rank, optica export asks which checkpoint to use.",
            fix=[
                "Name the rank: " + _with_rank(state.argv, "1"),
                "or re-run with --yes to export rank 1.",
            ],
        )
    olog.err_console.print("Checkpoints, best first:")
    for item in ranked:
        olog.err_console.print(_ranked_line(item))
    while True:
        answer: str = typer.prompt(
            "Export which checkpoint? Rank, or several comma-separated", default="1"
        )
        try:
            return export_manager.parse_ranks(split_values([answer]), len(ranked))
        except OpticaValidationError as exc:
            for line in [exc.message, *exc.fix]:
                olog.err_console.print(f"  {line}")


def _with_rank(argv: list[str], value: str) -> str:
    return "optica " + " ".join([*argv, "--checkpoint-rank", value])


def _export_body(state: GlobalState, values: list[str], raw_output: str) -> None:
    project_root = Path.cwd()
    # --- Everything knowable before a question is asked. ------------------
    ranked = export_manager.ranked_checkpoints(project_root)
    ranks = export_manager.parse_ranks(values, len(ranked)) if values else None
    import_torch_stack()

    # --- Questions. --------------------------------------------------------
    container, export_name = _resolve_export_output(state, raw_output)
    if ranks is None:
        ranks = _selection_prompt(state, ranked)

    for rank in ranks:
        item = ranked[rank - 1]
        for stale in export_manager.stale_checkpoint_paths(item.checkpoint, project_root):
            olog.warn(
                f"Checkpoint path no longer exists: {stale}",
                why="It may have been archived or deleted. Check "
                f"{checkpoints.CHECKPOINTS_DIR}/{checkpoints.ARCHIVE_DIR}/",
            )
        if export_manager.missing_run_end(item.checkpoint):
            olog.warn(
                f"{item.checkpoint.path.name} is from a run that did not finish.",
                why="epochs_trained and early_stopped are written at run end, so "
                "model_info.json records them as null.",
            )

    # --- Actions. ------------------------------------------------------------
    for removed in export_manager.clean_stale_partials(container):
        olog.detail(f"Removed an interrupted export: {removed.name}")
    moment = datetime.now().replace(microsecond=0)
    records = []
    for rank in ranks:
        item = ranked[rank - 1]
        with_rank = rank != 1 or len(ranks) > 1
        if export_name is not None:
            base = f"{export_name}_ckpt{rank}" if with_rank else export_name
        else:
            base = export_manager.folder_name(
                str(item.checkpoint.info.get("model_family")),
                int(item.checkpoint.info.get("num_classes", 0)),
                moment,
                rank,
                with_rank=with_rank,
            )
        name = export_manager.unique_name(container, base)
        records.append(
            export_manager.export_checkpoint(
                item,
                of=len(ranked),
                container=container,
                name=name,
                moment=moment,
                project_root=project_root,
            )
        )
    for record in records:
        olog.success(
            f"Export complete — rank {record.rank} of {len(ranked)} to {record.folder}"
        )
        olog.status(f"  Files: {', '.join(record.files)}")


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
    if clip_threshold is not None:
        # The plan's own messages for the three hard-error bands, per command.
        # Config load would reject the same values, but with its generic range
        # error, and it runs first, so the flag is checked here before it.
        input_manager.check_clip_threshold(clip_threshold, command="run")
    if source is not None and source not in SOURCES:
        raise OpticaValidationError(
            f"--source {source} is not a known source.",
            options=list(SOURCES),
            default="open-datasets",
        )
    resolved = state.config(
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
    local = input_manager.require_single_input_source(folder, manifest)
    resolved_mode = input_manager.resolve_mode(
        command="run",
        explicit=mode,
        configured=_configured(resolved, "default_mode"),
        local_input=local is not input_manager.InputSource.FETCH,
        argv=state.argv,
    )
    olog.status(resolved_mode.line)
    names = split_values(classes)
    rank = _single_rank(split_values(checkpoint_rank))
    explicit_dataset = _dataset_explicit(state.argv)
    if state.dry_run:
        _run_dry_run(
            state,
            classes,
            names,
            resolved_mode=resolved_mode,
            folder=folder,
            manifest=manifest,
            dataset=dataset,
            dataset_explicit=explicit_dataset,
            output=output,
        )
        return
    with acquire_lock("optica run"):
        _run_body(
            state,
            resolved,
            classes,
            names,
            resolved_mode=resolved_mode,
            folder=folder,
            manifest=manifest,
            dataset=dataset,
            dataset_explicit=explicit_dataset,
            output=output,
            rank=rank,
            overwrite=overwrite,
            source=source,
            images_per_class=images_per_class,
            clip_threshold=clip_threshold,
            model=model,
        )


def _single_rank(values: list[str]) -> int | None:
    """``run`` exports one checkpoint, so it takes one rank.

    `RunResult` carries a single `ExportResult`, which is what makes several
    ranks a question for standalone ``optica export`` rather than for ``run``.
    """
    if not values:
        return None
    ranks = export_manager.parse_ranks(values, available=len(values) + 1)
    if len(ranks) > 1:
        raise OpticaValidationError(
            f"optica run exports one checkpoint; {len(ranks)} ranks were given.",
            why="A run produces one model, and its result carries one export.",
            fix=[
                "Run the pipeline, then export the others:",
                "optica export --checkpoint-rank " + ",".join(values),
            ],
        )
    return ranks[0]


def _dataset_explicit(argv: Sequence[str]) -> bool:
    """Whether ``--dataset`` was actually written on the command line.

    The acquisition short-circuit turns on an **explicit** ``--dataset``; a bare
    ``./dataset/`` never triggers it, so the default cannot be read back off the
    resolved value.
    """
    return any(
        arg in ("--dataset", "-d") or arg.startswith("--dataset=") for arg in argv
    )


def _run_classes(
    state: GlobalState,
    classes: list[str] | None,
    names: list[str],
    *,
    start: pipeline.Step,
) -> list[str]:
    """``run`` resolves ``-c`` the way ``fetch`` does — where acquisition runs.

    Prompting where a prompt can fire, hard-erroring where one cannot. A run
    that resumes at training or export takes its classes from the dataset, so
    the requirement does not apply to it.
    """
    if start in (pipeline.Step.FETCH, pipeline.Step.REVIEW):
        return _resolve_classes(classes, "run", state)
    return names


def _run_dry_run(
    state: GlobalState,
    classes: list[str] | None,
    names: list[str],
    *,
    resolved_mode: input_manager.ResolvedMode,
    folder: Path | None,
    manifest: Path | None,
    dataset: Path,
    dataset_explicit: bool,
    output: Path,
) -> None:
    """The resolved plan, rendered. Every value in it is the API's."""
    session = pipeline.inspect_session(
        dataset=dataset,
        project_root=Path.cwd(),
        output=output,
        mode=resolved_mode.mode,
    )
    start = session.resume_from if session.found else pipeline.Step.FETCH
    names = _run_classes(state, classes, names, start=start)
    result = api.run(
        names,
        mode=resolved_mode.mode,
        folder=folder,
        manifest=manifest,
        dataset=dataset if dataset_explicit else None,
        output=output,
        dry_run=True,
    )
    plan = result.plan or {}
    shown = ", ".join(plan.get("classes", [])) or "(from the dataset)"
    olog.status(f"Classes: {shown}")
    olog.status(f"Destination: {plan.get('destination')}")
    if plan.get("short_circuit"):
        olog.status("Acquisition: skipped — --dataset names an organized dataset")
    olog.status(f"Starts at: {plan.get('start_at')}")
    olog.status("Dry run — nothing was fetched, trained or written.")


def _run_body(
    state: GlobalState,
    resolved: ResolvedConfig,
    classes: list[str] | None,
    names: list[str],
    *,
    resolved_mode: input_manager.ResolvedMode,
    folder: Path | None,
    manifest: Path | None,
    dataset: Path,
    dataset_explicit: bool,
    output: Path,
    rank: int | None,
    overwrite: bool,
    source: str | None,
    images_per_class: int | None,
    clip_threshold: float | None,
    model: str | None,
) -> None:
    """Ask the top-level resumption question, then hand the pipeline over.

    Every stage decision — the sequence, the resume point, the per-stage
    warnings and the completion lines — belongs to :func:`optica.run`. What is
    here is the part the API cannot have: the prompt.
    """
    config = resolved.config
    _ensure_output(state, output)
    start = _resume_choice(state, dataset, output, resolved_mode.mode)
    names = _run_classes(
        state, classes, names, start=start or pipeline.Step.FETCH
    )
    api.run(
        names,
        mode=resolved_mode.mode,
        folder=folder,
        manifest=manifest,
        dataset=dataset if dataset_explicit else None,
        model=model,
        output=output,
        checkpoint_rank=rank,
        overwrite=overwrite,
        start_at=start.value if start is not None else None,
        fetch_config=api.FetchConfig(
            source=source,
            images_per_class=images_per_class,
            clip_threshold=clip_threshold,
            max_open_datasets_per_class=config.max_open_datasets_per_class,
            curation_port=config.curation_port,
            curation_timeout_minutes=config.curation_timeout_minutes,
        ),
        train_config=api.TrainConfig(
            epochs=_flag_value(resolved, "epochs"),
            batch_size=_flag_value(resolved, "batch_size"),
            augmentation=_flag_value(resolved, "augmentation"),
        ),
        export_config=api.ExportConfig(checkpoint_rank=rank),
    )


def _flag_value(resolved: ResolvedConfig, key: str) -> Any:
    """A config value only where a flag set it, so the API resolves the rest."""
    if resolved.sources.get(key) is Source.FLAG:
        return getattr(resolved.config, key)
    return None


def _resume_choice(
    state: GlobalState, dataset: Path, output: Path, mode: str
) -> pipeline.Step | None:
    """The top-level R/C/S prompt. None means *start at the top*.

    Fires only when a previous session left something behind. ``--yes`` picks
    **R**, so the discard confirmation under **C** never arises unattended.
    """
    project_root = Path.cwd()
    session = pipeline.inspect_session(
        dataset=dataset, project_root=project_root, output=output, mode=mode
    )
    if not session.found:
        return None
    marks = olog.markers_for(olog.err_console)
    olog.err_console.print("Previous session found:")
    for status in session.steps:
        if status.state is pipeline.StepState.NOT_STARTED:
            continue
        glyph = marks.ok if status.state is pipeline.StepState.COMPLETE else marks.fail
        line = f"{session.name_of(status.step)} {status.state.value}"
        if status.detail:
            line += f" — {status.detail}"
        olog.err_console.print(f"  {glyph} {line}")
    resume = session.resume_from
    choice = prompts.choose(
        f"Resume from last completed step ({session.name_of(resume).lower()})?",
        {"R": "Resume", "C": "Choose step", "S": "Start fresh"},
        default="R",
        assume_yes="R" if state.yes else None,
        non_interactive_fix="Re-run with --yes to resume it.",
    )
    if choice == "R":
        return resume
    if choice == "S":
        listing = input_manager.clear_staging()
        if not listing.empty:
            olog.status(f"Cleared {len(listing.lines)} staging entries.")
        return pipeline.Step.FETCH
    return _step_selector(session, dataset, output, project_root)


_STEP_KEYS: Final[dict[str, pipeline.Step]] = {
    "F": pipeline.Step.FETCH,
    "C": pipeline.Step.REVIEW,
    "T": pipeline.Step.TRAIN,
    "E": pipeline.Step.EXPORT,
}


def _step_selector(
    session: pipeline.SessionState,
    dataset: Path,
    output: Path,
    project_root: Path,
) -> pipeline.Step:
    """**C** — the four steps with their status; an unusable one says why.

    A step whose inputs are absent is **listed but not offered**, with its
    reason. Choosing a step earlier than the last completed one discards the
    later steps' staging, behind a confirmation; declining returns here rather
    than ending the run, the same shape the mass-rejection prompt uses.
    """
    while True:
        options: dict[str, str] = {}
        for key, offered in _STEP_KEYS.items():
            status = session.of(offered)
            name = session.name_of(offered)
            if status.selectable:
                options[key] = f"{name} — {status.state.value}"
            else:
                olog.err_console.print(
                    f"  {name} — {status.state.value}, not available: {status.blocked}"
                )
        choice = prompts.choose(
            "Which step should the run start at?",
            options,
            default=next(iter(options)),
            non_interactive_fix="Re-run with --yes to resume instead.",
        )
        step: pipeline.Step = _STEP_KEYS[choice]
        later = [
            session.of(after)
            for after in pipeline.steps_after(step)
            if session.of(after).state is not pipeline.StepState.NOT_STARTED
        ]
        if not later:
            return step
        # Asked before anything is removed: re-running an earlier step
        # invalidates what followed it, and the removal is the user's to allow.
        olog.err_console.print("Re-running this step invalidates what followed it:")
        for status in later:
            olog.err_console.print(
                f"  {session.name_of(status.step)} — {status.detail}"
            )
        if not prompts.confirm(
            "Remove them and start there? (n to choose again)",
            default=False,
            category=prompts.PromptCategory.DESTRUCTIVE,
        ):
            continue
        for line in pipeline.discard_after(
            step, dataset=dataset, project_root=project_root, output=output
        ):
            olog.status(f"  Removed {line}")
        return step
