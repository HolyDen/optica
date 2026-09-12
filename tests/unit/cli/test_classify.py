"""The ``classify`` command group and the flat aliases.

Covers plan § "CLI Layer & Conventions" → *Commands*, *Namespacing and
aliases*, *Global flags*, and the *CLI Flag Reference (V1)*.

The comma value separator is tested where it is implemented, in
``tests/unit/cli/test_init.py``.
"""

from __future__ import annotations

import pytest

from optica.cli.main import app
from optica.config.defaults import DEFAULT_TASK
from optica.exceptions import ExitCode


@pytest.fixture(autouse=True)
def _isolated(fake_home, project_dir):
    """Keep every invocation out of the developer's home and project."""
    return project_dir


def _commands() -> set[str]:
    from typer.main import get_command

    group = get_command(app)
    return set(getattr(group, "commands", {}))


class TestCommandSurface:
    """The plan's command table, both spellings of every command."""

    @pytest.mark.parametrize(
        "name", ["run", "fetch", "curate", "train", "export", "label"]
    )
    def test_the_flat_alias_exists(self, name):
        assert name in _commands()

    def test_the_canonical_group_exists(self):
        assert DEFAULT_TASK in _commands()

    def test_config_is_registered_beside_the_task_group(self):
        assert "config" in _commands()

    @pytest.mark.parametrize(
        "name", ["run", "fetch", "curate", "train", "export", "label"]
    )
    def test_both_spellings_reach_the_same_command(self, name, capsys):
        flat = app.invoke_guarded([name, "--help"])
        flat_out = capsys.readouterr().out
        grouped = app.invoke_guarded([DEFAULT_TASK, name, "--help"])
        grouped_out = capsys.readouterr().out
        assert flat == grouped == ExitCode.SUCCESS
        # Same help body, modulo the program name in the usage line.
        assert flat_out.count("--help") == grouped_out.count("--help")

    def test_aliases_resolve_through_the_default_task(self):
        # main.py never spells "classify" as a literal; a post-V1 task slots in
        # by being added to the task mapping.
        from optica.cli.main import _TASK_GROUPS

        assert set(_TASK_GROUPS) == {DEFAULT_TASK}

    def test_setup_is_not_registered_yet(self):
        # cli/setup.py is pass 5.
        assert "setup" not in _commands()


class TestFixedValueFlags:
    """Errors always list valid options, and the default where one applies."""

    def test_fetch_rejects_mode_label_and_lists_only_its_own_values(self, capsys):
        # fetch is remote acquisition; label mode takes local input. The valid
        # values are listed per command, so `label` must not appear.
        assert app.invoke_guarded(["fetch", "--mode", "label"]) == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "curate" in err
        assert "clip" in err
        assert "Valid options: curate, clip" in err

    def test_run_accepts_all_three_modes(self, capsys):
        for mode in ("label", "curate", "clip"):
            code = app.invoke_guarded(["run", "--mode", mode])
            # Reaches the unbuilt stage rather than a validation error.
            assert code == ExitCode.ERROR
            assert "not valid for optica run" not in capsys.readouterr().err

    def test_unknown_model_lists_options_and_default(self, capsys):
        assert app.invoke_guarded(["train", "--model", "nope"]) == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "efficientnet-small" in err
        assert "Default: efficientnet-small" in err

    def test_unknown_source_lists_options_and_default(self, capsys):
        assert app.invoke_guarded(["run", "--source", "flikr"]) == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "flickr" in err
        assert "open-datasets" in err


class TestGlobalFlagsEitherPosition:
    """``--verbose``, ``--quiet``, ``--yes``, ``--force`` apply to the full run."""

    @pytest.mark.parametrize(
        "argv",
        [
            ["--quiet", "fetch", "-c", "cat"],
            ["fetch", "--quiet", "-c", "cat"],
        ],
    )
    def test_quiet_is_accepted_before_or_after_the_command(self, argv):
        from optica.utils import logging as olog

        app.invoke_guarded(argv)
        assert olog.get_verbosity() is olog.Verbosity.QUIET

    @pytest.mark.parametrize(
        "argv",
        [
            ["--verbose", "train"],
            ["train", "--verbose"],
        ],
    )
    def test_verbose_is_accepted_before_or_after_the_command(self, argv):
        from optica.utils import logging as olog

        app.invoke_guarded(argv)
        assert olog.get_verbosity() is olog.Verbosity.VERBOSE

    def test_dry_run_is_accepted_on_the_commands_that_take_it(self):
        for name in ("fetch", "train", "export", "run"):
            assert app.invoke_guarded([name, "--dry-run"]) == ExitCode.ERROR

    def test_dry_run_is_not_offered_on_label_or_curate(self):
        # The plan: --dry-run does not apply to label, curate, setup or config.
        for name in ("label", "curate"):
            assert app.invoke_guarded([name, "--dry-run"]) == ExitCode.USAGE


class TestConfigLoadsBeforeTheCommandActs:
    """A bad value in .optica.toml errors rather than misbehaving silently."""

    def test_a_broken_config_stops_fetch(self, project_dir, capsys):
        (project_dir / ".optica.toml").write_text("epochs = 0\n", encoding="utf-8")
        assert app.invoke_guarded(["fetch", "-c", "cat"]) == ExitCode.ERROR
        assert "epochs" in capsys.readouterr().err

    def test_a_flag_value_is_validated_too(self, capsys):
        assert app.invoke_guarded(["train", "--epochs", "0"]) == ExitCode.ERROR
        err = capsys.readouterr().err
        # The error names the flag that set the value, not "config".
        assert "--epochs" in err

    def test_a_non_integer_for_an_integer_flag_is_a_clean_error(self, capsys):
        assert app.invoke_guarded(["train", "--epochs", "ten"]) == ExitCode.USAGE
        assert "Traceback" not in capsys.readouterr().err


class TestLock:
    """Write commands take the global lock; it is released afterwards."""

    def test_the_lock_is_released_when_the_stage_raises(self, fake_home):
        from optica.utils.lockfile import lock_path

        app.invoke_guarded(["fetch", "-c", "cat"])
        assert not lock_path().exists()

    def test_a_live_lock_blocks_a_write_command(self, fake_home, monkeypatch, capsys):
        import json

        from optica.utils import lockfile

        lockfile.lock_path().write_text(
            json.dumps({"pid": 4242, "command": "optica run", "run_id": "r"}),
            encoding="utf-8",
        )
        monkeypatch.setattr(lockfile, "pid_is_live", lambda pid: True)
        assert app.invoke_guarded(["train"]) == ExitCode.ERROR
        assert "already running" in capsys.readouterr().err

    def test_version_is_exempt(self, fake_home, monkeypatch):
        import json

        from optica.utils import lockfile

        lockfile.lock_path().write_text(
            json.dumps({"pid": 4242, "command": "optica run", "run_id": "r"}),
            encoding="utf-8",
        )
        monkeypatch.setattr(lockfile, "pid_is_live", lambda pid: True)
        assert app.invoke_guarded(["--version"]) == ExitCode.SUCCESS


class TestPlanValuesStillToImplement:
    """Flag behaviour whose implementation belongs to a later pass."""

    @pytest.mark.skip(reason="stub - pass 2")
    def test_classes_is_warned_and_ignored_by_curate(self):
        """Curate reads the fetched staging structure, not a class list."""

    @pytest.mark.skip(reason="stub - pass 2")
    def test_folder_with_manifest_is_a_mutually_exclusive_flag_error(self):
        """OpticaValidationError, per the plan's error-family table."""

    @pytest.mark.skip(reason="stub - pass 2")
    def test_mode_defaults_contextually(self):
        """Curate when acquiring by fetch.

        Label when --folder or --manifest is given.
        """

    @pytest.mark.skip(reason="stub - pass 4")
    def test_checkpoint_rank_absence_prompts_rather_than_meaning_rank_1(self):
        """`--yes` answers that prompt with rank 1."""

    @pytest.mark.skip(reason="stub - pass 4")
    def test_run_checks_required_extras_up_front(self):
        """The composite entry point resolves its extras from the invocation.

        It raises before fetching begins.
        """
