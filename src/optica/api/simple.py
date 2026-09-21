"""The Simple API (Tier 3) and Python API (Tier 4).

Implements plan § "Python API" → *Simple API (Tier 3) and Python API (Tier 4)*,
*Result types*, and the import-time contract; § "`optica run` resumption and
preconditions" for the sequencing `run` performs.

Three rules shape everything here, and they are the difference between this
layer and the CLI:

* **Prompts live in the CLI layer only.** This module never reads stdin. Every
  prompt site resolves one of three ways — *defaultable* takes the `--yes`
  table's own answer, *destructive* raises unless the caller passed
  ``overwrite=True``, and *not defaultable* (the blocklist definition prompt)
  raises `OpticaValidationError`.
* **Warnings become structured results and Python warnings, from one source.**
  Every warning the CLI would print is recorded on the result, and
  ``warnings.warn`` is emitted **from those entries** under `OpticaWarning`.
  One source, two surfaces, so they cannot diverge.
* **The stage boundary governs the API identically.** A function accepts only
  input its own stage can act on; `run` is the only one that sequences a stage
  into the next.

Nothing here reconfigures the caller's streams: `protect_streams` is the CLI
entry point's, never the API's.
"""

from __future__ import annotations

import math
import shutil
import warnings as _warnings
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from optica.config.defaults import MODELS, MODES, SOURCES
from optica.config.manager import ConfigManager, ResolvedConfig
from optica.config.schema import OpticaConfig
from optica.exceptions import (
    OpticaError,
    OpticaTrainingError,
    OpticaValidationError,
    OpticaWarning,
)
from optica.export import manager as export_manager
from optica.input import clip as clip_adapter
from optica.input import manager as input_manager
from optica.input.classes import (
    Overlap,
    ResolvedClass,
    is_blocklisted,
    normalize_class_names,
    resolve_auto_classes,
)
from optica.input.curation import (
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
    load_organized_dataset,
    parse_manifest,
    preflight,
    require_flat_folder,
)
from optica.input.sessions import LabelingSession, SourceType, load_labeling, staging_root
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
from optica.pipeline import ORDER, Step, inspect_session, steps_from
from optica.training import checkpoints
from optica.training.engine import (
    finetune_ratio_warning,
    phase2_skipped_by_one_epoch,
)
from optica.training.splits import training_data_hash
from optica.training.trainer import TrainOutcome, TrainPlan, TrainSettings
from optica.training.trainer import train as run_training
from optica.utils import logging as olog
from optica.utils import workspace
from optica.utils.lockfile import acquire_lock
from optica.utils.mlstack import import_torch_stack, select_device

if TYPE_CHECKING:  # pragma: no cover - typing only, never a runtime import
    from optica.input.curation import CurationView

__all__ = [
    "CPU_BATCH_LIMIT",
    "ExportConfig",
    "ExportResult",
    "FetchConfig",
    "FetchResult",
    "OpticaResult",
    "RunResult",
    "TrainConfig",
    "TrainResult",
    "WarningCode",
    "WarningEntry",
    "curate",
    "export",
    "fetch",
    "label",
    "report_training",
    "run",
    "train",
]


# ------------------------------------------------------------ result types


class WarningCode:
    """Every warning code the API emits.

    **Codes are stable API surface** — renaming one is a breaking change, which
    is why they are gathered here rather than written as literals at the point
    each is raised. Each names *what is true*, in the shape the plan's own two
    examples use (``class_imbalance``, ``low_resolution``): the subject and its
    condition, never the command that happened to surface it.
    """

    CLASS_IMBALANCE: Final = "class_imbalance"
    """A class holds under half the largest class's images."""

    LOW_RESOLUTION: Final = "low_resolution"
    """Images below the 128px size threshold were upscaled, or used as they are."""

    UNREADABLE_IMAGES: Final = "unreadable_images"
    """Files that could not be decoded were left out of the run."""

    CLASS_OVERLAP: Final = "class_overlap"
    """One class name is a substring of another, so their images may mix."""

    SOFT_CAP: Final = "soft_cap"
    """``images_per_class`` is above the Open Images courtesy limit."""

    CLIP_THRESHOLD: Final = "clip_threshold"
    """``clip_threshold`` is in a band the CLI would have warned or prompted on."""

    CLIP_SHORTFALL: Final = "clip_shortfall"
    """Fewer images than requested passed CLIP filtering."""

    INCOMPLETE_FETCH: Final = "incomplete_fetch"
    """Curation is running over a class whose fetch did not finish."""

    EXTRA_STAGED_CLASSES: Final = "extra_staged_classes"
    """Staging holds classes this call did not ask for; curation will show them."""

    LOW_SELECTION: Final = "low_selection"
    """A class finished curation under the low-selection thresholds."""

    CPU_BATCH_SIZE: Final = "cpu_batch_size"
    """Training on CPU at a batch size that may exhaust memory."""

    FINETUNE_RATIO: Final = "finetune_ratio"
    """``finetune_ratio`` is at an extreme, or one epoch leaves no Phase 2."""

    CHECKPOINT_SOFT_LIMIT: Final = "checkpoint_soft_limit"
    """More checkpoints are kept than ``3 x max_checkpoints``."""

    RESUME_SETTINGS_IGNORED: Final = "resume_settings_ignored"
    """A resumed run keeps the interrupted run's settings; arguments are ignored."""

    CHECKPOINT_RUN_INCOMPLETE: Final = "checkpoint_run_incomplete"
    """The exported checkpoint's run never finished.

    ``epochs_trained`` and ``early_stopped`` are written at run end, so
    ``model_info.json`` records them as ``null``. Chosen over
    ``interrupted_checkpoint`` (which would assert a cause the check does not
    establish — a crash leaves the same state), ``incomplete_run`` (which
    collides with :func:`run` in this same namespace), and ``missing_run_end``
    (the detector's own function name, which is mechanism rather than
    condition). See ``notes/build-log.md``.
    """

    STALE_CHECKPOINT_PATH: Final = "stale_checkpoint_path"
    """A path in the run's log no longer exists — archived or deleted."""


@dataclass(frozen=True)
class WarningEntry:
    """One warning, in the form a caller can branch on.

    Attributes:
        code: A stable identifier from :class:`WarningCode`. What makes the
            entry branchable.
        message: The sentence the CLI prints. ``warnings.warn`` renders this,
            so the two surfaces cannot diverge.
        context: The values that produced it — class names, counts, paths. What
            makes the entry actionable.
    """

    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class OpticaResult:
    """The base every result carries. Never returned directly.

    Attributes:
        warnings: Every warning the CLI would have printed.
        dry_run: True when nothing was written.
        plan: The resolved decisions. Populated only when ``dry_run``.
    """

    warnings: list[WarningEntry] = field(default_factory=list)
    dry_run: bool = False
    plan: dict[str, Any] | None = None


@dataclass
class FetchResult(OpticaResult):
    """What `fetch`, `label` and `curate` return.

    Attributes:
        classes: The classes the call resolved.
        counts: Images delivered per class, post-filter.
        source: The fetch source, or None where nothing was fetched.
        mode: The resolved mode.
        dataset_path: Where images landed, or None where they stayed in staging.
    """

    classes: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    source: str | None = None
    mode: str | None = None
    dataset_path: Path | None = None


@dataclass
class TrainResult(OpticaResult):
    """What `train` returns.

    Everything the terminal completion block reports comes from here — one
    computation feeding both surfaces. Under ``dry_run`` every outcome field is
    None.

    Attributes:
        best_checkpoint: The rank-1 checkpoint folder.
        best_val_accuracy: Its validation accuracy.
        test_accuracy: Its test accuracy, None where no class had a test image.
        test_loss: Its test loss, likewise.
        epochs_run: Epochs completed.
        epochs_requested: Epochs asked for.
        early_stopped: **Copied from the training loop's own flag**, never
            derived from ``epochs_run < epochs_requested``: each phase has its
            own early-stopping window, so a completed run whose Phase 1 stopped
            early ends short of ``epochs`` with ``early_stopped`` False.
        phases: The allocation the rounding rule produced.
        checkpoints: Retained checkpoint folders, best first.
        log_paths: The global copy, then the project-local one.
    """

    best_checkpoint: Path | None = None
    best_val_accuracy: float | None = None
    test_accuracy: float | None = None
    test_loss: float | None = None
    epochs_run: int | None = None
    epochs_requested: int | None = None
    early_stopped: bool | None = None
    phases: tuple[int, int] | None = None
    checkpoints: list[Path] | None = None
    log_paths: list[Path] | None = None


@dataclass
class ExportResult(OpticaResult):
    """What `export` returns.

    Attributes:
        export_folder: The folder written. The first, where several ranks were
            exported.
        files: File names inside it.
        checkpoint_rank: The rank exported.
    """

    export_folder: Path | None = None
    files: list[str] = field(default_factory=list)
    checkpoint_rank: int | None = None


@dataclass
class RunResult(OpticaResult):
    """What `run` returns: the stage results, None for stages that did not run.

    Attributes:
        fetch: The acquisition stage's result.
        train: The training stage's result.
        export: The export stage's result.
    """

    fetch: FetchResult | None = None
    train: TrainResult | None = None
    export: ExportResult | None = None


# ----------------------------------------------------------- config objects


@dataclass(frozen=True)
class FetchConfig:
    """Tier 5's acquisition settings. Every field ``None`` means *unset*.

    Config-object fields tune *how*; what a call operates on — ``classes``,
    ``folder``, ``manifest``, ``dataset``, ``mode``, ``overwrite`` — are method
    arguments even where they are config-backed.
    """

    source: str | None = None
    images_per_class: int | None = None
    clip_threshold: float | None = None
    max_open_datasets_per_class: int | None = None
    curation_port: int | None = None
    curation_timeout_minutes: int | None = None


@dataclass(frozen=True)
class TrainConfig:
    """Tier 5's training settings — **exactly eleven fields**.

    The same eleven the artifact ``config`` block carries in
    ``checkpoint_info.json`` and ``model_info.json``, so the object a caller
    passes and the block that ships describe the same run. ``--no-augmentation``
    maps to ``augmentation=False``, per the negative-flag rule; ``--model`` and
    ``--output`` are **constructor** arguments on `Classifier`, not fields here,
    being settings every operation shares.
    """

    epochs: int | None = None
    batch_size: int | None = None
    learning_rate: float | None = None
    augmentation: bool | None = None
    early_stopping: int | None = None
    finetune_ratio: float | None = None
    optimizer: str | None = None
    max_checkpoints: int | None = None
    train_split: float | None = None
    val_split: float | None = None
    test_split: float | None = None


@dataclass(frozen=True)
class ExportConfig:
    """Tier 5's export settings.

    ``checkpoint_rank`` with **no ``checkpoint`` alias**: the CLI keeps that
    alias to protect surface users already depend on, while this object ships in
    V1 with no legacy to preserve.
    """

    checkpoint_rank: int | None = None


# ------------------------------------------------------------- collection


class _Collector:
    """Gathers warnings, then emits them once from their own entries."""

    def __init__(self) -> None:
        self.entries: list[WarningEntry] = []

    def add(self, code: str, message: str, /, **context: Any) -> None:
        """Record a warning and print it, exactly as the CLI would."""
        self.entries.append(WarningEntry(code, message, context))
        olog.warn(message)

    def extend(self, entries: Sequence[WarningEntry]) -> None:
        """Adopt another stage's entries, in invocation order."""
        self.entries.extend(entries)

    def emit(self) -> list[WarningEntry]:
        """Raise every entry as a Python warning and return them.

        ``warnings.warn`` is emitted **from the entries**, so a caller who never
        inspects the result still sees the quality signals, and one who does can
        branch on ``code`` rather than on an English sentence.
        """
        for entry in self.entries:
            _warnings.warn(entry.message, OpticaWarning, stacklevel=3)
        return list(self.entries)


@contextmanager
def _verbosity(verbose: bool) -> Iterator[None]:
    """Apply ``verbose=`` for one call and put the level back afterwards.

    The CLI's three levels collapse into the API's two: ``verbose=True`` is the
    default level, ``verbose=False`` is ``--quiet``. What a caller cannot
    express is ``--verbose``'s extra detail — stated, not resolved.

    The level is restored because this is a library: a call that left the
    process quieter than it found it would be a side effect nobody asked for.
    """
    previous = olog.get_verbosity()
    olog.set_verbosity(olog.Verbosity.NORMAL if verbose else olog.Verbosity.QUIET)
    try:
        yield
    finally:
        olog.set_verbosity(previous)


def _resolve_config(
    overrides: dict[str, object], names: dict[str, str]
) -> ResolvedConfig:
    """Resolve configuration, naming parameters where the CLI names flags."""
    return ConfigManager().resolve(overrides=overrides, flag_names=names)


def _fetch_overrides(
    config: FetchConfig | None,
    *,
    source: str | None,
    images_per_class: int | None,
    clip_threshold: float | None,
    mode: str | None,
) -> tuple[dict[str, object], dict[str, str]]:
    config = config or FetchConfig()
    values: dict[str, object] = {
        "default_source": source if source is not None else config.source,
        "images_per_class": images_per_class
        if images_per_class is not None
        else config.images_per_class,
        "clip_threshold": clip_threshold
        if clip_threshold is not None
        else config.clip_threshold,
        "default_mode": mode,
        "max_open_datasets_per_class": config.max_open_datasets_per_class,
        "curation_port": config.curation_port,
        "curation_timeout_minutes": config.curation_timeout_minutes,
    }
    names = {
        "default_source": "source",
        "images_per_class": "images_per_class",
        "clip_threshold": "clip_threshold",
        "default_mode": "mode",
        "max_open_datasets_per_class": "max_open_datasets_per_class",
        "curation_port": "curation_port",
        "curation_timeout_minutes": "curation_timeout_minutes",
    }
    return values, names


def _train_overrides(
    config: TrainConfig | None, model: str | None
) -> tuple[dict[str, object], dict[str, str]]:
    config = config or TrainConfig()
    values: dict[str, object] = {"default_model": model}
    names = {"default_model": "model"}
    for name in (
        "epochs",
        "batch_size",
        "learning_rate",
        "augmentation",
        "early_stopping",
        "finetune_ratio",
        "optimizer",
        "max_checkpoints",
        "train_split",
        "val_split",
        "test_split",
    ):
        values[name] = getattr(config, name)
        names[name] = name
    return values, names


def _check_choice(value: str | None, valid: Sequence[str], name: str) -> None:
    """Fixed-value parameters list their options, exactly as the flags do."""
    if value is not None and value not in valid:
        raise OpticaValidationError(
            f"{name}={value!r} is not a known {name}.",
            options=list(valid),
            default=valid[0] if name == "mode" else None,
        )


def _classes_of(raw: Sequence[str] | str | None) -> list[str]:
    """Accept a list or one comma-separated string, as the flag does."""
    if raw is None:
        return []
    values = [raw] if isinstance(raw, str) else list(raw)
    return [part.strip() for value in values for part in value.split(",") if part.strip()]


def _as_path(value: str | Path) -> Path:
    return value if isinstance(value, Path) else Path(value)


# ---------------------------------------------------------- class resolution


class _ApiClassPrompter:
    """The class sequence with nobody to ask.

    `define` is the sequence's one non-defaultable step, so it raises rather
    than prompting — naming the blocklisted class and that a concrete definition
    is required. Every other step takes the `--yes` table's own answer: group,
    continue past an overlap, confirm.
    """

    def __init__(self, collector: _Collector) -> None:
        self.collector = collector

    def define(self, name: str) -> list[str]:
        """Never prompts — the one prompt with no safe answer."""
        raise OpticaValidationError(
            f"'{name}' is too abstract to search for, and a concrete definition is "
            "required.",
            why="Auto modes need concrete, searchable, visual class names, and the "
            "Python API cannot ask what the term means mid-call.",
            fix=[
                "Name the sub-terms directly instead:",
                "optica.fetch(classes=['golden_retriever', 'poodle'])",
            ],
        )

    def group_or_separate(self, name: str, sub_terms: list[str]) -> bool:
        """Group — the ``--yes`` table's answer. Unreachable: `define` raised."""
        return True  # pragma: no cover - `define` raises before this is reached

    def accept_overlaps(self, overlaps: list[Overlap]) -> bool:
        """Y — continue, per the ``--yes`` table, with each overlap recorded."""
        for overlap in overlaps:
            self.collector.add(
                WarningCode.CLASS_OVERLAP,
                f"'{overlap.inner}' overlaps '{overlap.outer}'.",
                inner=overlap.inner,
                outer=overlap.outer,
            )
        return True

    def redefine_classes(self, current: list[str]) -> list[str]:
        """Unreachable: `accept_overlaps` never declines."""
        return list(current)  # pragma: no cover - never reached

    def confirm(self, classes: list[ResolvedClass], *, clean: bool) -> bool:
        """Confirmed. ``--yes`` skips the clean case and answers Y otherwise."""
        return True


# ------------------------------------------------------------------- fetch


def fetch(
    classes: Sequence[str] | str | None = None,
    *,
    mode: str | None = None,
    source: str | None = None,
    images_per_class: int | None = None,
    clip_threshold: float | None = None,
    dataset: str | Path = "dataset",
    overwrite: bool = False,
    dry_run: bool = False,
    verbose: bool = True,
    config: FetchConfig | None = None,
) -> FetchResult:
    """Fetch images for each class from a remote source.

    Args:
        classes: The class names. A list, or one comma-separated string.
        mode: ``curate`` (stage for review) or ``clip`` (filter and write
            ``dataset/``). ``label`` is a hard error: fetch is remote
            acquisition and label mode takes local input.
        source: ``open-datasets`` or ``flickr``.
        images_per_class: Images to collect per class.
        clip_threshold: The CLIP confidence threshold, for ``mode="clip"``.
        dataset: Where ``mode="clip"`` writes.
        overwrite: Required to replace a populated ``dataset/`` under
            ``mode="clip"``; without it a populated destination raises.
        dry_run: Resolve the plan and write nothing.
        verbose: False suppresses Rich output.
        config: Tier 5's settings object. Explicit arguments win over it.

    Returns:
        A :class:`FetchResult`.

    Raises:
        OpticaValidationError: A blocklisted class name, a bad parameter value,
            or a populated ``dataset/`` without ``overwrite=True``.
        OpticaCLIPError: ``mode="clip"``, or a blocklisted name under curate,
            with the clip extra missing.
    """
    collector = _Collector()
    with _verbosity(verbose):
        result = _fetch(
            collector,
            _classes_of(classes),
            mode=mode,
            source=source,
            images_per_class=images_per_class,
            clip_threshold=clip_threshold,
            dataset=_as_path(dataset),
            overwrite=overwrite,
            dry_run=dry_run,
        )
    result.warnings = collector.emit()
    return result


def _fetch(
    collector: _Collector,
    names: list[str],
    *,
    mode: str | None,
    source: str | None,
    images_per_class: int | None,
    clip_threshold: float | None,
    dataset: Path,
    overwrite: bool,
    dry_run: bool,
    config: FetchConfig | None = None,
) -> FetchResult:
    _check_choice(mode, ("curate", "clip"), "mode")
    _check_choice(source, SOURCES, "source")
    if clip_threshold is not None:
        input_manager.check_clip_threshold(clip_threshold, command="fetch")
    if not names:
        raise input_manager.missing_classes_error("fetch")
    overrides, flag_names = _fetch_overrides(
        config,
        source=source,
        images_per_class=images_per_class,
        clip_threshold=clip_threshold,
        mode=mode,
    )
    resolved = _resolve_config(overrides, flag_names)
    settings = resolved.config
    resolved_mode = input_manager.resolve_mode(
        command="fetch",
        explicit=mode,
        configured=_configured(resolved, "default_mode"),
        local_input=False,
    )
    names = normalize_class_names(names)
    blocklisted = [name for name in names if is_blocklisted(name)]
    clip_mode = resolved_mode.mode == "clip"
    if clip_mode:
        _clip_threshold_entry(collector, settings.clip_threshold)
    elif blocklisted:
        # The grouped path scores with CLIP after the fetch; membership is
        # knowable now, so the dependency is checked before quota is spent.
        input_manager.require_clip_extra()

    if dry_run:
        return FetchResult(
            dry_run=True,
            plan=_fetch_plan(settings, names, resolved_mode, dataset, blocklisted),
            classes=list(names),
            source=settings.default_source,
            mode=resolved_mode.mode,
        )

    if blocklisted:
        # Before any fetch begins, not when the sequence reaches the definition
        # step: `define` has no safe answer here, so the outcome is already
        # determined and nothing is gained by spending a request first.
        _ApiClassPrompter(collector).define(blocklisted[0])
    with acquire_lock("optica.fetch"):
        return _fetch_body(
            collector,
            names,
            resolved_mode.mode,
            settings,
            dataset,
            overwrite=overwrite,
        )


def _configured(resolved: ResolvedConfig, key: str) -> str | None:
    """The value only where a config file or the environment set it."""
    from optica.config.manager import Source

    if resolved.sources.get(key) in (Source.PROJECT, Source.GLOBAL, Source.ENV):
        return str(getattr(resolved.config, key))
    return None


def _fetch_plan(
    settings: OpticaConfig,
    names: list[str],
    resolved_mode: input_manager.ResolvedMode,
    dataset: Path,
    blocklisted: list[str],
) -> dict[str, Any]:
    """The four resolutions a caller cannot reproduce without duplicating logic."""
    return {
        "mode": resolved_mode.mode,
        "detection_order": resolved_mode.reason,
        "short_circuit": None,
        "destination": str(dataset)
        if resolved_mode.mode == "clip"
        else str(staging_root()),
        "classes": list(names),
        "source": settings.default_source,
        "images_per_class": settings.images_per_class,
        "needs_definition": blocklisted,
    }


def _clip_threshold_entry(collector: _Collector, value: float) -> None:
    """The seven bands, with nobody to answer the strict-end prompt.

    The three hard-error bands raise. The warn-and-continue bands and the
    strict-end prompt are both recorded and continued — ``--yes`` auto-confirms
    the first and auto-picks Y on the second, and the API behaves as though
    ``--yes`` were always passed.
    """
    check = input_manager.check_clip_threshold(value, command="fetch")
    input_manager.require_clip_extra()
    message = check.warning or check.prompt
    if message:
        collector.add(WarningCode.CLIP_THRESHOLD, message, clip_threshold=value)


def _fetch_body(
    collector: _Collector,
    names: list[str],
    mode: str,
    settings: OpticaConfig,
    dataset: Path,
    *,
    overwrite: bool,
) -> FetchResult:
    clip_mode = mode == "clip"
    if clip_mode:
        _require_free_destination(dataset, overwrite=overwrite)
    client = make_client()
    scorer: clip_adapter.ImageScorer | None = None
    try:
        context = SourceContext(
            client=client, api_key=settings.flickr_api_key, report=olog.status
        )
        source = create_source(settings.default_source, context)
        source.prepare([name for name in names if not is_blocklisted(name)])
        if settings.default_source == "open-datasets" and input_manager.soft_cap_exceeded(
            settings.images_per_class, settings.max_open_datasets_per_class
        ):
            collector.add(
                WarningCode.SOFT_CAP,
                f"images_per_class {settings.images_per_class} is above the Open "
                f"Images courtesy limit of {settings.max_open_datasets_per_class} "
                "per class.",
                images_per_class=settings.images_per_class,
                cap=settings.max_open_datasets_per_class,
            )
        _report_other_staged(collector, names)
        plan = resolve_auto_classes(
            names, settings.images_per_class, _ApiClassPrompter(collector)
        )
        source.prepare([query for cls in plan for query in cls.queries])
        if clip_mode or any(cls.grouped for cls in plan):
            scorer = clip_adapter.load_clip(report=olog.status, quiet=True)
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
        reports = [fetch_class(cls, source, downloader) for cls in fetch_plan]
        source_name = source.display_name
    finally:
        client.close()

    _report_fetch(collector, reports, final=scorer is None)
    if scorer is None:
        return FetchResult(
            classes=[cls.name for cls in plan],
            counts={report.name: report.staged for report in reports},
            source=source_name,
            mode=mode,
        )
    if clip_mode:
        counts = _clip_into_dataset(collector, plan, scorer, settings, dataset)
        olog.success(
            f"Fetch complete — {sum(counts.values())} images kept across "
            f"{len(counts)} classes in {dataset}"
        )
        return FetchResult(
            classes=[cls.name for cls in plan],
            counts=counts,
            source=source_name,
            mode=mode,
            dataset_path=dataset,
        )
    removed = _clip_grouped_staging(plan, scorer, settings.clip_threshold)
    counts = {
        report.name: report.staged - removed.get(report.name, 0) for report in reports
    }
    olog.success(
        f"Fetch complete — {sum(counts.values())} images across {len(counts)} classes"
    )
    return FetchResult(
        classes=[cls.name for cls in plan],
        counts=counts,
        source=source_name,
        mode=mode,
    )


def _require_free_destination(destination: Path, *, overwrite: bool) -> None:
    """The ``dataset/`` overwrite prompt: destructive, so it raises.

    ``--yes`` does not answer it on the CLI either — ``--overwrite`` is the only
    unattended route past it, and ``overwrite=True`` is its exact API
    counterpart.
    """
    if input_manager.destination_contents(destination) is None:
        return
    if overwrite:
        return
    raise OpticaValidationError(
        f"{destination} already exists and is not empty.",
        why="Continuing would replace it — the destination is overwritten, never "
        "merged into.",
        fix=[
            "Pass overwrite=True to replace it, or choose another destination:",
            f"optica.train(dataset='{destination}-new')",
        ],
    )


def _report_other_staged(collector: _Collector, names: Sequence[str]) -> None:
    requested = set(names)
    others = sorted({s.name for s in staged_classes() if s.name not in requested})
    if others:
        collector.add(
            WarningCode.EXTRA_STAGED_CLASSES,
            f"Staging also holds images for {', '.join(others)}, which curation "
            "will show.",
            classes=others,
        )


def _report_fetch(
    collector: _Collector, reports: Sequence[ClassFetchReport], *, final: bool = True
) -> None:
    """The completion block. ``final=False`` where CLIP filtering follows."""
    for report in reports:
        olog.status(f"  {report.name}: {report.staged} images")
    resized = sum(report.resized for report in reports)
    if resized:
        collector.add(
            WarningCode.LOW_RESOLUTION,
            f"{resized} fetched images were smaller than {SIZE_THRESHOLD}px and were "
            "upscaled.",
            count=resized,
        )
    if final:
        total = sum(report.staged for report in reports)
        olog.success(f"Fetch complete — {total} images across {len(reports)} classes")


def _clip_into_dataset(
    collector: _Collector,
    plan: Sequence[ResolvedClass],
    scorer: clip_adapter.ImageScorer,
    settings: OpticaConfig,
    dataset: Path,
) -> dict[str, int]:
    """Clip mode's ingest: score, keep the best, write ``dataset/`` atomically."""
    partial = input_manager.partial_destination(dataset)
    if partial.exists():
        shutil.rmtree(partial)
    counts: dict[str, int] = {}
    short: list[clip_adapter.ClipFilterReport] = []
    try:
        for cls in plan:
            report = _clip_score(scorer, cls, settings.clip_threshold, keep=cls.target)
            folder = partial / cls.name
            folder.mkdir(parents=True, exist_ok=True)
            seen: set[str] = set()
            written = 0
            for path in report.kept_paths:
                data = path.read_bytes()
                digest = md5_of(data)
                if digest in seen:
                    continue
                seen.add(digest)
                (folder / path.name).write_bytes(data)
                written += 1
            report.kept = written
            counts[cls.name] = written
            if report.shortfall:
                short.append(report)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    input_manager.commit_dataset(partial, dataset)
    for cls in plan:
        shutil.rmtree(staging_root() / cls.name, ignore_errors=True)
    if short:
        collector.add(
            WarningCode.CLIP_SHORTFALL,
            "Fewer images than requested passed CLIP filtering: "
            + ", ".join(f"{r.name} kept {r.kept} of {r.target}" for r in short)
            + ".",
            classes={r.name: r.kept for r in short},
        )
    return counts


def _clip_grouped_staging(
    plan: Sequence[ResolvedClass],
    scorer: clip_adapter.ImageScorer,
    threshold: float,
) -> dict[str, int]:
    """The grouped path under curate: filter each group's staging by its sub-terms."""
    removed: dict[str, int] = {}
    for cls in plan:
        if not cls.grouped:
            continue
        report = _clip_score(scorer, cls, threshold, keep=None)
        for path in report.rejected_paths:
            path.unlink(missing_ok=True)
        removed[cls.name] = len(report.rejected_paths)
    return removed


def _clip_score(
    scorer: clip_adapter.ImageScorer,
    cls: ResolvedClass,
    threshold: float,
    *,
    keep: int | None,
) -> clip_adapter.ClipFilterReport:
    images = staged_images(staging_root() / cls.name)
    prompts = [clip_adapter.prompt_for(query) for query in cls.queries]
    scores = scorer.score(images, prompts)
    return clip_adapter.select_survivors(
        cls.name, list(zip(images, scores, strict=True)), threshold, keep
    )


# ------------------------------------------------------------ label, curate


def label(
    classes: Sequence[str] | str | None = None,
    *,
    folder: str | Path | None = None,
    manifest: str | Path | None = None,
    dataset: str | Path = "dataset",
    overwrite: bool = False,
    verbose: bool = True,
    config: FetchConfig | None = None,
) -> FetchResult:
    """Label a flat folder or an unlabeled manifest in the browser.

    Blocks on a browser, not on stdin — the one thing this layer waits on a
    human for, and permitted: the rule forbids prompting on stdin, not opening
    the UI the call exists to open.

    Raises:
        OpticaValidationError: Neither or both of ``folder`` and ``manifest``,
            an input its stage cannot act on, or a populated ``dataset/``
            without ``overwrite=True``.
        OpticaWebError: The web extra is missing.
    """
    from optica.server.app import BrowserSession, IdleTimer, Outcome, load_web, serve
    from optica.server.labeling import LabelingController

    collector = _Collector()
    names = _classes_of(classes)
    with _verbosity(verbose):
        source = input_manager.require_single_input_source(
            _as_path(folder) if folder else None,
            _as_path(manifest) if manifest else None,
        )
        if source is input_manager.InputSource.FETCH:
            raise OpticaValidationError(
                "label needs a flat folder or a manifest to label.",
                why="Neither folder= nor manifest= was given.",
                fix=[
                    "optica.label(folder='./images', classes=['cat', 'dog'])",
                    "optica.label(manifest='./images.csv', classes=['cat', 'dog'])",
                ],
            )
        load_web()
        if not names:
            raise input_manager.missing_classes_error("label")
        target = _label_target(
            _as_path(folder) if folder else None,
            _as_path(manifest) if manifest else None,
        )
        overrides, flag_names = _fetch_overrides(
            config, source=None, images_per_class=None, clip_threshold=None, mode=None
        )
        settings = _resolve_config(overrides, flag_names).config
        destination = _as_path(dataset)
        with acquire_lock("optica.label"):
            _require_free_destination(destination, overwrite=overwrite)
            session = _labeling_session(target, names)
            readable, unreadable = preflight(target.files)
            _report_unreadable(collector, unreadable, "before labeling")
            controller = LabelingController(session, readable, unreadable)
            browser = BrowserSession(
                controller, IdleTimer(settings.curation_timeout_minutes)
            )
            outcome = serve(
                browser,
                configured_port=settings.curation_port,
                headline=f"Labeling {len(readable)} images",
            )
            _require_finished(outcome, Outcome, "Labeling")
            counts = _materialize_labels(collector, controller, destination, unreadable)
            olog.success(
                f"Labeling complete — {sum(counts.values())} images labeled across "
                f"{len(counts)} classes"
            )
    result = FetchResult(
        classes=sorted(counts),
        counts=counts,
        mode="label",
        dataset_path=destination,
    )
    result.warnings = collector.emit()
    return result


@dataclass(frozen=True)
class _LabelTarget:
    """What `label` labels: a flat folder, or an unlabeled manifest."""

    path: Path
    files: list[Path]
    source_type: SourceType
    content_hash: str | None = None


def _label_target(folder: Path | None, manifest: Path | None) -> _LabelTarget:
    if folder is not None:
        files = require_flat_folder(folder)
        return _LabelTarget(folder, [f.resolve() for f in files], SourceType.FOLDER)
    assert manifest is not None
    parsed = parse_manifest(manifest)
    parsed.require_unlabeled_for_label()
    return _LabelTarget(
        manifest,
        [row.path for row in parsed.rows],
        SourceType.MANIFEST,
        parsed.content_hash,
    )


def _labeling_session(target: _LabelTarget, names: list[str]) -> LabelingSession:
    """Resume, per the ``--yes`` table. Adopting is never automatic."""
    fresh = LabelingSession.new(
        None, target.path, target.source_type, names, target.content_hash
    )
    if not fresh.path.exists():
        return fresh
    return load_labeling(fresh.path)


def _require_finished(outcome: Any, outcomes: Any, stage: str) -> None:
    """A browser step that did not finish is an error, never a quiet return."""
    if outcome is outcomes.TIMED_OUT:
        raise OpticaError(
            f"{stage} incomplete — the session closed without activity; progress is "
            "saved.",
            fix="Call it again to resume.",
        )
    if outcome is outcomes.INTERRUPTED:
        raise KeyboardInterrupt(f"{stage} was interrupted; progress is saved.")


def _report_unreadable(
    collector: _Collector, reports: Sequence[InPlaceReport], when: str
) -> None:
    """User-provided files: listed individually with their reason, untouched."""
    if not reports:
        return
    count = len(reports)
    collector.add(
        WarningCode.UNREADABLE_IMAGES,
        f"{count} file{'s' if count != 1 else ''} could not be read {when} and "
        f"{'is' if count == 1 else 'are'} left out. The files are untouched.",
        count=count,
        reasons=reasons_summary(reports),
    )


def _materialize_labels(
    collector: _Collector,
    controller: Any,
    dataset: Path,
    unreadable: Sequence[InPlaceReport],
) -> dict[str, int]:
    items = controller.labeled_items()
    session = controller.session
    before = controller.counts()
    partial = input_manager.partial_destination(dataset)
    if partial.exists():
        shutil.rmtree(partial)
    report = copy_into_dataset(items, partial)
    try:
        _report_unreadable(collector, report.unreadable, "while copying")
        owners = {str(path): name for path, name in items}
        for bad in report.unreadable:
            before[owners[str(bad.path)]] -= 1
        check_floor(before)
        after = {name: report.copied.get(name, 0) for name in session.classes}
        check_floor_after_dedupe(before, after, resumable_session=True)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    input_manager.commit_dataset(partial, dataset)
    session.path.unlink(missing_ok=True)
    if report.resized:
        collector.add(
            WarningCode.LOW_RESOLUTION,
            f"{report.resized} images smaller than {SIZE_THRESHOLD}px were upscaled.",
            count=report.resized,
        )
    return {name: report.copied.get(name, 0) for name in session.classes}


def curate(
    *,
    dataset: str | Path = "dataset",
    overwrite: bool = False,
    verbose: bool = True,
    config: FetchConfig | None = None,
) -> FetchResult:
    """Review fetched images in the browser and keep the good ones.

    Takes no ``classes``: curation reviews the classes already fetched into
    staging.

    Raises:
        OpticaValidationError: Nothing is staged, or a populated ``dataset/``
            without ``overwrite=True``.
        OpticaWebError: The web extra is missing.
    """
    from optica.server.app import BrowserSession, IdleTimer, Outcome, load_web, serve
    from optica.server.curation import CurationController

    collector = _Collector()
    with _verbosity(verbose):
        load_web()
        overrides, flag_names = _fetch_overrides(
            config, source=None, images_per_class=None, clip_threshold=None, mode=None
        )
        settings = _resolve_config(overrides, flag_names).config
        destination = _as_path(dataset)
        with acquire_lock("optica.curate"):
            view = load_view()
            if view.incomplete:
                collector.add(
                    WarningCode.INCOMPLETE_FETCH,
                    f"The fetch for {', '.join(view.incomplete)} did not finish; "
                    "curating what was fetched.",
                    classes=list(view.incomplete),
                )
            _require_free_destination(destination, overwrite=overwrite)
            session = open_session()
            controller = CurationController(view, session, settings.images_per_class)
            browser = BrowserSession(
                controller, IdleTimer(settings.curation_timeout_minutes)
            )
            outcome = serve(
                browser,
                configured_port=settings.curation_port,
                headline=(
                    f"Curating {sum(view.fetched.values())} images across "
                    f"{len(view.images)} classes"
                ),
            )
            _require_finished(outcome, Outcome, "Curation")
            counts = _materialize_selection(
                collector, controller.view, session, destination
            )
            olog.success(
                f"Curation complete — {sum(counts.values())} images selected across "
                f"{len(counts)} classes"
            )
    result = FetchResult(
        classes=sorted(counts),
        counts=counts,
        mode="curate",
        dataset_path=destination,
    )
    result.warnings = collector.emit()
    return result


def _materialize_selection(
    collector: _Collector, view: CurationView, session: Any, dataset: Path
) -> dict[str, int]:
    """Write the selection, then delete what curation rejected, silently."""
    selected = selected_counts(view, session)
    for warning in selection_warnings(view.fetched, selected):
        # The mass-rejection prompt: `--yes` picks C, then Y — continue with the
        # selection as it stands.
        collector.add(
            WarningCode.LOW_SELECTION,
            warning.message,
            class_name=warning.class_name,
            trigger=str(warning.trigger),
        )
    partial = input_manager.partial_destination(dataset)
    if partial.exists():
        shutil.rmtree(partial)
    report = materialize_selection(view, session, partial)
    try:
        certified = {name: n for name, n in selected.items() if n >= HARD_FLOOR}
        after = {name: report.written.get(name, 0) for name in certified}
        check_floor_after_dedupe(certified, after)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    input_manager.commit_dataset(partial, dataset)
    for name, paths in view.images.items():
        for path in paths:
            if not session.is_selected(name, str(path)):
                path.unlink(missing_ok=True)
    session.path.unlink(missing_ok=True)
    return dict(report.written)


# ------------------------------------------------------------------- train


def train(
    classes: Sequence[str] | str | None = None,
    *,
    dataset: str | Path = "dataset",
    manifest: str | Path | None = None,
    model: str | None = None,
    output: str | Path = "optica-output",
    overwrite: bool = False,
    dry_run: bool = False,
    verbose: bool = True,
    config: TrainConfig | None = None,
) -> TrainResult:
    """Train on an organized dataset, or on a fully labeled manifest.

    ``classes`` is optional when ``dataset/`` already exists — the folder names
    are the source of truth — and required otherwise. A flat folder or a
    partially labeled manifest is a precondition error: labeling is another
    stage's work.

    Raises:
        OpticaTorchError: The torch stack is missing.
        OpticaValidationError: An input this stage cannot act on.
        OpticaTrainingError: The dataset, the resume state, or memory.
    """
    collector = _Collector()
    with _verbosity(verbose):
        result = _train(
            collector,
            _classes_of(classes),
            dataset=_as_path(dataset),
            manifest=_as_path(manifest) if manifest else None,
            model=model,
            output=_as_path(output),
            overwrite=overwrite,
            dry_run=dry_run,
            config=config,
        )
    result.warnings = collector.emit()
    return result


def _train(
    collector: _Collector,
    requested: list[str],
    *,
    dataset: Path,
    manifest: Path | None,
    model: str | None,
    output: Path,
    overwrite: bool,
    dry_run: bool,
    config: TrainConfig | None,
) -> TrainResult:
    _check_choice(model, MODELS, "model")
    overrides, flag_names = _train_overrides(config, model)
    resolved = _resolve_config(overrides, flag_names)
    settings = resolved.config
    project_root = Path.cwd()
    ckpt_root = project_root / checkpoints.CHECKPOINTS_DIR

    copy_manifest: Callable[[], None] | None = None
    if manifest is not None:
        copy_manifest = _materialize_manifest(
            collector, manifest, dataset, overwrite=overwrite
        )
        names = sorted(parse_manifest(manifest).classes)
    else:
        names = sorted(load_organized_dataset(dataset).classes)
    if requested:
        # The subset confirmation: `--yes` proceeds with the requested classes.
        input_manager.compare_classes(requested, names)
        names = sorted(requested)

    if dry_run:
        return TrainResult(
            dry_run=True,
            plan={
                "mode": "train",
                "detection_order": "manifest" if manifest else "dataset",
                "short_circuit": None,
                "destination": str(output),
                "classes": names,
                "model": settings.default_model,
                "epochs": settings.epochs,
            },
        )

    import_torch_stack()
    with acquire_lock("optica.train"):
        _ensure_output(output)
        resume = checkpoints.resumable(checkpoints.list_active(ckpt_root))
        if resume is None:
            _checkpoint_soft_limit(collector, ckpt_root, settings.max_checkpoints)
        if copy_manifest is not None:
            copy_manifest()
        files = _ingest_dataset(collector, dataset, names)
        train_settings, model_family, class_weights = _run_settings(
            collector, resolved, files, dataset, resume
        )
        _safety_checks(collector, train_settings)
        plan = TrainPlan(
            dataset_root=dataset,
            files=files,
            model_family=model_family,
            settings=train_settings,
            class_weights=class_weights,
            project_root=project_root,
            output=output,
            resume_from=resume,
        )
        outcome = run_training(plan)
    report_training(outcome, project_root)
    return _train_result(outcome)


def _train_result(outcome: TrainOutcome) -> TrainResult:
    """Copy the loop's own flag; never derive it from the epoch counts."""
    return TrainResult(
        best_checkpoint=outcome.best_checkpoint,
        best_val_accuracy=outcome.best_val_accuracy,
        test_accuracy=outcome.test_accuracy,
        test_loss=outcome.test_loss,
        epochs_run=outcome.epochs_run,
        epochs_requested=outcome.epochs_requested,
        early_stopped=outcome.early_stopped,
        phases=outcome.phases,
        checkpoints=list(outcome.checkpoints),
        log_paths=list(outcome.log_paths),
    )


def report_training(outcome: TrainOutcome, project_root: Path) -> None:
    """``✓ Training complete — best val_accuracy 0.852`` and its detail lines.

    The one renderer for this block, called by ``optica train`` and by this
    module's own :func:`train`. It reads ``patience``,
    ``phase1_stopped_early`` and ``classes_without_test``, which live on
    ``TrainOutcome`` and deliberately **not** on `TrainResult` — which is why
    the renderer lives beside the outcome rather than in the CLI, where
    ``optica run`` could not reach those three fields at all.
    """
    best = outcome.best_val_accuracy
    olog.success(
        "Training complete — best val_accuracy "
        + (f"{best:.3f}" if best is not None else "n/a")
    )
    epochs = f"  Epochs: {outcome.epochs_run} of {outcome.epochs_requested}"
    if outcome.early_stopped:
        epochs += f" (stopped early — val_loss, patience {outcome.patience})"
    olog.status(epochs)
    phase1, phase2 = outcome.phases
    phases = f"  Phases: {phase1} head warmup + {phase2} fine-tune"
    if outcome.phase1_stopped_early:
        phases += f" (head warmup stopped early after {outcome.phases_run[0]})"
    olog.status(phases)
    n_classes = len(outcome.split_counts)
    absent = len(outcome.classes_without_test)
    if outcome.test_accuracy is None or absent == n_classes:
        olog.status("  Test: not evaluated — no class received a test allocation")
    else:
        loss = outcome.test_loss if outcome.test_loss is not None else float("nan")
        line = f"  Test: accuracy {outcome.test_accuracy:.3f}, loss {loss:.3f}"
        if absent:
            line += f" ({absent} class{'es' if absent != 1 else ''} absent from test set)"
        olog.status(line)
    olog.status(
        f"  Checkpoints: {len(outcome.checkpoints)} saved in "
        f"./{checkpoints.CHECKPOINTS_DIR}/"
    )



def _materialize_manifest(
    collector: _Collector, manifest: Path, dataset: Path, *, overwrite: bool
) -> Callable[[], None]:
    parsed = parse_manifest(manifest)
    parsed.require_fully_labeled()
    _require_free_destination(dataset, overwrite=overwrite)
    items = [(row.path, row.class_name) for row in parsed.rows if row.class_name]

    def copy() -> None:
        partial = input_manager.partial_destination(dataset)
        if partial.exists():
            shutil.rmtree(partial)
        report = copy_into_dataset(items, partial)
        try:
            _report_unreadable(collector, report.unreadable, "while copying")
            before: dict[str, int] = {}
            for _, name in items:
                before[name] = before.get(name, 0) + 1
            for bad in report.unreadable:
                before[next(n for p, n in items if p == bad.path)] -= 1
            check_floor(before)
            check_floor_after_dedupe(
                before, {name: report.copied.get(name, 0) for name in before}
            )
        except BaseException:
            shutil.rmtree(partial, ignore_errors=True)
            raise
        input_manager.commit_dataset(partial, dataset)

    return copy


def _ensure_output(output: Path) -> None:
    """``output`` is always a container here; ``--yes`` creates it."""
    if output.is_dir():
        return
    if output.exists():
        raise OpticaValidationError(
            f"output={output} is a file, not a folder.",
            why="output is the container for run outputs.",
            fix="Choose a folder path: optica.train(output='./optica-output')",
        )
    workspace.create_ignored(output)


def _checkpoint_soft_limit(
    collector: _Collector, root: Path, max_checkpoints: int
) -> None:
    """K — keep all, per the ``--yes`` table, with the soft limit recorded."""
    kept = len(checkpoints.list_active(root))
    limit = checkpoints.soft_limit(max_checkpoints)
    if kept > limit:
        collector.add(
            WarningCode.CHECKPOINT_SOFT_LIMIT,
            f"{kept} checkpoints are kept in {root}/, more than {limit} "
            "(3 x max_checkpoints).",
            kept=kept,
            limit=limit,
        )


def _ingest_dataset(
    collector: _Collector, dataset: Path, names: Sequence[str]
) -> dict[str, list[Path]]:
    """Pre-flight and deduplicate in place, writing nothing."""
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
    _report_unreadable(collector, unreadable, "in the dataset")
    if undersized:
        collector.add(
            WarningCode.LOW_RESOLUTION,
            f"{undersized} images are smaller than {SIZE_THRESHOLD}px and will be "
            "used as they are.",
            count=undersized,
        )
    before = {name: len(paths) for name, paths in readable.items()}
    check_floor(before)
    unique = {name: find_duplicates(paths)[0] for name, paths in readable.items()}
    check_floor_after_dedupe(before, {name: len(p) for name, p in unique.items()})
    return unique


def _run_settings(
    collector: _Collector,
    resolved: ResolvedConfig,
    files: dict[str, list[Path]],
    dataset: Path,
    resume: checkpoints.Checkpoint | None,
) -> tuple[TrainSettings, str, bool]:
    """Resolve the run's settings, resuming the interrupted one where there is one."""
    from optica.config.manager import Source

    config = resolved.config
    if resume is not None:
        settings = TrainSettings.from_json(resume.info.get("config", {}))
        if sorted(resume.info.get("classes", [])) != sorted(files):
            raise OpticaTrainingError(
                "The dataset's classes no longer match the interrupted run.",
                why=f"Checkpoint: {', '.join(resume.info.get('classes', []))}. "
                f"Now: {', '.join(sorted(files))}.",
                fix="Remove or archive the interrupted checkpoint to start fresh.",
            )
        if training_data_hash(dataset) != resume.info.get("training_data_hash"):
            raise OpticaTrainingError(
                "The dataset has changed since the interrupted run.",
                why="Resuming would re-split a different set of files under the same "
                "random_state, mixing training and validation images.",
                fix="Remove or archive the interrupted checkpoint to start fresh.",
            )
        ignored = [
            name
            for key, name in resolved.flag_names.items()
            if resolved.sources.get(key) is Source.FLAG
        ]
        if ignored:
            collector.add(
                WarningCode.RESUME_SETTINGS_IGNORED,
                f"Resuming with the interrupted run's settings; "
                f"{', '.join(ignored)} ignored.",
                ignored=ignored,
            )
        return settings, str(resume.info["model_family"]), bool(
            resume.info.get("class_weights_applied")
        )

    settings = TrainSettings(
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
    counts = {name: len(paths) for name, paths in files.items()}
    imbalance = imbalanced_classes(counts)
    class_weights = imbalance is not None
    if imbalance is not None:
        # C — continue with automatic class weighting, per the `--yes` table.
        collector.add(
            WarningCode.CLASS_IMBALANCE,
            "Class imbalance detected; continuing with automatic class weighting.",
            counts=dict(imbalance.counts),
        )
    return settings, config.default_model, class_weights


def _safety_checks(collector: _Collector, settings: TrainSettings) -> None:
    """The warnings and safety prompts a fresh run raises before it starts."""
    warning = finetune_ratio_warning(settings.finetune_ratio)
    if warning:
        collector.add(
            WarningCode.FINETUNE_RATIO, warning, finetune_ratio=settings.finetune_ratio
        )
    if phase2_skipped_by_one_epoch(settings.epochs, settings.finetune_ratio):
        collector.add(
            WarningCode.FINETUNE_RATIO,
            "epochs=1 leaves no epoch for fine-tuning, so Phase 2 is skipped.",
            epochs=settings.epochs,
            finetune_ratio=settings.finetune_ratio,
        )
    device = select_device()
    if device.type == "cpu" and settings.batch_size > CPU_BATCH_LIMIT:
        collector.add(
            WarningCode.CPU_BATCH_SIZE,
            f"Training on CPU with batch_size {settings.batch_size} may cause memory "
            "issues on modest hardware.",
            batch_size=settings.batch_size,
        )


CPU_BATCH_LIMIT: Final = 16
"""Above this, training on CPU raises the safety prompt the CLI shows."""

DEFAULT_DATASET: Final = Path("dataset")
"""``./dataset``. Passing it explicitly is what ``--dataset`` being explicit means."""


# ------------------------------------------------------------------ export


def export(
    *,
    checkpoint_rank: int | None = None,
    output: str | Path = "optica-output",
    dry_run: bool = False,
    verbose: bool = True,
    config: ExportConfig | None = None,
) -> ExportResult:
    """Export a trained checkpoint as a PyTorch ``.pt`` artifact.

    ``checkpoint_rank`` defaults to rank 1 — the best — which is the
    ``--yes`` table's answer to the CLI's selection prompt.

    Raises:
        OpticaTorchError: The torch stack is missing.
        OpticaExportError: No checkpoint exists, or the export cannot be written.
    """
    collector = _Collector()
    with _verbosity(verbose):
        result = _export(
            collector,
            rank=checkpoint_rank
            if checkpoint_rank is not None
            else (config.checkpoint_rank if config else None),
            output=_as_path(output),
            dry_run=dry_run,
        )
    result.warnings = collector.emit()
    return result


def _export(
    collector: _Collector, *, rank: int | None, output: Path, dry_run: bool
) -> ExportResult:
    project_root = Path.cwd()
    ranked = export_manager.ranked_checkpoints(project_root)
    chosen = rank if rank is not None else 1
    if not 1 <= chosen <= len(ranked):
        raise OpticaValidationError(
            f"checkpoint_rank={chosen} does not exist.",
            why=f"{len(ranked)} checkpoint{'s' if len(ranked) != 1 else ''} "
            "are available.",
            fix="Pass a rank between 1 and " + str(len(ranked)) + ".",
        )
    item = ranked[chosen - 1]
    if dry_run:
        return ExportResult(
            dry_run=True,
            plan={
                "mode": "export",
                "detection_order": "checkpoint rank",
                "short_circuit": None,
                "destination": str(output),
                "checkpoint": str(item.checkpoint.path),
            },
            checkpoint_rank=chosen,
        )

    import_torch_stack()
    with acquire_lock("optica.export"):
        export_manager.require_writable(_ensure_container(output))
        for stale in export_manager.stale_checkpoint_paths(item.checkpoint, project_root):
            collector.add(
                WarningCode.STALE_CHECKPOINT_PATH,
                f"Checkpoint path no longer exists: {stale}",
                path=stale,
            )
        if export_manager.missing_run_end(item.checkpoint):
            collector.add(
                WarningCode.CHECKPOINT_RUN_INCOMPLETE,
                f"{item.checkpoint.path.name} is from a run that did not finish.",
                checkpoint=item.checkpoint.path.name,
                fields=["epochs_trained", "early_stopped"],
            )
        export_manager.clean_stale_partials(output)
        moment = datetime.now().replace(microsecond=0)
        name = export_manager.folder_name(
            str(item.checkpoint.info["model_family"]),
            len(item.checkpoint.info.get("classes", [])),
            moment,
            chosen,
            with_rank=chosen != 1,
        )
        record = export_manager.export_checkpoint(
            item,
            of=len(ranked),
            container=output,
            name=export_manager.unique_name(output, name),
            moment=moment,
            project_root=project_root,
        )
    olog.success(
        f"Export complete — rank {chosen} of {len(ranked)} to {record.folder}"
    )
    olog.status(f"  Files: {', '.join(record.files)}")
    return ExportResult(
        export_folder=record.folder, files=list(record.files), checkpoint_rank=chosen
    )


def _ensure_container(output: Path) -> Path:
    """``output`` is a container. Created where absent — ``--yes`` answers Y."""
    if output.exists() and not output.is_dir():
        raise OpticaValidationError(
            f"output={output} is a file, not a folder.",
            why="output is the container every export folder is written into.",
            fix="Choose a folder path: optica.export(output='./optica-output')",
        )
    workspace.create_ignored(output)
    return output


# --------------------------------------------------------------------- run


def run(
    classes: Sequence[str] | str | None = None,
    *,
    mode: str | None = None,
    source: str | None = None,
    images_per_class: int | None = None,
    clip_threshold: float | None = None,
    folder: str | Path | None = None,
    manifest: str | Path | None = None,
    dataset: str | Path | None = None,
    model: str | None = None,
    output: str | Path = "optica-output",
    checkpoint_rank: int | None = None,
    overwrite: bool = False,
    dry_run: bool = False,
    verbose: bool = True,
    start_at: str | None = None,
    fetch_config: FetchConfig | None = None,
    train_config: TrainConfig | None = None,
    export_config: ExportConfig | None = None,
) -> RunResult:
    """Run the whole pipeline: acquire, then train, then export.

    The only function that sequences one stage into the next. Required extras
    are resolved from the arguments and checked **before fetching begins** —
    ``mode="clip"`` needs clip, the label and curate paths need web, the train
    and export steps need torch — so a missing extra cannot land after the
    curation attention has been spent.

    **Resumption.** A previous session's state is read before anything runs,
    and the pipeline starts at the first step that is not complete — the
    ``--yes`` table's *R — resume*, which this layer takes because it behaves as
    though ``--yes`` were always passed. Stages skipped that way are ``None`` on
    the result. ``start_at`` overrides that: it names the step to begin at, and
    exists because the terminal's **C** answer has no other way to reach here.

    Args:
        classes: The class names. A list, or one comma-separated string.
        mode: ``label``, ``curate`` or ``clip``.
        source: ``open-datasets`` or ``flickr``.
        images_per_class: Images to collect per class.
        clip_threshold: The CLIP confidence threshold, for ``mode="clip"``.
        folder: A flat folder of images to label.
        manifest: A CSV or JSON manifest to label or train from.
        dataset: Where images land and training reads from. Passing it
            explicitly is what an explicit ``--dataset`` means, and is what the
            acquisition short-circuit tests.
        model: The backbone family.
        output: The container for the export folders and the project-local log.
        checkpoint_rank: The checkpoint to export. Rank 1 by default.
        overwrite: Required to replace a populated ``dataset/``.
        dry_run: Resolve the plan and write nothing.
        verbose: False suppresses Rich output.
        start_at: ``"fetch"``, ``"review"``, ``"train"`` or ``"export"``.
            None resumes.
        fetch_config: Acquisition settings.
        train_config: Training settings.
        export_config: Export settings.

    Raises:
        OpticaMissingExtraError: An extra the resolved pipeline needs.
        OpticaValidationError: A blocklisted class name, an unknown
            ``start_at``, or a populated ``dataset/`` without ``overwrite=True``.
    """
    collector = _Collector()
    with _verbosity(verbose):
        result = _run(
            collector,
            _classes_of(classes),
            mode=mode,
            source=source,
            images_per_class=images_per_class,
            clip_threshold=clip_threshold,
            folder=_as_path(folder) if folder else None,
            manifest=_as_path(manifest) if manifest else None,
            dataset=_as_path(dataset) if dataset is not None else DEFAULT_DATASET,
            dataset_explicit=dataset is not None,
            model=model,
            output=_as_path(output),
            checkpoint_rank=checkpoint_rank,
            overwrite=overwrite,
            dry_run=dry_run,
            start_at=start_at,
            fetch_config=fetch_config,
            train_config=train_config,
            export_config=export_config,
        )
    result.warnings = collector.emit()
    return result


def _run(
    collector: _Collector,
    names: list[str],
    *,
    mode: str | None,
    source: str | None,
    images_per_class: int | None,
    clip_threshold: float | None,
    folder: Path | None,
    manifest: Path | None,
    dataset: Path,
    dataset_explicit: bool,
    model: str | None,
    output: Path,
    checkpoint_rank: int | None,
    overwrite: bool,
    dry_run: bool,
    start_at: str | None,
    fetch_config: FetchConfig | None,
    train_config: TrainConfig | None,
    export_config: ExportConfig | None,
) -> RunResult:
    _check_choice(mode, MODES, "mode")
    _check_choice(source, SOURCES, "source")
    _check_choice(model, MODELS, "model")
    local = input_manager.require_single_input_source(folder, manifest)
    resolved_mode = input_manager.resolve_mode(
        command="run",
        explicit=mode,
        configured=None,
        local_input=local is not input_manager.InputSource.FETCH,
    )
    short_circuit = input_manager.short_circuits_acquisition(
        dataset=dataset,
        dataset_explicit=dataset_explicit,
        folder=folder,
        manifest=manifest,
        explicit_mode=mode,
    )

    if dry_run:
        return RunResult(
            dry_run=True,
            plan={
                "mode": resolved_mode.mode,
                "detection_order": resolved_mode.reason,
                "short_circuit": short_circuit,
                "destination": str(output),
                "classes": list(names),
                "start_at": _start_at(
                    start_at,
                    dataset=dataset,
                    output=output,
                    mode=resolved_mode.mode,
                    short_circuit=short_circuit,
                ).value,
            },
        )

    start = _start_at(
        start_at,
        dataset=dataset,
        output=output,
        mode=resolved_mode.mode,
        short_circuit=short_circuit,
    )
    runs = set(steps_from(start))
    # After the dry run, which does no work and so needs no stack: the entry
    # check exists to fire before the user's attention and quota are spent, and
    # a dry run spends neither.
    _require_extras(resolved_mode.mode, names, runs)

    acquisition: FetchResult | None = None
    if Step.FETCH in runs and resolved_mode.mode == "label":
        acquisition = label(
            names,
            folder=folder,
            manifest=manifest,
            dataset=dataset,
            overwrite=overwrite,
            config=fetch_config,
        )
    elif Step.FETCH in runs:
        acquisition = _fetch(
            collector,
            names,
            mode=resolved_mode.mode,
            source=source,
            images_per_class=images_per_class,
            clip_threshold=clip_threshold,
            dataset=dataset,
            overwrite=overwrite,
            dry_run=False,
            config=fetch_config,
        )
    if Step.REVIEW in runs and resolved_mode.mode == "curate":
        acquisition = curate(dataset=dataset, overwrite=overwrite, config=fetch_config)
    elif Step.REVIEW in runs and resolved_mode.mode == "label" and acquisition is None:
        # Resumed at the review step: labeling is the review step in this mode.
        acquisition = label(
            names,
            folder=folder,
            manifest=manifest,
            dataset=dataset,
            overwrite=overwrite,
            config=fetch_config,
        )
    if acquisition is not None:
        collector.extend(acquisition.warnings)

    trained: TrainResult | None = None
    if Step.TRAIN in runs:
        trained = train(
            dataset=dataset,
            model=model,
            output=output,
            overwrite=overwrite,
            config=train_config,
        )
        collector.extend(trained.warnings)
    exported: ExportResult | None = None
    if Step.EXPORT in runs:
        exported = export(
            checkpoint_rank=checkpoint_rank, output=output, config=export_config
        )
        collector.extend(exported.warnings)
    return RunResult(fetch=acquisition, train=trained, export=exported)


def _start_at(
    requested: str | None,
    *,
    dataset: Path,
    output: Path,
    mode: str,
    short_circuit: bool,
) -> Step:
    """Where the pipeline begins: the caller's step, or **R**'s.

    With no ``start_at`` this is *R — resume*: the first step of a previous
    session that is not complete. With nothing left behind it is the top, and an
    explicit ``dataset=`` that short-circuits acquisition begins at training,
    which is the resolution that rule already had.
    """
    if requested is not None:
        try:
            return Step(requested)
        except ValueError as exc:
            raise OpticaValidationError(
                f"start_at={requested!r} is not a pipeline step.",
                options=[step.value for step in ORDER],
            ) from exc
    if short_circuit:
        return Step.TRAIN
    state = inspect_session(
        dataset=dataset, project_root=Path.cwd(), output=output, mode=mode
    )
    return state.resume_from if state.found else Step.FETCH


def _require_extras(mode: str, names: Sequence[str], runs: set[Step]) -> None:
    """Every extra the resolved pipeline needs, checked at entry.

    Whether the pipeline can complete is fully determined at invocation, so a
    failure knowable at entry fires at entry — before the user's attention is
    spent on the curation or labeling step. A stage the resume point skips is
    not part of this pipeline, so its extra is not required either.
    """
    from optica.server.app import load_web

    if mode in ("label", "curate") and Step.REVIEW in runs:
        load_web()
    if Step.FETCH in runs and (
        mode == "clip" or (mode == "curate" and any(is_blocklisted(n) for n in names))
    ):
        input_manager.require_clip_extra()
    if Step.TRAIN in runs or Step.EXPORT in runs:
        import_torch_stack()
