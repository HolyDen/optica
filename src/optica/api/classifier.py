"""`Classifier` — the Tier 5 expert surface.

Implements plan § "Python API" → *Classifier (Tier 5)*: chainable methods, the
nine properties, the high-water-mark `Status`, and the construction rules for
`Classifier(checkpoint_path=…)`.

Tier 5 earns *Expert* by giving direct programmatic control over **the model
object** — not over the training loop: the optimizer and its per-optimizer
hyperparameters stay fixed. State validation is *flexible with helpful errors
over strict ordering*, because advanced users legitimately skip steps, so a
precondition raises with fix instructions rather than enforcing a sequence.

**Constructing a `Classifier` never requires torch.** `checkpoint_path=`
validates that the path exists and is a checkpoint folder; an existence check
needs no torch, and ``torch.load`` happens in the first method that needs the
model.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

from optica.api import simple
from optica.api.simple import (
    ExportConfig,
    FetchConfig,
    TrainConfig,
    WarningEntry,
)
from optica.exceptions import OpticaValidationError
from optica.training import checkpoints

__all__ = ["Classifier", "EpochRecord", "Status"]


class Status(StrEnum):
    """How far this `Classifier` has got.

    A **high-water mark, not a position in a sequence**: each value means *this
    stage has been completed at least once*. It never moves backwards within an
    object's life, and it is what preconditions are checked against — which is
    what makes *flexible with helpful errors over strict ordering*
    implementable. A caller who skips a stage gets an error naming the missing
    state, not a rejection for being out of order.
    """

    EMPTY = "empty"
    DATA_READY = "data_ready"
    TRAINED = "trained"
    EXPORTED = "exported"


_ORDER: dict[str, int] = {
    Status.EMPTY: 0,
    Status.DATA_READY: 1,
    Status.TRAINED: 2,
    Status.EXPORTED: 3,
}


@dataclass(frozen=True)
class EpochRecord:
    """One completed epoch, carrying what the training log records.

    Attributes:
        epoch: The 1-based epoch number.
        phase: 1 for head warmup, 2 for fine-tuning.
        train_loss: Training loss.
        train_accuracy: Training accuracy.
        val_loss: Validation loss.
        val_accuracy: Validation accuracy.
    """

    epoch: int
    phase: int
    train_loss: float
    train_accuracy: float
    val_loss: float
    val_accuracy: float

    @classmethod
    def from_json(cls, record: dict[str, Any]) -> EpochRecord:
        """Read one entry of a checkpoint's ``epoch_history``."""
        return cls(
            epoch=int(record.get("epoch", 0)),
            phase=int(record.get("phase", 0)),
            train_loss=float(record.get("train_loss", 0.0)),
            train_accuracy=float(record.get("train_accuracy", 0.0)),
            val_loss=float(record.get("val_loss", 0.0)),
            val_accuracy=float(record.get("val_accuracy", 0.0)),
        )


class Classifier:
    """The expert entry point: hold the object, call methods on it.

    Named after the task, following scikit-learn's convention — `Detector`,
    `Segmentor` and `Embedder` follow post-V1.

    Args:
        model: The backbone family. A **constructor** argument, being a setting
            every operation on this object shares.
        output: The container for run outputs. Likewise.
        dataset: Where images land and training reads from.
        verbose: False suppresses Rich output for every call.
        checkpoint_path: An existing checkpoint **folder** to start from,
            skipping the stages that produced it.

    Raises:
        OpticaValidationError: ``checkpoint_path`` does not exist, or exists but
            is not a checkpoint folder containing ``checkpoint_info.json`` — a
            bare ``.pt`` file being the latter.
    """

    def __init__(
        self,
        model: str | None = None,
        output: str | Path = "optica-output",
        *,
        dataset: str | Path = "dataset",
        verbose: bool = True,
        checkpoint_path: str | Path | None = None,
    ) -> None:
        self._model = model
        self._output = Path(output)
        self._dataset = Path(dataset)
        self._verbose = verbose
        self._status = Status.EMPTY
        self._classes: list[str] = []
        self._best_val_accuracy: float | None = None
        self._checkpoint_path: Path | None = None
        self._export_paths: list[Path] = []
        self._history: list[EpochRecord] = []
        self._warnings: list[WarningEntry] = []
        self._dataset_seen = False
        if checkpoint_path is not None:
            self._adopt_checkpoint(Path(checkpoint_path))

    # -- construction -----------------------------------------------------

    def _adopt_checkpoint(self, path: Path) -> None:
        """Validate and adopt an existing checkpoint folder. Never imports torch.

        The distinction between *missing* and *not a checkpoint* matters because
        `export` reads ``run_id``, ``val_accuracy``, ``epoch``, ``dataset_path``
        and the ``config`` block from ``checkpoint_info.json``; a file that does
        not carry it cannot be exported from, so accepting one would defer the
        failure to the operation the object was constructed to perform.
        """
        if not path.exists():
            raise OpticaValidationError(
                f"No checkpoint found at {path}",
                why="checkpoint_path names a path that does not exist.",
                fix="Check the path, or train one first: optica.train()",
            )
        checkpoint = checkpoints.read(path)
        if checkpoint is None:
            raise OpticaValidationError(
                f"{path} is not a checkpoint folder.",
                why="A checkpoint is a folder holding a readable "
                f"{checkpoints.INFO_FILE}; this is "
                + ("a file" if path.is_file() else "a folder without one")
                + ".",
                fix=f"Pass the folder that holds {checkpoints.INFO_FILE}, not a "
                "bare .pt file.",
            )
        self._checkpoint_path = path
        self._classes = [str(name) for name in checkpoint.info.get("classes", [])]
        self._best_val_accuracy = _as_float(checkpoint.info.get("val_accuracy"))
        family = str(checkpoint.info.get("model_family", ""))
        self._model = self._model or family or None
        self._history = [
            EpochRecord.from_json(record)
            for record in checkpoint.info.get("epoch_history", [])
            if isinstance(record, dict)
        ]
        self._advance(Status.TRAINED)

    # -- state ------------------------------------------------------------

    def _advance(self, status: Status) -> None:
        if _ORDER[status] > _ORDER[self._status]:
            self._status = status

    def _record(self, result: simple.OpticaResult) -> None:
        # Accumulated across calls in invocation order: `Classifier` methods
        # return `self` rather than a result object, so without this the tier
        # built for programmatic callers would be the only one unable to branch
        # on a warning.
        self._warnings.extend(result.warnings)

    def _require(self, status: Status, action: str, fix: str) -> None:
        if _ORDER[self._status] < _ORDER[status]:
            raise OpticaValidationError(
                f"{action} needs {status.value} and this Classifier is "
                f"{self._status.value}.",
                why="Preconditions are checked against the status high-water mark, "
                "not against call order.",
                fix=fix,
            )

    # -- methods ----------------------------------------------------------

    def fetch(
        self,
        classes: Sequence[str] | str | None = None,
        *,
        mode: str | None = None,
        overwrite: bool = False,
        config: FetchConfig | None = None,
    ) -> Self:
        """Acquire images. Returns ``self``."""
        result = simple.fetch(
            classes,
            mode=mode,
            dataset=self._dataset,
            overwrite=overwrite,
            verbose=self._verbose,
            config=config,
        )
        self._record(result)
        self._classes = result.classes or self._classes
        self._dataset_seen = result.dataset_path is not None
        self._advance(Status.DATA_READY)
        return self

    def label(
        self,
        classes: Sequence[str] | str | None = None,
        *,
        folder: str | Path | None = None,
        manifest: str | Path | None = None,
        overwrite: bool = False,
        config: FetchConfig | None = None,
    ) -> Self:
        """Label local input in the browser. Returns ``self``."""
        result = simple.label(
            classes,
            folder=folder,
            manifest=manifest,
            dataset=self._dataset,
            overwrite=overwrite,
            verbose=self._verbose,
            config=config,
        )
        self._record(result)
        self._classes = result.classes or self._classes
        self._dataset_seen = True
        self._advance(Status.DATA_READY)
        return self

    def curate(
        self, *, overwrite: bool = False, config: FetchConfig | None = None
    ) -> Self:
        """Review staged images in the browser. Returns ``self``."""
        result = simple.curate(
            dataset=self._dataset,
            overwrite=overwrite,
            verbose=self._verbose,
            config=config,
        )
        self._record(result)
        self._classes = result.classes or self._classes
        self._dataset_seen = True
        self._advance(Status.DATA_READY)
        return self

    def train(
        self,
        classes: Sequence[str] | str | None = None,
        *,
        manifest: str | Path | None = None,
        overwrite: bool = False,
        config: TrainConfig | None = None,
    ) -> Self:
        """Train on the dataset. Returns ``self``."""
        result = simple.train(
            classes,
            dataset=self._dataset,
            manifest=manifest,
            model=self._model,
            output=self._output,
            overwrite=overwrite,
            verbose=self._verbose,
            config=config,
        )
        self._record(result)
        self._best_val_accuracy = result.best_val_accuracy
        self._checkpoint_path = result.best_checkpoint
        if result.best_checkpoint is not None:
            self._history = _history_of(result.best_checkpoint)
            self._classes = _classes_of(result.best_checkpoint) or self._classes
        self._dataset_seen = True
        self._advance(Status.TRAINED)
        return self

    def export(self, *, config: ExportConfig | None = None) -> Self:
        """Write a PyTorch artifact from a checkpoint. Returns ``self``."""
        self._require(
            Status.TRAINED,
            "export",
            "Train first — clf.train() — or construct with "
            "Classifier(checkpoint_path=…).",
        )
        result = simple.export(
            output=self._output, verbose=self._verbose, config=config
        )
        self._record(result)
        if result.export_folder is not None:
            self._export_paths.append(result.export_folder)
        self._advance(Status.EXPORTED)
        return self

    def run(
        self,
        classes: Sequence[str] | str | None = None,
        *,
        mode: str | None = None,
        folder: str | Path | None = None,
        manifest: str | Path | None = None,
        overwrite: bool = False,
        fetch_config: FetchConfig | None = None,
        train_config: TrainConfig | None = None,
        export_config: ExportConfig | None = None,
    ) -> Self:
        """Run the whole pipeline on this object. Returns ``self``."""
        result = simple.run(
            classes,
            mode=mode,
            folder=folder,
            manifest=manifest,
            dataset=self._dataset,
            model=self._model,
            output=self._output,
            overwrite=overwrite,
            verbose=self._verbose,
            fetch_config=fetch_config,
            train_config=train_config,
            export_config=export_config,
        )
        self._record(result)
        if result.fetch is not None:
            self._classes = result.fetch.classes or self._classes
        if result.train is not None:
            self._best_val_accuracy = result.train.best_val_accuracy
            self._checkpoint_path = result.train.best_checkpoint
            if result.train.best_checkpoint is not None:
                self._history = _history_of(result.train.best_checkpoint)
        if result.export is not None and result.export.export_folder is not None:
            self._export_paths.append(result.export.export_folder)
        self._dataset_seen = True
        self._advance(Status.EXPORTED)
        return self

    # -- properties -------------------------------------------------------

    @property
    def classes(self) -> list[str]:
        """The classes, in the sorted order the dataset defines."""
        return list(self._classes)

    @property
    def model(self) -> str | None:
        """The backbone family this object trains."""
        return self._model

    @property
    def status(self) -> Status:
        """The high-water mark."""
        return self._status

    @property
    def dataset_path(self) -> Path | None:
        """The dataset this object has written or read, or None."""
        return self._dataset if self._dataset_seen else None

    @property
    def training_history(self) -> list[EpochRecord]:
        """One entry per completed epoch, as the training log records it."""
        return list(self._history)

    @property
    def best_val_accuracy(self) -> float | None:
        """The best checkpoint's validation accuracy."""
        return self._best_val_accuracy

    @property
    def checkpoint_path(self) -> Path | None:
        """The best checkpoint's **folder**, in ``model_info.json``'s form."""
        return self._checkpoint_path

    @property
    def export_paths(self) -> list[Path]:
        """One entry per export folder written."""
        return list(self._export_paths)

    @property
    def warnings(self) -> list[WarningEntry]:
        """Every warning raised across this object's calls, in order.

        The ninth property, carrying the warning contract into Tier 5: same
        entries, same source as the Tier 3/4 results and ``warnings.warn``.
        """
        return list(self._warnings)


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _history_of(folder: Path) -> list[EpochRecord]:
    checkpoint = checkpoints.read(folder)
    if checkpoint is None:
        return []
    return [
        EpochRecord.from_json(record)
        for record in checkpoint.info.get("epoch_history", [])
        if isinstance(record, dict)
    ]


def _classes_of(folder: Path) -> list[str]:
    checkpoint = checkpoints.read(folder)
    if checkpoint is None:
        return []
    return [str(name) for name in checkpoint.info.get("classes", [])]
