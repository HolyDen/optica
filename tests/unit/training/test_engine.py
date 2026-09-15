"""The Training Engine.

Covers plan § "Training" → *Training Engine* (two-phase allocation and its worked
values 5 → 1 + 4, 10 → 3 + 7, 2 → 1 + 1; the ``--epochs 1`` and
``finetune_ratio`` extremes), *Optimization* (fixed hyperparameters, no
scheduler, Phase 2 at a tenth of the rate) and *Early stopping* (``val_loss``,
``min_delta = 0``, reset at the phase boundary, ``early_stopped`` set by the loop).

The allocation and early stopping are pure and run in CI. The loop runs on a
two-parameter model built here, not a backbone: what is under test is the loop.
"""

from __future__ import annotations

from typing import Any

import pytest

from optica.training import engine

# --------------------------------------------------------------------- pure


class TestAllocatePhases:
    @pytest.mark.parametrize(
        ("epochs", "expected"),
        [(5, (1, 4)), (10, (3, 7)), (2, (1, 1)), (1, (1, 0))],
    )
    def test_the_plans_worked_values(self, epochs, expected):
        assert engine.allocate_phases(epochs, 0.70) == expected

    @pytest.mark.parametrize("epochs", range(1, 60))
    @pytest.mark.parametrize("ratio", [0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0])
    def test_the_phases_always_sum_to_epochs(self, epochs, ratio):
        assert sum(engine.allocate_phases(epochs, ratio)) == epochs

    def test_ratio_zero_is_head_only_and_one_is_fine_tune_only(self):
        assert engine.allocate_phases(10, 0.0) == (10, 0)
        assert engine.allocate_phases(10, 1.0) == (0, 10)

    def test_the_floor_is_not_fooled_by_float_error(self):
        # 20 x (1 - 0.9) is 1.9999999999999996; the plan's floor means 2.
        assert 20 * (1 - 0.9) < 2
        assert engine.allocate_phases(20, 0.9) == (2, 18)

    def test_phase1_minimum_applies_when_phase1_exists(self):
        assert engine.allocate_phases(3, 0.95) == (1, 2)


class TestEdgeCasePrompts:
    def test_one_epoch_at_the_default_ratio_asks(self):
        assert engine.phase2_skipped_by_one_epoch(1, 0.70)

    @pytest.mark.parametrize(
        ("epochs", "ratio"), [(1, 0.0), (1, 1.0), (2, 0.7), (10, 0.7)]
    )
    def test_nothing_else_asks(self, epochs, ratio):
        # --epochs 1 at 0.0 warns only; at 1.0 there is no phase 1 to keep.
        assert not engine.phase2_skipped_by_one_epoch(epochs, ratio)

    def test_both_extremes_warn_and_nothing_between(self):
        assert "skips fine-tuning" in (engine.finetune_ratio_warning(0.0) or "")
        assert "skips head warmup" in (engine.finetune_ratio_warning(1.0) or "")
        assert engine.finetune_ratio_warning(0.7) is None
        assert engine.finetune_ratio_warning(0.01) is None


class TestEarlyStopping:
    def test_patience_counts_epochs_without_improvement(self):
        stopper = engine.EarlyStopping(patience=2)
        assert not stopper.step(1.0)
        assert not stopper.step(1.0)  # equal is not an improvement: min_delta 0
        assert stopper.step(1.1)

    def test_any_improvement_resets_the_counter(self):
        stopper = engine.EarlyStopping(patience=2)
        stopper.step(1.0)
        stopper.step(1.2)
        assert not stopper.step(0.9999999)
        assert stopper.counter == 0

    def test_zero_disables_it(self):
        stopper = engine.EarlyStopping(patience=0)
        stopper.step(1.0)
        assert not any(stopper.step(2.0) for _ in range(50))

    def test_reset_opens_an_independent_window(self):
        stopper = engine.EarlyStopping(patience=2)
        stopper.step(0.1)
        stopper.step(0.5)
        stopper.reset()
        # 0.5 would not have improved on 0.1; after the reset it is the new best.
        assert not stopper.step(0.5)
        assert stopper.best == 0.5


# --------------------------------------------------------------------- slow


class _Recorder:
    def __init__(self) -> None:
        self.started: list[tuple[int, int, int]] = []
        self.batches = 0

    def epoch_started(self, epoch: int, total: int, phase: int, batches: int) -> None:
        self.started.append((epoch, total, phase))

    def batch_done(self) -> None:
        self.batches += 1

    def epoch_finished(self, metrics: Any) -> None:
        pass


def _build(
    phases: tuple[int, int],
    patience: int,
    val_losses: list[float] | None = None,
    optimizer: str = "adamw",
):
    """A two-parameter model: ``body`` (Phase 2 only) and ``head`` (both phases).

    ``val_losses``, when given, replaces the real validation loss epoch by epoch,
    so early stopping can be driven exactly.
    """
    import torch

    torch.manual_seed(0)
    model = torch.nn.Sequential(torch.nn.Linear(4, 4), torch.nn.Linear(4, 2))
    body, head = model[0], model[1]
    x = torch.randn(16, 4)
    y = (x[:, 0] > 0).long()
    batches = [(x[:8], y[:8]), (x[8:], y[8:])]

    def set_phase(phase: int) -> list[Any]:
        for p in body.parameters():
            p.requires_grad = phase == 2
        for p in head.parameters():
            p.requires_grad = True
        return [p for p in model.parameters() if p.requires_grad]

    record: dict[str, Any] = {"lrs": [], "trainable": []}

    def on_epoch_end(metrics: Any, eng: engine.Engine) -> None:
        assert eng.optimizer is not None
        record["lrs"].append(eng.optimizer.param_groups[0]["lr"])
        record["trainable"].append(
            sum(p.numel() for g in eng.optimizer.param_groups for p in g["params"])
        )

    eng = engine.Engine(
        model=model,
        loaders=(batches, batches),
        components=engine.classification_components(),
        class_weights=None,
        set_phase=set_phase,
        set_train_mode=lambda: None,
        optimizer_name=optimizer,
        learning_rate=0.01,
        phases=phases,
        patience=patience,
        device=torch.device("cpu"),
        on_epoch_end=on_epoch_end,
        reporter=_Recorder(),
    )
    if val_losses is not None:
        losses = iter(val_losses)
        real = eng.evaluate

        def scripted(loader: Any) -> tuple[float, float] | None:
            result = real(loader)
            assert result is not None
            return next(losses), result[1]

        eng.evaluate = scripted  # type: ignore[method-assign]
    return eng, record


@pytest.mark.slow
class TestLoop:
    def test_phases_run_in_order_with_phase2_at_a_tenth_of_the_rate(self):
        eng, record = _build((2, 3), patience=0)
        outcome = eng.run()
        assert [m.phase for m in outcome.state.history] == [1, 1, 2, 2, 2]
        assert record["lrs"] == [0.01, 0.01, 0.001, 0.001, 0.001]
        # Phase 1 trains the head's 10 parameters; Phase 2 adds the body's 20.
        assert record["trainable"] == [10, 10, 30, 30, 30]
        assert outcome.state.epoch == 5
        assert outcome.state.phase_completed == [2, 3]
        assert not outcome.early_stopped

    def test_patience_in_phase1_moves_on_to_fine_tuning(self):
        # Phase 1 of 5: best at epoch 1, then two worse epochs -> patience 2 trips.
        eng, _ = _build((5, 2), patience=2, val_losses=[1.0, 2.0, 2.0, 5.0, 5.0])
        outcome = eng.run()
        assert [m.phase for m in outcome.state.history] == [1, 1, 1, 2, 2]
        assert outcome.state.phase1_stopped_early
        assert not outcome.early_stopped  # the run did not end on patience

    def test_the_window_resets_at_the_phase_boundary(self):
        # Phase 2's first loss (5.0) is worse than Phase 1's best (1.0); without
        # the reset it would count toward patience and stop after one more.
        eng, _ = _build((2, 3), patience=2, val_losses=[1.0, 1.0, 5.0, 4.0, 3.0])
        outcome = eng.run()
        assert outcome.state.epoch == 5
        assert not outcome.early_stopped

    def test_patience_in_the_last_phase_ends_the_run_and_sets_early_stopped(self):
        eng, _ = _build((1, 5), patience=2, val_losses=[1.0, 1.0, 2.0, 2.0, 0.1, 0.1])
        outcome = eng.run()
        assert outcome.state.epoch == 4
        assert outcome.early_stopped

    def test_head_only_run_that_trips_patience_is_early_stopped(self):
        eng, _ = _build((5, 0), patience=1, val_losses=[1.0, 2.0, 0.5, 0.5, 0.5])
        outcome = eng.run()
        assert outcome.state.epoch == 2
        assert outcome.early_stopped

    def test_a_resumed_run_continues_where_the_state_says(self):
        partial = engine.EngineState(
            epoch=3, phase=2, phase_completed=[2, 1], early_stopping_counter=0
        )
        second, record = _build((2, 3), patience=0)
        outcome = second.run(partial)
        assert [m.epoch for m in outcome.state.history] == [4, 5]
        assert record["lrs"] == [0.001, 0.001]
        assert outcome.state.phase_completed == [2, 3]

    @pytest.mark.parametrize(
        ("name", "kind", "expected"),
        [
            ("adamw", "AdamW", {"weight_decay": 0.01}),
            ("adam", "Adam", {"weight_decay": 0.0}),
            ("sgd", "SGD", {"momentum": 0.9}),
        ],
    )
    def test_optimizer_hyperparameters_are_fixed(self, name, kind, expected):
        import torch

        param = torch.nn.Parameter(torch.zeros(1))
        optimizer = engine.build_optimizer(name, [param], 0.001)
        assert type(optimizer).__name__ == kind
        group = optimizer.param_groups[0]
        assert group["lr"] == 0.001
        for key, value in expected.items():
            assert group[key] == value

    def test_class_weights_reach_the_loss(self):
        import torch

        components = engine.classification_components()
        assert components.make_loss(None).weight is None
        weighted = components.make_loss([0.5, 2.0])
        assert torch.equal(weighted.weight, torch.tensor([0.5, 2.0]))
