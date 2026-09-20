"""The Export Manager.

Covers plan § "Export" → *Output structure* (``<family>_<N>cls_<YYYYMMDD>_<HHMMSS>``,
the ``_ckptX`` table, ``_x`` auto-increment), *``--output`` path handling* (every
row of the table as a situation), *``model_info.json``* (fields, copied
preprocessing, relative ``checkpoint_path``), Implementation Note 9 (the
``.partial`` write, stale partials removed), and § "Training" → *Checkpoints*
(global ranking, rank validation all upfront, the stale-path warning).

Torch-free: ``pytorch.export`` is replaced where a write is exercised.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from optica.exceptions import OpticaExportError, OpticaValidationError
from optica.export import manager
from optica.export import pytorch as writer
from optica.training import checkpoints as ckpt

MOMENT = datetime(2026, 3, 12, 16, 45, 10)


def _info(**overrides: Any) -> dict[str, Any]:
    info = {
        "run_id": "20260312_143022",
        "model_family": "efficientnet-small",
        "base_model": "efficientnet_b0",
        "classes": ["bird", "cat", "dog"],
        "num_classes": 3,
        "val_accuracy": 0.852,
        "val_loss": 0.342,
        "test_accuracy": 0.834,
        "test_loss": 0.391,
        "epoch": 7,
        "training_timestamp": "2026-03-12T14:30:22",
        "class_weights_applied": False,
        "dataset_path": "/home/user/projects/pets/dataset",
        "config": {"epochs": 10},
        "input_size": [224, 224],
        "mean": [0.485, 0.456, 0.406],
        "std": [0.229, 0.224, 0.225],
        "interpolation": "bicubic",
        "crop_pct": 0.875,
        "crop_mode": "center",
        "log_file": "~/.optica/logs/run.json",
        "epochs_trained": 8,
        "early_stopped": True,
    }
    info.update(overrides)
    return info


def _checkpoint(root: Path, name: str, **overrides: Any) -> ckpt.Checkpoint:
    folder = root / "checkpoints" / name
    folder.mkdir(parents=True)
    info = _info(**overrides)
    ckpt.write_info(folder, info)
    return ckpt.Checkpoint(folder, info)


class TestRanking:
    def test_no_checkpoint_is_the_export_precondition_error(self, tmp_path):
        with pytest.raises(OpticaExportError, match="No trained checkpoint"):
            manager.ranked_checkpoints(tmp_path)

    def test_global_ranking_over_the_active_folder(self, tmp_path):
        _checkpoint(tmp_path, "a", val_accuracy=0.8, epoch=2)
        _checkpoint(tmp_path, "b", val_accuracy=0.9, epoch=1)
        (tmp_path / "checkpoints" / "archive" / "x" / "c").mkdir(parents=True)
        ranked = manager.ranked_checkpoints(tmp_path)
        assert [(r.rank, r.checkpoint.path.name) for r in ranked] == [(1, "b"), (2, "a")]


class TestParseRanks:
    def test_valid_ranks_in_order_with_repeats_collapsed(self):
        assert manager.parse_ranks(["2", " 1 ", "2"], 3) == [2, 1]

    @pytest.mark.parametrize(
        ("value", "reason"),
        [
            ("0", "a rank must be 1 or more"),
            ("-1", "a rank must be 1 or more"),
            ("one", "a whole number is required"),
            ("1.5", "a whole number is required"),
            ("9", "there is no checkpoint at that rank"),
        ],
    )
    def test_each_invalid_value_names_its_reason(self, value, reason):
        with pytest.raises(OpticaValidationError) as info:
            manager.parse_ranks([value], 3)
        assert any(reason in line for line in info.value.fix)

    def test_every_invalid_value_is_reported_at_once(self):
        with pytest.raises(OpticaValidationError) as info:
            manager.parse_ranks(["0", "2", "x", "7"], 3)
        assert info.value.message == "--checkpoint-rank has 3 invalid values."
        text = "\n".join(info.value.fix)
        assert "0:" in text and "'x':" in text and "7:" in text
        assert "Available ranks: 1 to 3" in text

    def test_available_ranks_are_listed_only_for_a_nonexistent_rank(self):
        with pytest.raises(OpticaValidationError) as info:
            manager.parse_ranks(["0"], 3)
        assert not any("Available" in line for line in info.value.fix)


class TestClassifyOutput:
    def test_an_existing_folder_is_a_container(self, tmp_path):
        assert manager.classify_output(str(tmp_path)) is manager.OutputSituation.CONTAINER

    def test_a_file_is_an_error(self, tmp_path):
        (tmp_path / "f").write_text("x", encoding="utf-8")
        assert (
            manager.classify_output(str(tmp_path / "f"))
            is manager.OutputSituation.IS_FILE
        )

    @pytest.mark.parametrize("raw", ["out", "./out", "out/"])
    def test_a_missing_single_component_asks_to_create(self, raw, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert manager.classify_output(raw) is manager.OutputSituation.CREATE

    def test_a_missing_multi_component_path_is_ambiguous(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert (
            manager.classify_output("runs/pets")
            is manager.OutputSituation.NAME_OR_CONTAINER
        )

    @pytest.mark.parametrize("slash", ["/", "\\"])
    def test_a_trailing_slash_makes_it_a_container(self, slash, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert (
            manager.classify_output(f"runs/pets{slash}") is manager.OutputSituation.CREATE
        )

    @pytest.mark.parametrize(
        ("raw", "count"),
        [("out", 1), ("./out", 1), ("/out", 1), ("runs/pets", 2), ("/a/b/c", 3)],
    )
    def test_components_do_not_count_the_anchor(self, raw, count):
        # Pure: no filesystem is consulted, so nothing about this machine's
        # root directory is assumed.
        assert manager.component_count(raw) == count

    def test_an_unwritable_container_is_refused(self, tmp_path):
        # Constructed: a "container" that is a file cannot hold the probe.
        blocker = tmp_path / "blocker"
        blocker.write_text("x", encoding="utf-8")
        with pytest.raises(OpticaValidationError, match="not writable"):
            manager.require_writable(blocker)

    def test_a_writable_container_passes_and_keeps_nothing(self, tmp_path):
        manager.require_writable(tmp_path)
        assert list(tmp_path.iterdir()) == []


class TestNaming:
    def test_the_plans_folder_name(self):
        name = manager.folder_name("efficientnet-small", 3, MOMENT, 1, with_rank=False)
        assert name == "efficientnet-small_3cls_20260312_164510"

    def test_the_ckpt_suffix(self):
        assert manager.folder_name("resnet", 2, MOMENT, 2, with_rank=True).endswith(
            "_ckpt2"
        )

    def test_collisions_take_the_x_suffix(self, tmp_path):
        (tmp_path / "m").mkdir()
        (tmp_path / "m_2").mkdir()
        assert manager.unique_name(tmp_path, "m") == "m_3"
        assert manager.unique_name(tmp_path, "free") == "free"

    def test_a_stale_partial_is_not_a_collision(self, tmp_path):
        (tmp_path / ".m.partial").mkdir()
        assert manager.unique_name(tmp_path, "m") == "m"


class TestStalePartials:
    def test_only_export_shaped_partials_are_removed(self, tmp_path):
        export_partial = (
            tmp_path / ".efficientnet-small_3cls_20260312_164510_ckpt2.partial"
        )
        dataset_partial = tmp_path / ".dataset.partial"
        export_partial.mkdir()
        dataset_partial.mkdir()
        removed = manager.clean_stale_partials(tmp_path)
        assert removed == [export_partial]
        assert dataset_partial.exists()


class TestStaleCheckpointPaths:
    def test_paths_in_the_log_that_no_longer_exist(self, tmp_path):
        log = tmp_path / "run.json"
        log.write_text(
            json.dumps({"checkpoint_paths": ["checkpoints/here/", "checkpoints/gone/"]}),
            encoding="utf-8",
        )
        (tmp_path / "checkpoints" / "here").mkdir(parents=True)
        item = ckpt.Checkpoint(tmp_path / "checkpoints" / "here", {"log_file": str(log)})
        assert manager.stale_checkpoint_paths(item, tmp_path) == ["checkpoints/gone/"]

    def test_no_log_means_nothing_to_warn_about(self, tmp_path):
        item = ckpt.Checkpoint(tmp_path, {"log_file": str(tmp_path / "absent.json")})
        assert manager.stale_checkpoint_paths(item, tmp_path) == []


class TestModelInfo:
    def test_the_plans_fields(self, tmp_path):
        item = _checkpoint(tmp_path, "checkpoint_val0.852_epoch7")
        info = manager.model_info(
            item, rank=1, of=6, export_folder="f", moment=MOMENT, project_root=tmp_path
        )
        assert set(info) == {
            "run_id", "model_family", "base_model", "classes", "num_classes",
            "input_size", "mean", "std", "interpolation", "crop_pct", "crop_mode",
            "val_accuracy", "val_loss", "test_accuracy", "test_loss",
            "epochs_trained", "class_weights_applied", "early_stopped",
            "exported_rank", "exported_rank_of", "export_format", "export_folder",
            "training_timestamp", "export_timestamp", "dataset_path", "config",
            "checkpoint_path", "log_file",
        }  # fmt: skip
        assert info["export_format"] == "pt"
        assert info["exported_rank_of"] == 6
        assert info["export_timestamp"] == "2026-03-12T16:45:10"
        assert info["checkpoint_path"] == "checkpoints/checkpoint_val0.852_epoch7/"
        assert info["classes"] == ["bird", "cat", "dog"]

    def test_preprocessing_is_copied_from_the_checkpoint_not_resolved(self, tmp_path):
        item = _checkpoint(tmp_path, "c", crop_pct=0.95, input_size=[320, 320])
        info = manager.model_info(
            item, rank=1, of=1, export_folder="f", moment=MOMENT, project_root=tmp_path
        )
        assert (info["crop_pct"], info["input_size"]) == (0.95, [320, 320])

    def test_an_unfinished_run_exports_with_null_run_end_fields(self, tmp_path):
        info = _info()
        del info["epochs_trained"], info["early_stopped"]
        folder = tmp_path / "checkpoints" / "c"
        folder.mkdir(parents=True)
        item = ckpt.Checkpoint(folder, info)
        assert manager.missing_run_end(item)
        exported = manager.model_info(
            item, rank=1, of=1, export_folder="f", moment=MOMENT, project_root=tmp_path
        )
        assert exported["epochs_trained"] is None and exported["early_stopped"] is None

    def test_a_checkpoint_without_preprocessing_cannot_be_exported(self, tmp_path):
        info = _info()
        del info["crop_pct"]
        item = ckpt.Checkpoint(tmp_path, info)
        with pytest.raises(OpticaExportError, match="crop_pct"):
            manager.model_info(
                item,
                rank=1,
                of=1,
                export_folder="f",
                moment=MOMENT,
                project_root=tmp_path,
            )


class TestAtomicWrite:
    def _ranked(self, tmp_path: Path) -> manager.Ranked:
        return manager.Ranked(1, _checkpoint(tmp_path, "c"))

    def test_the_folder_appears_complete(self, tmp_path, monkeypatch):
        seen: dict[str, Any] = {}

        def fake_export(folder, checkpoint_folder, info):
            seen["folder"] = folder
            (folder / "model.pt").write_bytes(b"pt")
            (folder / "usage_examples.md").write_text("x", encoding="utf-8")
            return ["model.pt", "usage_examples.md"]

        # Patched through the module object: since pass 5, `optica.export` on
        # the package is the Tier 3 function, so a dotted string cannot
        # walk to the module (notes/build-log.md).
        monkeypatch.setattr(writer, "export", fake_export)
        out = tmp_path / "out"
        out.mkdir()
        record = manager.export_checkpoint(
            self._ranked(tmp_path), of=1, container=out, name="m", moment=MOMENT,
            project_root=tmp_path,
        )  # fmt: skip
        assert seen["folder"] == out / ".m.partial"  # written beside, not in place
        assert record.folder == out / "m"
        assert sorted(p.name for p in record.folder.iterdir()) == record.files == [
            "class_names.json", "model.pt", "model_info.json", "usage_examples.md",
        ]  # fmt: skip
        assert json.loads((record.folder / "class_names.json").read_text()) == [
            "bird", "cat", "dog",
        ]  # fmt: skip
        assert not (out / ".m.partial").exists()

    def test_a_failure_leaves_nothing_visible(self, tmp_path, monkeypatch):
        def failing(folder, checkpoint_folder, info):
            (folder / "model.pt").write_bytes(b"half")
            raise OpticaExportError("boom")

        monkeypatch.setattr(writer, "export", failing)
        out = tmp_path / "out"
        out.mkdir()
        with pytest.raises(OpticaExportError):
            manager.export_checkpoint(
                self._ranked(tmp_path), of=1, container=out, name="m", moment=MOMENT,
                project_root=tmp_path,
            )  # fmt: skip
        assert list(out.iterdir()) == []
