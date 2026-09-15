"""The Training Engine: a generic two-phase loop with injected components.

Implements plan § "Training" → *Training Engine* (steps 4-10, two-phase training,
the ``--epochs 1`` and ``finetune_ratio`` edge cases), *Optimization* and
*Early stopping*.

**Generic by construction.** The loop knows nothing about classification: the
loss, the metric and the head arrive as :class:`TaskComponents`, and which
parameters a phase trains arrives as a callable. A post-V1 task supplies new
components rather than a new loop.

**Phase allocation** — ``phase1 = max(1, floor(epochs x (1 - finetune_ratio)))``,
``phase2 = epochs - phase1``, summing to ``epochs`` exactly — with the floor
tolerance from :mod:`optica.training.splits` (``20`` epochs at ``0.9`` is
``2 + 18``, not the ``1 + 19`` a bare float floor gives). ``finetune_ratio``
exactly ``0.0`` is head-only, exactly ``1.0`` is fine-tune-only; the one-epoch
minimum applies only to phases that exist.

**Optimization.** ``CrossEntropyLoss`` via the task components; AdamW
``weight_decay=0.01``, Adam ``weight_decay=0``, SGD ``momentum=0.9``, every other
hyperparameter at its PyTorch default; no scheduler. A fresh optimizer is built
per phase over that phase's trainable parameters, and Phase 2 runs at
``learning_rate x 0.1``.

**Early stopping** monitors ``val_loss`` with ``min_delta = 0`` and resets at the
phase boundary. What a trip *does* is not stated by the plan beyond that each
phase has its own window; decided (``notes/build-log.md``): patience reached in
Phase 1 ends Phase 1 and fine-tuning begins; reached in the last phase that
exists, it ends the run — and only that sets ``early_stopped``.

Nothing here imports torch at module level; the pure parts run in CI.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Protocol

from optica.training.splits import exact_floor
from optica.utils.mlstack import import_torch_stack

if TYPE_CHECKING:
    import torch
    from torch import nn

__all__ = [
    "PHASE2_LR_FACTOR",
    "EarlyStopping",
    "Engine",
    "EngineOutcome",
    "EngineState",
    "EpochMetrics",
    "Reporter",
    "TaskComponents",
    "allocate_phases",
    "build_optimizer",
    "classification_components",
    "finetune_ratio_warning",
    "phase2_skipped_by_one_epoch",
]

PHASE2_LR_FACTOR: Final = 0.1
_WEIGHT_DECAY: Final[dict[str, float]] = {"adamw": 0.01, "adam": 0.0}
_SGD_MOMENTUM: Final = 0.9


def allocate_phases(epochs: int, finetune_ratio: float) -> tuple[int, int]:
    """``(phase1, phase2)`` epochs, always summing to ``epochs``.

    Worked, from the plan at ``finetune_ratio = 0.70``: 5 → 1 + 4, 10 → 3 + 7,
    2 → 1 + 1, 1 → 1 + 0.
    """
    if epochs < 1:
        raise ValueError(f"epochs must be at least 1, got {epochs}")
    if finetune_ratio >= 1.0:
        return 0, epochs
    if finetune_ratio <= 0.0:
        return epochs, 0
    phase1 = max(1, exact_floor(epochs * (1 - finetune_ratio)))
    return phase1, epochs - phase1


def phase2_skipped_by_one_epoch(epochs: int, finetune_ratio: float) -> bool:
    """Whether the ``--epochs 1`` confirmation applies.

    Fine-tuning was asked for (a ratio strictly between 0 and 1) and the
    allocation leaves it no epoch — reachable only at ``epochs = 1``. At ratio
    ``0.0`` there is no Phase 2 to lose, and the plan gives that a warning only.
    """
    return 0.0 < finetune_ratio < 1.0 and allocate_phases(epochs, finetune_ratio)[1] == 0


def finetune_ratio_warning(finetune_ratio: float) -> str | None:
    """The warning for a permitted extreme, or None.

    ``0.0`` skips fine-tuning; ``1.0`` skips head warmup. Both are legal and both
    warn — a warning, which nothing suppresses (Implementation Note 19).
    """
    if finetune_ratio <= 0.0:
        return "finetune_ratio 0.0 skips fine-tuning: only the new head is trained."
    if finetune_ratio >= 1.0:
        return (
            "finetune_ratio 1.0 skips head warmup: the backbone's last layers train "
            "with a randomly initialised head from the first epoch."
        )
    return None


@dataclass
class EarlyStopping:
    """Patience on ``val_loss``, ``min_delta = 0``. ``patience = 0`` disables it.

    Attributes:
        patience: Epochs without improvement that end the phase.
        best: The lowest ``val_loss`` seen in this phase.
        counter: Epochs since ``best`` improved.
    """

    patience: int
    best: float | None = None
    counter: int = 0

    def step(self, val_loss: float) -> bool:
        """Record one epoch. Returns True when patience is reached."""
        if self.best is None or val_loss < self.best:
            self.best = val_loss
            self.counter = 0
            return False
        self.counter += 1
        return self.patience > 0 and self.counter >= self.patience

    def reset(self) -> None:
        """The phase boundary: an independent window."""
        self.best = None
        self.counter = 0


@dataclass
class TaskComponents:
    """What makes the generic loop a classification loop.

    Attributes:
        make_loss: Builds the loss from optional per-class weights.
        correct: Counts correct predictions in a batch.
    """

    make_loss: Callable[[Sequence[float] | None], Any]
    correct: Callable[[Any, Any], int]


def classification_components() -> TaskComponents:
    """``CrossEntropyLoss`` — weighted only when asked — and top-1 accuracy."""
    import_torch_stack()
    import torch

    def make_loss(weights: Sequence[float] | None) -> nn.Module:
        if weights is None:
            return torch.nn.CrossEntropyLoss()
        return torch.nn.CrossEntropyLoss(
            weight=torch.tensor(list(weights), dtype=torch.float32)
        )

    def correct(logits: torch.Tensor, targets: torch.Tensor) -> int:
        return int((logits.argmax(dim=1) == targets).sum().item())

    return TaskComponents(make_loss=make_loss, correct=correct)


def build_optimizer(
    name: str, params: Sequence[torch.nn.Parameter], learning_rate: float
) -> torch.optim.Optimizer:
    """The ``optimizer`` config key, with V1's fixed hyperparameters."""
    import_torch_stack()
    import torch

    if name == "adamw":
        return torch.optim.AdamW(
            params, lr=learning_rate, weight_decay=_WEIGHT_DECAY["adamw"]
        )
    if name == "adam":
        return torch.optim.Adam(
            params, lr=learning_rate, weight_decay=_WEIGHT_DECAY["adam"]
        )
    if name == "sgd":
        return torch.optim.SGD(params, lr=learning_rate, momentum=_SGD_MOMENTUM)
    raise ValueError(f"unknown optimizer {name!r}")


@dataclass
class EpochMetrics:
    """One completed epoch — the log's and ``epoch_history``'s entry."""

    epoch: int
    phase: int
    train_loss: float
    train_accuracy: float
    val_loss: float
    val_accuracy: float
    learning_rate: float
    seconds: float

    def as_json(self) -> dict[str, Any]:
        """JSON primitives, rounded — one entry of the log's ``epochs``."""
        return {
            "epoch": self.epoch,
            "phase": self.phase,
            "train_loss": round(self.train_loss, 6),
            "train_accuracy": round(self.train_accuracy, 6),
            "val_loss": round(self.val_loss, 6),
            "val_accuracy": round(self.val_accuracy, 6),
            "learning_rate": self.learning_rate,
            "seconds": round(self.seconds, 3),
        }


@dataclass
class EngineState:
    """Where a run is — what a checkpoint must carry to resume it.

    Attributes:
        epoch: Epochs completed.
        phase: The phase of the last completed epoch (1 before any).
        phase_completed: Epochs completed in phase 1 and phase 2.
        early_stopping_counter: The current phase's counter.
        early_stopping_best: The current phase's best ``val_loss``.
        history: Every completed epoch.
        phase1_stopped_early: Whether Phase 1 ended on patience.
    """

    epoch: int = 0
    phase: int = 1
    phase_completed: list[int] = field(default_factory=lambda: [0, 0])
    early_stopping_counter: int = 0
    early_stopping_best: float | None = None
    history: list[EpochMetrics] = field(default_factory=list)
    phase1_stopped_early: bool = False


@dataclass
class EngineOutcome:
    """How the loop ended.

    Attributes:
        state: The final state.
        early_stopped: The run ended because patience was reached — set here,
            never derived from the epoch count.
    """

    state: EngineState
    early_stopped: bool


class Reporter(Protocol):
    """Progress hooks. The CLI draws Rich bars; the API passes a silent one."""

    def epoch_started(self, epoch: int, total: int, phase: int, batches: int) -> None:
        """An epoch of ``batches`` training batches is starting."""

    def batch_done(self) -> None:
        """One training batch finished."""

    def epoch_finished(self, metrics: EpochMetrics) -> None:
        """An epoch finished, validated."""


class Engine:
    """Runs the phases. Components, parameter selection and callbacks are injected.

    Args:
        model: The configured model, already on ``device``.
        loaders: ``(train, val)`` data loaders.
        components: The task's loss and metric.
        class_weights: Per-class loss weights, or None (the default: unweighted).
        set_phase: Freezes the model for a phase and returns its trainable
            parameters.
        set_train_mode: Puts the model in training mode.
        optimizer_name: ``adamw``, ``adam`` or ``sgd``.
        learning_rate: Phase 1's rate; Phase 2 uses a tenth of it.
        phases: ``(phase1, phase2)`` epochs.
        patience: ``early_stopping``.
        device: Where tensors go.
        on_epoch_end: Called after each epoch with the metrics and the engine —
            where the trainer saves checkpoints and writes the log.
        reporter: Progress hooks.
    """

    def __init__(
        self,
        *,
        model: nn.Module,
        loaders: tuple[Any, Any],
        components: TaskComponents,
        class_weights: Sequence[float] | None,
        set_phase: Callable[[int], Sequence[torch.nn.Parameter]],
        set_train_mode: Callable[[], None],
        optimizer_name: str,
        learning_rate: float,
        phases: tuple[int, int],
        patience: int,
        device: torch.device,
        on_epoch_end: Callable[[EpochMetrics, Engine], None],
        reporter: Reporter,
    ) -> None:
        self.model = model
        self.train_loader, self.val_loader = loaders
        self.components = components
        self.criterion = components.make_loss(class_weights).to(device)
        self.set_phase = set_phase
        self.set_train_mode = set_train_mode
        self.optimizer_name = optimizer_name
        self.learning_rate = learning_rate
        self.phases = phases
        self.stopper = EarlyStopping(patience)
        self.device = device
        self.on_epoch_end = on_epoch_end
        self.reporter = reporter
        self.optimizer: torch.optim.Optimizer | None = None
        self.state = EngineState()

    @property
    def total_epochs(self) -> int:
        """Both phases' epochs."""
        return self.phases[0] + self.phases[1]

    def phase_learning_rate(self, phase: int) -> float:
        """``learning_rate``, times 0.1 in Phase 2."""
        return self.learning_rate * (PHASE2_LR_FACTOR if phase == 2 else 1.0)

    def evaluate(self, loader: Any) -> tuple[float, float] | None:
        """``(loss, accuracy)`` over a loader, or None when it holds no images."""
        import_torch_stack()
        import torch

        self.model.eval()
        total, correct, loss_sum = 0, 0, 0.0
        with torch.no_grad():
            for images, targets in loader:
                images, targets = images.to(self.device), targets.to(self.device)
                logits = self.model(images)
                loss_sum += float(self.criterion(logits, targets).item()) * len(targets)
                correct += self.components.correct(logits, targets)
                total += len(targets)
        if total == 0:
            return None
        return loss_sum / total, correct / total

    def _train_epoch(self) -> tuple[float, float]:
        assert self.optimizer is not None
        self.set_train_mode()
        total, correct, loss_sum = 0, 0, 0.0
        for images, targets in self.train_loader:
            images, targets = images.to(self.device), targets.to(self.device)
            self.optimizer.zero_grad(set_to_none=True)
            logits = self.model(images)
            loss = self.criterion(logits, targets)
            loss.backward()
            self.optimizer.step()
            loss_sum += float(loss.item()) * len(targets)
            correct += self.components.correct(logits.detach(), targets)
            total += len(targets)
            self.reporter.batch_done()
        return loss_sum / max(total, 1), correct / max(total, 1)

    def run(
        self,
        resume: EngineState | None = None,
        optimizer_state: dict[str, Any] | None = None,
    ) -> EngineOutcome:
        """Train both phases, from the start or from a resumed state.

        ``KeyboardInterrupt`` is not caught: the trainer marks the run's
        checkpoints interrupted and lets it propagate.
        """
        if resume is not None:
            self.state = resume
        state = self.state
        early_stopped = False
        for phase in (1, 2):
            planned = self.phases[phase - 1]
            done = state.phase_completed[phase - 1]
            if phase == 1 and (state.phase == 2 or state.phase1_stopped_early):
                continue
            if planned - done <= 0:
                continue
            params = self.set_phase(phase)
            self.optimizer = build_optimizer(
                self.optimizer_name, params, self.phase_learning_rate(phase)
            )
            resuming_this_phase = resume is not None and done > 0 and state.phase == phase
            if resuming_this_phase:
                self.stopper.counter = state.early_stopping_counter
                self.stopper.best = state.early_stopping_best
                if optimizer_state is not None:
                    self.optimizer.load_state_dict(optimizer_state)
            else:
                self.stopper.reset()
            stopped = False
            for _ in range(planned - done):
                started = time.monotonic()
                epoch = state.epoch + 1
                self.reporter.epoch_started(
                    epoch, self.total_epochs, phase, len(self.train_loader)
                )
                train_loss, train_accuracy = self._train_epoch()
                evaluated = self.evaluate(self.val_loader)
                assert evaluated is not None  # every class keeps a validation image
                val_loss, val_accuracy = evaluated
                stopped = self.stopper.step(val_loss)
                state.epoch = epoch
                state.phase = phase
                state.phase_completed[phase - 1] += 1
                state.early_stopping_counter = self.stopper.counter
                state.early_stopping_best = self.stopper.best
                metrics = EpochMetrics(
                    epoch=epoch,
                    phase=phase,
                    train_loss=train_loss,
                    train_accuracy=train_accuracy,
                    val_loss=val_loss,
                    val_accuracy=val_accuracy,
                    learning_rate=self.phase_learning_rate(phase),
                    seconds=time.monotonic() - started,
                )
                state.history.append(metrics)
                self.reporter.epoch_finished(metrics)
                self.on_epoch_end(metrics, self)
                if stopped:
                    break
            if stopped:
                last_phase = 2 if self.phases[1] > 0 else 1
                if phase == last_phase:
                    early_stopped = True
                    break
                state.phase1_stopped_early = True
        return EngineOutcome(state, early_stopped)
