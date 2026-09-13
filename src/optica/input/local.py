"""The Local Adapter: flat folders, organized datasets, and manifests.

Implements plan § "Input & Acquisition" → *Input Manager* (Local Adapter),
*Label mode — detection order* (the folder-shape errors), *``--manifest``*,
*Unreadable images — pre-flight verification*, and Known Constraints on
``dataset/`` and nested subfolders.

User-provided images are **always copied, originals untouched** — a flat
folder's images and a manifest's rows are copied into ``dataset/``, where
conversion and resizing take effect at copy time. An already-organized
``--dataset`` is read in place and never copied, so on that path the per-file
stages only report. Nothing here ever deletes or rewrites a user's file.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Final

from optica.exceptions import OpticaValidationError
from optica.input.classes import (
    LIST_TRUNCATE,
    MIN_CLASSES,
    list_names,
    normalize_class_names,
)
from optica.input.validation import (
    InPlaceReport,
    RejectReason,
    inspect_in_place,
    md5_of,
    process_owned,
    reasons_summary,
    unique_name,
)

__all__ = [
    "CopyReport",
    "LabelState",
    "Manifest",
    "ManifestRow",
    "OrganizedDataset",
    "copy_into_dataset",
    "copy_note",
    "list_files",
    "load_organized_dataset",
    "parse_manifest",
    "preflight",
    "require_flat_folder",
    "subfolders",
]

_JUNK: Final[frozenset[str]] = frozenset({"thumbs.db", "desktop.ini"})
_MANIFEST_EXTENSIONS: Final = (".csv", ".json")


# ---------------------------------------------------------------- folders


def list_files(folder: Path) -> list[Path]:
    """Candidate image files directly inside ``folder``, path-sorted.

    Every regular, non-hidden file is a candidate; pre-flight decides which are
    images. OS litter (``Thumbs.db``, ``desktop.ini``) is skipped so it is not
    reported as an unreadable image the user never put there.
    """
    return sorted(
        entry
        for entry in folder.iterdir()
        if entry.is_file()
        and not entry.name.startswith(".")
        and entry.name.casefold() not in _JUNK
    )


def subfolders(folder: Path) -> list[Path]:
    """Non-hidden directories directly inside ``folder``, name-sorted."""
    return sorted(
        entry
        for entry in folder.iterdir()
        if entry.is_dir() and not entry.name.startswith(".")
    )


def _require_directory(path: Path, flag: str) -> None:
    if not path.exists():
        raise OpticaValidationError(
            f"No folder found at {path}",
            why=f"{flag} names a path that does not exist.",
            fix="Check the path and try again.",
        )
    if not path.is_dir():
        raise OpticaValidationError(
            f"{path} is not a folder.",
            why=f"{flag} expects a directory.",
            fix="Check the path and try again.",
        )


def require_flat_folder(path: Path) -> list[Path]:
    """Return the files of a flat folder, refusing an organized one.

    ``--folder`` expects a flat folder of unlabeled images. One already organized
    into subfolders is an error naming the detected subfolders.

    Raises:
        OpticaValidationError: When the path is missing, not a folder, or
            organized into subfolders.
    """
    _require_directory(path, "--folder")
    folders = subfolders(path)
    if folders:
        shown = ", ".join(f"{folder.name}/" for folder in folders[:LIST_TRUNCATE])
        if len(folders) > LIST_TRUNCATE:
            shown += f" (and {len(folders) - LIST_TRUNCATE} more)"
        raise OpticaValidationError(
            f"{path} appears to already be organized into subfolders: {shown}",
            why="--folder expects a flat folder of unlabeled images.",
            fix=[
                "If your dataset is already organized, use --dataset instead:",
                f"optica train --dataset {path}",
            ],
        )
    return list_files(path)


@dataclass(frozen=True)
class OrganizedDataset:
    """An ``ImageFolder``-shaped dataset, read in place.

    Attributes:
        root: The dataset folder.
        classes: Class folder name to its files, in sorted class order.
    """

    root: Path
    classes: dict[str, list[Path]]

    @property
    def counts(self) -> dict[str, int]:
        """Files per class."""
        return {name: len(files) for name, files in self.classes.items()}


def load_organized_dataset(path: Path, *, flag: str = "--dataset") -> OrganizedDataset:
    """Read an organized dataset, enforcing ``dataset/``'s reserved shape.

    ``dataset/`` is reserved: it must contain class subfolders, and loose images
    placed directly in it are an error rather than being silently
    misinterpreted. Nested subfolders inside a class are a hard error listing
    both resolutions, since flattening and promoting are genuinely different
    actions and silently picking either could misclassify a real dataset.

    Raises:
        OpticaValidationError: A missing path, loose files, a flat folder given
            as a dataset, nested subfolders, unsafe folder names, or fewer than
            two classes.
    """
    _require_directory(path, flag)
    folders = subfolders(path)
    loose = list_files(path)
    if not folders and loose:
        raise OpticaValidationError(
            f"{path} is a flat folder, not an organized dataset.",
            why=f"{flag} expects class subfolders, such as {path / 'cat'} and "
            f"{path / 'dog'}.",
            fix=[
                "To label a flat folder of images, use --folder instead:",
                f"optica label --folder {path} -c cat,dog",
            ],
        )
    if loose:
        raise OpticaValidationError(
            f"Loose files found directly inside {path}: "
            f"{list_names([p.name for p in loose])}",
            why="A dataset folder holds class subfolders only; loose images are not "
            "assigned to any class.",
            fix="Move each image into its class folder, or out of the dataset.",
        )
    if not folders:
        raise OpticaValidationError(
            f"No dataset found at {path}",
            why="Optica expects class subfolders inside this directory.",
            fix=[
                "Run: optica label --folder ./my-images -c cat,dog",
                f"Or create subfolders manually: {path / 'cat'}, {path / 'dog'}",
            ],
        )

    nested_errors: list[str] = []
    for folder in folders:
        nested = subfolders(folder)
        if not nested:
            continue
        shown = ", ".join(f"{sub.name}/" for sub in nested)
        lines = [
            f"Nested subfolders found inside class '{folder.name}' ({shown}) — "
            "unsupported.",
            f"Flatten: move images up into {folder} directly, or",
            "Separate: rename folders as their own top-level classes:",
        ]
        lines.extend(
            f"  {folder / sub.name} → {path / f'{folder.name}_{sub.name}'}"
            for sub in nested
        )
        nested_errors.extend(lines)
    if nested_errors:
        raise OpticaValidationError(nested_errors[0], fix=nested_errors[1:] or None)

    names = normalize_class_names(
        (folder.name for folder in folders), surface=f"the folders in {path}"
    )
    if len(names) < MIN_CLASSES:
        raise OpticaValidationError(
            f"{path} resolves to fewer than {MIN_CLASSES} classes. "
            f"Got: {', '.join(names)}",
            why="Training on fewer than 2 classes is meaningless.",
            fix=f"Add at least one more class folder inside {path}.",
        )
    return OrganizedDataset(path, {folder.name: list_files(folder) for folder in folders})


# ------------------------------------------------------------- pre-flight


def preflight(paths: Sequence[Path]) -> tuple[list[Path], list[InPlaceReport]]:
    """Run the per-file stages on user-provided files, writing nothing.

    Unreadable files are dropped from the run, left untouched on disk, and
    returned so the caller can list each with its reason.

    Returns:
        ``(readable, unreadable_reports)``.

    Raises:
        OpticaValidationError: When **no** file is readable — the only shortfall
            determinable before the browser opens.
    """
    readable: list[Path] = []
    unreadable: list[InPlaceReport] = []
    for path in paths:
        report = inspect_in_place(path)
        if report.readable:
            readable.append(path)
        else:
            unreadable.append(report)
    if paths and not readable:
        raise OpticaValidationError(
            f"None of the {len(paths)} files could be read as images.",
            why="There would be nothing to work with.",
            fix=reasons_summary(unreadable),
        )
    if not paths:
        raise OpticaValidationError(
            "No image files were found.",
            why="There would be nothing to work with.",
            fix="Check the path and try again.",
        )
    return readable, unreadable


# --------------------------------------------------------------- manifest


class LabelState(StrEnum):
    """How much of a manifest is labeled."""

    ALL = "all"
    NONE = "none"
    MIXED = "mixed"


@dataclass(frozen=True)
class ManifestRow:
    """One manifest row, resolved.

    Attributes:
        path: The absolute image path, relative paths resolved against the
            manifest's own directory.
        class_name: The class, or None when the row is unlabeled.
        row: The 1-based data-row number, for error messages.
    """

    path: Path
    class_name: str | None
    row: int


@dataclass
class Manifest:
    """A parsed manifest. Disposable input: never rewritten.

    Attributes:
        source: The manifest file.
        rows: Rows in file order, exact duplicates removed.
        content_hash: SHA-256 of the file's bytes, for the session ID.
        has_class_column: Whether a ``class`` column exists at all.
        header: The columns found, for the missing-column error.
        duplicates_removed: Exact duplicate rows dropped.
    """

    source: Path
    rows: list[ManifestRow]
    content_hash: str
    has_class_column: bool
    header: list[str] = field(default_factory=list)
    duplicates_removed: int = 0

    @property
    def label_state(self) -> LabelState:
        """Whether every row, no row, or some rows carry a class."""
        labeled = sum(1 for row in self.rows if row.class_name is not None)
        if labeled == 0:
            return LabelState.NONE
        return LabelState.ALL if labeled == len(self.rows) else LabelState.MIXED

    @property
    def classes(self) -> list[str]:
        """Distinct classes, in first-appearance order."""
        seen: dict[str, None] = {}
        for row in self.rows:
            if row.class_name is not None:
                seen.setdefault(row.class_name, None)
        return list(seen)

    def require_consistent(self) -> None:
        """Refuse a mixed manifest, naming the unlabeled rows.

        V1 keeps a flat hard error: the partial-label flow is post-V1.
        """
        if self.label_state is not LabelState.MIXED:
            return
        unlabeled = [str(row.row) for row in self.rows if row.class_name is None]
        raise OpticaValidationError(
            f"Manifest {self.source} is partially labeled.",
            why=f"Rows without a class: {list_names(unlabeled)}",
            fix="Give every row a class, or remove the class column entirely to label "
            "them all in the browser.",
        )

    def require_fully_labeled(self) -> None:
        """Refuse a manifest that is not fully labeled.

        A missing ``class`` column is reported with what the header row held,
        with no judgement about which column was meant.
        """
        if not self.has_class_column:
            raise OpticaValidationError(
                "Manifest is missing the 'class' column.",
                why=f"The first row was read as the header. Found: "
                f"{', '.join(self.header) or '(nothing)'} — rename the intended column "
                "to 'class' and try again.",
            )
        self.require_consistent()
        if self.label_state is LabelState.NONE:
            raise OpticaValidationError(
                f"Manifest {self.source} has no labeled rows.",
                why="Training needs every row to carry a class.",
                fix=f"Label it first: optica label --manifest {self.source} -c cat,dog",
            )

    def require_unlabeled_for_label(self) -> None:
        """Refuse a fully labeled manifest passed to ``optica label``.

        A hard error, not a correction pass.
        """
        self.require_consistent()
        if self.rows and self.label_state is LabelState.ALL:
            raise OpticaValidationError(
                f"Manifest {self.source} is already fully labeled.",
                why="optica label labels unlabeled images; this manifest has nothing "
                "left "
                "to label.",
                fix=f"Train on it directly: optica train --manifest {self.source}",
            )


_URL: Final = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]+://")


def _is_url(value: str) -> bool:
    # A scheme of two or more characters, so a Windows drive path (`C:\x`,
    # `C:/x`) is never mistaken for one.
    return bool(_URL.match(value))


def parse_manifest(path: Path) -> Manifest:
    """Read a CSV or JSON manifest.

    Format is decided by extension, never by sniffing. CSV requires a header row
    and is read with ``csv.DictReader`` semantics. JSON is an array of objects.
    ``path`` and ``class`` are the only accepted column names, matched
    case-insensitively with surrounding whitespace trimmed; other columns are
    ignored. Relative paths resolve against the manifest's own directory. URLs
    are unsupported in V1. Exact duplicate rows collapse; the same path under two
    classes is a hard error. Class names go through both class-name rules.

    Raises:
        OpticaValidationError: For every manifest-shape violation.
    """
    if path.suffix.lower() not in _MANIFEST_EXTENSIONS:
        raise OpticaValidationError(
            f"{path} is not a .csv or .json manifest.",
            why="Manifest format is decided by extension, and only .csv and .json are "
            "supported.",
            fix="Rename the file with the extension that matches its contents.",
        )
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise OpticaValidationError(
            f"No manifest found at {path}",
            why="--manifest names a file that does not exist.",
            fix="Check the path and try again.",
        ) from exc
    except OSError as exc:
        raise OpticaValidationError(
            f"Could not read the manifest at {path}",
            why=f"{type(exc).__name__}: {exc}",
        ) from exc

    content_hash = hashlib.sha256(raw).hexdigest()
    records, header = (
        _read_csv(path, raw) if path.suffix.lower() == ".csv" else _read_json(path, raw)
    )
    columns = {name.strip().casefold() for name in header}
    if "path" not in columns:
        raise OpticaValidationError(
            "Manifest is missing the 'path' column.",
            why=f"The first row was read as the header. Found: "
            f"{', '.join(h.strip() for h in header) or '(nothing)'} — rename the "
            "intended "
            "column to 'path' and try again.",
        )
    has_class = "class" in columns
    # Keys are normalized per record, so JSON objects that spell a column
    # differently from one another (`path`, `Path`) still agree.
    records = [{str(k).strip().casefold(): v for k, v in r.items()} for r in records]

    base = path.parent.resolve()
    rows: list[ManifestRow] = []
    by_path: dict[Path, ManifestRow] = {}
    url_rows: list[str] = []
    contradictions: list[str] = []
    duplicates = 0
    for number, record in enumerate(records, start=1):
        value = str(record.get("path") or "").strip()
        if not value:
            raise OpticaValidationError(
                f"Manifest row {number} has an empty 'path'.",
                why="Every row must name an image file.",
            )
        if _is_url(value):
            url_rows.append(str(number))
            continue
        raw_class = record.get("class")
        class_name = str(raw_class).strip() if raw_class is not None else ""
        candidate = Path(value)
        resolved = (candidate if candidate.is_absolute() else base / candidate).resolve()
        row = ManifestRow(resolved, class_name or None, number)
        previous = by_path.get(row.path)
        if previous is not None:
            if previous.class_name == row.class_name:
                duplicates += 1
                continue
            contradictions.append(
                f"rows {previous.row} and {row.row}: {row.path} is both "
                f"{previous.class_name or '(unlabeled)'} and "
                f"{row.class_name or '(unlabeled)'}"
            )
            continue
        by_path[row.path] = row
        rows.append(row)

    if url_rows:
        raise OpticaValidationError(
            f"URLs are not supported in manifests in V1 (rows {list_names(url_rows)}).",
            why="A manifest is local input: every path must name a file on this machine.",
            fix="Download the images first and point the manifest at the local copies.",
        )
    if contradictions:
        raise OpticaValidationError(
            "The manifest assigns the same image to two different classes.",
            why="Which class is right cannot be guessed, and picking one would poison "
            "the dataset.",
            fix=contradictions[:LIST_TRUNCATE],
        )

    manifest = Manifest(
        source=path,
        rows=rows,
        content_hash=content_hash,
        has_class_column=has_class,
        header=[h.strip() for h in header],
        duplicates_removed=duplicates,
    )
    if manifest.classes:
        normalize_class_names(manifest.classes, surface="the manifest's class column")
    return manifest


def _read_csv(path: Path, raw: bytes) -> tuple[list[dict[str, object]], list[str]]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise OpticaValidationError(
            f"The manifest at {path} is not UTF-8 text.",
            why=str(exc),
            fix="Save it as UTF-8 and try again.",
        ) from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    header = list(reader.fieldnames or [])
    try:
        records: list[dict[str, object]] = [dict(record) for record in reader]
    except csv.Error as exc:
        raise OpticaValidationError(
            f"The manifest at {path} is not valid CSV.", why=str(exc)
        ) from exc
    return records, header


def _read_json(path: Path, raw: bytes) -> tuple[list[dict[str, object]], list[str]]:
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OpticaValidationError(
            f"The manifest at {path} is not valid JSON.", why=str(exc)
        ) from exc
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise OpticaValidationError(
            f"The manifest at {path} is not a JSON array of objects.",
            why='Expected: [{"path": "img.jpg", "class": "cat"}, ...]',
        )
    header: dict[str, None] = {}
    for item in data:
        for key in item:
            header.setdefault(str(key), None)
    records = [{str(k): v for k, v in item.items()} for item in data]
    return records, list(header)


# -------------------------------------------------------------------- copy


@dataclass
class CopyReport:
    """What a copy into ``dataset/`` did. Nothing is silent.

    Attributes:
        copied: Images written, per class.
        renamed: Files written under an ``_x`` suffix after a name collision.
        converted: Files converted to a targeted format.
        resized: Files upscaled to the size threshold (a quality warning).
        duplicates: Byte-identical files excluded within a class.
        unreadable: User-provided files that could not be read, with reasons.
    """

    copied: dict[str, int] = field(default_factory=dict)
    renamed: int = 0
    converted: int = 0
    resized: int = 0
    duplicates: dict[str, int] = field(default_factory=dict)
    unreadable: list[InPlaceReport] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Images written across all classes."""
        return sum(self.copied.values())


def copy_note(sources: Iterable[Path], destination: Path) -> str:
    """The disk-usage note shown at copy time.

    ``Copying 1,200 images (2.3 GB) to dataset/ — originals untouched``.
    Storage duplication at scale is the real cost of copying rather than
    linking, so it is surfaced rather than hidden.
    """
    count = 0
    size = 0
    for source in sources:
        count += 1
        try:
            size += source.stat().st_size
        except OSError:
            continue
    return (
        f"Copying {count:,} image{'s' if count != 1 else ''} ({_human(size)}) to "
        f"{destination.name}/ — originals untouched"
    )


def _human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1000 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1000
    return f"{value:.1f} GB"  # pragma: no cover - loop always returns


def copy_into_dataset(items: Sequence[tuple[Path, str]], destination: Path) -> CopyReport:
    """Copy user-provided images into ``destination/<class>/``.

    The one copy mechanism ``--folder`` labeling output and manifest
    materialization share. Conversion and resizing take effect **here**, at copy
    time, on Optica's own copy. Target names are post-conversion names, and
    collisions resolve by deterministic ``_x`` suffixing in the order given.
    MD5 deduplication runs within each class; a byte-identical file is excluded,
    never written.

    The caller has already run the ``dataset/`` conflict check.

    Args:
        items: ``(source, class)`` pairs, in row order.
        destination: The dataset folder.

    Returns:
        What was done, including every unreadable source with its reason.
    """
    report = CopyReport()
    taken: dict[str, set[str]] = {}
    hashes: dict[str, set[str]] = {}
    for source, class_name in items:
        try:
            data = source.read_bytes()
        except OSError:
            report.unreadable.append(InPlaceReport(source, RejectReason.UNOPENABLE))
            continue
        processed = process_owned(data)
        if isinstance(processed, RejectReason):
            report.unreadable.append(InPlaceReport(source, processed))
            continue

        digest = md5_of(processed.data)
        class_hashes = hashes.setdefault(class_name, set())
        if digest in class_hashes:
            report.duplicates[class_name] = report.duplicates.get(class_name, 0) + 1
            continue
        class_hashes.add(digest)

        folder = destination / class_name
        folder.mkdir(parents=True, exist_ok=True)
        names = taken.setdefault(class_name, set())
        wanted = f"{source.stem}{processed.extension}"
        name = unique_name(wanted, names)
        if name != wanted:
            report.renamed += 1
        (folder / name).write_bytes(processed.data)
        report.copied[class_name] = report.copied.get(class_name, 0) + 1
        report.converted += int(processed.converted)
        report.resized += int(processed.resized)
    return report
