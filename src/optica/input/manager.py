"""The Input Manager.

Implements plan § "Input & Acquisition" → *Input Manager*, *Label mode —
detection order* (including mode defaults, the acquisition short-circuit, and
the one-input-source rule), *Class-count validation*, *``--classes`` against an
already-organized dataset*, *Fetch sources* (the soft cap), *``dataset/``
conflict*, the ``clip_threshold`` bands of *CLIP Adapter*, and § "Configuration"
→ ``optica config --clear-staging``, whose deletion logic lives here.

Every check here is one whose answer is knowable before work begins, so every
one runs before anything is written or any browser opens. Nothing here prompts:
where a decision needs an answer, the function returns the question's content
and the CLI asks it.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Final

from optica.exceptions import (
    OpticaCLIPError,
    OpticaConfigError,
    OpticaValidationError,
)
from optica.input.classes import LIST_TRUNCATE, list_names
from optica.input.fetch import StagedClass, staged_classes
from optica.input.local import list_files, subfolders
from optica.input.sessions import (
    CurationSession,
    labeling_dir,
    load_labeling,
    staging_root,
)

__all__ = [
    "FETCH_MODES",
    "RUN_MODES",
    "DetectionCase",
    "InputSource",
    "LabelingSessionEntry",
    "ResolvedMode",
    "StagingListing",
    "SubsetConfirmation",
    "ThresholdBand",
    "ThresholdCheck",
    "check_clip_threshold",
    "clear_staging",
    "clip_available",
    "commit_dataset",
    "compare_classes",
    "describe_destination",
    "destination_contents",
    "detect_label_input",
    "list_staging",
    "missing_classes_error",
    "overwrite_refused",
    "partial_destination",
    "replace_destination",
    "require_clip_extra",
    "require_single_input_source",
    "resolve_mode",
    "short_circuits_acquisition",
    "soft_cap_exceeded",
    "threshold_band",
]

FETCH_MODES: Final = ("curate", "clip")
RUN_MODES: Final = ("label", "curate", "clip")


# ------------------------------------------------------------ input sources


class InputSource(StrEnum):
    """Where an invocation's images come from."""

    FOLDER = "--folder"
    MANIFEST = "--manifest"
    FETCH = "fetch"


def require_single_input_source(
    folder: Path | None, manifest: Path | None
) -> InputSource:
    """Exactly one input source per invocation.

    ``--folder`` **xor** ``--manifest`` **xor** neither, where neither means
    acquisition by fetch. ``--dataset`` is not an input source.

    Raises:
        OpticaValidationError: When more than one is given — stated as
            unsupported in V1, not as invalid.
    """
    if folder is not None and manifest is not None:
        raise OpticaValidationError(
            "Combining input sources is unsupported in V1: --folder and --manifest "
            "were both given.",
            why="Each invocation takes its images from exactly one place.",
            fix="Run once with --folder and once with --manifest, or combine the "
            "images into one manifest.",
        )
    if folder is not None:
        return InputSource.FOLDER
    if manifest is not None:
        return InputSource.MANIFEST
    return InputSource.FETCH


# -------------------------------------------------------------------- modes


@dataclass(frozen=True)
class ResolvedMode:
    """The mode an invocation runs, and why.

    Attributes:
        mode: ``label``, ``curate`` or ``clip``.
        reason: The parenthetical the run reports — the resolved mode is always
            reported, so an ignored config setting is visible rather than silent.
    """

    mode: str
    reason: str

    @property
    def line(self) -> str:
        """``Mode: label (default for local input)``."""
        return f"Mode: {self.mode} ({self.reason})"


def _drop_mode(argv: Sequence[str]) -> list[str]:
    out: list[str] = []
    skip = False
    for arg in argv:
        if skip:
            skip = False
            continue
        if arg == "--mode":
            skip = True
            continue
        if arg.startswith("--mode="):
            continue
        out.append(arg)
    return out


def resolve_mode(
    *,
    command: str,
    explicit: str | None,
    configured: str | None,
    local_input: bool,
    argv: Sequence[str] | None = None,
) -> ResolvedMode:
    """Resolve ``--mode`` for one invocation.

    The contextual default is ``curate`` when acquiring by fetch and ``label``
    when ``--folder`` or ``--manifest`` is given. ``default_mode`` from config
    applies **only where the command accepts ``--mode`` and the value is legal
    for this invocation as a whole** — legality is per invocation, not per
    command, so no config setting can turn a valid invocation into an error.

    Args:
        command: ``fetch`` or ``run``.
        explicit: ``--mode`` as given, already checked against the command's
            accepted values.
        configured: ``default_mode`` when explicitly set in config, else None.
        local_input: Whether ``--folder`` or ``--manifest`` was given.
        argv: The command line, for the corrected command in the error below.

    Raises:
        OpticaValidationError: ``--mode curate`` or ``--mode clip`` with local
            input — both require fetched input.
    """
    accepted = FETCH_MODES if command == "fetch" else RUN_MODES
    if explicit is not None:
        if local_input and explicit in ("curate", "clip"):
            fix = ["These modes acquire by fetch; local input uses label mode."]
            if argv is not None:
                fix.append("optica " + " ".join(_drop_mode(argv)))
            raise OpticaValidationError(
                f"--mode {explicit} requires fetched input, not --folder or --manifest.",
                why="curate and clip mode search a remote source for each class.",
                fix=fix,
            )
        return ResolvedMode(explicit, "--mode")

    def legal(mode: str) -> bool:
        if mode not in accepted:
            return False
        return (mode == "label") == local_input

    if configured is not None and legal(configured):
        return ResolvedMode(configured, "from config")
    if local_input:
        return ResolvedMode("label", "default for local input")
    return ResolvedMode("curate", "default")


# -------------------------------------------------------------- detection


class DetectionCase(IntEnum):
    """Label-mode detection order, cases 1 to 4. Case 5 is an error."""

    FOLDER = 1
    MANIFEST = 2
    DATASET = 3
    DEFAULT_DATASET = 4


def detect_label_input(
    *,
    folder: Path | None,
    manifest: Path | None,
    dataset: Path,
    dataset_explicit: bool,
) -> DetectionCase:
    """Decide which input ``--mode label`` operates on.

    1. ``--folder`` → labeling. 2. ``--manifest`` → by its label state.
    3. ``--dataset`` → it must exist; **a missing explicit path is a hard error,
    never a fall-through to case 4**. 4. ``./dataset/`` present → train.
    5. Nothing → a precondition error listing every valid option.

    Raises:
        OpticaValidationError: For case 3's missing path and for case 5.
    """
    if folder is not None:
        return DetectionCase.FOLDER
    if manifest is not None:
        return DetectionCase.MANIFEST
    if dataset_explicit:
        if not dataset.exists():
            raise OpticaValidationError(
                f"No dataset found at {dataset}",
                why="--dataset names a path that does not exist.",
                fix="Check the path; an explicit --dataset is never swapped for "
                "./dataset/.",
            )
        return DetectionCase.DATASET
    if dataset.is_dir() and any(subfolders(dataset)):
        return DetectionCase.DEFAULT_DATASET
    raise OpticaValidationError(
        "No input found for label mode.",
        why="Label mode needs a flat folder, a manifest, or an organized dataset.",
        fix=[
            "Label a folder: optica run --mode label --folder ./images -c cat,dog",
            "Use a manifest: optica run --mode label --manifest ./images.csv",
            "Train an organized dataset: optica run --dataset ./dataset",
        ],
    )


def short_circuits_acquisition(
    *,
    dataset: Path,
    dataset_explicit: bool,
    folder: Path | None,
    manifest: Path | None,
    explicit_mode: str | None,
) -> bool:
    """Whether ``optica run`` skips acquisition and begins at training.

    Only an **explicit** ``--dataset`` pointing at an organized dataset, with no
    input-source flag and no explicit ``--mode curate``/``clip``. A bare
    ``./dataset/`` never triggers it.
    """
    if not dataset_explicit or folder is not None or manifest is not None:
        return False
    if explicit_mode in ("curate", "clip"):
        return False
    return dataset.is_dir() and any(subfolders(dataset))


# ------------------------------------------------------------- destination


def destination_contents(destination: Path) -> dict[str, int] | None:
    """Per-class file counts of a populated destination, or None if absent or empty.

    The check is keyed to the destination, not to any input flag: every command
    that will materialize into a dataset destination runs it before any action,
    so a new input route inherits it. The prompt names what is there rather than
    warning in the abstract, which is what these counts are for. Loose files
    directly inside are reported under ``(loose files)``.
    """
    if not destination.exists():
        return None
    if not destination.is_dir():
        return {"(not a folder)": 1}
    counts = {folder.name: len(list_files(folder)) for folder in subfolders(destination)}
    loose = list_files(destination)
    if loose:
        counts["(loose files)"] = len(loose)
    if not counts:
        return None
    return counts


def describe_destination(
    destination: Path, counts: dict[str, int], source: str
) -> list[str]:
    """The overwrite prompt's lines: what is there, and what will replace it."""
    lines = [
        f"{destination.name}/ already exists and will be replaced with new {source}:"
    ]
    items = list(counts.items())
    lines.extend(f"  {name}: {count} images" for name, count in items[:LIST_TRUNCATE])
    if len(items) > LIST_TRUNCATE:
        lines.append(f"  (and {len(items) - LIST_TRUNCATE} more)")
    return lines


def overwrite_refused(destination: Path) -> OpticaValidationError:
    """The error an unattended run raises at a populated destination.

    ``--overwrite`` is the only unattended route past the prompt; neither
    ``--yes`` nor ``--force`` reaches a destructive prompt.
    """
    return OpticaValidationError(
        f"{destination} already exists and is not empty.",
        why="Replacing it deletes its contents, which needs an explicit answer.",
        fix=[
            "Re-run with --overwrite to replace it, or",
            "choose a different destination with --dataset.",
        ],
    )


def replace_destination(destination: Path) -> None:
    """Remove the destination's contents before writing.

    "Overwrite" means replace: merging would silently mix stale images into a
    dataset the user believed replaced. Removes exactly the destination Optica
    resolved, and nothing above it.
    """
    if destination.is_dir():
        shutil.rmtree(destination)
    elif destination.exists():
        destination.unlink()
    destination.mkdir(parents=True, exist_ok=True)


def partial_destination(destination: Path) -> Path:
    """The sibling a new dataset is written into before it replaces ``destination``.

    ``<parent>/.<name>.partial/`` — a sibling, because a rename is atomic only
    within one filesystem; the same convention fetch and export use.
    """
    return destination.parent / f".{destination.name}.partial"


def commit_dataset(partial: Path, destination: Path) -> None:
    """Replace ``destination`` with the finished dataset written at ``partial``.

    The existing contents are removed first — "overwrite" means replace, never
    merge — and only once the new dataset is complete and has passed its checks,
    so a failed materialization leaves the user's old dataset exactly as it was.
    The caller has already had the replacement confirmed.
    """
    if destination.is_dir() and not destination.is_symlink():
        shutil.rmtree(destination)
    elif destination.exists() or destination.is_symlink():
        destination.unlink()
    os.replace(partial, destination)


# --------------------------------------------------- --classes vs a dataset


@dataclass(frozen=True)
class SubsetConfirmation:
    """The train-on-a-subset confirmation's content.

    Attributes:
        included: Requested classes, in request order.
        excluded: Folders present but not requested, sorted.
        total_folders: Folders found in the dataset.
    """

    included: list[str]
    excluded: list[str]
    total_folders: int

    @property
    def lines(self) -> list[str]:
        """The prompt text, exclude list truncated past 10."""
        return [
            f"--classes requests training on: {', '.join(self.included)} "
            f"({len(self.included)} of {self.total_folders} folders found)",
            f"Excluded from this run: {list_names(self.excluded)}",
        ]

    @property
    def question(self) -> str:
        """The Y/n question. ``--yes`` answers Y."""
        return f"Proceed with the {len(self.included)} requested classes only?"


def compare_classes(
    requested: Sequence[str], folders: Sequence[str]
) -> SubsetConfirmation | None:
    """Cross-validate ``--classes`` against an organized dataset, asymmetrically.

    A class named with no matching folder is a hard error — almost always a typo
    — and **fires first**, so a subset question is never asked while a typo
    remains. Folders not named are a legitimate subset, allowed after an explicit
    confirmation. An exact match, in any order, proceeds silently.

    Returns:
        The confirmation to ask, or None for an exact match.

    Raises:
        OpticaValidationError: When any requested class has no folder.
    """
    folder_set = set(folders)
    missing = [name for name in requested if name not in folder_set]
    extra = sorted(name for name in folders if name not in set(requested))
    if missing:
        fix = [f"In --classes but no matching folder: {list_names(missing)}"]
        if extra:
            fix.append(f"In dataset/ but not in --classes: {list_names(extra)}")
        fix.append(
            "Fix the --classes list, drop --classes, or rename the folders, and try "
            "again."
        )
        raise OpticaValidationError(
            "--classes does not match the dataset folder structure.", fix=fix
        )
    if not extra:
        return None
    return SubsetConfirmation(list(requested), extra, len(folders))


# ------------------------------------------------------------ clip settings


class ThresholdBand(StrEnum):
    """The seven ``clip_threshold`` bands."""

    OUT_OF_RANGE = "out of range"
    ZERO = "exactly 0.0"
    ONE = "exactly 1.0"
    STRICT = "0.75 to <1.0"
    HIGH = "0.5 to <0.75"
    NORMAL = "0.1 to <0.5"
    LOW = ">0.0 to <0.1"


def threshold_band(value: float) -> ThresholdBand:
    """Which of the seven bands ``value`` falls in."""
    if value < 0.0 or value > 1.0:
        return ThresholdBand.OUT_OF_RANGE
    if value == 0.0:
        return ThresholdBand.ZERO
    if value == 1.0:
        return ThresholdBand.ONE
    if value >= 0.75:
        return ThresholdBand.STRICT
    if value >= 0.5:
        return ThresholdBand.HIGH
    if value >= 0.1:
        return ThresholdBand.NORMAL
    return ThresholdBand.LOW


@dataclass(frozen=True)
class ThresholdCheck:
    """What a threshold asks of the command about to use it.

    Attributes:
        band: The band.
        warning: A warn-and-continue message, if any.
        prompt: A Y/n question for the strict end, if any. ``--yes`` answers Y.
    """

    band: ThresholdBand
    warning: str | None = None
    prompt: str | None = None


def check_clip_threshold(value: float, *, command: str) -> ThresholdCheck:
    """Apply the seven bands to a ``clip_threshold`` about to be used.

    The three hard-error bands are also enforced at config load; the prompt and
    the two warnings belong to the command using the value, which is here.

    Raises:
        OpticaConfigError: For the three hard-error bands. The ``0.0`` message
            lists the valid alternatives per command — ``run`` also offers
            ``--mode label``, which ``fetch`` does not accept.
    """
    band = threshold_band(value)
    if band is ThresholdBand.OUT_OF_RANGE:
        raise OpticaConfigError(
            f"--clip-threshold {value} is outside 0.0 to 1.0.",
            why="CLIP similarity scores lie between 0.0 and 1.0.",
            fix="Use a value such as 0.25 (the calibrated default).",
        )
    if band is ThresholdBand.ZERO:
        fix = ["To skip filtering, use --mode curate instead."]
        if command == "run":
            fix = ["To skip filtering, use --mode curate or --mode label instead."]
        raise OpticaConfigError(
            "--clip-threshold 0.0 disables CLIP filtering entirely.",
            why="clip mode requires a threshold greater than 0.0.",
            fix=fix,
        )
    if band is ThresholdBand.ONE:
        raise OpticaConfigError(
            "--clip-threshold 1.0 lets no image pass, leaving every class empty.",
            why="clip mode requires a threshold below 1.0.",
            fix="Use a value such as 0.25 (the calibrated default).",
        )
    if band is ThresholdBand.STRICT:
        return ThresholdCheck(
            band,
            prompt=f"clip_threshold {value} is very strict — few images will pass. "
            "Continue?",
        )
    if band is ThresholdBand.HIGH:
        return ThresholdCheck(
            band,
            warning=f"clip_threshold {value} is high; many relevant images may be "
            "dropped.",
        )
    if band is ThresholdBand.LOW:
        return ThresholdCheck(
            band,
            warning=f"clip_threshold {value} is very low; little will be filtered out.",
        )
    return ThresholdCheck(band)


def clip_available() -> bool:
    """Whether ``open-clip-torch`` is importable — checked without importing it."""
    return importlib.util.find_spec("open_clip") is not None


def require_clip_extra() -> None:
    """The entry check for a path that will need CLIP later.

    Raises:
        OpticaCLIPError: With the capability-named install message.
    """
    if not clip_available():
        raise OpticaCLIPError()


def soft_cap_exceeded(images_per_class: int, cap: int) -> bool:
    """Whether ``--images-per-class`` exceeds ``max_open_datasets_per_class``.

    The soft cap is a courtesy limit for public infrastructure: a warning with a
    Y/n before the fetch begins, which ``--yes`` answers Y.
    """
    return images_per_class > cap


# ------------------------------------------------------------------ staging


@dataclass(frozen=True)
class LabelingSessionEntry:
    """One labeling session file, as ``--clear-staging`` lists it.

    Attributes:
        path: The session file.
        source: The folder or manifest it labels, or None if unreadable.
        labeled: Images labeled so far, or None if unreadable.
    """

    path: Path
    source: str | None
    labeled: int | None


@dataclass
class StagingListing:
    """All three staging shapes.

    Attributes:
        fetched: Auto-fetch class directories, complete and ``.partial``.
        curation: ``curation.json``, if present.
        labeling: Labeling session files.
        other: Anything else found under staging.
    """

    fetched: list[StagedClass] = field(default_factory=list)
    curation: Path | None = None
    labeling: list[LabelingSessionEntry] = field(default_factory=list)
    other: list[Path] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        """Whether there is nothing to clear."""
        return not (self.fetched or self.curation or self.labeling or self.other)

    @property
    def lines(self) -> list[str]:
        """What ``--clear-staging`` lists before asking."""
        lines: list[str] = []
        for staged in self.fetched:
            state = " (incomplete fetch)" if staged.partial else ""
            lines.append(f"Fetched: {staged.name} — {staged.images} images{state}")
        if self.curation is not None:
            lines.append(f"Curation session: {self.curation}")
        for entry in self.labeling:
            if entry.source is None:
                lines.append(f"Labeling session: {entry.path} (unreadable)")
            else:
                lines.append(
                    f"Labeling session: {entry.source} — {entry.labeled} images labeled"
                )
        lines.extend(f"Other: {path}" for path in self.other)
        return lines


def list_staging(home: Path | None = None) -> StagingListing:
    """List every staging shape.

    A labeling session file that cannot be read is **listed**, marked
    unreadable, rather than raised: this is the command that removes it, and
    refusing to list the file would leave the user no way to clear it.
    """
    listing = StagingListing(fetched=staged_classes(home))
    root = staging_root(home)
    if not root.is_dir():
        return listing
    curation = CurationSession.at(home)
    if curation.exists():
        listing.curation = curation
    sessions_dir = labeling_dir(home)
    if sessions_dir.is_dir():
        for path in sorted(sessions_dir.glob("*.json")):
            try:
                session = load_labeling(path)
            except Exception:  # noqa: BLE001 - listed as unreadable, not raised
                listing.labeling.append(LabelingSessionEntry(path, None, None))
                continue
            labeled = sum(session.counts().values())
            listing.labeling.append(LabelingSessionEntry(path, session.source, labeled))
    known = {staged.path for staged in listing.fetched} | {curation, sessions_dir}
    listing.other = sorted(entry for entry in root.iterdir() if entry not in known)
    return listing


def clear_staging(home: Path | None = None) -> StagingListing:
    """Delete all staging contents, returning what was there.

    Removes the contents of ``~/.optica/staging/`` and keeps the directory
    itself. The caller has already listed it and received a confirmation.
    """
    listing = list_staging(home)
    root = staging_root(home)
    if root.is_dir():
        for entry in root.iterdir():
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry)
            else:
                entry.unlink()
    return listing


# ------------------------------------------------------------ class flag


def missing_classes_error(command: str) -> OpticaValidationError:
    """The error where the class-name prompt cannot fire.

    ``✕ --classes is required for fetch — nothing to search for.``
    """
    reason = "nothing to search for" if command == "fetch" else "nothing to label with"
    return OpticaValidationError(
        f"--classes is required for {command} — {reason}.",
        fix=f"Example: optica {command} --classes cat,dog",
    )
