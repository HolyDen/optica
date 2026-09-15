"""The training log: one JSON file, written after every epoch, in two places.

Implements plan § "Training" → *Training log*. Not in plan § "Code Structure"'s
tree; added in pass 4 (``notes/build-log.md``), because the engine is generic
and the log is the classification run's record.

- ``~/.optica/logs/run_<YYYYMMDD>_<HHMMSS>_<model>_<N>classes.json`` — global.
- ``<output>/logs/`` — the same file, project-local; follows ``--output``.

Both are permanent and user-managed: no rotation, no cap, no clearing command.
``checkpoint_paths`` goes stale after archiving and is **not** updated — an
accepted limitation the plan says not to fix.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from optica.input.sessions import atomic_write_json

__all__ = ["RunLog", "log_filename", "run_id_for", "tilde_path"]


def run_id_for(moment: datetime) -> str:
    """``YYYYMMDD_HHMMSS`` — the run's identifier and its log name's timestamp."""
    return moment.strftime("%Y%m%d_%H%M%S")


def log_filename(run_id: str, model_family: str, num_classes: int) -> str:
    """``run_20260312_143022_efficientnet-small_3classes.json``."""
    return f"run_{run_id}_{model_family}_{num_classes}classes.json"


def tilde_path(path: Path, home: Path | None = None) -> str:
    """``path`` in tilde form, ``/``-separated, when it is under the home directory.

    ``log_file`` is stored this way — ``~`` is what conceals the username — and
    expanded only on read. A path outside home is returned as it is.
    """
    home = home or Path.home()
    try:
        relative = path.resolve().relative_to(home.resolve())
    except ValueError:
        return str(path)
    return "~/" + relative.as_posix()


@dataclass
class RunLog:
    """The log's content and its two destinations.

    Attributes:
        paths: Where it is written — global first, then project-local.
        data: The JSON document.
    """

    paths: Sequence[Path]
    data: dict[str, Any] = field(default_factory=dict)

    def write(self) -> None:
        """Write both copies. Called at run start and after every epoch."""
        for path in self.paths:
            atomic_write_json(path, self.data)

    def record_epoch(self, entry: dict[str, Any]) -> None:
        """Append one epoch's metrics and rewrite both copies."""
        self.data.setdefault("epochs", []).append(entry)
        self.write()

    def truncate_after(self, epoch: int) -> None:
        """Drop epochs after ``epoch`` — on resume they are trained again."""
        self.data["epochs"] = [
            e for e in self.data.get("epochs", []) if e["epoch"] <= epoch
        ]
