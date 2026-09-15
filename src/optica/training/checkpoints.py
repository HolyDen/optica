"""Checkpoint folders: naming, ranking, archiving, resume state.

Implements plan § "Training" → *Checkpoints* and *``checkpoint_info.json``*.

A checkpoint is a **folder** everywhere in Optica —
``checkpoints/checkpoint_val<accuracy>_epoch<n>/`` — holding
``checkpoint_info.json`` and the weights. It is ranked by folder, archived by
folder, and its info file travels inside it.

**What the folder holds is not specified by the plan** beyond
``checkpoint_info.json``. Assumed (``notes/build-log.md``): ``checkpoint.pt``, a
dict of tensors and JSON primitives only — ``state_dict`` (the model) and
``optimizer_state`` (for resume) — so it loads under ``torch.load``'s
``weights_only=True`` default like the export does.

Everything in this module except :func:`save_weights` and :func:`load_weights`
is torch-free and runs in CI.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from optica.exceptions import OpticaTrainingError
from optica.input.sessions import atomic_write_json
from optica.utils.mlstack import import_torch_stack

if TYPE_CHECKING:
    from torch import nn

__all__ = [
    "ARCHIVE_DIR",
    "CHECKPOINTS_DIR",
    "INFO_FILE",
    "SOFT_LIMIT_FACTOR",
    "WEIGHTS_FILE",
    "Checkpoint",
    "amend",
    "archive",
    "archive_timestamp",
    "delete",
    "folder_name",
    "list_active",
    "load_weights",
    "mark_interrupted",
    "mark_run_end",
    "rank",
    "resumable",
    "save_weights",
    "soft_limit",
    "unique_folder",
    "write_info",
]

CHECKPOINTS_DIR: Final = "checkpoints"
ARCHIVE_DIR: Final = "archive"
INFO_FILE: Final = "checkpoint_info.json"
WEIGHTS_FILE: Final = "checkpoint.pt"
SOFT_LIMIT_FACTOR: Final = 3


def folder_name(val_accuracy: float, epoch: int) -> str:
    """``checkpoint_val0.852_epoch7``: accuracy to three decimals, as in the plan."""
    return f"checkpoint_val{val_accuracy:.3f}_epoch{epoch}"


def unique_folder(root: Path, name: str) -> Path:
    """``root/name``, or its first free ``_x`` suffix (``_2``, ``_3``, …).

    Collisions are checked in the **active** folder only; ``archive/`` is never
    looked at. Case-insensitive, as NTFS and APFS are.
    """
    taken = {p.name.casefold() for p in root.iterdir()} if root.is_dir() else set()
    candidate, counter = name, 2
    while candidate.casefold() in taken:
        candidate = f"{name}_{counter}"
        counter += 1
    return root / candidate


def archive_timestamp(moment: datetime) -> str:
    """``YYYYMMDD_HHMMSS`` — year-inclusive, as every timestamped name is."""
    return moment.strftime("%Y%m%d_%H%M%S")


@dataclass(frozen=True)
class Checkpoint:
    """One checkpoint folder and what its info file says.

    Attributes:
        path: The folder.
        info: ``checkpoint_info.json``, parsed.
    """

    path: Path
    info: dict[str, Any]

    @property
    def val_accuracy(self) -> float:
        """``val_accuracy``, 0.0 when absent."""
        return float(self.info.get("val_accuracy", 0.0))

    @property
    def epoch(self) -> int:
        """``epoch``, 0 when absent."""
        return int(self.info.get("epoch", 0))

    @property
    def timestamp(self) -> str:
        """``training_timestamp`` — the run's start, ISO-8601."""
        return str(self.info.get("training_timestamp", ""))

    @property
    def run_id(self) -> str:
        """``run_id``."""
        return str(self.info.get("run_id", ""))

    @property
    def interrupted(self) -> bool:
        """Whether the run was interrupted after this was saved."""
        return bool(self.info.get("interrupted", False))


def _read_info(folder: Path) -> dict[str, Any] | None:
    try:
        data = json.loads((folder / INFO_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def list_active(root: Path) -> list[Checkpoint]:
    """Every checkpoint folder directly in ``root``, ``archive/`` excluded.

    A folder without a readable ``checkpoint_info.json`` is not a checkpoint and
    is skipped.
    """
    if not root.is_dir():
        return []
    found = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name == ARCHIVE_DIR:
            continue
        info = _read_info(entry)
        if info is not None:
            found.append(Checkpoint(entry, info))
    return found


def rank(checkpoints: Iterable[Checkpoint]) -> list[Checkpoint]:
    """Best first: val accuracy, then higher epoch, then **older** timestamp."""
    by_timestamp = sorted(checkpoints, key=lambda c: c.timestamp)  # older first
    return sorted(by_timestamp, key=lambda c: (-c.val_accuracy, -c.epoch))


def resumable(checkpoints: Iterable[Checkpoint]) -> Checkpoint | None:
    """The newest checkpoint carrying ``"interrupted": true``, if any.

    Newest by run timestamp, then by epoch within a run. Older interrupted
    checkpoints are left alone.
    """
    interrupted = [c for c in checkpoints if c.interrupted]
    if not interrupted:
        return None
    return max(interrupted, key=lambda c: (c.timestamp, c.epoch))


def soft_limit(max_checkpoints: int) -> int:
    """Kept checkpoints above this number warn: ``3 x max_checkpoints``."""
    return SOFT_LIMIT_FACTOR * max_checkpoints


def write_info(folder: Path, info: dict[str, Any]) -> None:
    """Write ``checkpoint_info.json`` atomically — at save time, not run end."""
    atomic_write_json(folder / INFO_FILE, info)


def amend(folder: Path, **fields: Any) -> None:
    """Add or replace fields in an existing ``checkpoint_info.json``.

    The post-save amendment: ``"interrupted": true``, or the run-end pair.
    """
    info = _read_info(folder)
    if info is None:
        return
    info.update(fields)
    write_info(folder, info)


def mark_interrupted(folders: Iterable[Path]) -> None:
    """Amend each of a run's retained checkpoints with ``"interrupted": true``."""
    for folder in folders:
        amend(folder, interrupted=True)


def mark_run_end(
    folders: Iterable[Path], *, epochs_trained: int, early_stopped: bool
) -> None:
    """Write the run-end pair into **every** retained checkpoint of the run.

    ``interrupted`` is reset to false as well: a resumed run that finishes is not
    interrupted, and leaving the flag would offer to resume it again.
    """
    for folder in folders:
        amend(
            folder,
            epochs_trained=epochs_trained,
            early_stopped=early_stopped,
            interrupted=False,
        )


def archive(checkpoints: Sequence[Checkpoint], root: Path, moment: datetime) -> Path:
    """Move checkpoints into ``root/archive/<YYYYMMDD_HHMMSS>/``.

    Info files travel inside the folders, so an archived checkpoint stays
    self-describing.
    """
    target = root / ARCHIVE_DIR / archive_timestamp(moment)
    target.mkdir(parents=True, exist_ok=True)
    for checkpoint in checkpoints:
        shutil.move(
            str(checkpoint.path), str(unique_folder(target, checkpoint.path.name))
        )
    return target


def delete(checkpoints: Sequence[Checkpoint]) -> None:
    """Remove checkpoint folders."""
    for checkpoint in checkpoints:
        shutil.rmtree(checkpoint.path)


def save_weights(
    folder: Path, model: nn.Module, optimizer_state: dict[str, Any] | None
) -> None:
    """Write ``checkpoint.pt``: tensors and JSON primitives only.

    Written to a temp name in the same folder and moved into place, so a crash
    mid-write never leaves a half file under the real name.
    """
    import_torch_stack()
    import torch

    folder.mkdir(parents=True, exist_ok=True)
    temp = folder / f".{WEIGHTS_FILE}.tmp"
    torch.save(
        {"state_dict": model.state_dict(), "optimizer_state": optimizer_state}, temp
    )
    temp.replace(folder / WEIGHTS_FILE)


def load_weights(folder: Path, *, map_location: Any = "cpu") -> dict[str, Any]:
    """Read ``checkpoint.pt`` with ``weights_only=True``.

    Raises:
        OpticaTrainingError: Missing or unreadable.
    """
    import_torch_stack()
    import torch

    path = folder / WEIGHTS_FILE
    try:
        payload: dict[str, Any] = torch.load(
            path, map_location=map_location, weights_only=True
        )
    except Exception as exc:
        raise OpticaTrainingError(
            f"The checkpoint weights at {path} could not be read.",
            why=f"{type(exc).__name__}: {exc}",
            fix="Start a fresh run, or remove that checkpoint folder.",
        ) from exc
    return payload
