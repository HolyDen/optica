"""Checkpoint folders.

Covers plan § "Training" → *Checkpoints* (``checkpoint_val<accuracy>_epoch<n>``
naming, the global ``_x`` suffix checked against the active folder only,
ranking by val accuracy then higher epoch then older timestamp, archive
timestamp ``YYYYMMDD_HHMMSS``, the ``3 x max_checkpoints`` soft limit, the
newest interrupted checkpoint as the resumable one) and *``checkpoint_info.json``*
(written at save, amended with ``interrupted`` and the run-end pair in every
retained checkpoint). Weights round-trip under ``weights_only=True`` is ``slow``.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from optica.training import checkpoints as ckpt


def _make(root: Path, name: str, **info: Any) -> ckpt.Checkpoint:
    folder = root / name
    folder.mkdir(parents=True)
    defaults = {
        "val_accuracy": 0.5,
        "epoch": 1,
        "training_timestamp": "2026-01-01T00:00:00",
    }
    ckpt.write_info(folder, {**defaults, **info})
    return ckpt.Checkpoint(folder, {**defaults, **info})


class TestNaming:
    def test_the_plans_form(self):
        assert ckpt.folder_name(0.852, 7) == "checkpoint_val0.852_epoch7"
        assert ckpt.folder_name(1.0, 12) == "checkpoint_val1.000_epoch12"

    def test_collisions_take_the_global_x_suffix(self, tmp_path):
        (tmp_path / "checkpoint_val0.852_epoch7").mkdir()
        (tmp_path / "checkpoint_val0.852_epoch7_2").mkdir()
        assert ckpt.unique_folder(tmp_path, "checkpoint_val0.852_epoch7").name == (
            "checkpoint_val0.852_epoch7_3"
        )

    def test_archived_checkpoints_are_not_collisions(self, tmp_path):
        (tmp_path / "archive" / "20260101_000000" / "checkpoint_val0.852_epoch7").mkdir(
            parents=True
        )
        assert ckpt.unique_folder(tmp_path, "checkpoint_val0.852_epoch7").name == (
            "checkpoint_val0.852_epoch7"
        )

    def test_archive_timestamp_is_year_inclusive(self):
        assert (
            ckpt.archive_timestamp(datetime(2026, 3, 12, 14, 30, 22)) == "20260312_143022"
        )


class TestListingAndRanking:
    def test_archive_and_non_checkpoints_are_excluded(self, tmp_path):
        _make(tmp_path, "checkpoint_val0.500_epoch1")
        (tmp_path / "archive").mkdir()
        (tmp_path / "stray").mkdir()
        assert [c.path.name for c in ckpt.list_active(tmp_path)] == [
            "checkpoint_val0.500_epoch1"
        ]

    def test_rank_by_accuracy_then_higher_epoch_then_older_timestamp(self, tmp_path):
        a = _make(
            tmp_path,
            "a",
            val_accuracy=0.9,
            epoch=3,
            training_timestamp="2026-01-02T00:00:00",
        )
        b = _make(
            tmp_path,
            "b",
            val_accuracy=0.9,
            epoch=5,
            training_timestamp="2026-01-03T00:00:00",
        )
        c = _make(
            tmp_path,
            "c",
            val_accuracy=0.9,
            epoch=5,
            training_timestamp="2026-01-01T00:00:00",
        )
        d = _make(tmp_path, "d", val_accuracy=0.95, epoch=1)
        e = _make(tmp_path, "e", val_accuracy=0.1, epoch=9)
        assert [x.path.name for x in ckpt.rank([a, b, c, d, e])] == [
            "d",
            "c",
            "b",
            "a",
            "e",
        ]

    def test_the_newest_interrupted_checkpoint_is_resumable(self, tmp_path):
        _make(
            tmp_path,
            "old",
            interrupted=True,
            training_timestamp="2026-01-01T00:00:00",
            epoch=9,
        )
        newer = _make(
            tmp_path,
            "new",
            interrupted=True,
            training_timestamp="2026-02-01T00:00:00",
            epoch=2,
        )
        _make(
            tmp_path, "done", interrupted=False, training_timestamp="2026-03-01T00:00:00"
        )
        found = ckpt.resumable(ckpt.list_active(tmp_path))
        assert found is not None and found.path == newer.path

    def test_nothing_is_resumable_without_the_flag(self, tmp_path):
        _make(tmp_path, "done")
        assert ckpt.resumable(ckpt.list_active(tmp_path)) is None

    def test_the_soft_limit_is_three_times_max_checkpoints(self):
        assert ckpt.soft_limit(3) == 9


class TestAmendments:
    def test_interrupted_is_added_to_each(self, tmp_path):
        folders = [_make(tmp_path, f"c{i}").path for i in range(2)]
        ckpt.mark_interrupted(folders)
        assert all(c.interrupted for c in ckpt.list_active(tmp_path))

    def test_the_run_end_pair_reaches_every_retained_checkpoint(self, tmp_path):
        folders = [
            _make(tmp_path, f"c{i}", epoch=i + 1, interrupted=True).path for i in range(3)
        ]
        ckpt.mark_run_end(folders, epochs_trained=8, early_stopped=True)
        for item in ckpt.list_active(tmp_path):
            assert item.info["epochs_trained"] == 8
            assert item.info["early_stopped"] is True
            assert item.info["interrupted"] is False

    def test_other_fields_survive_an_amendment(self, tmp_path):
        folder = _make(tmp_path, "c", classes=["cat", "dog"]).path
        ckpt.amend(folder, interrupted=True)
        assert ckpt.list_active(tmp_path)[0].info["classes"] == ["cat", "dog"]


class TestHousekeeping:
    def test_archive_moves_folders_with_their_info(self, tmp_path):
        items = [_make(tmp_path, "c1"), _make(tmp_path, "c2")]
        target = ckpt.archive(items, tmp_path, datetime(2026, 9, 15, 10, 0, 0))
        assert target == tmp_path / "archive" / "20260915_100000"
        assert sorted(p.name for p in target.iterdir()) == ["c1", "c2"]
        assert (target / "c1" / ckpt.INFO_FILE).exists()
        assert ckpt.list_active(tmp_path) == []

    def test_delete_removes_the_folders(self, tmp_path):
        items = [_make(tmp_path, "c1")]
        ckpt.delete(items)
        assert not (tmp_path / "c1").exists()


@pytest.mark.slow
class TestWeights:
    def test_round_trip_loads_under_weights_only(self, tmp_path):
        import torch

        model = torch.nn.Linear(3, 2)
        optimizer = torch.optim.AdamW(model.parameters(), lr=0.01)
        model(torch.randn(4, 3)).sum().backward()
        optimizer.step()
        ckpt.save_weights(tmp_path / "c", model, optimizer.state_dict())
        payload = ckpt.load_weights(tmp_path / "c")
        assert set(payload) == {"state_dict", "optimizer_state"}
        assert torch.equal(payload["state_dict"]["weight"], model.state_dict()["weight"])
        # And directly, with the default torch.load a consumer would use.
        torch.load(tmp_path / "c" / ckpt.WEIGHTS_FILE, weights_only=True)
        assert not list((tmp_path / "c").glob(".*.tmp"))

    def test_an_unreadable_weights_file_is_a_training_error(self, tmp_path):
        from optica.exceptions import OpticaTrainingError

        (tmp_path / "c").mkdir()
        (tmp_path / "c" / ckpt.WEIGHTS_FILE).write_bytes(b"not a checkpoint")
        with pytest.raises(OpticaTrainingError, match="could not be read"):
            ckpt.load_weights(tmp_path / "c")
