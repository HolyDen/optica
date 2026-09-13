"""``optica config``.

Covers plan § "Configuration" — the ``--init`` create and overwrite prompts,
``--set``, ``--view``, ``--global`` — and Implementation Note 11, which is why
``--yes`` answers one prompt on this command and not the other.

Exit code ``3`` is reachable here and nowhere else in pass 1: it is a declined
prompt, and ``config --init``'s create confirmation is the only V1 prompt whose
backing is entirely pass 1's.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from optica.cli.main import app
from optica.exceptions import ExitCode


@pytest.fixture(autouse=True)
def _isolated(fake_home, project_dir):
    return project_dir


@pytest.fixture
def interactive(monkeypatch):
    monkeypatch.setattr("optica.utils.prompts.is_interactive", lambda: True)


class TestInit:
    def test_yes_creates_the_file(self, project_dir):
        assert app.invoke_guarded(["config", "--init", "--yes"]) == ExitCode.SUCCESS
        assert (project_dir / ".optica.toml").exists()

    def test_an_accepted_prompt_creates_the_file(
        self, project_dir, interactive, monkeypatch
    ):
        monkeypatch.setattr("typer.confirm", lambda *a, **k: True)
        assert app.invoke_guarded(["config", "--init"]) == ExitCode.SUCCESS
        assert (project_dir / ".optica.toml").exists()

    def test_a_declined_prompt_exits_three(self, project_dir, interactive, monkeypatch):
        monkeypatch.setattr("typer.confirm", lambda *a, **k: False)
        assert app.invoke_guarded(["config", "--init"]) == ExitCode.ABORTED
        # And writes nothing: a declined prompt is not a partial run.
        assert not (project_dir / ".optica.toml").exists()

    def test_a_declined_prompt_is_not_130(self, project_dir, interactive, monkeypatch):
        # `confirm(..., abort=True)` would have produced 130 here, which is why
        # Optica never uses it.
        monkeypatch.setattr("typer.confirm", lambda *a, **k: False)
        assert app.invoke_guarded(["config", "--init"]) != ExitCode.INTERRUPTED

    def test_an_interrupt_at_the_prompt_exits_130(
        self, project_dir, interactive, monkeypatch
    ):
        import typer

        def interrupt(*args: object, **kwargs: object) -> bool:
            raise typer.Abort

        monkeypatch.setattr("typer.confirm", interrupt)
        assert app.invoke_guarded(["config", "--init"]) == ExitCode.INTERRUPTED

    def test_no_terminal_and_no_yes_is_a_hard_error(self, project_dir, monkeypatch):
        monkeypatch.setattr("optica.utils.prompts.is_interactive", lambda: False)
        assert app.invoke_guarded(["config", "--init"]) == ExitCode.ERROR
        assert not (project_dir / ".optica.toml").exists()

    def test_nothing_is_written_before_the_prompt_is_answered(
        self, project_dir, interactive, monkeypatch
    ):
        seen: list[bool] = []

        def check(*args: object, **kwargs: object) -> bool:
            seen.append((project_dir / ".optica.toml").exists())
            return False

        monkeypatch.setattr("typer.confirm", check)
        app.invoke_guarded(["config", "--init"])
        assert seen == [False]


class TestInitOverwrite:
    """The overwrite prompt is destructive: ``--yes`` never answers it."""

    def test_yes_does_not_answer_the_overwrite_prompt(
        self, project_dir, interactive, monkeypatch
    ):
        (project_dir / ".optica.toml").write_text("epochs = 12\n", encoding="utf-8")
        asked: list[str] = []

        def record(question: str, **kwargs: object) -> bool:
            asked.append(question)
            return False

        monkeypatch.setattr("typer.confirm", record)
        assert app.invoke_guarded(["config", "--init", "--yes"]) == ExitCode.ABORTED
        assert asked == ["Overwrite?"]

    def test_an_accepted_overwrite_replaces_the_file(
        self, project_dir, interactive, monkeypatch
    ):
        (project_dir / ".optica.toml").write_text("epochs = 12\n", encoding="utf-8")
        monkeypatch.setattr("typer.confirm", lambda *a, **k: True)
        assert app.invoke_guarded(["config", "--init"]) == ExitCode.SUCCESS
        assert "# epochs = 10" in (project_dir / ".optica.toml").read_text(
            encoding="utf-8"
        )

    def test_the_existing_file_message_points_at_set(
        self, project_dir, interactive, monkeypatch, capsys
    ):
        (project_dir / ".optica.toml").write_text("epochs = 12\n", encoding="utf-8")
        monkeypatch.setattr("typer.confirm", lambda *a, **k: False)
        app.invoke_guarded(["config", "--init"])
        out = capsys.readouterr().out
        assert "already exists" in out
        assert "optica config --set" in out


class TestSet:
    def test_writes_and_reports_the_path(self, capsys):
        assert app.invoke_guarded(["config", "--set", "epochs", "20"]) == ExitCode.SUCCESS
        out = capsys.readouterr().out
        assert "epochs" in out
        assert "config.toml" in out

    def test_an_unknown_key_is_rejected_with_a_suggestion(self, capsys):
        assert app.invoke_guarded(["config", "--set", "epocs", "20"]) == ExitCode.ERROR
        assert "epochs" in capsys.readouterr().err

    def test_an_invalid_value_is_rejected(self, capsys):
        code = app.invoke_guarded(["config", "--set", "curation_port", "80"])
        assert code == ExitCode.ERROR

    def test_a_key_with_no_value_is_a_clean_error(self, capsys):
        assert app.invoke_guarded(["config", "--set", "epochs"]) == ExitCode.ERROR
        assert "needs a value" in capsys.readouterr().err

    def test_global_forces_the_global_file(self, project_dir, fake_home):
        app.invoke_guarded(["config", "--init", "--yes"])
        app.invoke_guarded(["config", "--set", "epochs", "20", "--global"])
        assert "epochs = 20" in (
            fake_home / ".optica" / "config.toml"
        ).read_text(encoding="utf-8")

    def test_an_api_key_is_never_echoed(self, capsys):
        app.invoke_guarded(["config", "--set", "flickr_api_key", "super-secret"])
        assert "super-secret" not in capsys.readouterr().out


class TestView:
    def test_shows_every_key_with_a_source(self, capsys):
        assert app.invoke_guarded(["config", "--view"]) == ExitCode.SUCCESS
        out = capsys.readouterr().out
        assert "epochs" in out
        assert "default" in out

    def test_masks_an_api_key_but_keeps_its_source(self, monkeypatch, capsys):
        monkeypatch.setenv("FLICKR_API_KEY", "super-secret")
        app.invoke_guarded(["config", "--view"])
        out = capsys.readouterr().out
        assert "super-secret" not in out
        assert "flickr_api_key" in out

    def test_an_unset_api_key_shows_not_set(self, capsys):
        app.invoke_guarded(["config", "--view"])
        assert "(not set)" in capsys.readouterr().out

    def test_a_broken_config_is_reported_rather_than_rendered(
        self, project_dir, capsys
    ):
        (project_dir / ".optica.toml").write_text("epocs = 20\n", encoding="utf-8")
        assert app.invoke_guarded(["config", "--view"]) == ExitCode.ERROR
        assert "epochs" in capsys.readouterr().err


class TestFlagCombinations:
    def test_no_action_flag_explains_what_to_run(self, capsys):
        assert app.invoke_guarded(["config"]) == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "--view" in err
        assert "--set" in err
        assert "--init" in err

    def test_two_action_flags_are_rejected(self, capsys):
        code = app.invoke_guarded(["config", "--init", "--view"])
        assert code == ExitCode.ERROR
        assert "cannot be combined" in capsys.readouterr().err


class TestPlanValuesStillToImplement:
    @staticmethod
    def _stage(home: Path) -> Path:
        staging = home / ".optica" / "staging"
        (staging / "cat").mkdir(parents=True)
        (staging / "cat" / "0001.jpg").write_bytes(b"x")
        (staging / "dog.partial").mkdir()
        (staging / "curation.json").write_text('{"version": 1}', encoding="utf-8")
        return staging

    def test_clear_staging_lists_and_clears_all_staging(
        self, fake_home, interactive, monkeypatch, capsys
    ):
        """Delegates to the Input Manager, which pass 2 builds."""
        staging = self._stage(fake_home)
        monkeypatch.setattr("typer.confirm", lambda *a, **k: True)
        assert app.invoke_guarded(["config", "--clear-staging"]) == ExitCode.SUCCESS
        out = capsys.readouterr().out
        assert "cat — 1 images" in out
        assert "incomplete fetch" in out
        assert "Curation session" in out
        assert staging.is_dir()
        assert list(staging.iterdir()) == []

    def test_clear_staging_confirmation_is_destructive(
        self, fake_home, interactive, monkeypatch
    ):
        """`--yes` must not answer it.

        On the same command where it answers the create prompt.
        """
        staging = self._stage(fake_home)
        asked: list[str] = []

        def decline(question, **kwargs):
            asked.append(question)
            return False

        monkeypatch.setattr("typer.confirm", decline)
        code = app.invoke_guarded(["config", "--clear-staging", "--yes"])
        # Asked despite --yes, declined, and nothing deleted: exit 3.
        assert asked == ["Delete all staging contents?"]
        assert code == ExitCode.ABORTED
        assert (staging / "cat" / "0001.jpg").exists()

    def test_clear_staging_unattended_refuses_rather_than_deleting(
        self, fake_home, monkeypatch
    ):
        monkeypatch.setattr("optica.utils.prompts.is_interactive", lambda: False)
        staging = self._stage(fake_home)
        code = app.invoke_guarded(["config", "--clear-staging", "--yes", "--force"])
        assert code == ExitCode.ERROR
        assert (staging / "cat" / "0001.jpg").exists()

    def test_clear_staging_with_nothing_staged(self, fake_home, capsys):
        assert app.invoke_guarded(["config", "--clear-staging"]) == ExitCode.SUCCESS
        assert "already empty" in capsys.readouterr().out
