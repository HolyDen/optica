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

Stage bodies that belong to later passes still raise :func:`_not_yet`: the
browser (``label``, ``curate``) in pass 3, training and export in pass 4, and
``run``'s sequencing in pass 5. Pass 2 adds the preconditions those commands
check before their stage begins.
"""

from __future__ import annotations

import math
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import typer

from optica.cli import GlobalState, get_state, split_values
from optica.config.defaults import MODELS, MODES, SOURCES
from optica.config.manager import ResolvedConfig, Source
from optica.config.schema import OpticaConfig
from optica.exceptions import (
    ExitCode,
    OpticaCurationError,
    OpticaError,
    OpticaValidationError,
)
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
    InPlaceReport,
    check_floor,
    check_floor_after_dedupe,
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
from optica.utils import logging as olog
from optica.utils import prompts
from optica.utils.lockfile import acquire_lock
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


def _not_yet(stage: str) -> OpticaError:
    """Return the error a not-yet-built stage raises.

    Each stage's body lands in its own pass. The message is a plain statement
    rather than an apology, and it exits ``1`` like any other
    :class:`~optica.exceptions.OpticaError`. ``options`` is not used: that field
    lists a fixed-value flag's valid values, and borrowing it for a build note
    would put the wrong thing under "Valid options".
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
    with acquire_lock("optica run"):
        split_values(classes)
        split_values(checkpoint_rank)
        raise _not_yet("optica run")
