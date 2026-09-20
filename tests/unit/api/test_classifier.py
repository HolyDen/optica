"""`Classifier` — the Tier 5 expert surface.

Covers plan § "Python API" → *Classifier (Tier 5)*: the nine properties, the
chainable methods, `status` as a high-water mark, the parameter-placement rule
(constructor vs method vs config field), and **`Classifier(checkpoint_path=…)`
raising `OpticaValidationError` both when the path does not exist and when it
exists but is not a checkpoint folder** — a bare ``.pt`` file included.

Construction never imports torch, which is constructed here rather than assumed:
the ML stack's entry point is replaced by one that fails the test if it is
reached.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from optica.api.classifier import Classifier, EpochRecord, Status
from optica.exceptions import OpticaValidationError
from optica.training import checkpoints as ckpt
from tests.unit.export.test_manager import _info


@pytest.fixture(autouse=True)
def no_torch(monkeypatch):
    """Nothing in this file may reach the ML stack."""

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("constructing a Classifier must never import torch")

    monkeypatch.setattr("optica.api.simple.import_torch_stack", forbidden)
    monkeypatch.setattr("optica.utils.mlstack.import_torch_stack", forbidden)
    return forbidden


def _checkpoint(
    root: Path, name: str = "checkpoint_val0.852_epoch7", **over: Any
) -> Path:
    folder = root / "checkpoints" / name
    folder.mkdir(parents=True)
    ckpt.write_info(folder, _info(**over))
    return folder


class TestCheckpointPathValidation:
    def test_a_path_that_does_not_exist_raises(self, tmp_path):
        with pytest.raises(OpticaValidationError) as info:
            Classifier(checkpoint_path=tmp_path / "nowhere")
        assert "No checkpoint found at" in info.value.message

    def test_a_bare_pt_file_raises_rather_than_deferring_to_export(self, tmp_path):
        # It exists, so the *missing* branch must not claim it; it carries no
        # checkpoint_info.json, so export could not read run_id, val_accuracy,
        # epoch, dataset_path or the config block from it.
        weights = tmp_path / "model.pt"
        weights.write_bytes(b"not a checkpoint folder")
        with pytest.raises(OpticaValidationError) as info:
            Classifier(checkpoint_path=weights)
        assert "is not a checkpoint folder" in info.value.message
        assert "a file" in (info.value.why or "")
        assert "checkpoint_info.json" in " ".join(info.value.fix)

    def test_a_folder_without_checkpoint_info_raises(self, tmp_path):
        folder = tmp_path / "checkpoints" / "checkpoint_val0.852_epoch7"
        folder.mkdir(parents=True)
        (folder / "checkpoint.pt").write_bytes(b"weights only")
        with pytest.raises(OpticaValidationError) as info:
            Classifier(checkpoint_path=folder)
        assert "is not a checkpoint folder" in info.value.message
        assert "a folder without one" in (info.value.why or "")

    def test_a_folder_whose_info_will_not_parse_raises(self, tmp_path):
        folder = tmp_path / "checkpoints" / "checkpoint_val0.852_epoch7"
        folder.mkdir(parents=True)
        (folder / ckpt.INFO_FILE).write_text("{ not json", encoding="utf-8")
        with pytest.raises(OpticaValidationError, match="is not a checkpoint folder"):
            Classifier(checkpoint_path=folder)

    def test_both_failures_are_the_same_class(self, tmp_path):
        missing = tmp_path / "nowhere"
        wrong = tmp_path / "model.pt"
        wrong.write_bytes(b"x")
        raised = []
        for path in (missing, wrong):
            with pytest.raises(OpticaValidationError) as info:
                Classifier(checkpoint_path=path)
            raised.append(type(info.value))
        assert raised == [OpticaValidationError, OpticaValidationError]

    def test_a_real_checkpoint_is_adopted_without_torch(self, tmp_path):
        folder = _checkpoint(tmp_path)
        clf = Classifier(checkpoint_path=folder)
        assert clf.status is Status.TRAINED
        assert clf.checkpoint_path == folder
        assert clf.classes == ["bird", "cat", "dog"]
        assert clf.best_val_accuracy == 0.852
        assert clf.model == "efficientnet-small"

    def test_an_explicit_model_is_not_overwritten_by_the_checkpoints(self, tmp_path):
        folder = _checkpoint(tmp_path)
        assert Classifier("resnet", checkpoint_path=folder).model == "resnet"

    def test_the_epoch_history_comes_from_the_checkpoint(self, tmp_path):
        folder = _checkpoint(
            tmp_path,
            epoch_history=[
                {
                    "epoch": 1,
                    "phase": 1,
                    "train_loss": 0.9,
                    "train_accuracy": 0.5,
                    "val_loss": 0.8,
                    "val_accuracy": 0.6,
                }
            ],
        )
        [record] = Classifier(checkpoint_path=folder).training_history
        assert record == EpochRecord(1, 1, 0.9, 0.5, 0.8, 0.6)


class TestStatus:
    def test_a_fresh_classifier_is_empty(self):
        clf = Classifier()
        assert clf.status is Status.EMPTY
        assert clf.classes == []
        assert clf.checkpoint_path is None
        assert clf.export_paths == []
        assert clf.training_history == []
        assert clf.warnings == []
        assert clf.dataset_path is None

    def test_it_is_a_high_water_mark_and_never_moves_backwards(self, tmp_path):
        clf = Classifier(checkpoint_path=_checkpoint(tmp_path))
        assert clf.status is Status.TRAINED
        clf._advance(Status.DATA_READY)
        assert clf.status is Status.TRAINED
        clf._advance(Status.EXPORTED)
        assert clf.status.value == "exported"

    def test_export_before_training_names_the_missing_state(self):
        with pytest.raises(OpticaValidationError) as info:
            Classifier().export()
        assert "needs trained" in info.value.message
        assert "is empty" in info.value.message
        assert "checkpoint_path" in " ".join(info.value.fix)


class TestChaining:
    def test_every_method_returns_self(self, tmp_path, monkeypatch):
        from optica.api import simple

        clf = Classifier(checkpoint_path=_checkpoint(tmp_path))
        monkeypatch.setattr(
            simple,
            "export",
            lambda **kwargs: simple.ExportResult(
                export_folder=tmp_path / "out" / "model", files=["model.pt"]
            ),
        )
        assert clf.export() is clf
        assert clf.export() is clf
        # One entry per export folder written, so two calls leave two.
        assert clf.export_paths == [tmp_path / "out" / "model"] * 2

    def test_warnings_accumulate_across_calls_in_invocation_order(
        self, tmp_path, monkeypatch
    ):
        from optica.api import simple

        clf = Classifier(checkpoint_path=_checkpoint(tmp_path))
        entries = iter(
            [
                simple.WarningEntry("stale_checkpoint_path", "first"),
                simple.WarningEntry("checkpoint_run_incomplete", "second"),
            ]
        )
        monkeypatch.setattr(
            simple,
            "export",
            lambda **kwargs: simple.ExportResult(warnings=[next(entries)]),
        )
        clf.export().export()
        assert [entry.message for entry in clf.warnings] == ["first", "second"]


class TestParameterPlacement:
    def test_model_and_output_are_constructor_arguments(self):
        import inspect

        parameters = inspect.signature(Classifier.__init__).parameters
        assert "model" in parameters
        assert "output" in parameters

    def test_inputs_and_per_call_safety_are_method_arguments(self):
        import inspect

        fetch = inspect.signature(Classifier.fetch).parameters
        assert {"classes", "mode", "overwrite"} <= set(fetch)
        label = inspect.signature(Classifier.label).parameters
        assert {"folder", "manifest", "overwrite"} <= set(label)

    def test_no_method_takes_a_force_or_yes_argument(self):
        import inspect

        for name in ("fetch", "label", "curate", "train", "export", "run"):
            parameters = inspect.signature(getattr(Classifier, name)).parameters
            assert "force" not in parameters
            assert "yes" not in parameters
            assert "verbose" not in parameters  # a constructor setting
