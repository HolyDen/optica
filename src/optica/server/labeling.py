"""What the labeling page decides.

Implements plan § "Labeling & Curation" → *Labeling UI*: the class widget
(radio buttons for 2-5 classes, a dropdown for 6+), *"Finish" gating* on both
conditions at once, *The labeling interaction* (Assign, Next, Back, Finish,
auto-advance), and *Finish with images left unlabeled*; and *Staging shapes* →
the labeling session file, which every decision is written through as it
happens.

**Every decision goes through** :meth:`LabelingSession.save
<optica.input.sessions.LabelingSession.save>` — the session file under
``~/.optica/staging/labeling/``. Nothing here writes a manifest, which is
disposable input whose content hash is part of the session ID; and nothing here
writes ``dataset/``, which the terminal does after Finish.

No FastAPI here: the routes are a thin layer over this, and this runs in CI.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from optica.input.classes import LIST_TRUNCATE, MIN_CLASSES
from optica.input.sessions import EntryState, LabelingSession
from optica.input.validation import HARD_FLOOR, InPlaceReport

__all__ = [
    "RADIO_MAX_CLASSES",
    "LabelingController",
    "finish_hint",
    "unlabeled_message",
    "widget_for",
]

RADIO_MAX_CLASSES: Final = 5
"""Radio buttons for 2-5 classes, a dropdown for 6+. Labeling's own threshold —
curation's tabs/dropdown threshold is a different UI and is not harmonized."""


def widget_for(class_count: int) -> str:
    """``radio`` or ``dropdown``, fixed at load in V1."""
    return "radio" if class_count <= RADIO_MAX_CLASSES else "dropdown"


def _images(count: int) -> str:
    return f"{count} image{'s' if count != 1 else ''}"


def finish_hint(classes: Sequence[str], counts: dict[str, int]) -> str | None:
    """The persistent hint beside a disabled Finish, or None when Finish is enabled.

    Finish is gated on **both** conditions — fewer than 2 classes, or any class
    below the 5-image floor — and when both are unmet the hint states both at
    once, never one after the other.
    """
    parts: list[str] = []
    if len(classes) < MIN_CLASSES:
        parts.append(f"Labeling needs at least {MIN_CLASSES} classes.")
    short = [name for name in classes if counts.get(name, 0) < HARD_FLOOR]
    if short:
        needs = ", ".join(
            f"{name} needs {HARD_FLOOR - counts.get(name, 0)} more" for name in short
        )
        parts.append(f"Every class needs at least {HARD_FLOOR} images. {needs}.")
    return " ".join(parts) or None


def unlabeled_message(skipped: int, unreached: int) -> str | None:
    """The Finish confirmation, split by cause, or None when nothing is left out.

    ``32 images will not be included: 4 skipped, 28 not yet reached.``
    """
    total = skipped + unreached
    if total == 0:
        return None
    return (
        f"{_images(total)} will not be included: {skipped} skipped, "
        f"{unreached} not yet reached."
    )


class LabelingController:
    """The labeling page's state, over one :class:`LabelingSession`.

    Args:
        session: The session, new or resumed, with its class list already
            settled by the terminal's resume prompt.
        images: The images that passed pre-flight. Ordered by path here,
            deterministically, so the image list is never stored.
        unreadable: What pre-flight dropped, for the first-load notice.
    """

    page: Final = "labeling"

    def __init__(
        self,
        session: LabelingSession,
        images: Sequence[Path],
        unreadable: Sequence[InPlaceReport] = (),
    ) -> None:
        self.session = session
        self.images: list[str] = sorted(str(path) for path in images)
        if not self.images:
            raise ValueError("labeling needs at least one readable image")
        self.unreadable = list(unreadable)
        self.index = self._start_index()
        self.finished = False

    def _start_index(self) -> int:
        # The first unlabeled image at or after `position`; when nothing remains
        # the session is complete, and the page shows where it was left.
        resumed = self.session.resume_index(self.images)
        if resumed is not None:
            return resumed
        position = self.session.position
        if position in self.images:
            return self.images.index(position)
        return len(self.images) - 1

    # -- reads ------------------------------------------------------------

    def image_path(self, image_id: str) -> Path | None:
        """The file for an image ID — its index in the path-sorted list."""
        if not image_id.isdigit():
            return None
        index = int(image_id)
        return Path(self.images[index]) if index < len(self.images) else None

    def counts(self) -> dict[str, int]:
        """Labeled images per class, counting only images in this run.

        An entry for a file that has since gone, or that pre-flight now rejects,
        is not an image this Finish can deliver, so it does not count toward the
        floor.
        """
        counts = dict.fromkeys(self.session.classes, 0)
        for image in self.images:
            entry = self.session.entries.get(image)
            if entry and entry.get("state") == EntryState.LABELED:
                name = entry.get("class")
                if name in counts:
                    counts[name] += 1
        return counts

    def labeled_items(self) -> list[tuple[Path, str]]:
        """``(image, class)`` for every labeled image, in path order."""
        items: list[tuple[Path, str]] = []
        for image in self.images:
            entry = self.session.entries.get(image)
            if entry and entry.get("state") == EntryState.LABELED:
                name = entry.get("class")
                if name in self.session.classes:
                    items.append((Path(image), str(name)))
        return items

    def unlabeled_split(self) -> tuple[int, int]:
        """``(skipped, not yet reached)`` over this run's images."""
        return self.session.unlabeled_split(self.images)

    def state(self) -> dict[str, Any]:
        """Everything the page renders."""
        classes = list(self.session.classes)
        counts = self.counts()
        image = self.images[self.index]
        entry = self.session.entries.get(image) or {}
        skipped, unreached = self.unlabeled_split()
        hint = finish_hint(classes, counts)
        shown = self.unreadable[:LIST_TRUNCATE]
        return {
            "source": self.session.source,
            "classes": classes,
            "widget": widget_for(len(classes)),
            "counts": counts,
            "counts_line": "Classes: "
            + ", ".join(f"{name} ({_images(counts[name])})" for name in classes),
            "total": len(self.images),
            "index": self.index,
            "position": f"{self.index + 1} of {len(self.images)}",
            "at_end": self.index == len(self.images) - 1,
            "image": {
                "id": str(self.index),
                "name": Path(image).name,
                "state": entry.get("state"),
                "class": entry.get("class"),
            },
            "auto_advance": self.session.auto_advance,
            "finish": {"enabled": hint is None, "hint": hint},
            "progress": {
                "labeled": sum(counts.values()),
                "skipped": skipped,
                "not_reached": unreached,
            },
            "unreadable": {
                "count": len(self.unreadable),
                "lines": [f"{report.path}: {report.reason}" for report in shown],
                "more": len(self.unreadable) - len(shown),
            },
            "finished": self.finished,
        }

    # -- decisions --------------------------------------------------------

    def _at(self, index: int) -> str:
        if not 0 <= index < len(self.images):
            raise ValueError(f"image index {index} is out of range")
        return self.images[index]

    def _move(self, index: int) -> None:
        self.index = max(0, min(index, len(self.images) - 1))
        # `position` records the path last shown, not an index.
        self.session.position = self.images[self.index]

    def assign(self, index: int, class_name: str) -> dict[str, Any]:
        """Commit ``class_name`` for the image at ``index``.

        With auto-advance on, move to the next image. After Back, that is the
        image the user came from — the same rule, not a special case.
        """
        image = self._at(index)
        self.session.assign(image, class_name)
        self._move(index + 1 if self.session.auto_advance else index)
        self.session.save()
        return self.state()

    def next(self, index: int) -> dict[str, Any]:
        """Advance. An image left without an assignment is recorded as skipped.

        Always enabled. An image already labeled keeps its label — skipping is
        what Next means for an image with no decision, not an overwrite.
        """
        image = self._at(index)
        if image not in self.session.entries:
            self.session.skip(image)
        self._move(index + 1)
        self.session.save()
        return self.state()

    def back(self, index: int) -> dict[str, Any]:
        """Return to the previous image, its assignment shown."""
        self._at(index)
        self._move(index - 1)
        self.session.save()
        return self.state()

    def set_auto_advance(self, enabled: bool) -> dict[str, Any]:
        """The session-local checkbox. Written to the session, never to config."""
        self.session.auto_advance = enabled
        self.session.save()
        return self.state()

    def finish(self, *, confirmed: bool) -> dict[str, Any]:
        """Finish, if the gate allows it.

        Unlabeled images never block Finish, but are never excluded silently:
        until ``confirmed``, a non-zero split is returned for the page to ask
        about. ``--yes`` does not answer this — whoever presses Finish is present.

        Returns:
            ``{"status": "blocked", "hint": …}``, ``{"status": "confirm",
            "message": …}`` or ``{"status": "finished"}``, each with ``state``.
        """
        hint = finish_hint(self.session.classes, self.counts())
        if hint is not None:
            return {"status": "blocked", "hint": hint, "state": self.state()}
        message = unlabeled_message(*self.unlabeled_split())
        if message is not None and not confirmed:
            return {"status": "confirm", "message": message, "state": self.state()}
        self.finished = True
        return {"status": "finished", "state": self.state()}
