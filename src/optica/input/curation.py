"""The Curation Adapter: from auto-fetch staging to a curated ``dataset/``.

Implements plan § "Input & Acquisition" → *Input Manager* (Curation Adapter),
and § "Labeling & Curation" → *Curation Server* (the low-selection thresholds
and the Confirm gate), *Deletion, staging, and interruption* (mass rejection)
and *Staging shapes* (fetch completion, ``curation.json``).

This module is the half of curation that needs no browser: reading staging,
applying the stored deselections, deciding what the thresholds say, and writing
the result. The server that shows it to a person arrives in pass 3 and calls
into this rather than reimplementing it.

A standalone ``optica curate`` reports an incomplete fetch and proceeds with
what is there — the resume prompt belongs to ``optica fetch`` alone.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Final

from optica.exceptions import OpticaError, OpticaValidationError
from optica.input.classes import ResolvedClass
from optica.input.fetch import (
    ClassFetchReport,
    FetchSource,
    ImageGetter,
    StagedClass,
    fetch_class,
    staged_classes,
    staged_images,
    staged_queries,
)
from optica.input.sessions import CurationSession, load_curation, staging_root
from optica.input.validation import md5_of

__all__ = [
    "LOW_SELECTION_MINIMUM",
    "LOW_SELECTION_RATIO",
    "CurationView",
    "MaterializeReport",
    "RejectionTrigger",
    "SelectionWarning",
    "confirm_blocked_classes",
    "fetch_more",
    "fetch_more_refusal",
    "fetch_more_shortfall",
    "load_view",
    "materialize_selection",
    "open_session",
    "selected_counts",
    "selection_warnings",
]

LOW_SELECTION_RATIO: Final = 0.30
"""A class with under 30% of its fetched images selected warns."""

LOW_SELECTION_MINIMUM: Final = 10
"""A class with fewer than 10 images selected warns."""


@dataclass(frozen=True)
class CurationView:
    """What curation would show.

    Attributes:
        images: Per class, the staged image paths, path-sorted.
        incomplete: Classes whose fetch was interrupted (``.partial``).
    """

    images: dict[str, list[Path]]
    incomplete: list[str] = field(default_factory=list)

    @property
    def fetched(self) -> dict[str, int]:
        """Staged images per class."""
        return {name: len(paths) for name, paths in self.images.items()}


def load_view(home: Path | None = None) -> CurationView:
    """Read auto-fetch staging for curation.

    Raises:
        OpticaValidationError: When staging holds no images at all — the
            precondition ``optica curate`` checks.
    """
    classes: list[StagedClass] = staged_classes(home)
    images: dict[str, list[Path]] = {}
    incomplete: list[str] = []
    for staged in classes:
        if staged.partial:
            incomplete.append(staged.name)
        images.setdefault(staged.name, []).extend(staged_images(staged.path))
    images = {name: sorted(paths) for name, paths in images.items() if paths}
    if not images:
        raise OpticaValidationError(
            "No fetched images are staged for curation.",
            why="optica curate reviews images that optica fetch has already downloaded.",
            fix="Run: optica fetch --classes cat,dog",
        )
    return CurationView(images, incomplete)


def open_session(home: Path | None = None) -> CurationSession:
    """Load ``curation.json``, or start a new session if none exists.

    Raises:
        OpticaCurationError: When the file exists but is unreadable, corrupt,
            or an unrecognized version.
    """
    path = CurationSession.at(home)
    if path.exists():
        return load_curation(path)
    return CurationSession(path)


def _selected(view: CurationView, session: CurationSession) -> dict[str, list[Path]]:
    return {
        name: [p for p in paths if session.is_selected(name, str(p))]
        for name, paths in view.images.items()
    }


class RejectionTrigger(StrEnum):
    """The two independent mass-rejection triggers."""

    PERCENTAGE = "percentage"
    MINIMUM = "minimum"


@dataclass(frozen=True)
class SelectionWarning:
    """One class tripping one low-selection trigger.

    Attributes:
        class_name: The class.
        trigger: Which threshold.
        selected: Images selected.
        fetched: Images fetched.
    """

    class_name: str
    trigger: RejectionTrigger
    selected: int
    fetched: int

    @property
    def message(self) -> str:
        """The trigger's own message — each fires with its own."""
        if self.trigger is RejectionTrigger.PERCENTAGE:
            percent = round(100 * self.selected / self.fetched) if self.fetched else 0
            return (
                f"{self.class_name}: only {self.selected} of {self.fetched} fetched "
                f"images selected ({percent}%, below 30%)"
            )
        return (
            f"{self.class_name}: only {self.selected} images selected "
            f"(fewer than {LOW_SELECTION_MINIMUM})"
        )


def selection_warnings(
    fetched: dict[str, int], selected: dict[str, int]
) -> list[SelectionWarning]:
    """Both low-selection triggers, per class, independently.

    The browser's advisory banner and the post-Confirm mass-rejection prompt use
    the same two thresholds: under 30% of fetched images selected, or fewer than
    10 selected. A class can trip both, and each fires with its own message.
    """
    warnings: list[SelectionWarning] = []
    for name, total in fetched.items():
        count = selected.get(name, 0)
        if total and count / total < LOW_SELECTION_RATIO:
            warnings.append(
                SelectionWarning(name, RejectionTrigger.PERCENTAGE, count, total)
            )
        if count < LOW_SELECTION_MINIMUM:
            warnings.append(
                SelectionWarning(name, RejectionTrigger.MINIMUM, count, total)
            )
    return warnings


def confirm_blocked_classes(selected: dict[str, int]) -> list[str]:
    """Classes with **zero** selected images — the only thing that disables Confirm.

    The low-selection banner is advisory; Confirm stays active through it.
    """
    return [name for name, count in selected.items() if count == 0]


def selected_counts(view: CurationView, session: CurationSession) -> dict[str, int]:
    """Selected images per class, applying the stored deselections."""
    return {name: len(paths) for name, paths in _selected(view, session).items()}


@dataclass
class MaterializeReport:
    """What writing a curated selection did.

    Attributes:
        written: Images written per class.
        duplicates: Byte-identical selected images excluded per class.
    """

    written: dict[str, int] = field(default_factory=dict)
    duplicates: dict[str, int] = field(default_factory=dict)


def materialize_selection(
    view: CurationView, session: CurationSession, destination: Path
) -> MaterializeReport:
    """Write the selected images into ``destination/<class>/``.

    Staged bytes already passed the per-file stages when they were written into
    staging, so they are copied as they are. MD5 deduplication runs again within
    each class, since two selections can meet here that never met in staging.
    Names are kept — staging's sequence names are unique within a class.

    The caller has already run the ``dataset/`` conflict check, and runs the
    post-deduplication floor re-check on the result.
    """
    report = MaterializeReport()
    for name, paths in _selected(view, session).items():
        folder = destination / name
        folder.mkdir(parents=True, exist_ok=True)
        seen: set[str] = set()
        for path in paths:
            data = path.read_bytes()
            digest = md5_of(data)
            if digest in seen:
                report.duplicates[name] = report.duplicates.get(name, 0) + 1
                continue
            seen.add(digest)
            (folder / path.name).write_bytes(data)
            report.written[name] = report.written.get(name, 0) + 1
    return report


# ---------------------------------------------------------------- fetch more


def fetch_more_shortfall(images_per_class: int, selected: int) -> int:
    """Images Fetch More requests: enough to restore ``images_per_class`` selected.

    Zero when the class already has that many selected — a class can trip the
    percentage trigger with plenty selected, and fetching more would only lower
    its percentage further.
    """
    return max(0, images_per_class - selected)


def fetch_more_refusal(name: str, home: Path | None = None) -> str | None:
    """Why Fetch More cannot run for ``name`` in this build, or None if it can.

    A grouped blocklist class was fetched as several sub-term queries, and its
    images are CLIP-scored after each fetch. ``optica fetch`` runs that stage
    (``input/clip.py``, pass 4); Fetch More does not yet — it would need a
    per-sub-term top-up target and the CLIP model loaded inside the curation
    server (``notes/build-log.md``). An ordinary class was fetched as one query,
    its own name.
    """
    root = staging_root(home)
    folder = root / name if (root / name).is_dir() else root / f"{name}.partial"
    queries = staged_queries(folder)
    if queries and queries != {name}:
        return (
            f"{name} was fetched as a group of sub-terms, which needs CLIP filtering "
            "after each fetch; Fetch More does not run it in this build."
        )
    return None


def fetch_more(
    name: str,
    count: int,
    source: FetchSource,
    downloader: ImageGetter,
    home: Path | None = None,
    *,
    on_image: Callable[[], None] | None = None,
) -> ClassFetchReport:
    """Fetch ``count`` more images for a staged class — the Curation Adapter's bridge.

    Runs the Fetch Adapter's own fill-to-target loop with the target raised by
    ``count``, so candidates already tried are skipped and new images continue
    the class's numbering and default to selected (``curation.json`` records
    deselections only).

    Raises:
        OpticaError: When :func:`fetch_more_refusal` gives a reason.
    """
    refusal = fetch_more_refusal(name, home)
    if refusal is not None:
        raise OpticaError(
            f"Fetch More is not available for {name}.",
            why=refusal,
            fix=f"Fetch it again from the start: optica fetch --classes {name}",
        )
    staged = next((s for s in staged_classes(home) if s.name == name), None)
    existing = staged.images if staged is not None else 0
    target = ResolvedClass(name, [name], per_query=existing + count)
    return fetch_class(target, source, downloader, home, on_image=on_image)
