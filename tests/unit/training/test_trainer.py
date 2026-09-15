"""One classification training run.

Covers plan § "Training" → *Training Engine* steps 1-10 as a whole, *Checkpoints*
(top N per run, test evaluation at each save, the resume prompt's checkpoint),
*``checkpoint_info.json``* (fields, run-end amendment, ``class_weights`` aligned
with ``classes``), *Training log* (both copies, per epoch, interruption fields)
and § "Input & Acquisition" → *Class imbalance* (inverse-frequency weights).

The pure helpers run in CI. The runs are ``slow``: a synthetic dataset from
``image_dataset``, ``pretrained=False``, and ``torch.device("cpu")`` passed
explicitly — never whatever accelerator the machine happens to have.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from optica.training import checkpoints as ckpt
from optica.training import trainer
from optica.training.engine import Engine, EpochMetrics


class TestClassWeights:
    def test_inverse_frequency_index_aligned(self):
        # total 60, 2 classes: 60 / (2 x 45) and 60 / (2 x 15).
        assert trainer.class_weights_for([45, 15]) == [pytest.approx(0.666667), 2.0]

    def test_balanced_classes_weigh_one(self):
        assert trainer.class_weights_for([10, 10, 10]) == [1.0, 1.0, 1.0]


def _history(*rows: tuple[int, int, float]) -> list[dict[str, Any]]:
    return [
        EpochMetrics(e, p, 1.0, 0.5, loss, 0.5, 0.001, 1.0).as_json()
        for e, p, loss in rows
    ]


class TestResumeState:
    def test_counters_and_the_current_phase_best_are_rebuilt(self):
        info = {
            "epoch": 5,
            "training_phase": 2,
            "phase1_epochs_completed": 3,
            "phase2_epochs_completed": 2,
            "early_stopping_counter": 1,
            "epoch_history": _history(
                (1, 1, 0.2), (2, 1, 0.1), (3, 1, 0.3), (4, 2, 0.6), (5, 2, 0.7)
            ),
        }
        state = trainer.resume_state(info, patience=5)
        assert (state.epoch, state.phase, state.phase_completed) == (5, 2, [3, 2])
        assert state.early_stopping_counter == 1
        # Phase 2's best, not the run's: 0.1 was in phase 1.
        assert state.early_stopping_best == 0.6
        assert len(state.history) == 5
        assert not state.phase1_stopped_early

    def test_a_phase1_checkpoint_at_patience_was_where_phase1_stopped(self):
        info = {
            "epoch": 3,
            "training_phase": 1,
            "phase1_epochs_completed": 3,
            "phase2_epochs_completed": 0,
            "early_stopping_counter": 2,
            "epoch_history": _history((1, 1, 0.1), (2, 1, 0.2), (3, 1, 0.3)),
        }
        assert trainer.resume_state(info, patience=2).phase1_stopped_early
        assert not trainer.resume_state(info, patience=0).phase1_stopped_early


class TestTopN:
    def _ck(self, acc: float, epoch: int) -> ckpt.Checkpoint:
        return ckpt.Checkpoint(Path(f"c{epoch}"), {"val_accuracy": acc, "epoch": epoch})

    def _m(self, acc: float, epoch: int) -> EpochMetrics:
        return EpochMetrics(epoch, 1, 0.0, 0.0, 0.0, acc, 0.0, 0.0)

    def test_below_the_limit_every_epoch_qualifies(self):
        assert trainer._qualifies([self._ck(0.9, 1)], self._m(0.1, 2), 3)

    def test_at_the_limit_only_a_better_epoch_qualifies(self):
        retained = [self._ck(0.9, 1), self._ck(0.8, 2)]
        assert not trainer._qualifies(retained, self._m(0.7, 3), 2)
        assert trainer._qualifies(retained, self._m(0.85, 3), 2)

    def test_a_tie_with_the_worst_goes_to_the_later_epoch(self):
        retained = [self._ck(0.9, 1), self._ck(0.8, 2)]
        assert trainer._qualifies(retained, self._m(0.8, 3), 2)


# --------------------------------------------------------------------- slow


def _plan(root: Path, dataset: Path, **overrides: Any) -> trainer.TrainPlan:
    settings = trainer.TrainSettings(
        epochs=overrides.pop("epochs", 3),
        batch_size=8,
        learning_rate=0.001,
        augmentation=False,
        early_stopping=overrides.pop("early_stopping", 0),
        finetune_ratio=overrides.pop("finetune_ratio", 0.7),
        max_checkpoints=overrides.pop("max_checkpoints", 3),
        val_split=overrides.pop("val_split", 0.15),
        test_split=overrides.pop("test_split", 0.15),
    )
    files = {p.name: sorted(p.iterdir()) for p in sorted(dataset.iterdir())}
    return trainer.TrainPlan(
        dataset_root=dataset,
        files=files,
        model_family="mobilenet",
        settings=settings,
        class_weights=overrides.pop("class_weights", False),
        project_root=root,
        output=root / "optica-output",
        home=root / "home",
        pretrained=False,
        **overrides,
    )


def _cpu() -> Any:
    import torch

    return torch.device("cpu")


class _InterruptAt:
    def __init__(self, epoch: int) -> None:
        self.epoch = epoch

    def epoch_started(self, epoch: int, total: int, phase: int, batches: int) -> None:
        if epoch == self.epoch:
            raise KeyboardInterrupt

    def batch_done(self) -> None:
        pass

    def epoch_finished(self, metrics: Any) -> None:
        pass


@pytest.mark.slow
class TestRun:
    def test_a_completed_run(self, tmp_path, image_dataset):
        dataset = image_dataset({"dog": 10, "cat": 10})
        outcome = trainer.train(_plan(tmp_path, dataset), device=_cpu())

        assert outcome.epochs_run == 3
        assert outcome.phases == (1, 2) and outcome.phases_run == (1, 2)
        assert not outcome.early_stopped
        assert outcome.split_counts == {
            "cat": {"train": 8, "val": 1, "test": 1},
            "dog": {"train": 8, "val": 1, "test": 1},
        }
        retained = ckpt.rank(ckpt.list_active(tmp_path / "checkpoints"))
        assert [c.path for c in retained] == outcome.checkpoints
        assert len(retained) == 3
        info = retained[0].info
        assert info["classes"] == ["cat", "dog"]  # sorted ImageFolder order
        assert info["base_model"] == "mobilenetv3_large_100"
        assert info["test_accuracy"] is not None
        assert info["epochs_trained"] == 3 and info["early_stopped"] is False
        assert info["interrupted"] is False
        assert info["config"]["epochs"] == 3
        assert info["log_file"].startswith("~/.optica/logs/run_")
        assert Path(info["dataset_path"]).is_absolute()
        assert [e["epoch"] for e in info["epoch_history"]] == list(
            range(1, info["epoch"] + 1)
        )

        global_log, local_log = outcome.log_paths
        assert global_log.read_bytes() == local_log.read_bytes()
        log = json.loads(local_log.read_text(encoding="utf-8"))
        assert [e["epoch"] for e in log["epochs"]] == [1, 2, 3]
        assert log["run_id"] == outcome.run_id
        assert local_log.name == f"run_{outcome.run_id}_mobilenet_2classes.json"
        assert log["checkpoint_paths"] == [
            f"checkpoints/{c.path.name}/" for c in retained
        ]

    def test_only_the_top_n_of_a_run_are_retained(self, tmp_path, image_dataset):
        dataset = image_dataset({"cat": 10, "dog": 10})
        outcome = trainer.train(
            _plan(tmp_path, dataset, epochs=5, max_checkpoints=2), device=_cpu()
        )
        retained = ckpt.list_active(tmp_path / "checkpoints")
        assert len(retained) == 2 == len(outcome.checkpoints)
        log = json.loads(outcome.log_paths[1].read_text(encoding="utf-8"))
        best_two = sorted(
            log["epochs"], key=lambda e: (e["val_accuracy"], e["epoch"]), reverse=True
        )[:2]
        assert sorted(c.epoch for c in retained) == sorted(e["epoch"] for e in best_two)

    def test_no_test_allocation_means_null_test_metrics(self, tmp_path, image_dataset):
        dataset = image_dataset({"cat": 5, "dog": 5})  # 5 -> 4/1/0
        outcome = trainer.train(_plan(tmp_path, dataset, epochs=1), device=_cpu())
        assert outcome.classes_without_test == ["cat", "dog"]
        info = ckpt.list_active(tmp_path / "checkpoints")[0].info
        assert info["test_accuracy"] is None and info["test_loss"] is None

    def test_class_weights_are_recorded_aligned_with_classes(
        self, tmp_path, image_dataset
    ):
        dataset = image_dataset({"cat": 20, "dog": 6})
        trainer.train(
            _plan(tmp_path, dataset, epochs=1, class_weights=True), device=_cpu()
        )
        info = ckpt.list_active(tmp_path / "checkpoints")[0].info
        assert info["class_weights_applied"] is True
        split = json.loads(
            next((tmp_path / "optica-output" / "logs").iterdir()).read_text(
                encoding="utf-8"
            )
        )["split_counts"]
        counts = [split["cat"]["train"], split["dog"]["train"]]
        assert info["class_weights"] == trainer.class_weights_for(counts)

    def test_interruption_marks_the_run_and_resume_finishes_it(
        self, tmp_path, image_dataset
    ):
        dataset = image_dataset({"cat": 10, "dog": 10})
        plan = _plan(tmp_path, dataset, epochs=4)
        with pytest.raises(trainer.TrainingInterrupted) as info:
            trainer.train(plan, _InterruptAt(3), device=_cpu())
        assert (info.value.at_epoch, info.value.total) == (3, 4)

        saved = ckpt.list_active(tmp_path / "checkpoints")
        assert sorted(c.epoch for c in saved) == [1, 2]
        assert all(c.interrupted for c in saved)
        assert all("epochs_trained" not in c.info for c in saved)  # run did not finish
        log_path = next((tmp_path / "optica-output" / "logs").iterdir())
        log = json.loads(log_path.read_text(encoding="utf-8"))
        assert log["interrupted"] is True and log["interrupted_at_epoch"] == 3
        assert [e["epoch"] for e in log["epochs"]] == [1, 2]

        candidate = ckpt.resumable(saved)
        assert candidate is not None and candidate.epoch == 2
        resumed = trainer.train(
            _plan(tmp_path, dataset, epochs=4, resume_from=candidate), device=_cpu()
        )
        assert resumed.run_id == candidate.run_id
        assert resumed.epochs_run == 4
        assert resumed.phases_run == (1, 3)
        final = ckpt.list_active(tmp_path / "checkpoints")
        assert all(not c.interrupted for c in final)
        assert all(c.info["epochs_trained"] == 4 for c in final)
        assert {c.info["random_state"] for c in final} == {candidate.info["random_state"]}
        log = json.loads(log_path.read_text(encoding="utf-8"))
        assert [e["epoch"] for e in log["epochs"]] == [1, 2, 3, 4]
        assert "interrupted" not in log
        assert log["resumed"][0]["at_epoch"] == 2

    def test_resume_restores_the_checkpoint_weights(
        self, tmp_path, image_dataset, monkeypatch
    ):
        import torch

        dataset = image_dataset({"cat": 10, "dog": 10})
        with pytest.raises(trainer.TrainingInterrupted):
            trainer.train(
                _plan(tmp_path, dataset, epochs=3), _InterruptAt(2), device=_cpu()
            )
        candidate = ckpt.resumable(ckpt.list_active(tmp_path / "checkpoints"))
        assert candidate is not None
        stored = ckpt.load_weights(candidate.path)["state_dict"]

        seen: dict[str, Any] = {}
        real_run = Engine.run

        def spy(self, resume=None, optimizer_state=None):
            seen["weights"] = {k: v.clone() for k, v in self.model.state_dict().items()}
            seen["optimizer_state"] = optimizer_state
            return real_run(self, resume, optimizer_state)

        monkeypatch.setattr(Engine, "run", spy)
        trainer.train(
            _plan(tmp_path, dataset, epochs=3, resume_from=candidate), device=_cpu()
        )
        assert all(torch.equal(seen["weights"][k], stored[k]) for k in stored)
        assert seen["optimizer_state"] is not None
