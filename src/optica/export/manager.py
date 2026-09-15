"""The Export Manager: which checkpoint, where, under what name, written atomically.

Implements plan § "Export" → *Output structure* (container folder, subfolder
naming, ``_ckptX``, ``_x`` auto-increment), *Artifact contents* and
*``model_info.json``* (the three metadata files), *``--output`` path handling*
(the situations; the prompts are the CLI's), and § "Training" → *Checkpoints*
(global ranking, rank validation, the stale-path warning). Implementation Note 9:
the atomic ``.partial`` write.

**V1 calls** :func:`optica.export.pytorch.export` **directly** — the format
registry arrives with the second format, not built for one.

**Prompts are not here.** This module decides what a situation *is*; the CLI
asks the question it implies, and the API (pass 5) takes the ``--yes`` answer.
Everything except the call into ``pytorch.export`` is torch-free and runs in CI.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

from optica.exceptions import OpticaExportError, OpticaValidationError
from optica.input.classes import list_names
from optica.training import checkpoints as ckpt

__all__ = [
    "CLASS_NAMES_FILE",
    "EXPORT_FORMAT",
    "MODEL_INFO_FILE",
    "ExportRecord",
    "OutputSituation",
    "Ranked",
    "classify_output",
    "clean_stale_partials",
    "component_count",
    "export_checkpoint",
    "folder_name",
    "missing_run_end",
    "model_info",
    "parse_ranks",
    "ranked_checkpoints",
    "require_writable",
    "stale_checkpoint_paths",
    "unique_name",
]

EXPORT_FORMAT: Final = "pt"
CLASS_NAMES_FILE: Final = "class_names.json"
MODEL_INFO_FILE: Final = "model_info.json"
_TIMESTAMP: Final = "%Y%m%d_%H%M%S"
_ISO: Final = "%Y-%m-%dT%H:%M:%S"
_EXPORT_NAME: Final = re.compile(r"^.+_\d+cls_\d{8}_\d{6}(_ckpt\d+)?(_\d+)?$")


# ----------------------------------------------------------------- ranking


@dataclass(frozen=True)
class Ranked:
    """A checkpoint and its global rank (1 is best).

    Attributes:
        rank: Position in the global ranking.
        checkpoint: The folder and its info.
    """

    rank: int
    checkpoint: ckpt.Checkpoint


def ranked_checkpoints(project_root: Path) -> list[Ranked]:
    """Every active checkpoint, globally ranked.

    Val accuracy, then higher epoch, then older timestamp; ``archive/`` excluded.

    Raises:
        OpticaExportError: No checkpoint exists — the command's precondition.
    """
    root = project_root / ckpt.CHECKPOINTS_DIR
    ranked = ckpt.rank(ckpt.list_active(root))
    if not ranked:
        raise OpticaExportError(
            f"No trained checkpoint found in ./{ckpt.CHECKPOINTS_DIR}/.",
            why="optica export writes a model from a checkpoint that training saved.",
            fix="Train one first: optica train",
        )
    return [Ranked(i, c) for i, c in enumerate(ranked, start=1)]


def parse_ranks(values: Sequence[str], available: int) -> list[int]:
    """Validate ``--checkpoint-rank`` values all at once.

    Each value must be a whole number, at least 1, and an existing rank. Every
    invalid value is reported in one error, with its reason — never the first
    only. Repeats collapse, first occurrence kept.

    Raises:
        OpticaValidationError: Listing every invalid value, and the available
            ranks when any value named one that does not exist.
    """
    ranks: list[int] = []
    problems: list[str] = []
    missing = False
    for raw in values:
        text = raw.strip()
        try:
            value = int(text)
        except ValueError:
            problems.append(f"{text!r}: a whole number is required")
            continue
        if value < 1:
            problems.append(f"{value}: a rank must be 1 or more")
        elif value > available:
            problems.append(f"{value}: there is no checkpoint at that rank")
            missing = True
        elif value not in ranks:
            ranks.append(value)
    if problems:
        fix = list(problems)
        if missing:
            fix.append(
                f"Available ranks: 1 to {available}"
                if available > 1
                else "Available ranks: 1"
            )
        raise OpticaValidationError(
            f"--checkpoint-rank has {len(problems)} invalid "
            f"value{'s' if len(problems) != 1 else ''}.",
            fix=fix,
        )
    return ranks


def stale_checkpoint_paths(checkpoint: ckpt.Checkpoint, project_root: Path) -> list[str]:
    """``checkpoint_paths`` in the run's log that no longer exist.

    The log's list goes stale after archiving and is deliberately not updated;
    export warns instead. Read from the log named by ``log_file``; an unreadable
    or absent log yields nothing to warn about.
    """
    raw = checkpoint.info.get("log_file")
    if not isinstance(raw, str):
        return []
    try:
        log = json.loads(Path(raw).expanduser().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    paths = log.get("checkpoint_paths", []) if isinstance(log, dict) else []
    return [p for p in paths if isinstance(p, str) and not (project_root / p).exists()]


def missing_run_end(checkpoint: ckpt.Checkpoint) -> bool:
    """Whether the checkpoint's run never finished.

    Its info then lacks the run-end ``epochs_trained`` and ``early_stopped``.
    """
    return (
        "epochs_trained" not in checkpoint.info or "early_stopped" not in checkpoint.info
    )


# ------------------------------------------------------------------ output


class OutputSituation(StrEnum):
    """What ``--output`` is, before anything is created. The plan's table, by row."""

    CONTAINER = "container"
    """Exists as a folder: use it."""
    IS_FILE = "is_file"
    """Exists as a file: hard error."""
    CREATE = "create"
    """Absent, single component or trailing slash: ``Create it? [Y/n]``."""
    NAME_OR_CONTAINER = "name_or_container"
    """Absent, several components, no trailing slash: N / C / A."""


def classify_output(raw: str) -> OutputSituation:
    r"""Place ``--output`` in the plan's table.

    ``raw`` is the text as typed, because ``Path`` drops a trailing slash and
    the slash is what settles name-versus-container. A component count excludes
    the anchor, so ``C:\out`` and ``/out`` are single-component like ``out``.
    """
    path = Path(raw)
    if path.is_dir():
        return OutputSituation.CONTAINER
    if path.exists():
        return OutputSituation.IS_FILE
    if component_count(raw) <= 1 or raw.endswith(("/", "\\")):
        return OutputSituation.CREATE
    return OutputSituation.NAME_OR_CONTAINER


def component_count(raw: str) -> int:
    """Path components of ``raw``, not counting a root or drive anchor."""
    path = Path(raw)
    return len(path.parts) - (1 if path.anchor else 0)


def require_writable(container: Path) -> None:
    """Pre-export validation: a probe file is created and removed.

    ``os.access`` does not answer this reliably for directories on Windows.

    Raises:
        OpticaValidationError: The container cannot be written to.
    """
    probe = container / f".optica-write-probe-{os.getpid()}"
    try:
        probe.write_bytes(b"")
        probe.unlink()
    except OSError as exc:
        raise OpticaValidationError(
            f"--output {container} is not writable.",
            why=f"{type(exc).__name__}: {exc}",
            fix="Choose a folder you can write to: "
            "optica export --output ./optica-output",
        ) from exc


# ------------------------------------------------------------------ naming


def folder_name(
    model_family: str, num_classes: int, moment: datetime, rank: int, *, with_rank: bool
) -> str:
    """``efficientnet-small_3cls_20260312_164510`` — ``_ckptX`` when ``with_rank``.

    The suffix applies whenever a non-default rank is involved: rank 2 alone, or
    any rank of a multi-rank export (``1,2`` gives ``_ckpt1`` and ``_ckpt2``).
    """
    base = f"{model_family}_{num_classes}cls_{moment.strftime(_TIMESTAMP)}"
    return f"{base}_ckpt{rank}" if with_rank else base


def unique_name(container: Path, name: str) -> str:
    """``name``, or its first free ``_x`` suffix among the container's entries.

    Active subfolders only — exports have no archive. A stale ``.partial`` of the
    same name is not a collision; it is removed before writing.
    """
    taken = (
        {p.name.casefold() for p in container.iterdir() if not p.name.startswith(".")}
        if container.is_dir()
        else set()
    )
    candidate, counter = name, 2
    while candidate.casefold() in taken:
        candidate = f"{name}_{counter}"
        counter += 1
    return candidate


def clean_stale_partials(container: Path) -> list[Path]:
    """Remove ``.<export-folder>.partial/`` folders an interrupted export left.

    Only names in the export naming form are touched: ``--output .`` makes the
    project root the container, where ``.dataset.partial/`` belongs to a
    materialization, not to export. A partial of an export written under a
    user-chosen name (the N branch) is not recognisable and is left.
    """
    removed: list[Path] = []
    if not container.is_dir():
        return removed
    for entry in container.iterdir():
        name = entry.name
        is_partial = entry.is_dir() and name.startswith(".") and name.endswith(".partial")
        if is_partial and _EXPORT_NAME.match(name[1 : -len(".partial")]):
            shutil.rmtree(entry)
            removed.append(entry)
    return removed


# ---------------------------------------------------------------- metadata


def model_info(
    checkpoint: ckpt.Checkpoint,
    *,
    rank: int,
    of: int,
    export_folder: str,
    moment: datetime,
    project_root: Path,
) -> dict[str, Any]:
    """``model_info.json``, from ``checkpoint_info.json`` and the export itself.

    The six preprocessing values are the ones training recorded, not re-resolved:
    a later timm may answer differently for the same tag. ``epochs_trained`` and
    ``early_stopped`` are null for a checkpoint whose run never finished.
    """
    info = checkpoint.info
    missing = [key for key in _REQUIRED if key not in info]
    if missing:
        raise OpticaExportError(
            f"{checkpoint.path.name} cannot be exported: its checkpoint_info.json lacks "
            f"{list_names(missing)}.",
            why="Export copies these from the checkpoint rather than guessing them.",
            fix="Export a checkpoint saved by this version of Optica, or train again.",
        )
    return {
        "run_id": info["run_id"],
        "model_family": info["model_family"],
        "base_model": info["base_model"],
        "classes": list(info["classes"]),
        "num_classes": info["num_classes"],
        "input_size": list(info["input_size"]),
        "mean": list(info["mean"]),
        "std": list(info["std"]),
        "interpolation": info["interpolation"],
        "crop_pct": info["crop_pct"],
        "crop_mode": info["crop_mode"],
        "val_accuracy": info.get("val_accuracy"),
        "val_loss": info.get("val_loss"),
        "test_accuracy": info.get("test_accuracy"),
        "test_loss": info.get("test_loss"),
        "epochs_trained": info.get("epochs_trained"),
        "class_weights_applied": bool(info.get("class_weights_applied", False)),
        "early_stopped": info.get("early_stopped"),
        "exported_rank": rank,
        "exported_rank_of": of,
        "export_format": EXPORT_FORMAT,
        "export_folder": export_folder,
        "training_timestamp": info.get("training_timestamp"),
        "export_timestamp": moment.strftime(_ISO),
        "dataset_path": info.get("dataset_path"),
        "config": info.get("config", {}),
        "checkpoint_path": _relative_folder(checkpoint.path, project_root),
        "log_file": info.get("log_file"),
    }


_REQUIRED: Final = (
    "run_id",
    "model_family",
    "base_model",
    "classes",
    "num_classes",
    "input_size",
    "mean",
    "std",
    "interpolation",
    "crop_pct",
    "crop_mode",
)


def _relative_folder(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix() + "/"
    except ValueError:
        return path.as_posix() + "/"


# ------------------------------------------------------------------- write


@dataclass
class ExportRecord:
    """One export folder written.

    Attributes:
        folder: The final folder.
        rank: The checkpoint rank it came from.
        files: File names inside it.
        info: Its ``model_info.json``.
    """

    folder: Path
    rank: int
    files: list[str] = field(default_factory=list)
    info: dict[str, Any] = field(default_factory=dict)


def export_checkpoint(
    ranked: Ranked,
    *,
    of: int,
    container: Path,
    name: str,
    moment: datetime,
    project_root: Path,
) -> ExportRecord:
    """Write one export folder, atomically.

    Everything goes into ``<container>/.<name>.partial/`` and is renamed to
    ``<container>/<name>/`` in one operation — a sibling, so the rename stays on
    one filesystem. On any failure the partial is removed and nothing is visible.
    """
    from optica.export import pytorch

    final = container / name
    partial = container / f".{name}.partial"
    if partial.exists():
        shutil.rmtree(partial)
    info = model_info(
        ranked.checkpoint,
        rank=ranked.rank,
        of=of,
        export_folder=name,
        moment=moment,
        project_root=project_root,
    )
    partial.mkdir(parents=True)
    try:
        files = pytorch.export(partial, ranked.checkpoint.path, info)
        # Inside the partial folder: the folder's rename is what makes the export
        # atomic, so the files need no temp-and-replace of their own.
        (partial / CLASS_NAMES_FILE).write_text(
            json.dumps(info["classes"], ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (partial / MODEL_INFO_FILE).write_text(
            json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        if final.exists():
            raise OpticaExportError(
                f"{final} appeared while the export was being written.",
                why="Another process wrote to the same output folder.",
                fix="Run the export again; a new name is chosen.",
            )
        partial.rename(final)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    return ExportRecord(
        final,
        ranked.rank,
        sorted([*files, CLASS_NAMES_FILE, MODEL_INFO_FILE]),
        info,
    )
