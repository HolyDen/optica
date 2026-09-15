"""``optica train``, through the real command, with the trainer replaced.

Covers plan § "Training" → *Terminal completion*, *Checkpoints* (the training
resume prompt fires first and skips K/A/D/S; K/A/D/S and the soft limit), the
CPU batch-size safety prompt, the ``--epochs 1`` confirmation and the
``finetune_ratio`` warnings; § "Input & Acquisition" → *Class imbalance and image
validation* on a dataset the user brought (C/A only, per-file stages report
without writing, deduplication excluded, the floor before and after), and
*``--classes`` against an already-organized dataset*; § "Export" → *``--output``
path handling* as it applies to the training log; and the ``--yes`` table rows
for every one of those prompts.

**Nothing here needs torch.** ``import_torch_stack``, ``select_device`` and the
trainer are replaced, and the device is constructed per test — CPU or CUDA as
the test states, never the machine's. The real training loop is covered by
``tests/unit/training/``.
"""

from __future__ import annotations

import csv
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from optica.cli.main import app
from optica.exceptions import ExitCode
from optica.training import checkpoints as ckpt
from optica.training.trainer import TrainingInterrupted, TrainOutcome


class FakeTrainer:
    def __init__(self) -> None:
        self.plans: list[Any] = []
        self.raise_: BaseException | None = None
        self.outcome_overrides: dict[str, Any] = {}

    def __call__(self, plan, reporter=None, *, device=None, on_status=None) -> Any:
        self.plans.append(plan)
        if self.raise_ is not None:
            raise self.raise_
        fields: dict[str, Any] = {
            "run_id": "20260915_120000",
            "best_checkpoint": Path("checkpoints/checkpoint_val0.852_epoch7"),
            "best_val_accuracy": 0.852,
            "test_accuracy": 0.834,
            "test_loss": 0.391,
            "epochs_run": plan.settings.epochs,
            "epochs_requested": plan.settings.epochs,
            "phases": (3, 7),
            "phases_run": (3, 7),
            "early_stopped": False,
            "phase1_stopped_early": False,
            "checkpoints": [Path("a"), Path("b"), Path("c")],
            "log_paths": [],
            "classes_without_test": [],
            "split_counts": {name: {} for name in plan.files},
            "patience": plan.settings.early_stopping,
        }
        fields.update(self.outcome_overrides)
        return TrainOutcome(**fields)


@pytest.fixture
def device():
    """The device the command sees. CUDA unless a test says CPU."""
    return SimpleNamespace(type="cuda")


@pytest.fixture
def fake(monkeypatch, fake_home, project_dir, device):
    trainer = FakeTrainer()
    trainer.torch_imports = 0  # type: ignore[attr-defined]

    def import_stack():
        trainer.torch_imports += 1  # type: ignore[attr-defined]

    monkeypatch.setattr("optica.cli.classify.import_torch_stack", import_stack)
    monkeypatch.setattr("optica.cli.classify.select_device", lambda: device)
    monkeypatch.setattr("optica.cli.classify._device_description", lambda d: d.type)
    monkeypatch.setattr("optica.cli.classify.run_training", trainer)
    return trainer


@pytest.fixture
def interactive(monkeypatch):
    monkeypatch.setattr("optica.utils.prompts.is_interactive", lambda: True)
    monkeypatch.setattr("optica.cli.main.is_interactive", lambda: True)


@pytest.fixture
def dataset(project_dir, image_dataset):
    return image_dataset({"cat": 10, "dog": 10}, root=project_dir / "dataset")


def _checkpoint(root: Path, name: str, **info: Any) -> Path:
    folder = root / "checkpoints" / name
    folder.mkdir(parents=True)
    ckpt.write_info(
        folder,
        {
            "val_accuracy": 0.5,
            "epoch": 1,
            "training_timestamp": "2026-01-01T00:00:00",
            **info,
        },
    )
    return folder


def _answers(
    monkeypatch,
    choices: dict[str, str] | None = None,
    confirms: dict[str, bool] | None = None,
):
    asked: list[str] = []

    def prompt(text, **kwargs):
        asked.append(text)
        for key, value in (choices or {}).items():
            if key in text:
                return value
        return kwargs.get("default", "")

    def confirm(text, **kwargs):
        asked.append(text)
        for key, value in (confirms or {}).items():
            if key in text:
                return value
        return True

    monkeypatch.setattr("typer.prompt", prompt)
    monkeypatch.setattr("typer.confirm", confirm)
    return asked


class TestHappyPath:
    def test_yes_trains_with_the_resolved_settings_and_prints_the_completion_block(
        self, fake, dataset, capsys
    ):
        code = app.invoke_guarded(
            ["train", "--epochs", "10", "--batch-size", "16", "--yes"]
        )
        captured = capsys.readouterr()
        assert code == ExitCode.SUCCESS, captured.err
        [plan] = fake.plans
        assert sorted(plan.files) == ["cat", "dog"]
        assert all(len(paths) == 10 for paths in plan.files.values())
        assert plan.settings.epochs == 10 and plan.settings.batch_size == 16
        assert plan.model_family == "efficientnet-small"
        assert plan.resume_from is None and plan.class_weights is False
        out = captured.out
        assert "✓ Training complete — best val_accuracy 0.852" in out
        assert "  Epochs: 10 of 10\n" in out
        assert "  Phases: 3 head warmup + 7 fine-tune" in out
        assert "  Test: accuracy 0.834, loss 0.391" in out
        assert "  Checkpoints: 3 saved in ./checkpoints/" in out

    def test_early_stopping_is_visible_in_the_epochs_line(self, fake, dataset, capsys):
        fake.outcome_overrides = {"epochs_run": 8, "early_stopped": True}
        app.invoke_guarded(["train", "--epochs", "10", "--yes"])
        assert (
            "  Epochs: 8 of 10 (stopped early — val_loss, patience 5)"
            in capsys.readouterr().out
        )

    def test_test_absent_for_some_classes_says_how_many(self, fake, dataset, capsys):
        fake.outcome_overrides = {"classes_without_test": ["cat"]}
        app.invoke_guarded(["train", "--yes"])
        assert "(1 class absent from test set)" in capsys.readouterr().out

    def test_no_test_allocation_reads_not_evaluated(self, fake, dataset, capsys):
        fake.outcome_overrides = {
            "classes_without_test": ["cat", "dog"],
            "test_accuracy": None,
            "test_loss": None,
        }
        app.invoke_guarded(["train", "--yes"])
        assert (
            "Test: not evaluated — no class received a test allocation"
            in capsys.readouterr().out
        )

    def test_an_interrupt_exits_130_with_the_incomplete_line(self, fake, dataset, capsys):
        fake.raise_ = TrainingInterrupted(3, 10)
        assert app.invoke_guarded(["train", "--yes"]) == ExitCode.INTERRUPTED
        assert (
            "Training incomplete — interrupted at epoch 3/10" in capsys.readouterr().err
        )

    def test_the_lock_is_released(self, fake, dataset):
        from optica.utils.lockfile import lock_path

        app.invoke_guarded(["train", "--yes"])
        assert not lock_path().exists()


class TestEntryChecks:
    def test_a_missing_dataset_errors_before_torch_is_imported(self, fake, capsys):
        assert app.invoke_guarded(["train", "--yes"]) == ExitCode.ERROR
        assert "No folder found at dataset" in capsys.readouterr().err
        assert fake.torch_imports == 0
        assert fake.plans == []

    def test_a_class_named_without_a_folder_is_a_hard_error_first(
        self, fake, dataset, capsys
    ):
        code = app.invoke_guarded(["train", "-c", "cat,pug", "--yes"])
        assert code == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "In --classes but no matching folder: pug" in err
        assert fake.torch_imports == 0

    def test_a_subset_is_confirmed_and_yes_trains_on_it(
        self, fake, project_dir, image_dataset, capsys
    ):
        image_dataset({"cat": 5, "dog": 5, "bird": 5}, root=project_dir / "dataset")
        assert app.invoke_guarded(["train", "-c", "dog,cat", "--yes"]) == ExitCode.SUCCESS
        assert sorted(fake.plans[0].files) == ["cat", "dog"]
        assert "Excluded from this run: bird" in capsys.readouterr().err

    def test_a_subset_without_a_terminal_or_yes_refuses(
        self, fake, project_dir, image_dataset
    ):
        image_dataset({"cat": 5, "dog": 5, "bird": 5}, root=project_dir / "dataset")
        assert app.invoke_guarded(["train", "-c", "dog,cat"]) == ExitCode.ERROR
        assert fake.plans == []


class TestIngest:
    def test_unreadable_files_are_left_out_and_untouched(self, fake, dataset, capsys):
        broken = dataset / "cat" / "broken.png"
        broken.write_bytes(b"not an image")
        assert app.invoke_guarded(["train", "--yes"]) == ExitCode.SUCCESS
        assert len(fake.plans[0].files["cat"]) == 10
        assert broken not in fake.plans[0].files["cat"]
        assert broken.read_bytes() == b"not an image"
        assert "broken.png" in capsys.readouterr().err

    def test_duplicates_are_excluded_from_the_run_not_deleted(
        self, fake, dataset, capsys
    ):
        copy = dataset / "dog" / "copy.png"
        copy.write_bytes((dataset / "dog" / "0000.png").read_bytes())
        assert app.invoke_guarded(["train", "--yes"]) == ExitCode.SUCCESS
        assert len(fake.plans[0].files["dog"]) == 10
        assert copy.exists()
        assert "1 duplicate image left out of the run" in capsys.readouterr().out

    def test_falling_below_the_floor_after_deduplication_is_the_plan_error(
        self, fake, project_dir, image_dataset, capsys
    ):
        root = image_dataset({"cat": 5, "dog": 10}, root=project_dir / "dataset")
        (root / "cat" / "dupe.png").write_bytes((root / "cat" / "0000.png").read_bytes())
        (root / "cat" / "0004.png").write_bytes((root / "cat" / "0001.png").read_bytes())
        assert app.invoke_guarded(["train", "--yes"]) == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "cat fell below the 5-image minimum after duplicate removal." in err
        assert fake.plans == []

    def test_undersized_images_warn_and_are_not_resized(
        self, fake, project_dir, image_dataset, capsys
    ):
        root = image_dataset({"cat": 5, "dog": 5}, root=project_dir / "dataset", size=32)
        before = (root / "cat" / "0000.png").read_bytes()
        assert app.invoke_guarded(["train", "--yes"]) == ExitCode.SUCCESS
        assert "smaller than 128px" in capsys.readouterr().err
        assert (root / "cat" / "0000.png").read_bytes() == before


class TestImbalance:
    @pytest.fixture
    def lopsided(self, project_dir, image_dataset):
        return image_dataset({"cat": 20, "dog": 6}, root=project_dir / "dataset")

    def test_yes_picks_c_and_weights_the_loss(self, fake, lopsided, capsys):
        assert app.invoke_guarded(["train", "--yes"]) == ExitCode.SUCCESS
        assert fake.plans[0].class_weights is True
        err = capsys.readouterr().err
        assert "Class imbalance detected:" in err
        assert "cat: 20 images" in err and "dog: 6 images" in err

    def test_fetch_more_is_not_offered_on_a_brought_dataset(
        self, fake, lopsided, interactive, monkeypatch
    ):
        asked = _answers(monkeypatch)
        app.invoke_guarded(["train"])
        menu = next(
            text for text in asked if "Continue with automatic class weighting" in text
        )
        assert "[C]" in menu and "[A]" in menu
        assert "[F]" not in menu

    def test_a_aborts_with_exit_3(self, fake, lopsided, interactive, monkeypatch):
        _answers(monkeypatch, choices={"class weighting": "A"})
        assert app.invoke_guarded(["train"]) == ExitCode.ABORTED
        assert fake.plans == []

    def test_a_balanced_dataset_asks_nothing(
        self, fake, dataset, interactive, monkeypatch
    ):
        asked = _answers(monkeypatch)
        app.invoke_guarded(["train"])
        assert not any("imbalance" in text.lower() for text in asked)
        assert fake.plans[0].class_weights is False


class TestCpuBatchSize:
    def test_on_cpu_above_16_yes_continues(self, fake, dataset, device, capsys):
        device.type = "cpu"
        assert app.invoke_guarded(["train", "--yes"]) == ExitCode.SUCCESS
        assert (
            "Training on CPU with batch_size 32 may cause memory issues"
            in capsys.readouterr().err
        )

    def test_force_suppresses_it_but_the_warning_still_shows(
        self, fake, dataset, device, interactive, monkeypatch, capsys
    ):
        device.type = "cpu"
        asked = _answers(monkeypatch, confirms={"Continue anyway": False})
        assert app.invoke_guarded(["train", "--force"]) == ExitCode.SUCCESS
        assert not any("Continue anyway" in text for text in asked)
        assert "may cause memory issues" in capsys.readouterr().err

    def test_n_exits_3_with_the_adjustment_commands(
        self, fake, dataset, device, interactive, monkeypatch, capsys
    ):
        device.type = "cpu"
        _answers(monkeypatch, confirms={"Continue anyway": False})
        assert app.invoke_guarded(["train"]) == ExitCode.ABORTED
        err = capsys.readouterr().err
        assert "optica train --batch-size 8 or optica config --set batch_size 8" in err
        assert fake.plans == []

    @pytest.mark.parametrize(("kind", "batch"), [("cuda", "32"), ("cpu", "16")])
    def test_not_asked_on_a_gpu_or_at_16(
        self, fake, dataset, device, kind, batch, interactive, monkeypatch
    ):
        device.type = kind
        asked = _answers(monkeypatch)
        app.invoke_guarded(["train", "--batch-size", batch])
        assert not any("Continue anyway" in text for text in asked)


class TestEpochAllocationPrompts:
    def test_one_epoch_at_the_default_ratio_confirms_and_n_exits_3(
        self, fake, dataset, interactive, monkeypatch
    ):
        _answers(monkeypatch, confirms={"--epochs 1": False})
        assert app.invoke_guarded(["train", "--epochs", "1"]) == ExitCode.ABORTED
        assert fake.plans == []

    def test_yes_continues_past_it(self, fake, dataset):
        assert app.invoke_guarded(["train", "--epochs", "1", "--yes"]) == ExitCode.SUCCESS

    @pytest.mark.parametrize(
        ("ratio", "text"), [("0.0", "skips fine-tuning"), ("1.0", "skips head warmup")]
    )
    def test_the_ratio_extremes_warn(
        self, fake, dataset, project_dir, ratio, text, capsys
    ):
        (project_dir / ".optica.toml").write_text(
            f"finetune_ratio = {ratio}\n", encoding="utf-8"
        )
        assert app.invoke_guarded(["train", "--yes"]) == ExitCode.SUCCESS
        assert text in capsys.readouterr().err


class TestCheckpointHousekeeping:
    def test_yes_keeps_everything(self, fake, dataset, project_dir):
        folder = _checkpoint(project_dir, "checkpoint_val0.500_epoch1")
        assert app.invoke_guarded(["train", "--yes"]) == ExitCode.SUCCESS
        assert folder.exists()

    def test_the_prompt_offers_four_options(
        self, fake, dataset, project_dir, interactive, monkeypatch
    ):
        _checkpoint(project_dir, "checkpoint_val0.500_epoch1")
        asked = _answers(monkeypatch)
        app.invoke_guarded(["train"])
        menu = next(text for text in asked if "What would you like to do?" in text)
        for letter in ("[K] Keep all", "[A] Archive all", "[D] Delete all", "[S] Select"):
            assert letter in menu

    def test_archive_moves_them_to_a_timestamped_folder(
        self, fake, dataset, project_dir, interactive, monkeypatch
    ):
        _checkpoint(project_dir, "checkpoint_val0.500_epoch1")
        _answers(monkeypatch, choices={"What would you like to do?": "A"})
        assert app.invoke_guarded(["train"]) == ExitCode.SUCCESS
        [stamp] = list((project_dir / "checkpoints" / "archive").iterdir())
        assert len(stamp.name) == len("20260915_120000") and stamp.name[8] == "_"
        assert (stamp / "checkpoint_val0.500_epoch1" / ckpt.INFO_FILE).exists()

    def test_delete_removes_them(
        self, fake, dataset, project_dir, interactive, monkeypatch
    ):
        folder = _checkpoint(project_dir, "checkpoint_val0.500_epoch1")
        _answers(monkeypatch, choices={"What would you like to do?": "D"})
        assert app.invoke_guarded(["train"]) == ExitCode.SUCCESS
        assert not folder.exists()

    def test_select_decides_per_checkpoint(
        self, fake, dataset, project_dir, interactive, monkeypatch
    ):
        keep = _checkpoint(
            project_dir, "checkpoint_val0.900_epoch2", val_accuracy=0.9, epoch=2
        )
        drop = _checkpoint(project_dir, "checkpoint_val0.500_epoch1")
        _answers(
            monkeypatch,
            choices={
                "What would you like to do?": "S",
                "checkpoint_val0.900_epoch2\n": "K",
                "checkpoint_val0.500_epoch1\n": "D",
            },
        )
        assert app.invoke_guarded(["train"]) == ExitCode.SUCCESS
        assert keep.exists() and not drop.exists()

    def test_nothing_is_deleted_when_a_later_question_stops_the_run(
        self, fake, dataset, project_dir, device, interactive, monkeypatch
    ):
        folder = _checkpoint(project_dir, "checkpoint_val0.500_epoch1")
        device.type = "cpu"
        _answers(
            monkeypatch,
            choices={"What would you like to do?": "D"},
            confirms={"Continue anyway": False},
        )
        assert app.invoke_guarded(["train"]) == ExitCode.ABORTED
        assert folder.exists()

    def test_without_a_terminal_or_yes_it_refuses(self, fake, dataset, project_dir):
        _checkpoint(project_dir, "checkpoint_val0.500_epoch1")
        assert app.invoke_guarded(["train"]) == ExitCode.ERROR
        assert fake.plans == []

    def test_the_soft_limit_warns_above_three_times_max_checkpoints(
        self, fake, dataset, project_dir, capsys
    ):
        for i in range(10):
            _checkpoint(project_dir, f"checkpoint_val0.500_epoch{i}", epoch=i)
        assert app.invoke_guarded(["train", "--yes"]) == ExitCode.SUCCESS
        assert "10 checkpoints are kept" in capsys.readouterr().err

    def test_at_the_soft_limit_nothing_warns(self, fake, dataset, project_dir, capsys):
        for i in range(9):
            _checkpoint(project_dir, f"checkpoint_val0.500_epoch{i}", epoch=i)
        app.invoke_guarded(["train", "--yes"])
        assert "checkpoints are kept" not in capsys.readouterr().err


class TestResume:
    def _interrupted(self, project_dir: Path, dataset: Path, **info: Any) -> Path:
        from optica.training.splits import training_data_hash

        base = {
            "interrupted": True,
            "epoch": 7,
            "run_id": "20260101_000000",
            "model_family": "resnet",
            "classes": ["cat", "dog"],
            "training_data_hash": training_data_hash(dataset),
            "class_weights_applied": False,
            "config": {
                "epochs": 12,
                "batch_size": 8,
                "learning_rate": 0.01,
                "augmentation": False,
                "early_stopping": 2,
                "finetune_ratio": 0.5,
            },
        }
        return _checkpoint(project_dir, "checkpoint_val0.852_epoch7", **{**base, **info})

    def test_yes_continues_with_the_runs_settings(
        self, fake, dataset, project_dir, capsys
    ):
        folder = self._interrupted(project_dir, dataset)
        assert app.invoke_guarded(["train", "--yes"]) == ExitCode.SUCCESS
        [plan] = fake.plans
        assert plan.resume_from is not None and plan.resume_from.path == folder
        assert plan.model_family == "resnet"
        assert plan.settings.epochs == 12 and plan.settings.batch_size == 8
        err = capsys.readouterr().err
        assert (
            "Training was interrupted at epoch 7 of 12 (checkpoint_val0.852_epoch7)."
            in err
        )

    def test_continuing_skips_checkpoint_housekeeping_entirely(
        self, fake, dataset, project_dir, interactive, monkeypatch
    ):
        # Interactive, with every question recorded: under --yes the K/A/D/S menu
        # is answered without being shown, so its absence there would prove nothing.
        self._interrupted(project_dir, dataset)
        other = _checkpoint(project_dir, "checkpoint_val0.100_epoch1")
        asked = _answers(
            monkeypatch,
            choices={"What would you like to do?": "D"},
            confirms={"Continue from checkpoint?": True},
        )
        assert app.invoke_guarded(["train"]) == ExitCode.SUCCESS
        assert any("Continue from checkpoint?" in text for text in asked)
        assert not any("What would you like to do?" in text for text in asked)
        assert other.exists()

    def test_flags_given_with_a_resume_are_named_as_ignored(
        self, fake, dataset, project_dir, capsys
    ):
        self._interrupted(project_dir, dataset)
        app.invoke_guarded(["train", "--epochs", "3", "--yes"])
        assert "--epochs ignored" in capsys.readouterr().err
        assert fake.plans[0].settings.epochs == 12

    def test_n_starts_fresh_and_housekeeping_follows(
        self, fake, dataset, project_dir, interactive, monkeypatch
    ):
        self._interrupted(project_dir, dataset)
        asked = _answers(monkeypatch, confirms={"Continue from checkpoint?": False})
        assert app.invoke_guarded(["train"]) == ExitCode.SUCCESS
        assert fake.plans[0].resume_from is None
        order = [
            i
            for i, text in enumerate(asked)
            if "Continue from checkpoint?" in text or "What would you like" in text
        ]
        assert len(order) == 2 and "Continue from checkpoint?" in asked[order[0]]

    def test_a_changed_dataset_refuses_to_resume(
        self, fake, dataset, project_dir, capsys
    ):
        self._interrupted(project_dir, dataset)
        (dataset / "cat" / "new.png").write_bytes(
            (dataset / "cat" / "0000.png").read_bytes()[:-1] + b"\x00"
        )
        assert app.invoke_guarded(["train", "--yes"]) == ExitCode.ERROR
        assert (
            "The dataset has changed since the interrupted run."
            in capsys.readouterr().err
        )
        assert fake.plans == []

    def test_the_prompt_reads_the_interrupted_epoch_from_the_log(
        self, fake, dataset, project_dir, fake_home, capsys
    ):
        log = fake_home / ".optica" / "logs" / "run.json"
        log.parent.mkdir(parents=True)
        log.write_text('{"interrupted_at_epoch": 9}', encoding="utf-8")
        self._interrupted(project_dir, dataset, log_file=str(log))
        app.invoke_guarded(["train", "--yes"])
        assert "interrupted at epoch 9 of 12" in capsys.readouterr().err


class TestOutput:
    def test_an_absent_container_is_created_under_yes(self, fake, dataset, project_dir):
        assert (
            app.invoke_guarded(["train", "--output", "runs", "--yes"]) == ExitCode.SUCCESS
        )
        assert (project_dir / "runs").is_dir()

    def test_without_a_terminal_or_yes_it_refuses(self, fake, dataset, project_dir):
        assert app.invoke_guarded(["train", "--output", "runs"]) == ExitCode.ERROR
        assert not (project_dir / "runs").exists()

    def test_a_file_is_a_hard_error(self, fake, dataset, project_dir, capsys):
        (project_dir / "runs").write_text("x", encoding="utf-8")
        assert (
            app.invoke_guarded(["train", "--output", "runs", "--yes"]) == ExitCode.ERROR
        )
        assert "is a file, not a folder" in capsys.readouterr().err


class TestManifest:
    def _manifest(
        self, project_dir: Path, image_dataset, rows: list[tuple[str, str]] | None = None
    ) -> Path:
        source = image_dataset({"cat": 6, "dog": 6}, root=project_dir / "images")
        path = project_dir / "labels.csv"
        rows = rows or [(str(p), p.parent.name) for p in sorted(source.rglob("*.png"))]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["path", "class"])
            writer.writerows(rows)
        return path

    def test_a_fully_labeled_manifest_materializes_then_trains(
        self, fake, project_dir, image_dataset
    ):
        manifest = self._manifest(project_dir, image_dataset)
        assert (
            app.invoke_guarded(["train", "--manifest", str(manifest), "--yes"])
            == ExitCode.SUCCESS
        )
        assert sorted(p.name for p in (project_dir / "dataset").iterdir()) == [
            "cat",
            "dog",
        ]
        assert all(len(v) == 6 for v in fake.plans[0].files.values())

    def test_a_populated_dataset_refuses_unattended_without_overwrite(
        self, fake, project_dir, image_dataset, dataset
    ):
        manifest = self._manifest(project_dir, image_dataset)
        assert (
            app.invoke_guarded(["train", "--manifest", str(manifest), "--yes"])
            == ExitCode.ERROR
        )
        assert fake.plans == []
        assert fake.torch_imports == 0


class TestDryRun:
    def test_it_reports_the_plan_and_touches_nothing(
        self, fake, dataset, project_dir, capsys
    ):
        assert (
            app.invoke_guarded(["train", "--dry-run", "--epochs", "10"])
            == ExitCode.SUCCESS
        )
        out = capsys.readouterr().out
        assert "Epochs: 10 — 3 head warmup + 7 fine-tune" in out
        assert "cat: 10 images → 8/1/1" in out
        assert "Dry run — nothing was trained or written." in out
        assert fake.torch_imports == 0 and fake.plans == []
        assert not (project_dir / "checkpoints").exists()
        assert not (project_dir / "optica-output").exists()
