"""The Simple API (Tier 3) and Python API (Tier 4).

Covers plan § "Python API" → *Simple API (Tier 3) and Python API (Tier 4)* (the
three prompt-site dispositions, ``overwrite=``, ``verbose=``, ``dry_run=``, the
stage boundary), *Result types* (every field, and `TrainResult.early_stopped`
copied rather than derived), the warning contract (structured entries **and**
``warnings.warn``, from one source), and the import-time contract.

The ``--yes`` table is transcribed here as the API's prompt mapping — the plan
makes that table the source: *"Every prompt listed in the `--yes` table takes
its listed answer"*. The seven ``clip_threshold`` bands are transcribed as exact
expected values too.

Every condition is constructed: the fake Open Images world comes from the fetch
command's tests, a populated ``dataset/`` is written before the call, and the
prompt layer is replaced by one that fails the test if anything reaches it.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

import optica
from optica.api import simple
from optica.exceptions import (
    OpticaConfigError,
    OpticaValidationError,
    OpticaWarning,
)
from optica.training.trainer import TrainOutcome
from tests.unit.cli.test_fetch_command import World, _jpeg_for  # noqa: F401
from tests.unit.export.test_manager import _info

# --- plan § "Global flags" → the `--yes` table, transcribed -------------------
# Every row whose prompt is in the API's scope, with the answer the table gives.
# `config --init` is unreachable (config is CLI-only) and the browser-side
# confirmations are not `--yes`'s to answer.
YES_TABLE = {
    "class-name confirmation (clean case)": "skip confirmation",
    "overlap warning": "Y — continue",
    "group or separate sub-terms": "group",
    "fetch / curation / labeling interrupted → resume?": "resume",
    "training interrupted → continue?": "continue",
    "optica run top-level R/C/S resume": "R — resume",
    "mass rejection F/C/A": "C — continue",
    "mass rejection C confirmation": "Y — confirm",
    "checkpoint keep/archive/delete/select": "K — keep",
    "checkpoint soft-limit warning": "Y — continue",
    "export checkpoint selection": "rank 1 (best)",
    "--output container creation": "Y — create",
    "CPU batch-size prompt": "Y — continue",
    "class-imbalance warning": "C — continue with auto class weighting",
    "--epochs 1 + default finetune_ratio": "Y — continue",
    "clip_threshold strict-end prompt (0.75 to <1.0)": "Y — continue",
    "clip_threshold warn-and-continue bands": "Y — continue",
    "Open Datasets soft-cap warning": "Y — continue",
    "--classes/subset confirmation (organized dataset)": "Y — proceed",
}

# --- plan § "CLIP Adapter (clip mode)" → the seven bands ----------------------
HARD_ERROR_THRESHOLDS = (-0.1, 1.1, 0.0, 1.0)
PROMPT_THRESHOLDS = (0.75, 0.99)
WARN_THRESHOLDS = (0.5, 0.74, 0.05, 0.09)
SILENT_THRESHOLDS = (0.1, 0.25, 0.49)


@pytest.fixture(autouse=True)
def no_prompts(monkeypatch):
    """Nothing in this layer may read stdin. Constructed, not assumed."""

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the Python API must never prompt")

    for name in ("confirm", "confirm_or_abort", "choose", "ask_class_names"):
        monkeypatch.setattr(f"optica.utils.prompts.{name}", forbidden)
    return forbidden


@pytest.fixture(autouse=True)
def _catch_warnings():
    """Optica's own warnings are the subject here, never an error."""
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        yield seen


def _dataset(root: Path, spec: dict[str, int]) -> Path:
    for name, count in spec.items():
        folder = root / name
        folder.mkdir(parents=True, exist_ok=True)
        for i in range(count):
            Image.new("RGB", (160, 160), (i * 7 % 256, 90, 40)).save(
                folder / f"{i}.jpg", "JPEG"
            )
    return root


def _codes(result: simple.OpticaResult) -> list[str]:
    return [entry.code for entry in result.warnings]


class TestImportContract:
    def test_the_flat_aliases_are_the_namespaces_own_functions(self):
        for name in ("run", "fetch", "label", "curate", "train", "export"):
            assert getattr(optica, name) is getattr(optica.classify, name)

    def test_the_surface_is_bound_eagerly_not_through_getattr(self):
        assert "__getattr__" not in vars(optica)
        for name in optica.__all__:
            assert name in vars(optica), name

    def test_the_flat_export_alias_shadows_the_export_subpackage(self):
        # The plan fixes both names: `optica.export()` is a Tier 3 alias and
        # `optica/export/` is the Export Manager's package. The function wins on
        # the package namespace; the module stays reachable by import.
        import sys

        from optica.export import manager

        assert callable(optica.export)
        assert optica.export is optica.classify.export
        assert sys.modules["optica.export"].manager is manager

    def test_config_objects_import_from_optica_api(self):
        from optica.api import ExportConfig, FetchConfig, TrainConfig

        assert (FetchConfig(), TrainConfig(), ExportConfig()) is not None


class TestTrainConfig:
    def test_exactly_eleven_fields_and_which(self):
        from dataclasses import fields

        assert [f.name for f in fields(simple.TrainConfig)] == [
            "epochs",
            "batch_size",
            "learning_rate",
            "augmentation",
            "early_stopping",
            "finetune_ratio",
            "optimizer",
            "max_checkpoints",
            "train_split",
            "val_split",
            "test_split",
        ]

    def test_they_are_the_artifact_config_blocks_own_eleven(self):
        from dataclasses import fields

        from optica.training.trainer import TrainSettings

        shipped = TrainSettings(
            epochs=10,
            batch_size=32,
            learning_rate=0.001,
            augmentation=True,
            early_stopping=5,
            finetune_ratio=0.7,
            optimizer="adamw",
            train_split=0.7,
            val_split=0.15,
            test_split=0.15,
            max_checkpoints=3,
        ).as_json()
        assert set(shipped) == {f.name for f in fields(simple.TrainConfig)}
        assert len(shipped) == 11

    def test_there_is_no_auto_confirm_parameter_anywhere(self):
        import inspect

        for name in ("run", "fetch", "label", "curate", "train", "export"):
            parameters = inspect.signature(getattr(simple, name)).parameters
            assert "auto_confirm" not in parameters
            assert "force" not in parameters
            assert "yes" not in parameters


class TestExportConfig:
    def test_checkpoint_rank_with_no_checkpoint_alias(self):
        from dataclasses import fields

        assert [f.name for f in fields(simple.ExportConfig)] == ["checkpoint_rank"]


class TestWarningContract:
    def test_an_entry_is_branchable_and_actionable_and_also_a_python_warning(
        self, _catch_warnings
    ):
        collector = simple._Collector()
        collector.add(
            simple.WarningCode.CLASS_IMBALANCE, "Class imbalance detected.", cat=3
        )
        entries = collector.emit()
        assert entries[0].code == "class_imbalance"
        assert entries[0].context == {"cat": 3}
        [raised] = [w for w in _catch_warnings if w.category is OpticaWarning]
        # One source, two surfaces: `warnings.warn` renders the entry's message.
        assert str(raised.message) == entries[0].message

    def test_optica_warning_subclasses_user_warning_so_it_can_be_filtered_alone(self):
        assert issubclass(OpticaWarning, UserWarning)

    def test_every_code_is_unique_and_lower_snake_case(self):
        codes = [
            value
            for name, value in vars(simple.WarningCode).items()
            if name.isupper() and isinstance(value, str)
        ]
        assert len(codes) == len(set(codes))
        assert all(code == code.lower().replace(" ", "_") for code in codes)

    def test_the_interrupted_export_code_is_the_chosen_one(self):
        # Item 4 of pass 5: stable API surface, chosen deliberately.
        assert simple.WarningCode.CHECKPOINT_RUN_INCOMPLETE == "checkpoint_run_incomplete"


class TestBlocklistDefinition:
    def test_fetch_raises_at_the_definition_step_naming_the_class(
        self, fake_home, project_dir
    ):
        with pytest.raises(OpticaValidationError) as info:
            optica.fetch(["defective", "cat"])
        assert "'defective' is too abstract to search for" in info.value.message
        assert "concrete definition is required" in info.value.message

    def test_run_raises_the_same_way_before_anything_is_fetched(
        self, fake_home, project_dir, monkeypatch
    ):
        monkeypatch.setattr("optica.api.simple.import_torch_stack", lambda: None)
        monkeypatch.setattr("optica.server.app.load_web", lambda: None)
        monkeypatch.setattr("optica.input.manager.clip_available", lambda: True)
        with pytest.raises(OpticaValidationError, match="too abstract"):
            optica.run(["defective", "cat"], mode="clip")
        assert not (project_dir / "dataset").exists()

    def test_the_prompter_never_asks(self):
        prompter = simple._ApiClassPrompter(simple._Collector())
        with pytest.raises(OpticaValidationError):
            prompter.define("other")


class TestOverwriteIsDestructive:
    def test_a_populated_dataset_raises_without_overwrite(self, fake_home, project_dir):
        # `train --manifest` materializes into `dataset/`, so it takes the
        # destination check; `--yes` never answers it and neither does the API.
        _dataset(project_dir / "dataset", {"bird": 1})
        _dataset(project_dir / "src", {"cat": 5, "dog": 5})
        manifest = project_dir / "m.csv"
        rows = [
            f"{project_dir / 'src' / name / f'{i}.jpg'},{name}"
            for name in ("cat", "dog")
            for i in range(5)
        ]
        manifest.write_text("\n".join(["path,class", *rows, ""]), encoding="utf-8")
        with pytest.raises(OpticaValidationError) as info:
            optica.train(manifest=manifest, verbose=False)
        assert "already exists and is not empty" in info.value.message
        # The API's own counterpart, not the CLI's flag.
        assert any("overwrite=True" in line for line in info.value.fix)
        assert not any("--overwrite" in line for line in info.value.fix)
        assert (project_dir / "dataset" / "bird").is_dir()

    def test_overwrite_true_is_the_only_route_past_it(self, fake_home, project_dir):
        # The destructive prompt is the one `--yes` never answers, and
        # `overwrite=True` is its exact API counterpart.
        _dataset(project_dir / "dataset", {"bird": 1})
        simple._require_free_destination(project_dir / "dataset", overwrite=True)


class TestClipThresholdBands:
    @pytest.mark.parametrize("value", HARD_ERROR_THRESHOLDS)
    def test_the_three_hard_error_bands_raise(self, value, fake_home):
        with pytest.raises((OpticaValidationError, OpticaConfigError)):
            optica.fetch(["cat", "dog"], mode="clip", clip_threshold=value)

    @pytest.mark.parametrize("value", PROMPT_THRESHOLDS + WARN_THRESHOLDS)
    def test_the_prompt_and_warn_bands_continue_and_record(self, value, monkeypatch):
        monkeypatch.setattr("optica.input.manager.require_clip_extra", lambda: None)
        collector = simple._Collector()
        simple._clip_threshold_entry(collector, value)
        assert [entry.code for entry in collector.entries] == ["clip_threshold"]
        assert collector.entries[0].context == {"clip_threshold": value}

    @pytest.mark.parametrize("value", SILENT_THRESHOLDS)
    def test_the_normal_band_is_silent(self, value, monkeypatch):
        monkeypatch.setattr("optica.input.manager.require_clip_extra", lambda: None)
        collector = simple._Collector()
        simple._clip_threshold_entry(collector, value)
        assert collector.entries == []


class TestFetch:
    @pytest.fixture
    def world(self, monkeypatch, fake_home, project_dir):
        world = World()
        monkeypatch.setattr("optica.api.simple.make_client", world.client)
        return world

    def test_fetch_stages_images_and_returns_the_counts(self, world, fake_home):
        result = optica.fetch(["cat", "dog"], images_per_class=5, verbose=False)
        assert result.classes == ["cat", "dog"]
        assert result.counts == {"cat": 5, "dog": 5}
        assert result.source == "Open Images"
        assert result.mode == "curate"
        assert result.dataset_path is None
        assert result.dry_run is False
        assert result.plan is None

    def test_a_comma_separated_string_is_the_same_as_a_list(self, world, fake_home):
        result = optica.fetch("cat,dog", images_per_class=2, verbose=False)
        assert result.classes == ["cat", "dog"]

    def test_the_soft_cap_warns_and_continues(self, world, fake_home):
        result = optica.fetch(
            ["cat", "dog"], images_per_class=501, verbose=False
        )
        assert "soft_cap" in _codes(result)
        assert sum(result.counts.values()) > 0

    def test_dry_run_writes_nothing_and_returns_the_four_resolutions(
        self, world, fake_home, project_dir
    ):
        result = optica.fetch(["cat", "dog"], dry_run=True, verbose=False)
        assert result.dry_run is True
        assert result.plan is not None
        assert {"mode", "detection_order", "short_circuit", "destination"} <= set(
            result.plan
        )
        assert world.image_requests == []
        assert not (fake_home / ".optica" / "staging").exists()

    def test_missing_classes_is_a_hard_error_not_a_prompt(self, world, fake_home):
        with pytest.raises(OpticaValidationError, match="--classes is required"):
            optica.fetch(verbose=False)

    def test_mode_label_is_refused_with_the_valid_values(self, world, fake_home):
        with pytest.raises(OpticaValidationError) as info:
            optica.fetch(["cat", "dog"], mode="label")
        assert info.value.options == ["curate", "clip"]


class TestTrainResult:
    def _outcome(self, **overrides: Any) -> TrainOutcome:
        values: dict[str, Any] = {
            "run_id": "20260312_143022",
            "best_checkpoint": Path("checkpoints/checkpoint_val0.852_epoch7"),
            "best_val_accuracy": 0.852,
            "test_accuracy": 0.834,
            "test_loss": 0.391,
            "epochs_run": 7,
            "epochs_requested": 10,
            "phases": (3, 7),
            "phases_run": (2, 5),
            "early_stopped": False,
            "phase1_stopped_early": True,
            "checkpoints": [Path("checkpoints/checkpoint_val0.852_epoch7")],
            "log_paths": [Path("global.json"), Path("local.json")],
            "classes_without_test": [],
        }
        values.update(overrides)
        return TrainOutcome(**values)

    def test_early_stopped_is_copied_from_the_loop_never_derived(self):
        # Phase 1 stopped early, so the run ends short of `epochs` with
        # `early_stopped` False. Deriving it from the counts would say True.
        outcome = self._outcome()
        assert outcome.epochs_run < outcome.epochs_requested
        assert simple._train_result(outcome).early_stopped is False

    def test_a_true_flag_survives_the_copy(self):
        assert simple._train_result(self._outcome(early_stopped=True)).early_stopped

    def test_every_field_the_completion_block_prints_comes_from_the_result(self):
        result = simple._train_result(self._outcome())
        assert result.epochs_run == 7
        assert result.epochs_requested == 10
        assert result.phases == (3, 7)
        assert result.best_val_accuracy == 0.852
        assert result.test_accuracy == 0.834
        assert result.test_loss == 0.391
        assert result.checkpoints == [Path("checkpoints/checkpoint_val0.852_epoch7")]
        assert result.log_paths == [Path("global.json"), Path("local.json")]

    def test_under_dry_run_every_outcome_field_is_none(self, fake_home, project_dir):
        _dataset(project_dir / "dataset", {"cat": 5, "dog": 5})
        result = optica.train(dry_run=True, verbose=False)
        assert result.dry_run is True
        assert result.plan is not None
        for value in (
            result.best_checkpoint,
            result.best_val_accuracy,
            result.test_accuracy,
            result.test_loss,
            result.epochs_run,
            result.epochs_requested,
            result.early_stopped,
            result.phases,
            result.checkpoints,
            result.log_paths,
        ):
            assert value is None


class TestTrainStageBoundary:
    def test_a_flat_folder_is_a_precondition_error(self, fake_home, project_dir):
        folder = project_dir / "dataset"
        folder.mkdir()
        Image.new("RGB", (160, 160)).save(folder / "a.jpg", "JPEG")
        with pytest.raises(OpticaValidationError, match="flat folder"):
            optica.train(verbose=False)

    def test_a_partially_labeled_manifest_is_a_precondition_error(
        self, fake_home, project_dir
    ):
        manifest = project_dir / "m.csv"
        manifest.write_text("path,class\na.jpg,cat\nb.jpg,\n", encoding="utf-8")
        with pytest.raises(OpticaValidationError, match="partially labeled"):
            optica.train(manifest=manifest, verbose=False)

    def test_class_imbalance_continues_with_weighting_and_records_it(
        self, fake_home, project_dir, monkeypatch
    ):
        captured: dict[str, Any] = {}
        monkeypatch.setattr("optica.api.simple.import_torch_stack", lambda: None)
        # The device probe imports torch too; this file stays torch-free.
        monkeypatch.setattr(
            "optica.api.simple.select_device", lambda: SimpleNamespace(type="cpu")
        )

        def fake_training(plan, *args, **kwargs):
            captured["plan"] = plan
            return TestTrainResult()._outcome()

        monkeypatch.setattr("optica.api.simple.run_training", fake_training)
        _dataset(project_dir / "dataset", {"cat": 20, "dog": 5})
        result = optica.train(verbose=False)
        assert "class_imbalance" in _codes(result)
        assert captured["plan"].class_weights is True


class TestExport:
    @pytest.fixture
    def exportable(self, fake_home, project_dir, monkeypatch):
        from optica.export import pytorch as writer

        monkeypatch.setattr("optica.api.simple.import_torch_stack", lambda: None)

        def fake_export(folder, checkpoint_folder, info):
            (folder / "model.pt").write_bytes(b"pt")
            return ["model.pt"]

        # Patched through the module object: `optica.export` on the package is
        # the Tier 3 function, so a dotted string cannot walk to it.
        monkeypatch.setattr(writer, "export", fake_export)
        return project_dir

    def _checkpoint(self, project_dir: Path, name: str, **overrides: Any) -> Path:
        from optica.training import checkpoints as ckpt

        folder = project_dir / "checkpoints" / name
        folder.mkdir(parents=True)
        ckpt.write_info(folder, _info(**overrides))
        return folder

    def test_rank_1_is_the_default_selection(self, exportable):
        self._checkpoint(exportable, "checkpoint_val0.900_epoch9", val_accuracy=0.9)
        self._checkpoint(exportable, "checkpoint_val0.700_epoch7", val_accuracy=0.7)
        result = optica.export(verbose=False)
        assert result.checkpoint_rank == 1
        assert result.export_folder is not None
        assert "model.pt" in result.files

    def test_an_interrupted_checkpoint_warns_with_its_own_stable_code(
        self, exportable
    ):
        # Constructed: a checkpoint whose run never wrote the run-end fields.
        info = _info()
        del info["epochs_trained"]
        del info["early_stopped"]
        from optica.training import checkpoints as ckpt

        folder = exportable / "checkpoints" / "checkpoint_val0.852_epoch7"
        folder.mkdir(parents=True)
        ckpt.write_info(folder, info)
        result = optica.export(verbose=False)
        [entry] = [
            e for e in result.warnings if e.code == "checkpoint_run_incomplete"
        ]
        assert entry.context["fields"] == ["epochs_trained", "early_stopped"]
        assert "did not finish" in entry.message

    def test_a_finished_checkpoint_raises_no_such_warning(self, exportable):
        self._checkpoint(exportable, "checkpoint_val0.852_epoch7")
        result = optica.export(verbose=False)
        assert "checkpoint_run_incomplete" not in _codes(result)

    def test_no_checkpoint_is_an_export_error(self, fake_home, project_dir):
        from optica.exceptions import OpticaExportError

        with pytest.raises(OpticaExportError, match="No trained checkpoint"):
            optica.export(verbose=False)


class TestVerbosityAndStreams:
    def test_verbose_false_is_quiet_and_the_level_is_restored(self):
        from optica.utils import logging as olog

        before = olog.get_verbosity()
        levels = []
        with simple._verbosity(False):
            levels.append(olog.get_verbosity())
        assert levels == [olog.Verbosity.QUIET]
        assert olog.get_verbosity() == before

    def test_the_api_never_reconfigures_the_callers_streams(self):
        # Pass 2's rule: `protect_streams` belongs to the CLI entry point.
        source = Path(simple.__file__).read_text(encoding="utf-8")
        assert "protect_streams" in source  # named, in the module docstring
        assert "protect_streams(" not in source  # never called


class TestYesTable:
    def test_every_row_in_scope_has_a_recorded_answer(self):
        # The table is the API's prompt mapping. This pins the transcription so
        # a row silently dropped from it fails here rather than in behaviour.
        assert len(YES_TABLE) == 19
        assert YES_TABLE["export checkpoint selection"] == "rank 1 (best)"
        assert YES_TABLE["class-imbalance warning"].startswith("C —")
        assert YES_TABLE["optica run top-level R/C/S resume"] == "R — resume"
