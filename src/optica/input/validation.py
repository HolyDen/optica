"""The image validation pipeline.

Implements plan § "Input & Acquisition" → *Class imbalance and image
validation*, *Unreadable images — pre-flight verification*, and the manifest
section's *Filename collisions* rule, which runs on post-conversion names::

    Per-file        — runs as early as the path allows:
      Format check → Corruption check → Size check
    Class-dependent — runs once classes are assigned:
      MD5 deduplication (within-class)

**Ownership rule: a stage may write only where Optica owns the bytes.** Two
entry points follow from it. :func:`process_owned` takes bytes Optica is about
to write — a download into staging, a copy into ``dataset/`` — and converts and
resizes them. :func:`inspect_in_place` takes a file the user owns and only
reports: a convertible format is used as it stands, an undersized image warns
without being resized, and nothing is ever written or deleted.

There is one corruption check, not two. Pre-flight *is* this pipeline's
per-file stage, placed at the earliest point each path permits.
"""

from __future__ import annotations

import hashlib
import io
import warnings
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Final

from PIL import Image, UnidentifiedImageError

from optica.exceptions import OpticaValidationError
from optica.input.classes import LIST_TRUNCATE, list_names

__all__ = [
    "HARD_FLOOR",
    "IMBALANCE_RATIO",
    "JPEG_QUALITY",
    "SIZE_THRESHOLD",
    "TARGET_EXTENSIONS",
    "Imbalance",
    "InPlaceReport",
    "ProcessedImage",
    "RejectReason",
    "check_floor",
    "check_floor_after_dedupe",
    "find_duplicates",
    "imbalanced_classes",
    "inspect_in_place",
    "md5_of",
    "process_owned",
    "reasons_summary",
    "shortfall",
    "unique_name",
]

SIZE_THRESHOLD: Final = 128
"""Shorter side, in pixels, below which an image is upscaled with a warning.

Half the 224px input of three of the four backbones. Hardcoded in V1, with no
config key, and deliberately not tracking the backbone."""

JPEG_QUALITY: Final = 90
"""Pillow's default is 75, which is visibly lossy on a first re-encode."""

HARD_FLOOR: Final = 5
"""Images per class below which training is refused."""

IMBALANCE_RATIO: Final = 2.0
"""A class holding fewer than 1/2 of the largest class's images warns."""

TARGET_EXTENSIONS: Final[Mapping[str, str]] = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
}
"""The targeted formats. These pass through untouched; everything else Pillow
can decode converts, as does anything animated."""

# Pillow raises a DecompressionBombWarning above ~89M pixels and an error at
# twice that. A fetched or user-provided file of that size is not a plausible
# training image, and a warning printed from inside Pillow would bypass Rich.
_BOMB_ERRORS: Final = (Image.DecompressionBombError, Image.DecompressionBombWarning)


class RejectReason(StrEnum):
    """Why a file was excluded, as the decode attempt gives it.

    Never elaborated into judgements about quality, blur or relevance.
    """

    ZERO_BYTES = "zero bytes"
    UNOPENABLE = "could not be opened"
    UNDECODABLE = "format Pillow cannot decode"
    TRUNCATED = "truncated file"


@dataclass(frozen=True)
class ProcessedImage:
    """An owned image, ready to write.

    Attributes:
        data: The bytes to write — the original bytes when nothing changed.
        extension: The extension of the format the bytes are in, with the dot.
        converted: Whether the format changed.
        resized: Whether the image was upscaled to the size threshold.
        original_size: ``(width, height)`` before any resize.
    """

    data: bytes
    extension: str
    converted: bool
    resized: bool
    original_size: tuple[int, int]


@dataclass(frozen=True)
class InPlaceReport:
    """What the per-file stages found on a file the user owns.

    Attributes:
        path: The file.
        reason: Why it is unreadable, or None if it is readable.
        format: Pillow's format name, when readable.
        convertible: Whether it would convert, if Optica owned it.
        undersized: Whether its shorter side is below the threshold.
    """

    path: Path
    reason: RejectReason | None = None
    format: str | None = None
    convertible: bool = False
    undersized: bool = False

    @property
    def readable(self) -> bool:
        """Whether the file passed the corruption check."""
        return self.reason is None


# ------------------------------------------------------------- per-file stages


def _open(data: bytes) -> Image.Image | RejectReason:
    if not data:
        return RejectReason.ZERO_BYTES
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            return Image.open(io.BytesIO(data))
    except UnidentifiedImageError:
        return RejectReason.UNDECODABLE
    except _BOMB_ERRORS:
        return RejectReason.UNOPENABLE
    except OSError as exc:
        return (
            RejectReason.TRUNCATED if "runcated" in str(exc) else RejectReason.UNOPENABLE
        )
    except (ValueError, SyntaxError):
        return RejectReason.UNOPENABLE


def _is_animated(image: Image.Image) -> bool:
    return bool(getattr(image, "is_animated", False)) or getattr(image, "n_frames", 1) > 1


def _needs_lossless(image: Image.Image) -> bool:
    """Whether converting to JPEG would discard information.

    An alpha channel, a palette, or more than 8 bits per channel converts to
    PNG; everything else to JPEG.
    """
    if image.mode in {
        "RGBA",
        "LA",
        "PA",
        "P",
        "I",
        "I;16",
        "I;16B",
        "I;16L",
        "F",
        "RGBa",
    }:
        return True
    return "transparency" in image.info


def process_owned(data: bytes) -> ProcessedImage | RejectReason:
    """Run the per-file stages on bytes Optica owns, converting and resizing.

    The image is **fully decoded** here, not just header-checked: every owned
    path hashes, and may re-encode, the bytes anyway.

    Format targets: JPEG, PNG and WebP pass through untouched. Anything else,
    and anything animated (from its **first frame**), converts — to PNG where
    it carries alpha, a palette or more than 8 bits per channel, and to JPEG at
    quality 90 otherwise. Resize: an image whose shorter side is under 128px is
    upscaled until the shorter side reaches 128, aspect preserved, Lanczos, no
    crop and no padding. It **never downscales**.

    Args:
        data: The raw bytes.

    Returns:
        The image ready to write, or why it was rejected.
    """
    opened = _open(data)
    if isinstance(opened, RejectReason):
        return opened
    image = opened
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            source_format = image.format or ""
            animated = _is_animated(image)
            if animated:
                image.seek(0)
            image.load()
    except _BOMB_ERRORS:
        return RejectReason.UNOPENABLE
    except OSError as exc:
        return (
            RejectReason.TRUNCATED if "runcated" in str(exc) else RejectReason.UNOPENABLE
        )
    except (ValueError, SyntaxError, EOFError):
        return RejectReason.UNOPENABLE

    width, height = image.size
    if width <= 0 or height <= 0:
        return RejectReason.UNOPENABLE
    convert = animated or source_format not in TARGET_EXTENSIONS
    resize = min(width, height) < SIZE_THRESHOLD

    if not convert and not resize:
        return ProcessedImage(
            data, TARGET_EXTENSIONS[source_format], False, False, (width, height)
        )

    frame = image.copy() if animated else image
    # Decided on the decoded image, before any resize changes its mode.
    target = ("PNG" if _needs_lossless(frame) else "JPEG") if convert else source_format
    if resize:
        scale = SIZE_THRESHOLD / min(width, height)
        new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        # The shorter side lands exactly on the threshold, whatever rounding the
        # longer side takes.
        if width <= height:
            new_size = (SIZE_THRESHOLD, new_size[1])
        else:
            new_size = (new_size[0], SIZE_THRESHOLD)
        frame = _resample(frame, new_size)

    encoded = _encode(frame, target)
    return ProcessedImage(
        encoded, TARGET_EXTENSIONS[target], convert, resize, (width, height)
    )


def _resample(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    # Lanczos is not defined for palette or 16-bit integer modes in Pillow.
    if image.mode == "P":
        image = image.convert("RGBA" if "transparency" in image.info else "RGB")
    elif image.mode not in {"RGB", "RGBA", "L", "LA"}:
        image = image.convert("RGBA" if "A" in image.mode else "RGB")
    return image.resize(size, Image.Resampling.LANCZOS)


def _encode(image: Image.Image, target: str) -> bytes:
    buffer = io.BytesIO()
    if target == "JPEG":
        if image.mode != "RGB":
            image = image.convert("RGB")
        image.save(buffer, "JPEG", quality=JPEG_QUALITY)
    elif target == "WEBP":
        image.save(buffer, "WEBP", quality=JPEG_QUALITY)
    else:
        image.save(buffer, "PNG")
    return buffer.getvalue()


def inspect_in_place(path: Path) -> InPlaceReport:
    """Run the per-file stages on a file the user owns, **writing nothing**.

    Headers are validated rather than fully decoded — cheap, and on the path to
    producing thumbnails anyway. A header check does not see every truncation:
    a JPEG cut in half passes it (``notes/build-log.md``).

    Args:
        path: The file.

    Returns:
        What the stages found.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return InPlaceReport(path, RejectReason.UNOPENABLE)
    if size == 0:
        return InPlaceReport(path, RejectReason.ZERO_BYTES)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(path)
        with image:
            source_format = image.format or ""
            animated = _is_animated(image)
            dimensions = image.size
            image.verify()
    except UnidentifiedImageError:
        return InPlaceReport(path, RejectReason.UNDECODABLE)
    except _BOMB_ERRORS:
        return InPlaceReport(path, RejectReason.UNOPENABLE)
    except OSError as exc:
        reason = (
            RejectReason.TRUNCATED if "runcated" in str(exc) else RejectReason.UNOPENABLE
        )
        return InPlaceReport(path, reason)
    except (ValueError, SyntaxError, EOFError):
        return InPlaceReport(path, RejectReason.UNOPENABLE)
    return InPlaceReport(
        path,
        None,
        source_format,
        convertible=animated or source_format not in TARGET_EXTENSIONS,
        undersized=min(dimensions) < SIZE_THRESHOLD,
    )


# ------------------------------------------------------------------- naming


def unique_name(name: str, taken: set[str]) -> str:
    """Return ``name``, or its first free ``_x`` suffix, and reserve it.

    The global ``_x`` sequence: ``img.jpg``, ``img_2.jpg``, ``img_3.jpg``.
    Deterministic in the order names are offered, so manifest row order decides
    who keeps the bare name. Comparison is case-insensitive, because ``IMG.jpg``
    and ``img.jpg`` are one file on Windows and macOS.

    Args:
        name: The post-conversion target file name.
        taken: Case-folded names already used in this folder. Updated in place.

    Returns:
        The name to write.
    """
    candidate = name
    stem, dot, suffix = name.rpartition(".")
    if not dot:
        stem, suffix = name, ""
    counter = 2
    while candidate.casefold() in taken:
        candidate = f"{stem}_{counter}.{suffix}" if dot else f"{stem}_{counter}"
        counter += 1
    taken.add(candidate.casefold())
    return candidate


# --------------------------------------------------------- class-dependent


def md5_of(data: bytes) -> str:
    """The MD5 hex digest used for deduplication."""
    # MD5 checked per-class only — avoids removing valid images shared across
    # classes. It is a duplicate detector here, not a security boundary.
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


def find_duplicates(paths: Iterable[Path]) -> tuple[list[Path], list[Path]]:
    """Split one class's files into unique and byte-identical duplicates.

    Within-class only. The first file in the given order is kept; the caller
    decides what a duplicate means — deleted where Optica owns the bytes,
    excluded from the run where the user does.

    Returns:
        ``(unique, duplicates)``.
    """
    seen: set[str] = set()
    unique: list[Path] = []
    duplicates: list[Path] = []
    for path in paths:
        digest = md5_of(path.read_bytes())
        if digest in seen:
            duplicates.append(path)
        else:
            seen.add(digest)
            unique.append(path)
    return unique, duplicates


@dataclass(frozen=True)
class _FloorRow:
    name: str
    before: int
    after: int


def check_floor(counts: Mapping[str, int]) -> None:
    """Refuse any class below the five-image hard floor.

    Raises:
        OpticaValidationError: Naming every class below it.
    """
    short = [name for name, count in counts.items() if count < HARD_FLOOR]
    if not short:
        return
    raise OpticaValidationError(
        f"{list_names(short)} {'has' if len(short) == 1 else 'have'} fewer than "
        f"{HARD_FLOOR} images.",
        why=f"Every class needs at least {HARD_FLOOR} images to train.",
        fix=[f"{name}: {counts[name]} images" for name in short[:LIST_TRUNCATE]]
        + ["Add more images to those classes and run again."],
    )


def check_floor_after_dedupe(
    before: Mapping[str, int],
    after: Mapping[str, int],
    *,
    resumable_session: bool = False,
) -> None:
    """Re-check the hard floor after deduplication.

    Deduplication runs after labeling, so it can drop a class below the floor
    the labeling Finish gate certified. Every class that falls is named, with
    its counts before and after and the number of duplicates removed.

    Args:
        before: Counts before deduplication.
        after: Counts after.
        resumable_session: Whether the classes came from a labeling session,
            which adds that the session can be resumed.

    Raises:
        OpticaValidationError: When any class fell below the floor.
    """
    fallen = [
        _FloorRow(name, before.get(name, 0), count)
        for name, count in after.items()
        if count < HARD_FLOOR
    ]
    if not fallen:
        return
    lines = []
    for row in fallen[:LIST_TRUNCATE]:
        removed = row.before - row.after
        lines.append(
            f"{row.name}: {row.before} images → {row.after} unique "
            f"({removed} duplicate{'s' if removed != 1 else ''} removed)"
        )
    names = list_names([row.name for row in fallen])
    fix = [f"Add more images for {names} and run again."]
    if resumable_session:
        fix.append("The labeling session is saved; re-run the same command to resume it.")
    raise OpticaValidationError(
        f"{names} fell below the {HARD_FLOOR}-image minimum after duplicate removal.",
        why=lines[0] if len(lines) == 1 else None,
        fix=(lines if len(lines) > 1 else []) + fix,
    )


@dataclass(frozen=True)
class Imbalance:
    """The class-imbalance warning's content.

    Attributes:
        largest: The largest class's count.
        short: Classes below half of it, with their counts.
        counts: Every class's count, largest first.
    """

    largest: int
    short: dict[str, int]
    counts: dict[str, int] = field(default_factory=dict)


def imbalanced_classes(counts: Mapping[str, int]) -> Imbalance | None:
    """Whether any class holds fewer than 50% of the largest class.

    Ratio 2.0, measured on counts **after** deduplication — a class of 45 that is
    30 duplicates is not a class of 45. The only imbalance threshold in V1.

    Returns:
        The warning's content, or None when balanced.
    """
    if not counts:
        return None
    largest = max(counts.values())
    short = {
        name: count for name, count in counts.items() if count * IMBALANCE_RATIO < largest
    }
    if not short:
        return None
    ordered = dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))
    return Imbalance(largest=largest, short=short, counts=ordered)


def shortfall(counts: Mapping[str, int], name: str) -> int:
    """Images to request so ``name`` reaches the largest class's count.

    What the imbalance prompt's ``[F]`` asks the fetch for.
    """
    return max(0, max(counts.values(), default=0) - counts.get(name, 0))


def reasons_summary(reports: Sequence[InPlaceReport]) -> list[str]:
    """Render unreadable user-provided files one per line, truncated past 10."""
    bad = [report for report in reports if not report.readable]
    lines = [f"{report.path}: {report.reason}" for report in bad[:LIST_TRUNCATE]]
    if len(bad) > LIST_TRUNCATE:
        lines.append(f"(and {len(bad) - LIST_TRUNCATE} more)")
    return lines
