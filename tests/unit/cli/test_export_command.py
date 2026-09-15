"""``optica export``, through the real command, with the ``.pt`` writer replaced.

Covers plan § "Export" → *Output structure* (subfolder names, ``_ckptX``, ``_x``),
*``--output`` path handling* (every row, with its prompt and its ``--yes``
disposition), Implementation Note 9 (stale partials removed first), and
§ "Training" → *Checkpoints* (the selection prompt; absence is not rank 1; rank
validation all upfront; the stale-path warning), plus the ``--yes`` table rows
"Export checkpoint selection → rank 1" and "``--output`` container creation → Y".

Torch-free: ``import_torch_stack`` and ``pytorch.export`` are replaced. The real
writer is covered by ``tests/unit/export/test_pytorch.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from optica.cli.main import app
from optica.exceptions import ExitCode
from optica.training import checkpoints as ckpt
from tests.unit.export.test_manager import _info


@pytest.fixture
def writer(monkeypatch, fake_home, project_dir):
    calls: dict[str, Any] = {"exports": [], "torch_imports": 0}

    def import_stack():
        calls["torch_imports"] += 1

    def fake_export(folder, checkpoint_folder, info):
        calls["exports"].append((folder, checkpoint_folder, info))
        (folder / "model.pt").write_bytes(b"pt")
        (folder / "usage_examples.md").write_text("x", encoding="utf-8")
        return ["model.pt", "usage_examples.md"]

    monkeypatch.setattr("optica.cli.classify.import_torch_stack", import_stack)
    monkeypatch.setattr("optica.export.pytorch.export", fake_export)
    return calls


@pytest.fixture
def interactive(monkeypatch):
    monkeypatch.setattr("optica.utils.prompts.is_interactive", lambda: True)
    monkeypatch.setattr("optica.cli.main.is_interactive", lambda: True)


def _checkpoint(project_dir: Path, name: str, **overrides: Any) -> Path:
    folder = project_dir / "checkpoints" / name
    folder.mkdir(parents=True)
    ckpt.write_info(folder, _info(**overrides))
    return folder


@pytest.fixture
def three(project_dir):
    # The default container exists, so the output questions stay out of the way
    # of what a test is about; TestOutput constructs each missing-folder case.
    (project_dir / "optica-output").mkdir()
    return [
        _checkpoint(project_dir, "checkpoint_val0.900_epoch9", val_accuracy=0.9, epoch=9),
        _checkpoint(project_dir, "checkpoint_val0.800_epoch8", val_accuracy=0.8, epoch=8),
        _checkpoint(project_dir, "checkpoint_val0.700_epoch7", val_accuracy=0.7, epoch=7),
    ]


def _exports(project_dir: Path) -> list[str]:
    out = project_dir / "optica-output"
    return sorted(p.name for p in out.iterdir()) if out.is_dir() else []


_NAME = r"efficientnet-small_3cls_\d{8}_\d{6}"


class TestSelection:
    def test_yes_exports_rank_1_without_a_suffix(
        self, writer, three, project_dir, capsys
    ):
        assert app.invoke_guarded(["export", "--yes"]) == ExitCode.SUCCESS
        [name] = _exports(project_dir)
        assert __import__("re").fullmatch(_NAME, name)
        [(_, source, info)] = writer["exports"]
        assert source == three[0]
        assert info["exported_rank"] == 1 and info["exported_rank_of"] == 3
        folder = project_dir / "optica-output" / name
        assert (
            json.loads((folder / "model_info.json").read_text())["export_folder"] == name
        )
        assert "Export complete — rank 1 of 3" in capsys.readouterr().out

    def test_absence_prompts_rather_than_meaning_rank_1(
        self, writer, three, interactive, monkeypatch, capsys
    ):
        asked: list[str] = []

        def prompt(text, **kwargs):
            asked.append(text)
            return "2"

        monkeypatch.setattr("typer.prompt", prompt)
        assert app.invoke_guarded(["export"]) == ExitCode.SUCCESS
        assert asked == ["Export which checkpoint? Rank, or several comma-separated"]
        assert "checkpoint_val0.800_epoch8" in capsys.readouterr().err
        assert writer["exports"][0][1] == three[1]

    def test_the_prompt_accepts_several_ranks_and_re_asks_on_a_bad_answer(
        self, writer, three, interactive, monkeypatch, capsys
    ):
        answers = iter(["0,x", "3,1"])
        monkeypatch.setattr("typer.prompt", lambda text, **k: next(answers))
        assert app.invoke_guarded(["export"]) == ExitCode.SUCCESS
        assert [e[1] for e in writer["exports"]] == [three[2], three[0]]
        assert "2 invalid values" in capsys.readouterr().err

    def test_without_a_terminal_or_yes_it_refuses_naming_the_flag(
        self, writer, three, project_dir, capsys
    ):
        assert app.invoke_guarded(["export"]) == ExitCode.ERROR
        assert "--checkpoint-rank 1" in capsys.readouterr().err
        assert _exports(project_dir) == []

    @pytest.mark.parametrize(
        ("flag", "suffixes"),
        [("1", [""]), ("2", ["_ckpt2"]), ("1,2", ["_ckpt1", "_ckpt2"])],
    )
    def test_the_ckpt_suffix_table(self, writer, three, project_dir, flag, suffixes):
        assert (
            app.invoke_guarded(["export", "--checkpoint-rank", flag]) == ExitCode.SUCCESS
        )
        names = _exports(project_dir)
        assert [n[len(n.split("_cls")[0]) :] for n in names]  # non-empty
        stems = sorted(__import__("re").sub(_NAME, "", n) for n in names)
        assert stems == sorted(suffixes)

    def test_checkpoint_is_a_permanent_alias(self, writer, three, project_dir):
        assert app.invoke_guarded(["export", "--checkpoint", "2"]) == ExitCode.SUCCESS
        assert writer["exports"][0][1] == three[1]

    def test_a_same_second_re_export_takes_the_x_suffix(
        self, writer, three, project_dir, monkeypatch
    ):
        import datetime as real

        class Frozen(real.datetime):
            @classmethod
            def now(cls, tz=None) -> Frozen:
                return cls(2026, 9, 15, 12, 0, 0)

        monkeypatch.setattr("optica.cli.classify.datetime", Frozen)
        app.invoke_guarded(["export", "--yes"])
        app.invoke_guarded(["export", "--yes"])
        assert _exports(project_dir) == [
            "efficientnet-small_3cls_20260915_120000",
            "efficientnet-small_3cls_20260915_120000_2",
        ]


class TestRankValidation:
    def test_every_invalid_value_is_reported_before_torch_or_any_prompt(
        self, writer, three, project_dir, capsys
    ):
        code = app.invoke_guarded(["export", "--checkpoint-rank", "0,2,abc,9", "--yes"])
        assert code == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "--checkpoint-rank has 3 invalid values." in err
        assert "Available ranks: 1 to 3" in err
        assert writer["torch_imports"] == 0
        assert _exports(project_dir) == []

    def test_no_checkpoint_is_the_precondition_error(self, writer, project_dir, capsys):
        assert app.invoke_guarded(["export", "--yes"]) == ExitCode.ERROR
        assert "optica train" in capsys.readouterr().err


class TestOutput:
    def test_an_absent_single_component_is_created_under_yes(
        self, writer, three, project_dir
    ):
        assert app.invoke_guarded(["export", "--yes", "-o", "models"]) == ExitCode.SUCCESS
        assert len(list((project_dir / "models").iterdir())) == 1

    def test_the_default_output_gets_the_same_handling(
        self, writer, three, project_dir, capsys
    ):
        (project_dir / "optica-output").rmdir()
        assert app.invoke_guarded(["export", "--checkpoint-rank", "1"]) == ExitCode.ERROR
        assert (
            "--output ./optica-output does not exist. Create it?"
            in capsys.readouterr().err
        )
        assert not (project_dir / "optica-output").exists()

    def test_a_file_is_a_hard_error(self, writer, three, project_dir, capsys):
        (project_dir / "models").write_text("x", encoding="utf-8")
        assert app.invoke_guarded(["export", "--yes", "-o", "models"]) == ExitCode.ERROR
        assert "is a file, not a folder" in capsys.readouterr().err

    def test_multi_component_under_yes_is_a_hard_error_with_the_container_command(
        self, writer, three, project_dir, capsys
    ):
        code = app.invoke_guarded(["export", "--yes", "--output", "runs/pets"])
        assert code == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "optica export --yes --output runs/pets/" in err
        assert not (project_dir / "runs").exists()

    def test_a_trailing_slash_makes_it_a_container_under_yes(
        self, writer, three, project_dir
    ):
        code = app.invoke_guarded(["export", "--yes", "--output", "runs/pets/"])
        assert code == ExitCode.SUCCESS
        assert len(list((project_dir / "runs" / "pets").iterdir())) == 1

    def test_n_uses_the_last_component_as_the_export_name(
        self, writer, three, project_dir, interactive, monkeypatch
    ):
        monkeypatch.setattr(
            "typer.prompt", lambda text, **k: "N" if "does not exist" in text else "1"
        )
        assert app.invoke_guarded(["export", "--output", "runs/pets"]) == ExitCode.SUCCESS
        assert sorted(p.name for p in (project_dir / "runs").iterdir()) == ["pets"]
        info = json.loads((project_dir / "runs" / "pets" / "model_info.json").read_text())
        assert info["export_folder"] == "pets"

    def test_c_creates_the_container(
        self, writer, three, project_dir, interactive, monkeypatch
    ):
        monkeypatch.setattr(
            "typer.prompt", lambda text, **k: "C" if "does not exist" in text else "1"
        )
        assert app.invoke_guarded(["export", "--output", "runs/pets"]) == ExitCode.SUCCESS
        [inner] = list((project_dir / "runs" / "pets").iterdir())
        assert inner.name.startswith("efficientnet-small_3cls_")

    def test_a_aborts_with_exit_3_and_creates_nothing(
        self, writer, three, project_dir, interactive, monkeypatch
    ):
        monkeypatch.setattr("typer.prompt", lambda text, **k: "A")
        assert app.invoke_guarded(["export", "--output", "runs/pets"]) == ExitCode.ABORTED
        assert not (project_dir / "runs").exists()


class TestWarningsAndCleanup:
    def test_a_stale_partial_is_removed_before_writing(self, writer, three, project_dir):
        out = project_dir / "optica-output"
        stale = out / ".efficientnet-small_3cls_20260101_000000.partial"
        stale.mkdir()
        assert app.invoke_guarded(["export", "--yes"]) == ExitCode.SUCCESS
        assert not stale.exists()

    def test_the_stale_checkpoint_path_warning(
        self, writer, project_dir, fake_home, capsys
    ):
        log = fake_home / ".optica" / "logs" / "run.json"
        log.parent.mkdir(parents=True)
        log.write_text(
            json.dumps({"checkpoint_paths": ["checkpoints/checkpoint_val0.852_epoch7/"]}),
            encoding="utf-8",
        )
        _checkpoint(project_dir, "checkpoint_val0.900_epoch9", log_file=str(log))
        assert app.invoke_guarded(["export", "--yes"]) == ExitCode.SUCCESS
        err = capsys.readouterr().err
        assert (
            "Checkpoint path no longer exists: checkpoints/checkpoint_val0.852_epoch7/"
            in err
        )
        assert "It may have been archived or deleted. Check checkpoints/archive/" in err

    def test_an_unfinished_run_warns(self, writer, project_dir, capsys):
        folder = _checkpoint(project_dir, "checkpoint_val0.900_epoch9")
        info = json.loads((folder / ckpt.INFO_FILE).read_text())
        del info["epochs_trained"], info["early_stopped"]
        ckpt.write_info(folder, info)
        assert app.invoke_guarded(["export", "--yes"]) == ExitCode.SUCCESS
        assert "from a run that did not finish" in capsys.readouterr().err


class TestDryRun:
    def test_it_writes_nothing_and_asks_nothing(self, writer, three, project_dir, capsys):
        assert app.invoke_guarded(["export", "--dry-run"]) == ExitCode.SUCCESS
        out = capsys.readouterr().out
        assert "the selection prompt would ask; --yes picks 1" in out
        assert "Dry run — nothing was exported or written." in out
        assert writer["torch_imports"] == 0 and writer["exports"] == []
        assert _exports(project_dir) == []
