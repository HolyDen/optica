"""What the curation page decides.

Implements plan § "Labeling & Curation" → *Curation Server* → *Browser UI
(curate)*: click-to-toggle, Select All / Deselect All, per-class **tabs (6 or
fewer classes with short names) or a dropdown (7+ classes, or any name over 20
characters)**, the low-selection warning (under 30% of fetched images selected,
or fewer than 10) with its "Fetch More" banner — advisory only, Confirm stays
active — and Confirm disabled only by a class with **zero** selected; and
*Staging shapes* → ``curation.json``, written on every toggle.

The thresholds, the Confirm gate and the stored deselections belong to
:mod:`optica.input.curation` and :mod:`optica.input.sessions`; this module calls
them and does not restate them. **Every toggle goes through**
:meth:`CurationSession.save <optica.input.sessions.CurationSession.save>`.
Curation has no manifest; nothing here writes ``dataset/``, which the terminal
does after Confirm.

No FastAPI here, so this runs in CI.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

from optica.exceptions import OpticaError
from optica.input.curation import (
    CurationView,
    confirm_blocked_classes,
    fetch_more_refusal,
    fetch_more_shortfall,
    selected_counts,
    selection_warnings,
)
from optica.input.fetch import ClassFetchReport
from optica.input.sessions import CurationSession

__all__ = [
    "TAB_MAX_CLASSES",
    "TAB_MAX_NAME_LENGTH",
    "CurationController",
    "FetchMore",
    "confirm_hint",
    "navigation_for",
]

TAB_MAX_CLASSES: Final = 6
"""Tabs for up to 6 classes. Curation's own threshold — labeling's radio 2-5 /
dropdown 6+ is a different UI and is not harmonized."""

TAB_MAX_NAME_LENGTH: Final = 20
"""Any class name longer than this switches to the dropdown."""

FetchMore = Callable[[str, int, Callable[[], None]], ClassFetchReport]
"""Fetch ``count`` more images for a class, calling back once per image staged."""


def navigation_for(names: list[str]) -> str:
    """``tabs`` for 6 or fewer classes with short names, otherwise ``dropdown``."""
    short = all(len(name) <= TAB_MAX_NAME_LENGTH for name in names)
    return "tabs" if len(names) <= TAB_MAX_CLASSES and short else "dropdown"


def confirm_hint(blocked: list[str]) -> str | None:
    """The reason beside a disabled Confirm, or None when it is enabled."""
    if not blocked:
        return None
    return f"Select at least one image in {', '.join(blocked)} to confirm."


class CurationController:
    """The curation page's state, over ``curation.json`` and auto-fetch staging.

    Args:
        view: Staged images per class, from :func:`optica.input.curation.load_view`.
        session: The curation session, new or resumed.
        images_per_class: What Fetch More restores a class's selection to.
        reload: Re-reads staging after a fetch.
        fetch_more: Runs a fetch for one class, or None where fetching is not
            possible.
    """

    page: Final = "curation"

    def __init__(
        self,
        view: CurationView,
        session: CurationSession,
        images_per_class: int,
        *,
        reload: Callable[[], CurationView] | None = None,
        fetch_more: FetchMore | None = None,
    ) -> None:
        self.view = view
        self.session = session
        self.images_per_class = images_per_class
        self._reload = reload
        self._fetch_more = fetch_more
        self._lock = threading.RLock()
        self.fetching: dict[str, Any] | None = None
        self.last_fetch: dict[str, Any] | None = None
        self.finished = False
        if self.session.active_class not in self.view.images:
            self.session.active_class = self.names[0]

    # -- reads ------------------------------------------------------------

    @property
    def names(self) -> list[str]:
        """Class names, in staging's sorted order."""
        return list(self.view.images)

    def _class(self, class_index: int) -> str:
        names = self.names
        if not 0 <= class_index < len(names):
            raise ValueError(f"class index {class_index} is out of range")
        return names[class_index]

    def image_path(self, image_id: str) -> Path | None:
        """The file for ``<class index>/<image index>``.

        None while that class is being fetched into: its directory is renamed to
        ``.partial`` for the duration.
        """
        class_part, _, image_part = image_id.partition("/")
        if not (class_part.isdigit() and image_part.isdigit()):
            return None
        with self._lock:
            names = self.names
            class_index, image_index = int(class_part), int(image_part)
            if class_index >= len(names):
                return None
            name = names[class_index]
            if self.fetching is not None and self.fetching["class"] == name:
                return None
            paths = self.view.images[name]
            return paths[image_index] if image_index < len(paths) else None

    def selected(self) -> dict[str, int]:
        """Selected images per class."""
        return selected_counts(self.view, self.session)

    def state(self) -> dict[str, Any]:
        """Everything the page renders."""
        with self._lock:
            names = self.names
            fetched = self.view.fetched
            selected = self.selected()
            warnings = selection_warnings(fetched, selected)
            blocked = confirm_blocked_classes(selected)
            active = self.session.active_class
            if active not in names:
                active = names[0]
            active_index = names.index(active)
            classes = []
            for index, name in enumerate(names):
                shortfall = fetch_more_shortfall(self.images_per_class, selected[name])
                refusal = fetch_more_refusal(name) if self._fetch_more else None
                classes.append(
                    {
                        "index": index,
                        "name": name,
                        "fetched": fetched[name],
                        "selected": selected[name],
                        "warnings": [w.message for w in warnings if w.class_name == name],
                        "fetch_more": {
                            "available": self._fetch_more is not None
                            and refusal is None
                            and shortfall > 0,
                            "count": shortfall,
                            "unavailable_reason": refusal,
                        },
                        "incomplete_fetch": name in self.view.incomplete,
                    }
                )
            hint = confirm_hint(blocked)
            if self.fetching is not None:
                hint = f"Wait for the fetch for {self.fetching['class']} to finish."
            return {
                "classes": classes,
                "navigation": navigation_for(names),
                "active": active_index,
                "images": [
                    {
                        "id": f"{active_index}/{i}",
                        "name": path.name,
                        "selected": self.session.is_selected(active, str(path)),
                    }
                    for i, path in enumerate(self.view.images[active])
                ],
                "confirm": {
                    "enabled": not blocked and self.fetching is None,
                    "hint": hint,
                },
                "fetching": self.fetching,
                "last_fetch": self.last_fetch,
                "incomplete": list(self.view.incomplete),
                "finished": self.finished,
            }

    # -- decisions --------------------------------------------------------

    def _path(self, name: str, image_index: int) -> Path:
        paths = self.view.images[name]
        if not 0 <= image_index < len(paths):
            raise ValueError(f"image index {image_index} is out of range")
        return paths[image_index]

    def toggle(
        self, class_index: int, image_index: int, *, selected: bool
    ) -> dict[str, Any]:
        """Select or deselect one image, written to ``curation.json`` at once."""
        with self._lock:
            name = self._class(class_index)
            path = self._path(name, image_index)
            self.session.toggle(name, str(path), selected=selected)
            self.session.save()
        return self.state()

    def set_all(self, class_index: int, *, selected: bool) -> dict[str, Any]:
        """Select All / Deselect All for one class, as one write."""
        with self._lock:
            name = self._class(class_index)
            for path in self.view.images[name]:
                self.session.toggle(name, str(path), selected=selected)
            self.session.save()
        return self.state()

    def set_active(self, class_index: int) -> dict[str, Any]:
        """Switch tab or dropdown entry. Recorded, so a resume opens on it."""
        with self._lock:
            self.session.active_class = self._class(class_index)
            self.session.save()
        return self.state()

    def start_fetch_more(self, class_index: int) -> dict[str, Any]:
        """Fetch enough to restore ``images_per_class`` selected, in the background.

        Advisory, like the banner it belongs to: the rest of the page keeps
        working, and only Confirm waits for it.

        Raises:
            ValueError: When fetching is unavailable, already running, or would
                request nothing.
        """
        with self._lock:
            name = self._class(class_index)
            if self._fetch_more is None:
                raise ValueError("Fetch More is not available in this session.")
            if self.fetching is not None:
                raise ValueError(
                    f"A fetch for {self.fetching['class']} is already running."
                )
            refusal = fetch_more_refusal(name)
            if refusal is not None:
                raise ValueError(refusal)
            count = fetch_more_shortfall(self.images_per_class, self.selected()[name])
            if count == 0:
                raise ValueError(
                    f"{name} already has {self.images_per_class} or more images selected."
                )
            self.fetching = {"class": name, "requested": count, "delivered": 0}
            fetcher = self._fetch_more
        worker = threading.Thread(
            target=self._run_fetch,
            args=(fetcher, name, count),
            name="optica-fetch-more",
            daemon=True,
        )
        worker.start()
        return self.state()

    def _run_fetch(self, fetcher: FetchMore, name: str, count: int) -> None:
        def on_image() -> None:
            with self._lock:
                if self.fetching is not None:
                    self.fetching["delivered"] += 1

        outcome: dict[str, Any] = {"class": name, "requested": count}
        try:
            report = fetcher(name, count, on_image)
            outcome.update(delivered=report.delivered, error=None)
        except OpticaError as exc:
            outcome.update(delivered=0, error=exc.message)
        except Exception as exc:  # noqa: BLE001 - shown on the page, not a crash
            outcome.update(delivered=0, error=f"{type(exc).__name__}: {exc}")
        with self._lock:
            if self._reload is not None:
                try:
                    self.view = self._reload()
                except OpticaError as exc:
                    outcome["error"] = exc.message
            self.fetching = None
            self.last_fetch = outcome

    def confirm(self) -> dict[str, Any]:
        """Confirm, if no class has zero images selected and no fetch is running.

        The low-selection warning never blocks this; the mass-rejection prompt
        that follows in the terminal is where those thresholds are asked about.

        Returns:
            ``{"status": "blocked", "hint": …}`` or ``{"status": "finished"}``,
            each with ``state``.
        """
        with self._lock:
            blocked = confirm_blocked_classes(self.selected())
            if blocked or self.fetching is not None:
                state = self.state()
                return {
                    "status": "blocked",
                    "hint": state["confirm"]["hint"],
                    "state": state,
                }
            self.finished = True
        return {"status": "finished", "state": self.state()}
