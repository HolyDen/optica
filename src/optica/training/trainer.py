"""One classification training run, from resolved inputs to retained checkpoints.

Not in plan § "Code Structure"'s tree; added in pass 4 (``notes/build-log.md``).
The engine is task-generic and the CLI only asks questions, so the sequence of
plan § "Training" → *Training Engine* steps 1-10 for classification — split,
model, head, transforms, loop, top-N checkpoints with test evaluation, both log
copies, interruption and resume — lives here, where pass 5's API can call it too.

**Prompts are not here.** Every question (resume, K/A/D/S, imbalance, the CPU
batch size, ``--epochs 1``) is answered before :func:`train` is called, and the
answers arrive in :class:`TrainPlan`.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from optica.exceptions import OpticaTrainingError
from optica.training import checkpoints as ckpt
from optica.training.data import make_loaders
from optica.training.engine import (
    Engine,
    EngineState,
    EpochMetrics,
    Reporter,
    allocate_phases,
    classification_components,
)
from optica.training.models import (
    base_model_for,
    configure_head,
    load_backbone,
    resolve_data_config,
    set_phase,
    set_train_mode,
)
from optica.training.runlog import RunLog, log_filename, run_id_for, tilde_path
from optica.training.splits import DatasetSplit, stratified_split, training_data_hash
from optica.training.transforms import build_transforms
from optica.utils.mlstack import import_torch_stack, select_device

if TYPE_CHECKING:
    import torch

__all__ = [
    "RANDOM_STATE_BOUND",
    "TrainOutcome",
    "TrainPlan",
    "TrainSettings",
    "TrainingInterrupted",
    "class_weights_for",
    "resume_state",
    "train",
]

RANDOM_STATE_BOUND: Final = 2**31
_TIMESTAMP_FORMAT: Final = "%Y-%m-%dT%H:%M:%S"


class TrainingInterrupted(KeyboardInterrupt):
    """Ctrl+C during training, after the checkpoints and log were marked.

    A ``KeyboardInterrupt``, so anything that does not know about it still exits
    ``130``; it carries where the run was, for the ``✗ Training incomplete`` line.

    Attributes:
        at_epoch: The epoch in progress when interrupted.
        total: The epochs requested.
    """

    def __init__(self, at_epoch: int, total: int) -> None:
        super().__init__(f"interrupted at epoch {at_epoch}/{total}")
        self.at_epoch = at_epoch
        self.total = total


@dataclass(frozen=True)
class TrainSettings:
    """The config keys training reads — the ``config`` block, written verbatim.

    The plan's example block holds six keys; the split ratios, optimizer and
    ``max_checkpoints`` are recorded as well, because a resume must reproduce
    the split and the loop exactly and ``random_state`` alone cannot
    (``notes/build-log.md``).
    """

    epochs: int
    batch_size: int
    learning_rate: float
    augmentation: bool
    early_stopping: int
    finetune_ratio: float
    optimizer: str = "adamw"
    train_split: float = 0.70
    val_split: float = 0.15
    test_split: float = 0.15
    max_checkpoints: int = 3

    def as_json(self) -> dict[str, Any]:
        """The ``config`` block."""
        return {
            "epochs": self.epochs,
            "batch_size": self.batch_size,
            "learning_rate": self.learning_rate,
            "augmentation": self.augmentation,
            "early_stopping": self.early_stopping,
            "finetune_ratio": self.finetune_ratio,
            "optimizer": self.optimizer,
            "train_split": self.train_split,
            "val_split": self.val_split,
            "test_split": self.test_split,
            "max_checkpoints": self.max_checkpoints,
        }

    @classmethod
    def from_json(cls, block: dict[str, Any]) -> TrainSettings:
        """Rebuild from a stored ``config`` block, ignoring unknown keys."""
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in block.items() if k in known})


@dataclass
class TrainPlan:
    """Everything a run needs, every question already answered.

    Attributes:
        dataset_root: The dataset folder, as given.
        files: Class name to the files that survived pre-flight and
            deduplication. Classes are used in sorted order.
        model_family: The ``--model`` value.
        settings: The resolved config keys.
        class_weights: Whether the user chose automatic class weighting.
        project_root: Where ``checkpoints/`` lives.
        output: The ``--output`` container; the log goes in ``<output>/logs/``.
        home: The home directory for ``~/.optica/logs/`` (tests pass one).
        resume_from: The interrupted checkpoint to continue, if resuming.
        pretrained: False only in tests, which never download weights.
    """

    dataset_root: Path
    files: dict[str, list[Path]]
    model_family: str
    settings: TrainSettings
    class_weights: bool
    project_root: Path
    output: Path
    home: Path | None = None
    resume_from: ckpt.Checkpoint | None = None
    pretrained: bool = True

    @property
    def classes(self) -> list[str]:
        """Class names in sorted ``ImageFolder`` order — the output-index order."""
        return sorted(self.files)

    @property
    def checkpoints_root(self) -> Path:
        """``<project_root>/checkpoints``."""
        return self.project_root / ckpt.CHECKPOINTS_DIR


@dataclass
class TrainOutcome:
    """What the run produced — ``TrainResult``'s fields, and the completion block's.

    Attributes:
        run_id: ``YYYYMMDD_HHMMSS``.
        best_checkpoint: The rank-1 retained checkpoint folder.
        best_val_accuracy: Its validation accuracy.
        test_accuracy: Its test accuracy, None when no class had a test image.
        test_loss: Its test loss, likewise.
        epochs_run: Epochs completed.
        epochs_requested: ``--epochs``.
        phases: The allocation — ``(phase1, phase2)``.
        phases_run: Epochs actually completed per phase.
        early_stopped: Set by the loop.
        phase1_stopped_early: Phase 1 ended on patience and fine-tuning began.
        checkpoints: Retained checkpoint folders, best first.
        log_paths: Global copy, then project-local.
        classes_without_test: Classes the split gave no test image.
        split_counts: Per class, ``train``/``val``/``test``.
        device: Where it trained, e.g. ``cuda``.
        patience: ``early_stopping`` as the run used it.
    """

    run_id: str
    best_checkpoint: Path | None
    best_val_accuracy: float | None
    test_accuracy: float | None
    test_loss: float | None
    epochs_run: int
    epochs_requested: int
    phases: tuple[int, int]
    phases_run: tuple[int, int]
    early_stopped: bool
    phase1_stopped_early: bool
    checkpoints: list[Path]
    log_paths: list[Path]
    classes_without_test: list[str]
    split_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    device: str = ""
    patience: int = 0


def class_weights_for(train_counts: Sequence[int]) -> list[float]:
    """Inverse-frequency weights, index-aligned with the classes.

    ``total / (num_classes x count)`` — a class at the mean count weighs 1.0.
    Computed on the **training** split, which is what the loss sees
    (``notes/build-log.md``).
    """
    total = sum(train_counts)
    k = len(train_counts)
    return [round(total / (k * count), 6) for count in train_counts]


def resume_state(info: dict[str, Any], patience: int) -> EngineState:
    """Rebuild the loop's state from a checkpoint's ``checkpoint_info.json``.

    The current phase's best ``val_loss`` is not a stored field; it is the lowest
    ``val_loss`` of that phase in ``epoch_history``, which is the value the
    stored ``early_stopping_counter`` counts from. A Phase 1 checkpoint whose
    counter already reached patience was the epoch Phase 1 stopped on.
    """
    phase = int(info["training_phase"])
    history = [
        EpochMetrics(**{k: entry[k] for k in EpochMetrics.__dataclass_fields__})
        for entry in info.get("epoch_history", [])
    ]
    in_phase = [m.val_loss for m in history if m.phase == phase]
    counter = int(info.get("early_stopping_counter", 0))
    return EngineState(
        epoch=int(info["epoch"]),
        phase=phase,
        phase_completed=[
            int(info.get("phase1_epochs_completed", 0)),
            int(info.get("phase2_epochs_completed", 0)),
        ],
        early_stopping_counter=counter,
        early_stopping_best=min(in_phase) if in_phase else None,
        history=history,
        phase1_stopped_early=phase == 1 and patience > 0 and counter >= patience,
    )


class _SilentReporter:
    def epoch_started(self, epoch: int, total: int, phase: int, batches: int) -> None:
        pass

    def batch_done(self) -> None:
        pass

    def epoch_finished(self, metrics: EpochMetrics) -> None:
        pass


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def train(
    plan: TrainPlan,
    reporter: Reporter | None = None,
    *,
    device: torch.device | None = None,
    on_status: Callable[[str], None] = lambda _: None,
) -> TrainOutcome:
    """Run training to completion, early stop, or interruption.

    Raises:
        OpticaTorchError: The torch stack is missing.
        OpticaTrainingError: Weights cannot load, an image cannot decode, or
            memory runs out (with batch-size advice).
        KeyboardInterrupt: After the run's checkpoints and log are marked
            interrupted.
    """
    import_torch_stack()
    import torch

    reporter = reporter or _SilentReporter()
    device = device or select_device()
    settings = plan.settings
    classes = plan.classes
    base_model = base_model_for(plan.model_family)
    resume = plan.resume_from
    started = _now()

    if resume is not None:
        random_state = int(resume.info["random_state"])
        run_id = resume.run_id
        training_timestamp = resume.timestamp
    else:
        random_state = secrets.randbelow(RANDOM_STATE_BOUND)
        run_id = run_id_for(started)
        training_timestamp = started.strftime(_TIMESTAMP_FORMAT)

    torch.manual_seed(random_state)
    split = stratified_split(
        {name: plan.files[name] for name in classes},
        settings.val_split,
        settings.test_split,
        random_state,
    )

    on_status(f"Loading {base_model}")
    model = load_backbone(base_model, pretrained=plan.pretrained)
    configure_head(model, num_classes=len(classes))
    data_config = resolve_data_config(model)
    payload = ckpt.load_weights(resume.path) if resume is not None else None
    if payload is not None:
        model.load_state_dict(payload["state_dict"])
    model.to(device)

    train_tf, eval_tf = build_transforms(data_config, augmentation=settings.augmentation)
    train_loader, val_loader, test_loader = make_loaders(
        split,
        train_tf,
        eval_tf,
        batch_size=settings.batch_size,
        device=device,
        seed=random_state,
    )
    weights = class_weights_for(split.train_counts()) if plan.class_weights else None

    phases = allocate_phases(settings.epochs, settings.finetune_ratio)
    dataset_path = str(plan.dataset_root.resolve())
    data_hash = training_data_hash(plan.dataset_root)
    name = log_filename(run_id, plan.model_family, len(classes))
    global_log = (plan.home or Path.home()) / ".optica" / "logs" / name
    log = RunLog([global_log, plan.output / "logs" / name])
    log.data = _initial_log(
        run_id=run_id,
        plan=plan,
        base_model=base_model,
        classes=classes,
        split=split,
        random_state=random_state,
        weights=weights,
        data_hash=data_hash,
        dataset_path=dataset_path,
        data_config=data_config.as_json(),
        phases=phases,
        device=str(device),
    )
    if resume is not None:
        log.data["epochs"] = [m.as_json() for m in resume_state(resume.info, 0).history]
        log.data.setdefault("resumed", []).append(
            {
                "from_checkpoint": _relative(resume.path, plan.project_root),
                "at_epoch": resume.epoch,
                "timestamp": started.strftime(_TIMESTAMP_FORMAT),
            }
        )
    log.write()

    retained: list[ckpt.Checkpoint] = (
        [c for c in ckpt.list_active(plan.checkpoints_root) if c.run_id == run_id]
        if resume is not None
        else []
    )
    log_file = tilde_path(global_log, plan.home)

    def on_epoch_end(metrics: EpochMetrics, engine: Engine) -> None:
        nonlocal retained
        candidate_rank = _qualifies(retained, metrics, settings.max_checkpoints)
        if candidate_rank:
            test = engine.evaluate(test_loader)
            folder = ckpt.unique_folder(
                plan.checkpoints_root,
                ckpt.folder_name(metrics.val_accuracy, metrics.epoch),
            )
            state = engine.state
            optimizer_state = engine.optimizer.state_dict() if engine.optimizer else None
            ckpt.save_weights(folder, model, optimizer_state)
            info = {
                "run_id": run_id,
                "model_family": plan.model_family,
                "base_model": base_model,
                "classes": classes,
                "num_classes": len(classes),
                "val_accuracy": round(metrics.val_accuracy, 6),
                "val_loss": round(metrics.val_loss, 6),
                "test_accuracy": round(test[1], 6) if test else None,
                "test_loss": round(test[0], 6) if test else None,
                "epoch": metrics.epoch,
                "training_phase": metrics.phase,
                "phase1_epochs_completed": state.phase_completed[0],
                "phase2_epochs_completed": state.phase_completed[1],
                "early_stopping_counter": state.early_stopping_counter,
                "training_timestamp": training_timestamp,
                "interrupted": False,
                "random_state": random_state,
                "class_weights_applied": weights is not None,
                "class_weights": weights,
                "training_data_hash": data_hash,
                "dataset_path": dataset_path,
                "config": settings.as_json(),
                **data_config.as_json(),
                "epoch_history": [m.as_json() for m in state.history],
                "log_file": log_file,
            }
            ckpt.write_info(folder, info)
            retained.append(ckpt.Checkpoint(folder, info))
            ranked = ckpt.rank(retained)
            for dropped in ranked[settings.max_checkpoints :]:
                ckpt.delete([dropped])
            retained = ranked[: settings.max_checkpoints]
        log.data["checkpoint_paths"] = [
            _relative(c.path, plan.project_root) for c in ckpt.rank(retained)
        ]
        best = max(engine.state.history, key=lambda m: (m.val_accuracy, m.epoch))
        log.data["best_val_accuracy"] = round(best.val_accuracy, 6)
        log.data["best_epoch"] = best.epoch
        log.record_epoch(metrics.as_json())

    engine = Engine(
        model=model,
        loaders=(train_loader, val_loader),
        components=classification_components(),
        class_weights=weights,
        set_phase=lambda phase: set_phase(model, base_model, phase),
        set_train_mode=lambda: set_train_mode(model),
        optimizer_name=settings.optimizer,
        learning_rate=settings.learning_rate,
        phases=phases,
        patience=settings.early_stopping,
        device=device,
        on_epoch_end=on_epoch_end,
        reporter=reporter,
    )
    start_state = resume_state(resume.info, settings.early_stopping) if resume else None
    optimizer_state = payload.get("optimizer_state") if payload else None

    try:
        outcome = engine.run(start_state, optimizer_state)
    except KeyboardInterrupt:
        ckpt.mark_interrupted(c.path for c in retained)
        log.data["interrupted"] = True
        log.data["interrupted_at_epoch"] = engine.state.epoch + 1
        log.write()
        raise TrainingInterrupted(engine.state.epoch + 1, settings.epochs) from None
    except MemoryError as exc:
        raise _out_of_memory(settings.batch_size, exc) from exc
    except RuntimeError as exc:
        if (
            isinstance(exc, torch.cuda.OutOfMemoryError)
            or "out of memory" in str(exc).lower()
        ):
            raise _out_of_memory(settings.batch_size, exc) from exc
        raise

    state = outcome.state
    ckpt.mark_run_end(
        (c.path for c in retained),
        epochs_trained=state.epoch,
        early_stopped=outcome.early_stopped,
    )
    log.data["epochs_trained"] = state.epoch
    log.data["early_stopped"] = outcome.early_stopped
    log.data["phase1_stopped_early"] = state.phase1_stopped_early
    log.data.pop("interrupted", None)
    log.data.pop("interrupted_at_epoch", None)
    log.write()

    ranked = ckpt.rank(retained)
    best_ckpt = ranked[0] if ranked else None
    return TrainOutcome(
        run_id=run_id,
        best_checkpoint=best_ckpt.path if best_ckpt else None,
        best_val_accuracy=best_ckpt.val_accuracy if best_ckpt else None,
        test_accuracy=best_ckpt.info.get("test_accuracy") if best_ckpt else None,
        test_loss=best_ckpt.info.get("test_loss") if best_ckpt else None,
        epochs_run=state.epoch,
        epochs_requested=settings.epochs,
        phases=phases,
        phases_run=(state.phase_completed[0], state.phase_completed[1]),
        early_stopped=outcome.early_stopped,
        phase1_stopped_early=state.phase1_stopped_early,
        checkpoints=[c.path for c in ranked],
        log_paths=list(log.paths),
        classes_without_test=split.classes_without_test,
        split_counts={n: s.counts for n, s in split.classes.items()},
        device=str(device),
        patience=settings.early_stopping,
    )


def _qualifies(
    retained: Sequence[ckpt.Checkpoint], metrics: EpochMetrics, limit: int
) -> bool:
    """Whether this epoch ranks into the run's top ``limit``.

    Same ordering as export's ranking: val accuracy, then higher epoch — so a
    later epoch that ties the worst retained one replaces it.
    """
    if len(retained) < limit:
        return True
    worst = ckpt.rank(retained)[-1]
    return (metrics.val_accuracy, metrics.epoch) > (worst.val_accuracy, worst.epoch)


def _relative(path: Path, root: Path) -> str:
    """``checkpoints/<name>/`` — relative to the project root, ``/``-separated."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix() + "/"
    except ValueError:
        return path.as_posix() + "/"


def _initial_log(
    *,
    run_id: str,
    plan: TrainPlan,
    base_model: str,
    classes: list[str],
    split: DatasetSplit,
    random_state: int,
    weights: list[float] | None,
    data_hash: str,
    dataset_path: str,
    data_config: dict[str, Any],
    phases: tuple[int, int],
    device: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "model_family": plan.model_family,
        "base_model": base_model,
        "classes": classes,
        "num_classes": len(classes),
        "dataset_path": dataset_path,
        "training_data_hash": data_hash,
        "image_counts": {name: len(plan.files[name]) for name in classes},
        "split_counts": {name: s.counts for name, s in split.classes.items()},
        "random_state": random_state,
        "class_weights_applied": weights is not None,
        "class_weights": weights,
        "config": plan.settings.as_json(),
        "phases": {"phase1": phases[0], "phase2": phases[1]},
        "early_stopping": {
            "monitor": "val_loss",
            "patience": plan.settings.early_stopping,
            "min_delta": 0.0,
        },
        "preprocessing": data_config,
        "device": device,
        "epochs": [],
        "best_val_accuracy": None,
        "best_epoch": None,
        "checkpoint_paths": [],
    }


def _out_of_memory(batch_size: int, exc: BaseException) -> OpticaTrainingError:
    smaller = max(1, batch_size // 2)
    first_line = str(exc).splitlines()[0] if str(exc) else ""
    return OpticaTrainingError(
        f"Training ran out of memory at batch_size {batch_size}.",
        why=f"{type(exc).__name__}: {first_line}".strip(),
        fix=[
            f"Reduce the batch size: optica train --batch-size {smaller}",
            f"or: optica config --set batch_size {smaller}",
        ],
    )
