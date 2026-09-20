"""The four-step pipeline state model.

Covers plan § "`optica run` resumption and preconditions": the four steps with
their status (complete / incomplete / not started), *R resumes from the last
incomplete step*, **a step whose inputs are absent is listed but not selectable
and says why**, and *selecting a step earlier than the last completed one
discards the later steps' staging*.

The plan's own worked example — fetch complete at 150 images across 3 classes,
curation complete at 120 selected, training interrupted at epoch 3 of 10 — is
constructed here and its resume point asserted, as an exact expected value.

Every state is built on disk. Nothing is inherited from the machine: the home
directory, the project directory and the output container are all fixtures.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from optica import pipeline
from optica.pipeline import SessionState, Step, StepState
from optica.training import checkpoints as ckpt
from tests.unit.export.test_manager import _info


def _stage(home: Path, name: str, count: int, *, partial: bool = False) -> None:
    folder = home / ".optica" / "staging" / (f"{name}.partial" if partial else name)
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(1, count + 1):
        Image.new("RGB", (140, 140), (i * 9 % 256, 40, 80)).save(
            folder / f"{i:04d}.jpg", "JPEG"
        )


def _curation_session(home: Path) -> Path:
    path = home / ".optica" / "staging" / "curation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "created": "2026-03-12T14:30:22+00:00",
                "updated": "2026-03-12T14:35:00+00:00",
                "deselected": {"cat": ["0001.jpg"]},
                "active_class": "cat",
            }
        ),
        encoding="utf-8",
    )
    return path


def _dataset(root: Path, spec: dict[str, int]) -> Path:
    for name, count in spec.items():
        folder = root / name
        folder.mkdir(parents=True, exist_ok=True)
        for i in range(count):
            Image.new("RGB", (160, 160), (i * 7 % 256, 90, 40)).save(
                folder / f"{i}.jpg", "JPEG"
            )
    return root


def _checkpoint(project: Path, name: str, **over: Any) -> Path:
    folder = project / "checkpoints" / name
    folder.mkdir(parents=True, exist_ok=True)
    ckpt.write_info(folder, _info(**over))
    return folder


def _export_folder(output: Path, name: str = "efficientnet-small_3cls_20260312_143022"):
    folder = output / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "model.pt").write_bytes(b"pt")
    return folder


def _inspect(home: Path, project: Path, **kwargs: Any) -> SessionState:
    return pipeline.inspect_session(
        dataset=kwargs.pop("dataset", project / "dataset"),
        project_root=project,
        output=kwargs.pop("output", project / "optica-output"),
        home=home,
        **kwargs,
    )


class TestOrder:
    def test_the_four_steps_in_pipeline_order(self):
        assert pipeline.ORDER == (Step.FETCH, Step.REVIEW, Step.TRAIN, Step.EXPORT)

    def test_after_and_from(self):
        assert pipeline.steps_after(Step.REVIEW) == [Step.TRAIN, Step.EXPORT]
        assert pipeline.steps_from(Step.REVIEW) == [
            Step.REVIEW,
            Step.TRAIN,
            Step.EXPORT,
        ]
        assert pipeline.steps_after(Step.EXPORT) == []


class TestCleanProject:
    def test_nothing_found_and_the_top_is_where_it_starts(self, tmp_path):
        state = _inspect(tmp_path / "home", tmp_path / "project")
        assert state.found is False
        assert [s.state for s in state.steps] == [StepState.NOT_STARTED] * 4
        assert state.lines() == []
        assert state.resume_from is Step.FETCH


class TestFetchStatus:
    def test_staged_images_are_complete_with_their_counts(self, tmp_path):
        home, project = tmp_path / "home", tmp_path / "project"
        _stage(home, "cat", 3)
        _stage(home, "dog", 2)
        status = _inspect(home, project).of(Step.FETCH)
        assert status.state is StepState.COMPLETE
        assert status.detail == "5 images across 2 classes"

    def test_a_partial_class_is_incomplete_and_names_it(self, tmp_path):
        home, project = tmp_path / "home", tmp_path / "project"
        _stage(home, "cat", 3)
        _stage(home, "dog", 1, partial=True)
        status = _inspect(home, project).of(Step.FETCH)
        assert status.state is StepState.INCOMPLETE
        assert status.detail == "the fetch for dog did not finish"

    def test_a_consumed_staging_still_reads_complete(self, tmp_path):
        # Curation deletes the staging it reviewed. The fetch behind it ran.
        home, project = tmp_path / "home", tmp_path / "project"
        _dataset(project / "dataset", {"cat": 5, "dog": 5})
        status = _inspect(home, project).of(Step.FETCH)
        assert status.state is StepState.COMPLETE
        assert status.detail == "consumed by the review step"


class TestReviewStatus:
    def test_an_organized_dataset_is_complete(self, tmp_path):
        home, project = tmp_path / "home", tmp_path / "project"
        _dataset(project / "dataset", {"cat": 7, "dog": 5})
        status = _inspect(home, project).of(Step.REVIEW)
        assert status.state is StepState.COMPLETE
        assert status.detail.startswith("12 images across 2 classes in ")

    def test_a_curation_session_is_incomplete(self, tmp_path):
        home, project = tmp_path / "home", tmp_path / "project"
        _stage(home, "cat", 3)
        _curation_session(home)
        status = _inspect(home, project).of(Step.REVIEW)
        assert status.state is StepState.INCOMPLETE
        assert status.detail == "a curation session is in progress"

    def test_nothing_staged_leaves_it_listed_but_not_selectable(self, tmp_path):
        status = _inspect(tmp_path / "home", tmp_path / "project").of(Step.REVIEW)
        assert status.state is StepState.NOT_STARTED
        assert status.selectable is False
        assert status.blocked == "nothing is staged to review"

    def test_staged_images_make_it_selectable(self, tmp_path):
        home, project = tmp_path / "home", tmp_path / "project"
        _stage(home, "cat", 3)
        assert _inspect(home, project).of(Step.REVIEW).selectable is True

    def test_the_mode_names_it(self, tmp_path):
        home, project = tmp_path / "home", tmp_path / "project"
        _dataset(project / "dataset", {"cat": 5, "dog": 5})
        for mode, name in (
            ("curate", "Curation"),
            ("label", "Labeling"),
            ("clip", "CLIP filtering"),
            (None, "Curation"),
        ):
            state = _inspect(home, project, mode=mode)
            assert state.name_of(Step.REVIEW) == name


class TestTrainStatus:
    def test_an_interrupted_checkpoint_is_incomplete_with_its_epoch(self, tmp_path):
        home, project = tmp_path / "home", tmp_path / "project"
        _dataset(project / "dataset", {"cat": 5, "dog": 5})
        info = _info(epoch=3, config={"epochs": 10}, interrupted=True)
        del info["epochs_trained"]
        del info["early_stopped"]
        folder = project / "checkpoints" / "checkpoint_val0.852_epoch3"
        folder.mkdir(parents=True)
        ckpt.write_info(folder, info)
        status = _inspect(home, project).of(Step.TRAIN)
        assert status.state is StepState.INCOMPLETE
        assert status.detail == "interrupted at epoch 3 of 10"

    def test_a_finished_checkpoint_is_complete_with_its_accuracy(self, tmp_path):
        home, project = tmp_path / "home", tmp_path / "project"
        _dataset(project / "dataset", {"cat": 5, "dog": 5})
        _checkpoint(project, "checkpoint_val0.852_epoch7")
        status = _inspect(home, project).of(Step.TRAIN)
        assert status.state is StepState.COMPLETE
        assert status.detail == "best val_accuracy 0.852"

    def test_no_dataset_leaves_it_listed_but_not_selectable(self, tmp_path):
        status = _inspect(tmp_path / "home", tmp_path / "project").of(Step.TRAIN)
        assert status.selectable is False
        assert status.blocked is not None
        assert "no dataset at" in status.blocked


class TestExportStatus:
    def test_an_export_folder_is_complete(self, tmp_path):
        home, project = tmp_path / "home", tmp_path / "project"
        _checkpoint(project, "checkpoint_val0.852_epoch7")
        _export_folder(project / "optica-output")
        status = _inspect(home, project).of(Step.EXPORT)
        assert status.state is StepState.COMPLETE
        assert status.detail.startswith("1 export folder in ")

    def test_a_partial_export_is_incomplete(self, tmp_path):
        home, project = tmp_path / "home", tmp_path / "project"
        _checkpoint(project, "checkpoint_val0.852_epoch7")
        partial = (
            project / "optica-output" / ".efficientnet-small_3cls_20260312_143022.partial"
        )
        partial.mkdir(parents=True)
        status = _inspect(home, project).of(Step.EXPORT)
        assert status.state is StepState.INCOMPLETE
        assert status.detail == "an export did not finish writing"

    def test_no_checkpoint_leaves_it_listed_but_not_selectable(self, tmp_path):
        status = _inspect(tmp_path / "home", tmp_path / "project").of(Step.EXPORT)
        assert status.selectable is False
        assert status.blocked == "no trained checkpoint to export"

    def test_a_folder_the_user_put_there_is_not_an_export(self, tmp_path):
        home, project = tmp_path / "home", tmp_path / "project"
        _checkpoint(project, "checkpoint_val0.852_epoch7")
        (project / "optica-output" / "my-notes").mkdir(parents=True)
        assert _inspect(home, project).of(Step.EXPORT).state is StepState.NOT_STARTED


class TestThePlansWorkedExample:
    """The block at § "`optica run` resumption and preconditions"."""

    @pytest.fixture
    def example(self, tmp_path):
        home, project = tmp_path / "home", tmp_path / "project"
        # ✓ Fetch complete — 150 images across 3 classes (consumed by curation)
        # ✓ Curation complete — 120 images selected
        _dataset(project / "dataset", {"bird": 40, "cat": 40, "dog": 40})
        # ✗ Training incomplete — interrupted at epoch 3/10
        info = _info(epoch=3, config={"epochs": 10}, interrupted=True)
        del info["epochs_trained"]
        del info["early_stopped"]
        folder = project / "checkpoints" / "checkpoint_val0.400_epoch3"
        folder.mkdir(parents=True)
        ckpt.write_info(folder, info)
        return _inspect(home, project, mode="curate")

    def test_r_resumes_from_the_last_incomplete_step(self, example):
        assert example.found is True
        assert example.resume_from is Step.TRAIN

    def test_the_block_lists_every_started_step_and_no_other(self, example):
        assert example.lines() == [
            "Fetch complete — consumed by the review step",
            f"Curation complete — 120 images across 3 classes in "
            f"{example.of(Step.REVIEW).detail.split(' in ')[1]}",
            "Training incomplete — interrupted at epoch 3 of 10",
        ]

    def test_export_has_not_started_and_is_selectable(self, example):
        status = example.of(Step.EXPORT)
        assert status.state is StepState.NOT_STARTED
        assert status.selectable is True  # a checkpoint exists to export


class TestResumeFrom:
    def test_it_is_the_first_step_that_is_not_complete(self, tmp_path):
        home, project = tmp_path / "home", tmp_path / "project"
        _stage(home, "cat", 3)
        _stage(home, "dog", 3)
        state = _inspect(home, project)
        assert state.of(Step.FETCH).state is StepState.COMPLETE
        assert state.resume_from is Step.REVIEW

    def test_an_incomplete_fetch_comes_before_everything(self, tmp_path):
        home, project = tmp_path / "home", tmp_path / "project"
        _stage(home, "dog", 1, partial=True)
        _dataset(project / "dataset", {"cat": 5, "dog": 5})
        _checkpoint(project, "checkpoint_val0.852_epoch7")
        assert _inspect(home, project).resume_from is Step.FETCH

    def test_a_finished_pipeline_resumes_at_export(self, tmp_path):
        home, project = tmp_path / "home", tmp_path / "project"
        _dataset(project / "dataset", {"cat": 5, "dog": 5})
        _checkpoint(project, "checkpoint_val0.852_epoch7")
        _export_folder(project / "optica-output")
        assert _inspect(home, project).resume_from is Step.EXPORT


class TestDiscardAfter:
    def _everything(self, tmp_path) -> tuple[Path, Path]:
        home, project = tmp_path / "home", tmp_path / "project"
        _stage(home, "cat", 3)
        _dataset(project / "dataset", {"cat": 5, "dog": 5})
        _checkpoint(project, "checkpoint_val0.852_epoch7")
        _export_folder(project / "optica-output")
        return home, project

    def test_choosing_train_discards_only_the_exports(self, tmp_path):
        home, project = self._everything(tmp_path)
        removed = pipeline.discard_after(
            Step.TRAIN,
            dataset=project / "dataset",
            project_root=project,
            output=project / "optica-output",
            home=home,
        )
        assert removed == [f"1 export folders in {project / 'optica-output'}"]
        assert (project / "dataset").is_dir()
        assert (project / "checkpoints").is_dir()

    def test_choosing_review_discards_the_checkpoints_and_the_exports(self, tmp_path):
        home, project = self._everything(tmp_path)
        removed = pipeline.discard_after(
            Step.REVIEW,
            dataset=project / "dataset",
            project_root=project,
            output=project / "optica-output",
            home=home,
        )
        assert len(removed) == 2
        assert (project / "dataset").is_dir()  # the review step's own output stays
        assert not list((project / "checkpoints").glob("checkpoint_*"))
        assert not list((project / "optica-output").iterdir())

    def test_choosing_export_discards_nothing(self, tmp_path):
        home, project = self._everything(tmp_path)
        assert (
            pipeline.discard_after(
                Step.EXPORT,
                dataset=project / "dataset",
                project_root=project,
                output=project / "optica-output",
                home=home,
            )
            == []
        )
        assert (project / "dataset").is_dir()
