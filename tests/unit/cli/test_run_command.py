"""``optica run`` — the composite command, and its resumption prompt.

Covers plan § "`optica run` resumption and preconditions" as it reaches the
terminal: the ``Previous session found:`` block, the top-level R/C/S prompt, the
**C** step selector (including *listed but not selectable, and says why*), the
confirmation before a re-run discards what followed, and **S**; the ``--yes``
table row *`optica run` top-level R/C/S resume → R — resume*; § "Global flags"
for ``--dry-run``; and § "Export" for the one-rank rule ``RunResult`` implies.

The sequencing itself belongs to `optica.run()` and is covered in
``tests/unit/api/test_simple.py``. Here that call is replaced by a recorder, so
what is under test is the part the API cannot have: the prompt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from optica.api import simple
from optica.cli.main import app
from optica.exceptions import ExitCode
from optica.training import checkpoints as ckpt
from tests.unit.export.test_manager import _info


@pytest.fixture
def calls(monkeypatch, fake_home, project_dir):
    """Replace the pipeline with a recorder. The prompt is what is under test."""
    # The default container exists, so `--output`'s own question stays out of
    # the way of the prompt each test is about; TestOutput constructs its cases.
    (project_dir / "optica-output").mkdir(exist_ok=True)
    recorded: list[dict[str, Any]] = []

    def fake_run(classes=None, **kwargs: Any) -> simple.RunResult:
        recorded.append({"classes": classes, **kwargs})
        return simple.RunResult()

    monkeypatch.setattr("optica.cli.classify.api.run", fake_run)
    return recorded


@pytest.fixture
def interactive(monkeypatch):
    monkeypatch.setattr("optica.utils.prompts.is_interactive", lambda: True)
    monkeypatch.setattr("optica.cli.main.is_interactive", lambda: True)


def _dataset(root: Path, spec: dict[str, int]) -> Path:
    for name, count in spec.items():
        folder = root / name
        folder.mkdir(parents=True, exist_ok=True)
        for i in range(count):
            Image.new("RGB", (160, 160), (i * 7 % 256, 90, 40)).save(
                folder / f"{i}.jpg", "JPEG"
            )
    return root


def _stage(home: Path, name: str, count: int, *, partial: bool = False) -> None:
    folder = home / ".optica" / "staging" / (f"{name}.partial" if partial else name)
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(1, count + 1):
        Image.new("RGB", (140, 140), (i * 9 % 256, 40, 80)).save(
            folder / f"{i:04d}.jpg", "JPEG"
        )


def _checkpoint(project: Path, name: str, **over: Any) -> Path:
    folder = project / "checkpoints" / name
    folder.mkdir(parents=True, exist_ok=True)
    ckpt.write_info(folder, _info(**over))
    return folder


def _interrupted(project: Path) -> Path:
    info = _info(epoch=3, config={"epochs": 10}, interrupted=True)
    del info["epochs_trained"]
    del info["early_stopped"]
    folder = project / "checkpoints" / "checkpoint_val0.400_epoch3"
    folder.mkdir(parents=True, exist_ok=True)
    ckpt.write_info(folder, info)
    return folder


def _answers(monkeypatch, *replies: str) -> list[str]:
    """Drive both prompt shapes from one scripted queue, in order.

    ``choose`` reads through ``typer.prompt`` and ``confirm`` through
    ``typer.confirm``; sharing the queue keeps a test's answers in the order the
    command asks for them.
    """
    queue = list(replies)
    asked: list[str] = []

    def prompt(text: str, **kwargs: Any) -> str:
        asked.append(text)
        return queue.pop(0)

    def confirm(text: str, **kwargs: Any) -> bool:
        asked.append(text)
        return queue.pop(0).strip().lower().startswith("y")

    monkeypatch.setattr("typer.prompt", prompt)
    monkeypatch.setattr("typer.confirm", confirm)
    return asked


class TestNoPreviousSession:
    def test_a_clean_project_asks_nothing_and_starts_at_the_top(
        self, calls, project_dir
    ):
        code = app.invoke_guarded(["run", "-c", "cat,dog", "--yes"])
        assert code == ExitCode.SUCCESS
        [call] = calls
        assert call["start_at"] is None  # nothing to resume: the API starts at fetch
        assert call["classes"] == ["cat", "dog"]


class TestResumePrompt:
    def test_yes_picks_r_and_names_the_step_it_resumes_from(
        self, calls, fake_home, project_dir, capsys
    ):
        _dataset(project_dir / "dataset", {"cat": 5, "dog": 5})
        _interrupted(project_dir)
        code = app.invoke_guarded(["run", "-c", "cat,dog", "--yes"])
        err = capsys.readouterr().err
        assert code == ExitCode.SUCCESS
        assert "Previous session found:" in err
        assert "Curation complete" in err
        assert "Training incomplete — interrupted at epoch 3 of 10" in err
        [call] = calls
        assert call["start_at"] == "train"

    def test_the_block_marks_complete_and_incomplete_differently(
        self, calls, fake_home, project_dir, capsys
    ):
        _dataset(project_dir / "dataset", {"cat": 5, "dog": 5})
        _interrupted(project_dir)
        app.invoke_guarded(["run", "-c", "cat,dog", "--yes"])
        lines = [
            line.strip()
            for line in capsys.readouterr().err.splitlines()
            if "complete" in line
        ]
        complete = [line for line in lines if "incomplete" not in line]
        incomplete = [line for line in lines if "incomplete" in line]
        assert complete and incomplete
        assert complete[0][0] != incomplete[0][0]  # ✓ against ✗

    def test_without_a_terminal_and_without_yes_it_is_a_hard_error(
        self, calls, fake_home, project_dir, capsys
    ):
        _dataset(project_dir / "dataset", {"cat": 5, "dog": 5})
        code = app.invoke_guarded(["run", "-c", "cat,dog"])
        assert code == ExitCode.ERROR
        assert "--yes" in capsys.readouterr().err
        assert calls == []

    def test_r_in_a_terminal_resumes(
        self, calls, fake_home, project_dir, interactive, monkeypatch
    ):
        _dataset(project_dir / "dataset", {"cat": 5, "dog": 5})
        _answers(monkeypatch, "R")
        assert app.invoke_guarded(["run", "-c", "cat,dog"]) == ExitCode.SUCCESS
        assert calls[0]["start_at"] == "train"


class TestStartFresh:
    def test_s_clears_staging_and_starts_at_the_top(
        self, calls, fake_home, project_dir, interactive, monkeypatch
    ):
        _stage(fake_home, "cat", 3)
        _answers(monkeypatch, "S")
        assert app.invoke_guarded(["run", "-c", "cat,dog"]) == ExitCode.SUCCESS
        assert calls[0]["start_at"] == "fetch"
        staging = fake_home / ".optica" / "staging"
        assert not list(staging.iterdir())


class TestStepSelector:
    def test_a_step_whose_inputs_are_absent_is_listed_but_not_offered(
        self, calls, fake_home, project_dir, interactive, monkeypatch, capsys
    ):
        # Staging holds images, so review is selectable; there is no dataset and
        # no checkpoint, so train and export are not.
        _stage(fake_home, "cat", 3)
        asked = _answers(monkeypatch, "C", "C")
        assert app.invoke_guarded(["run", "-c", "cat,dog"]) == ExitCode.SUCCESS
        err = capsys.readouterr().err
        assert "not available: no dataset at" in err
        assert "not available: no trained checkpoint to export" in err
        menu = asked[-1]
        assert "[F]" in menu and "[C]" in menu
        assert "[T]" not in menu and "[E]" not in menu
        assert calls[0]["start_at"] == "review"

    def test_choosing_an_earlier_step_confirms_before_discarding(
        self, calls, fake_home, project_dir, interactive, monkeypatch, capsys
    ):
        _dataset(project_dir / "dataset", {"cat": 5, "dog": 5})
        _checkpoint(project_dir, "checkpoint_val0.852_epoch7")
        _answers(monkeypatch, "C", "T", "y")
        assert app.invoke_guarded(["run", "-c", "cat,dog"]) == ExitCode.SUCCESS
        assert calls[0]["start_at"] == "train"
        assert (project_dir / "dataset").is_dir()  # only what followed goes

    def test_declining_the_confirmation_returns_to_the_selector(
        self, calls, fake_home, project_dir, interactive, monkeypatch
    ):
        _dataset(project_dir / "dataset", {"cat": 5, "dog": 5})
        _checkpoint(project_dir, "checkpoint_val0.852_epoch7")
        export = project_dir / "optica-output" / "m_3cls_20260312_143022"
        export.mkdir(parents=True)
        asked = _answers(monkeypatch, "C", "T", "n", "E")
        assert app.invoke_guarded(["run", "-c", "cat,dog"]) == ExitCode.SUCCESS
        # Asked twice: the selector came back rather than ending the run.
        assert sum("Which step" in text for text in asked) == 2
        assert calls[0]["start_at"] == "export"
        assert export.is_dir()  # nothing was removed

    def test_confirming_removes_what_followed(
        self, calls, fake_home, project_dir, interactive, monkeypatch
    ):
        _dataset(project_dir / "dataset", {"cat": 5, "dog": 5})
        _checkpoint(project_dir, "checkpoint_val0.852_epoch7")
        export = project_dir / "optica-output" / "m_3cls_20260312_143022"
        export.mkdir(parents=True)
        _answers(monkeypatch, "C", "T", "y")
        assert app.invoke_guarded(["run", "-c", "cat,dog"]) == ExitCode.SUCCESS
        assert not export.exists()
        assert (project_dir / "checkpoints" / "checkpoint_val0.852_epoch7").is_dir()


class TestCheckpointRank:
    def test_several_ranks_point_at_optica_export(self, calls, project_dir, capsys):
        code = app.invoke_guarded(
            ["run", "-c", "cat,dog", "--yes", "--checkpoint-rank", "1,2"]
        )
        assert code == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "optica run exports one checkpoint" in err
        assert "optica export --checkpoint-rank 1,2" in err
        assert calls == []

    def test_one_rank_reaches_the_pipeline(self, calls, project_dir):
        app.invoke_guarded(["run", "-c", "cat,dog", "--yes", "--checkpoint-rank", "2"])
        assert calls[0]["checkpoint_rank"] == 2


class TestOutput:
    def test_a_file_is_a_hard_error(self, calls, project_dir, capsys):
        (project_dir / "out.txt").write_text("x", encoding="utf-8")
        code = app.invoke_guarded(
            ["run", "-c", "cat,dog", "--yes", "--output", "out.txt"]
        )
        assert code == ExitCode.ERROR
        assert "is a file, not a folder" in capsys.readouterr().err
        assert calls == []

    def test_an_absent_container_is_created_under_yes(self, calls, project_dir):
        app.invoke_guarded(["run", "-c", "cat,dog", "--yes", "--output", "elsewhere"])
        assert (project_dir / "elsewhere").is_dir()

    def test_it_is_always_a_container_never_an_export_name(
        self, calls, project_dir
    ):
        # `run` writes the project-local log there as well as the export
        # folders, so the export table's name-versus-container question cannot
        # arise: a multi-component path is created as a container.
        app.invoke_guarded(
            ["run", "-c", "cat,dog", "--yes", "--output", "deep/inside/here"]
        )
        assert (project_dir / "deep" / "inside" / "here").is_dir()


class TestDryRun:
    def test_it_reports_the_plan_and_runs_nothing(self, project_dir, capsys):
        code = app.invoke_guarded(["run", "-c", "cat,dog", "--yes", "--dry-run"])
        out = capsys.readouterr().out
        assert code == ExitCode.SUCCESS
        assert "Mode: curate (default)" in out
        assert "Classes: cat, dog" in out
        assert "Starts at: fetch" in out
        assert "Dry run" in out
        assert not (project_dir / "dataset").exists()

    def test_it_reports_where_a_resumed_run_would_start(
        self, fake_home, project_dir, capsys
    ):
        _dataset(project_dir / "dataset", {"cat": 5, "dog": 5})
        _interrupted(project_dir)
        app.invoke_guarded(["run", "-c", "cat,dog", "--yes", "--dry-run"])
        assert "Starts at: train" in capsys.readouterr().out

    def test_it_needs_no_ml_stack(self, project_dir, monkeypatch, capsys):
        # A dry run does no work, so the entry extras check has nothing to
        # protect and must not demand the stack.
        def absent() -> None:
            from optica.exceptions import OpticaTorchError

            raise OpticaTorchError("This operation requires the Optica ML stack.")

        monkeypatch.setattr("optica.api.simple.import_torch_stack", absent)
        code = app.invoke_guarded(["run", "-c", "cat,dog", "--yes", "--dry-run"])
        assert code == ExitCode.SUCCESS, capsys.readouterr().err


class TestClasses:
    def test_they_are_required_where_acquisition_runs(self, calls, project_dir, capsys):
        code = app.invoke_guarded(["run", "--yes"])
        assert code == ExitCode.ERROR
        assert "--classes is required" in capsys.readouterr().err

    def test_a_resumed_run_takes_them_from_the_dataset(
        self, calls, fake_home, project_dir
    ):
        _dataset(project_dir / "dataset", {"cat": 5, "dog": 5})
        _interrupted(project_dir)
        assert app.invoke_guarded(["run", "--yes"]) == ExitCode.SUCCESS
        assert calls[0]["classes"] == []
        assert calls[0]["start_at"] == "train"
