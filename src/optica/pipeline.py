"""The four-step pipeline's state, as `optica run`'s resumption reads it.

Implements plan § "`optica run` resumption and preconditions" → the step status
model: **the four pipeline steps with their status (complete / incomplete / not
started), where a step whose inputs are absent is listed but not selectable and
says why**, and *R resumes from the last incomplete step*.

**Shared, not CLI-only.** `optica.run()` behaves as though ``--yes`` were passed
and the ``--yes`` table's own row is *R — resume*, so the API resumes from the
same state model the terminal's R/C/S prompt renders. Three states are what make
that more than a per-stage short-circuit: a short-circuit has two, and the two
readings agree on *complete* and on *not started* and diverge on **partially
complete** — the case resumption exists for.

**Nothing here prompts, prints, or writes** — except :func:`discard_after`,
which the destructive confirmation in the CLI guards. The state is read from the
four places the pipeline leaves it: auto-fetch staging and the session files,
``dataset/``, ``checkpoints/``, and the export container.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from optica.export import manager as export_manager
from optica.input import manager as input_manager
from optica.input.local import subfolders
from optica.training import checkpoints

__all__ = [
    "ORDER",
    "SessionState",
    "Step",
    "StepState",
    "StepStatus",
    "discard_after",
    "inspect_session",
    "steps_after",
    "steps_from",
]


class Step(StrEnum):
    """The four pipeline steps, in pipeline order."""

    FETCH = "fetch"
    REVIEW = "review"
    TRAIN = "train"
    EXPORT = "export"


ORDER: tuple[Step, ...] = (Step.FETCH, Step.REVIEW, Step.TRAIN, Step.EXPORT)
"""Pipeline order. Position in it is what *earlier* and *later* mean."""


def steps_after(step: Step) -> list[Step]:
    """The steps after ``step``, in pipeline order."""
    return [s for s in ORDER if ORDER.index(s) > ORDER.index(step)]


def steps_from(step: Step) -> list[Step]:
    """``step`` and everything after it — what a resume actually runs."""
    return [s for s in ORDER if ORDER.index(s) >= ORDER.index(step)]


class StepState(StrEnum):
    """The plan's three states. A short-circuit has the outer two only."""

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    NOT_STARTED = "not started"


def _review_name(mode: str | None) -> str:
    """The review step's name, which is the mode's: curation, or labeling."""
    if mode == "label":
        return "Labeling"
    if mode == "clip":
        return "CLIP filtering"
    return "Curation"


@dataclass(frozen=True)
class StepStatus:
    """One step's state, its detail line, and why it cannot be selected.

    Attributes:
        step: Which step.
        state: complete, incomplete, or not started.
        detail: What the ``✓``/``✗`` line reports — counts, or how far a run
            got. Empty for a step that has not started.
        blocked: Why the step is **listed but not selectable**, or None when it
            can be selected. A step whose inputs are absent cannot be run.
    """

    step: Step
    state: StepState
    detail: str = ""
    blocked: str | None = None

    @property
    def selectable(self) -> bool:
        """Whether the step selector can offer this step."""
        return self.blocked is None


@dataclass(frozen=True)
class SessionState:
    """What a previous session left behind, across all four steps.

    Attributes:
        steps: One :class:`StepStatus` per step, in pipeline order.
        mode: The resolved mode, which names the review step.
    """

    steps: tuple[StepStatus, ...]
    mode: str | None = None

    def of(self, step: Step) -> StepStatus:
        """This step's status."""
        return next(status for status in self.steps if status.step is step)

    @property
    def found(self) -> bool:
        """Whether there is a previous session at all.

        The top-level prompt fires only when something was left behind; a clean
        project runs from the top with no question asked.
        """
        return any(s.state is not StepState.NOT_STARTED for s in self.steps)

    @property
    def resume_from(self) -> Step:
        """Where **R** starts: the first step that is not complete.

        The plan says *the last incomplete step*. The two readings name the same
        step for any state the pipeline itself can produce, since a step cannot
        complete before the one in front of it; they part only where a user
        brings a later stage's output by hand, and there the earliest unfinished
        step is the one that must run for the rest to have inputs.
        """
        for status in self.steps:
            if status.state is not StepState.COMPLETE:
                return status.step
        return Step.EXPORT

    def lines(self) -> list[str]:
        """The ``Previous session found:`` block, one line per started step.

        ``✓ Fetch complete — 150 images across 3 classes`` /
        ``✗ Training incomplete — interrupted at epoch 3/10``. Rendering the
        markers is the caller's; the words are here so both surfaces read the
        same.
        """
        out: list[str] = []
        for status in self.steps:
            if status.state is StepState.NOT_STARTED:
                continue
            name = self.name_of(status.step)
            line = f"{name} {status.state.value}"
            if status.detail:
                line += f" — {status.detail}"
            out.append(line)
        return out

    def name_of(self, step: Step) -> str:
        """The step's display name. The review step's is the mode's."""
        if step is Step.REVIEW:
            return _review_name(self.mode)
        return {"fetch": "Fetch", "train": "Training", "export": "Export"}[step.value]


def inspect_session(
    *,
    dataset: Path,
    project_root: Path,
    output: Path,
    mode: str | None = None,
    home: Path | None = None,
) -> SessionState:
    """Read the four steps' state from where the pipeline leaves it.

    Args:
        dataset: The dataset destination.
        project_root: Where ``checkpoints/`` lives.
        output: The export container.
        mode: The resolved mode, which names the review step.
        home: The home directory holding ``~/.optica/staging/``.

    Returns:
        A :class:`SessionState`. Reads only.
    """
    staging = input_manager.list_staging(home)
    organized = _organized(dataset)
    review = _review_status(staging, organized, dataset)
    return SessionState(
        steps=(
            _fetch_status(staging, review),
            review,
            _train_status(project_root, organized, dataset),
            _export_status(output, project_root),
        ),
        mode=mode,
    )


def _organized(dataset: Path) -> dict[str, int] | None:
    """Per-class counts of an organized ``dataset/``, or None when there is none."""
    if not dataset.is_dir():
        return None
    counts = {
        folder.name: sum(1 for entry in folder.iterdir() if entry.is_file())
        for folder in subfolders(dataset)
    }
    return counts or None


def _fetch_status(
    staging: input_manager.StagingListing, review: StepStatus
) -> StepStatus:
    """Fetch is complete once its images exist — in staging, or consumed already."""
    partial = [staged for staged in staging.fetched if staged.partial]
    if partial:
        names = ", ".join(staged.name for staged in partial)
        return StepStatus(
            Step.FETCH,
            StepState.INCOMPLETE,
            f"the fetch for {names} did not finish",
        )
    images = sum(staged.images for staged in staging.fetched)
    if images:
        return StepStatus(
            Step.FETCH,
            StepState.COMPLETE,
            f"{images} images across {len(staging.fetched)} classes",
        )
    if review.state is StepState.COMPLETE:
        # Curation consumed the staging it reviewed; the fetch behind it ran.
        return StepStatus(Step.FETCH, StepState.COMPLETE, "consumed by the review step")
    return StepStatus(Step.FETCH, StepState.NOT_STARTED)


def _review_status(
    staging: input_manager.StagingListing,
    organized: dict[str, int] | None,
    dataset: Path,
) -> StepStatus:
    """The review step: curation or labeling, complete once ``dataset/`` holds it."""
    if organized is not None:
        total = sum(organized.values())
        return StepStatus(
            Step.REVIEW,
            StepState.COMPLETE,
            f"{total} images across {len(organized)} classes in {dataset}",
        )
    if staging.curation is not None:
        return StepStatus(
            Step.REVIEW, StepState.INCOMPLETE, "a curation session is in progress"
        )
    if staging.labeling:
        labeled = sum(entry.labeled or 0 for entry in staging.labeling)
        return StepStatus(
            Step.REVIEW, StepState.INCOMPLETE, f"{labeled} images labeled so far"
        )
    blocked = None if staging.fetched else "nothing is staged to review"
    return StepStatus(Step.REVIEW, StepState.NOT_STARTED, blocked=blocked)


def _train_status(
    project_root: Path, organized: dict[str, int] | None, dataset: Path
) -> StepStatus:
    """Training: interrupted where a resumable checkpoint exists."""
    root = project_root / checkpoints.CHECKPOINTS_DIR
    active = checkpoints.list_active(root)
    blocked = None if organized is not None else f"no dataset at {dataset} to train on"
    resumable = checkpoints.resumable(active)
    if resumable is not None:
        total = resumable.info.get("config", {}).get("epochs", "?")
        return StepStatus(
            Step.TRAIN,
            StepState.INCOMPLETE,
            f"interrupted at epoch {resumable.epoch} of {total}",
            blocked=blocked,
        )
    if active:
        best = checkpoints.rank(active)[0]
        return StepStatus(
            Step.TRAIN,
            StepState.COMPLETE,
            f"best val_accuracy {best.val_accuracy:.3f}",
            blocked=blocked,
        )
    return StepStatus(Step.TRAIN, StepState.NOT_STARTED, blocked=blocked)


def _export_status(output: Path, project_root: Path) -> StepStatus:
    """Export: a partial folder means an export was interrupted mid-write."""
    blocked = (
        None
        if checkpoints.list_active(project_root / checkpoints.CHECKPOINTS_DIR)
        else "no trained checkpoint to export"
    )
    folders = export_manager.export_folders(output)
    if export_manager.partial_exports(output):
        return StepStatus(
            Step.EXPORT,
            StepState.INCOMPLETE,
            "an export did not finish writing",
            blocked=blocked,
        )
    if folders:
        return StepStatus(
            Step.EXPORT,
            StepState.COMPLETE,
            f"{len(folders)} export folder{'s' if len(folders) != 1 else ''} in {output}",
            blocked=blocked,
        )
    return StepStatus(Step.EXPORT, StepState.NOT_STARTED, blocked=blocked)


def discard_after(
    step: Step,
    *,
    dataset: Path,
    project_root: Path,
    output: Path,
    home: Path | None = None,
) -> list[str]:
    """Remove what the steps **after** ``step`` produced.

    Re-running an earlier step invalidates what followed it, so the plan
    discards the later steps' staging behind a confirmation. The caller owns
    that confirmation; nothing is removed without one.

    Returns:
        A line per thing removed, for the caller to report.
    """
    removed: list[str] = []
    later = set(steps_after(step))
    if Step.REVIEW in later and dataset.is_dir():
        shutil.rmtree(dataset)
        removed.append(f"the dataset at {dataset}")
    if Step.TRAIN in later:
        root = project_root / checkpoints.CHECKPOINTS_DIR
        active = checkpoints.list_active(root)
        if active:
            checkpoints.delete(active)
            removed.append(f"{len(active)} checkpoints in {root}")
    if Step.EXPORT in later:
        folders = export_manager.export_folders(output)
        for folder in folders:
            shutil.rmtree(folder)
        if folders:
            removed.append(f"{len(folders)} export folders in {output}")
    return removed
