"""Staging session stores: ``labeling/<session_id>.json`` and ``curation.json``.

Implements plan § "Labeling & Curation" → *Staging shapes* and *Deletion,
staging, and interruption*.

Two of the three staging shapes are state files, and both live here. The third
— auto-fetch staging — is a directory of images whose shape is the layout
itself, and belongs to the Fetch and Curation Adapters.

Both files are written on every decision by writing a temp file beside the
target and moving it into place in one OS operation, the same atomicity export
uses. Neither is ever partially recovered: a file that cannot be read, cannot be
parsed, or carries a version this build does not recognize is a hard error in
its own subsystem's class, naming the path and the remedy.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

from optica.exceptions import OpticaCurationError, OpticaError, OpticaLabelingError

__all__ = [
    "SESSION_VERSION",
    "CurationSession",
    "LabelingSession",
    "SourceType",
    "atomic_write_json",
    "labeling_dir",
    "load_curation",
    "load_labeling",
    "session_id",
    "staging_root",
]

SESSION_VERSION: Final = 1


def staging_root(home: Path | None = None) -> Path:
    """``~/.optica/staging/``. Not created here."""
    return (home or Path.home()) / ".optica" / "staging"


def labeling_dir(home: Path | None = None) -> Path:
    """``~/.optica/staging/labeling/``."""
    return staging_root(home) / "labeling"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` to ``path`` so the file is either old or new, never half.

    The temp file is created in the target's own directory, because a rename is
    atomic only within one filesystem.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def _read_json(path: Path, error: type[OpticaError], what: str) -> dict[str, Any]:
    fix = f"Delete {path} and start fresh — that session's progress will be lost."
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise error(
            f"The {what} at {path} could not be read.",
            why=f"{type(exc).__name__}: {exc}",
            fix=fix,
        ) from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise error(
            f"The {what} at {path} is corrupt.",
            why=f"It is not valid JSON ({exc.msg}, line {exc.lineno}).",
            fix=fix,
        ) from exc
    if not isinstance(data, dict):
        raise error(
            f"The {what} at {path} is corrupt.",
            why="It does not hold a JSON object.",
            fix=fix,
        )
    version = data.get("version")
    if version != SESSION_VERSION:
        # The field exists to be checked. In V1 only version 1 exists.
        raise error(
            f"The {what} at {path} has an unrecognized version: {version!r}.",
            why=f"This build of Optica reads version {SESSION_VERSION} only.",
            fix=fix,
        )
    return data


def _corrupt(error: type[OpticaError], what: str, path: Path, detail: str) -> OpticaError:
    return error(
        f"The {what} at {path} is corrupt.",
        why=detail,
        fix=f"Delete {path} and start fresh — that session's progress will be lost.",
    )


# ------------------------------------------------------------------ labeling


class SourceType(StrEnum):
    """What a labeling session labels."""

    FOLDER = "folder"
    MANIFEST = "manifest"


def session_id(source: Path, content_hash: str | None = None) -> str:
    """The digest naming a labeling session file.

    A folder path cannot be a filename, so the ID digests the identifying inputs:
    the resolved source path, plus the manifest's content hash where the source
    is a manifest — so a modified manifest starts a fresh session automatically
    (Implementation Note 14). ``-c`` is **never** part of it, which is what lets
    a corrected class list resume the same session.
    """
    digest = hashlib.sha256()
    digest.update(str(source.resolve()).encode("utf-8"))
    if content_hash is not None:
        digest.update(b"\0")
        digest.update(content_hash.encode("ascii"))
    return digest.hexdigest()[:16]


class EntryState(StrEnum):
    """A recorded decision about one image. Absence means *not yet reached*."""

    LABELED = "labeled"
    SKIPPED = "skipped"


@dataclass
class LabelingSession:
    """One labeling session, as stored on disk.

    Attributes:
        path: Where the file lives.
        source: The folder or manifest path, readable, recorded for
            ``config --clear-staging`` to list.
        source_type: Folder or manifest.
        classes: The class list. May grow and be renamed by the fast-follow live
            class definition without a shape change.
        entries: Per-image decisions keyed by absolute path. Assignments
            reference classes by **name**.
        position: The path last shown, not an index, so files added or removed
            between sessions shift nothing.
        auto_advance: The session-local checkbox. Never written to config.
        created: ISO-8601 timestamp.
        updated: ISO-8601 timestamp.
    """

    path: Path
    source: str
    source_type: SourceType
    classes: list[str]
    entries: dict[str, dict[str, str]] = field(default_factory=dict)
    position: str | None = None
    auto_advance: bool = True
    created: str = field(default_factory=_now)
    updated: str = field(default_factory=_now)

    @classmethod
    def new(
        cls,
        home: Path | None,
        source: Path,
        source_type: SourceType,
        classes: Sequence[str],
        content_hash: str | None = None,
    ) -> LabelingSession:
        """Create (but do not write) a session for ``source``."""
        path = labeling_dir(home) / f"{session_id(source, content_hash)}.json"
        return cls(path, str(source.resolve()), source_type, list(classes))

    def to_json(self) -> dict[str, Any]:
        """The on-disk shape, ``version`` first."""
        return {
            "version": SESSION_VERSION,
            "source": self.source,
            "source_type": self.source_type.value,
            "created": self.created,
            "updated": self.updated,
            "classes": list(self.classes),
            "auto_advance": self.auto_advance,
            "position": self.position,
            "entries": self.entries,
        }

    def save(self) -> None:
        """Rewrite the file in full, atomically. Called after every image."""
        self.updated = _now()
        atomic_write_json(self.path, self.to_json())

    # -- decisions -------------------------------------------------------

    def assign(self, image: str, class_name: str) -> None:
        """Record ``image`` as labeled into ``class_name``."""
        if class_name not in self.classes:
            raise ValueError(f"{class_name!r} is not one of this session's classes")
        self.entries[image] = {"state": EntryState.LABELED.value, "class": class_name}
        self.position = image

    def skip(self, image: str) -> None:
        """Record ``image`` as skipped — a recorded state, not a gap."""
        self.entries[image] = {"state": EntryState.SKIPPED.value}
        self.position = image

    def adopt_classes(self, new_classes: Sequence[str]) -> int:
        """Adopt a corrected class list, returning how many entries departed.

        Every entry assigned to a departing class is deleted. Absence already
        means *not yet reached*, so those images return to the queue with no new
        state introduced.
        """
        keep = set(new_classes)
        departing = [
            image
            for image, entry in self.entries.items()
            if entry.get("state") == EntryState.LABELED and entry.get("class") not in keep
        ]
        for image in departing:
            del self.entries[image]
        self.classes = list(new_classes)
        return len(departing)

    def classes_disagree(self, requested: Sequence[str]) -> bool:
        """Whether ``-c`` disagrees with the stored list — a conflict, not an override."""
        return list(requested) != list(self.classes)

    # -- derived ---------------------------------------------------------

    def resume_index(self, images: Sequence[str]) -> int | None:
        """Where a resumed session continues, in path-sorted ``images``.

        The first unlabeled image **at or after** ``position`` in path order.
        That one rule also covers a recorded file that has since been removed:
        the next unlabeled entry is simply the one that follows it. Returns None
        when nothing remains, which means the session is complete.
        """
        ordered = sorted(images)
        start = 0
        if self.position is not None:
            start = next(
                (i for i, p in enumerate(ordered) if p >= self.position), len(ordered)
            )
        for index in range(start, len(ordered)):
            if ordered[index] not in self.entries:
                return index
        return None

    def counts(self) -> dict[str, int]:
        """Labeled images per class, in class-list order."""
        counts = dict.fromkeys(self.classes, 0)
        for entry in self.entries.values():
            if entry.get("state") == EntryState.LABELED and entry.get("class") in counts:
                counts[entry["class"]] += 1
        return counts

    def unlabeled_split(self, images: Iterable[str]) -> tuple[int, int]:
        """``(skipped, not_yet_reached)`` — the Finish confirmation's two causes."""
        skipped = unreached = 0
        for image in images:
            entry = self.entries.get(image)
            if entry is None:
                unreached += 1
            elif entry.get("state") == EntryState.SKIPPED:
                skipped += 1
        return skipped, unreached


def load_labeling(path: Path) -> LabelingSession:
    """Read a labeling session file.

    Raises:
        OpticaLabelingError: If it is unreadable, corrupt, or an unrecognized
            version — a hard error, not a recoverable prompt.
    """
    what = "labeling session file"
    data = _read_json(path, OpticaLabelingError, what)
    try:
        source_type = SourceType(data["source_type"])
        classes = data["classes"]
        entries = data.get("entries", {})
        if not isinstance(classes, list) or not all(isinstance(c, str) for c in classes):
            raise TypeError("classes must be a list of names")
        if not isinstance(entries, dict):
            raise TypeError("entries must be an object")
        for entry in entries.values():
            state = EntryState(entry["state"])
            if state is EntryState.LABELED and not isinstance(entry.get("class"), str):
                raise TypeError("a labeled entry must name its class")
        return LabelingSession(
            path=path,
            source=str(data["source"]),
            source_type=source_type,
            classes=list(classes),
            entries={str(k): dict(v) for k, v in entries.items()},
            position=data.get("position"),
            auto_advance=bool(data.get("auto_advance", True)),
            created=str(data.get("created", "")),
            updated=str(data.get("updated", "")),
        )
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise _corrupt(
            OpticaLabelingError, what, path, f"Unexpected shape: {exc}"
        ) from exc


# ------------------------------------------------------------------ curation


@dataclass
class CurationSession:
    """``~/.optica/staging/curation.json`` — the one curation session.

    Records **deselected** paths rather than selected ones: the smaller set, and
    images added by Fetch More then default to selected with no special case.

    Attributes:
        path: Where the file lives.
        deselected: Deselected image paths, per class.
        active_class: The tab or dropdown entry last shown.
        created: ISO-8601 timestamp.
        updated: ISO-8601 timestamp.
    """

    path: Path
    deselected: dict[str, list[str]] = field(default_factory=dict)
    active_class: str | None = None
    created: str = field(default_factory=_now)
    updated: str = field(default_factory=_now)

    @classmethod
    def at(cls, home: Path | None = None) -> Path:
        """The file's path."""
        return staging_root(home) / "curation.json"

    def to_json(self) -> dict[str, Any]:
        """The on-disk shape."""
        return {
            "version": SESSION_VERSION,
            "created": self.created,
            "updated": self.updated,
            "deselected": self.deselected,
            "active_class": self.active_class,
        }

    def save(self) -> None:
        """Rewrite atomically. Called on every toggle."""
        self.updated = _now()
        atomic_write_json(self.path, self.to_json())

    def toggle(self, class_name: str, image: str, *, selected: bool) -> None:
        """Record one image's selection state.

        Deselecting writes the image's path as given — the stored form is
        unchanged. Matching, both here and in :meth:`is_selected`, is by class
        and **file name**; see :func:`_file_name`.
        """
        current = self.deselected.setdefault(class_name, [])
        name = _file_name(image)
        matching = [entry for entry in current if _file_name(entry) == name]
        if selected:
            for entry in matching:
                current.remove(entry)
        elif not matching:
            current.append(image)

    def is_selected(self, class_name: str, image: str) -> bool:
        """Selected is the default; only deselections are stored."""
        name = _file_name(image)
        return all(
            _file_name(entry) != name for entry in self.deselected.get(class_name, [])
        )


def _file_name(path: str) -> str:
    """The last component of a stored path, whichever separator it was written with.

    A deselection is matched by class and file name, not by full path.
    ``fetch_class`` renames a class directory between ``<class>.partial/`` and
    ``<class>/`` whenever a fetch completes or tops up, so a full-path match
    would silently reselect every image deselected before the rename. Staged
    file names are sequence-numbered and unique within a class, which is what
    makes the name a sufficient key. Provisional — ``notes/build-log.md``,
    "Stored deselections are matched by class and file name".
    """
    return path.replace("\\", "/").rsplit("/", 1)[-1]


def load_curation(path: Path) -> CurationSession:
    """Read ``curation.json``.

    Raises:
        OpticaCurationError: If it is unreadable, corrupt, or an unrecognized
            version.
    """
    what = "curation session file"
    data = _read_json(path, OpticaCurationError, what)
    try:
        deselected = data.get("deselected", {})
        if not isinstance(deselected, dict):
            raise TypeError("deselected must be an object")
        clean: dict[str, list[str]] = {}
        for name, paths in deselected.items():
            if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
                raise TypeError(f"deselected[{name!r}] must be a list of paths")
            clean[str(name)] = list(paths)
        active = data.get("active_class")
        if active is not None and not isinstance(active, str):
            raise TypeError("active_class must be a name or null")
        return CurationSession(
            path=path,
            deselected=clean,
            active_class=active,
            created=str(data.get("created", "")),
            updated=str(data.get("updated", "")),
        )
    except (TypeError, ValueError, AttributeError) as exc:
        raise _corrupt(
            OpticaCurationError, what, path, f"Unexpected shape: {exc}"
        ) from exc
