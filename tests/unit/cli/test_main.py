"""The global exception handler.

Covers plan § "CLI Layer & Conventions" → *Error handling and prompt
conventions*, Implementation Note 1, and the exit-code table in § "Exceptions".

The handler is the hard sequencing prerequisite: every other flag decision's
error behaviour executes through it, so the assertions here are about which
exception produces which exit code, and about no raw traceback ever surfacing.
"""

from __future__ import annotations

import pytest
import typer
from typer._click.exceptions import UsageError

from optica.cli.main import OpticaTyper, app
from optica.exceptions import ExitCode, OpticaConfigError, OpticaError
from optica.utils import logging as olog


@pytest.fixture
def probe_app() -> OpticaTyper:
    """An app with one command per outcome the handler has to classify."""
    probe = OpticaTyper(name="probe", add_completion=False)

    @probe.command()
    def ok() -> None:
        typer.echo("fine")

    @probe.command()
    def boom() -> None:
        raise OpticaConfigError(
            "train_split + val_split + test_split must equal 1.0",
            why="Got: 0.80 (config) + 0.10 (config) + 0.15 (default) = 1.05",
            fix="Set all three values to sum to 1.0.",
        )

    @probe.command()
    def declined() -> None:
        raise typer.Exit(code=ExitCode.ABORTED)

    @probe.command()
    def interrupted() -> None:
        raise KeyboardInterrupt

    @probe.command()
    def aborted() -> None:
        raise typer.Abort

    @probe.command()
    def surprise() -> None:
        raise RuntimeError("an internal invariant broke")

    @probe.command()
    def flags(
        classes: list[str] = typer.Option(None, "--classes", "-c"),
        epochs: int = typer.Option(10, "--epochs", "-e"),
    ) -> None:
        typer.echo(f"{classes}|{epochs}")

    return probe


class TestExitCodes:
    """Each code in the plan's table is reachable through the handler."""

    def test_success_is_zero(self, probe_app):
        assert probe_app.invoke_guarded(["ok"]) == ExitCode.SUCCESS

    def test_optica_error_is_one(self, probe_app):
        assert probe_app.invoke_guarded(["boom"]) == ExitCode.ERROR

    def test_usage_error_is_two(self, probe_app):
        assert probe_app.invoke_guarded(["ok", "--nope"]) == ExitCode.USAGE

    def test_declined_prompt_is_three(self, probe_app):
        assert probe_app.invoke_guarded(["declined"]) == ExitCode.ABORTED

    def test_sigint_is_130(self, probe_app):
        assert probe_app.invoke_guarded(["interrupted"]) == ExitCode.INTERRUPTED

    def test_click_abort_is_130_not_three(self, probe_app):
        # `Abort` is reserved for an interrupt at a prompt. A declined prompt is
        # Optica's own business and exits 3 -- which is why
        # `confirm(..., abort=True)` is banned everywhere.
        assert probe_app.invoke_guarded(["aborted"]) == ExitCode.INTERRUPTED

    def test_unexpected_exception_is_one_and_not_a_traceback(self, probe_app, capsys):
        assert probe_app.invoke_guarded(["surprise"]) == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "Traceback (most recent call last)" not in err
        assert "bug in Optica" in err


class TestUsageErrorsCaughtAtTheBase:
    """The catch is ``UsageError`` at the base, not a named list of subclasses."""

    @pytest.mark.parametrize(
        "argv",
        [
            ["ok", "--nope"],  # NoSuchOption
            ["flags", "--epochs", "ten"],  # BadParameter
            ["flags", "-c", "cat", "dog"],  # UsageError - extra argument
            ["nosuchcommand"],  # UsageError - no such command
        ],
    )
    def test_every_parser_error_shape_exits_two(self, probe_app, argv):
        assert probe_app.invoke_guarded(argv) == ExitCode.USAGE

    def test_two_is_clicks_own_code_read_off_the_exception(self):
        # The plan matches Click's 2 rather than contending for it.
        assert UsageError.exit_code == ExitCode.USAGE

    def test_the_vendored_class_is_the_one_typer_raises(self, probe_app):
        # typer 0.27.2 vendors Click as the private `typer._click`; a separately
        # installed `click` would supply a second, unrelated UsageError and this
        # catch would silently stop firing. This test is the pin: if a Typer
        # upgrade moves the class, it fails here rather than leaking tracebacks.
        command = typer.main.get_command(probe_app)
        with pytest.raises(UsageError):
            command.main(args=["ok", "--nope"], standalone_mode=False)

    def test_no_raw_traceback_reaches_the_user(self, probe_app, capsys):
        probe_app.invoke_guarded(["flags", "-c", "cat", "dog"])
        err = capsys.readouterr().err
        assert "Traceback (most recent call last)" not in err
        assert "Got unexpected extra argument" in err


class TestCommaValueSeparator:
    """Plan § *Value separator — comma, everywhere*.

    Verified against Click in ``notes/verified.md``: the parser itself never
    splits on commas, and a space-separated list is a usage error.
    """

    def test_repeated_flag_is_valid(self, probe_app, capsys):
        assert probe_app.invoke_guarded(["flags", "-c", "cat", "-c", "dog"]) == 0
        assert "['cat', 'dog']" in capsys.readouterr().out

    def test_space_separated_values_are_a_usage_error(self, probe_app):
        assert probe_app.invoke_guarded(["flags", "-c", "cat", "dog"]) == ExitCode.USAGE


class TestVersion:
    """``optica --version`` must work with no torch present."""

    def test_version_exits_zero(self, capsys):
        assert app.invoke_guarded(["--version"]) == ExitCode.SUCCESS
        assert "optica" in capsys.readouterr().out

    def test_no_torch_is_imported(self):
        import sys

        app.invoke_guarded(["--version"])
        assert "torch" not in sys.modules


class TestErrorRendering:
    """Plan § "Coding Style": what went wrong / why / how to fix."""

    def test_three_part_structure_reaches_stderr(self, probe_app, capsys):
        probe_app.invoke_guarded(["boom"])
        err = capsys.readouterr().err
        assert "must equal 1.0" in err
        assert "0.80 (config)" in err
        assert "Set all three values to sum to 1.0." in err

    def test_options_and_default_are_listed(self, capsys):
        olog.render_error(
            OpticaError(
                "Unknown source",
                options=["flickr", "open-datasets"],
                default="open-datasets",
            )
        )
        err = capsys.readouterr().err
        assert "flickr" in err
        assert "Default: open-datasets" in err


class TestNoValueFlagRedirect:
    """Plan § *Flag (no value) behavior*.

    ``--classes`` with no value redirects to the class-name prompt; every other
    flag with no value produces a wrapped error. Under ``--yes``, or with no
    terminal, the prompt cannot fire and the error is produced instead --
    ``--yes`` errors rather than hanging.
    """

    def test_classes_with_no_value_prompts_and_re_runs(
        self, probe_app, monkeypatch, capsys
    ):
        monkeypatch.setattr("optica.cli.main.is_interactive", lambda: True)
        monkeypatch.setattr("typer.prompt", lambda *a, **k: "cat,dog")
        assert probe_app.invoke_guarded(["flags", "--classes"]) == ExitCode.SUCCESS
        assert "['cat,dog']" in capsys.readouterr().out

    def test_classes_with_no_value_errors_under_yes(self, probe_app, monkeypatch):
        # Wherever the class-name prompt would fire, `--yes` errors rather than
        # hanging on it. `--classes` is trailing here because Click consumes the
        # *next* token as an option's value whatever it looks like -- see
        # notes/build-log.md for the pass 2 item that follows from it.
        monkeypatch.setattr("optica.cli.main.is_interactive", lambda: True)
        monkeypatch.setattr("typer.prompt", lambda *a, **k: pytest.fail("prompted"))
        assert (
            probe_app.invoke_guarded(["flags", "--yes", "--classes"]) == ExitCode.USAGE
        )

    def test_classes_with_no_value_errors_without_a_terminal(
        self, probe_app, monkeypatch
    ):
        monkeypatch.setattr("optica.cli.main.is_interactive", lambda: False)
        assert probe_app.invoke_guarded(["flags", "--classes"]) == ExitCode.USAGE

    def test_another_flag_with_no_value_is_a_wrapped_error(
        self, probe_app, monkeypatch, capsys
    ):
        monkeypatch.setattr("optica.cli.main.is_interactive", lambda: True)
        assert probe_app.invoke_guarded(["flags", "--epochs"]) == ExitCode.USAGE
        assert "requires an argument" in capsys.readouterr().err

    def test_the_prompt_never_loops(self, probe_app, monkeypatch):
        # An empty answer must not re-enter the prompt.
        monkeypatch.setattr("optica.cli.main.is_interactive", lambda: True)
        monkeypatch.setattr("typer.prompt", lambda *a, **k: "")
        assert probe_app.invoke_guarded(["flags", "--classes"]) == ExitCode.USAGE


class TestPlanValuesStillToImplement:
    """Values the plan states that pass 1 cannot yet exercise end to end.

    Free test cases while the code is being written, expensive archaeology
    later.
    """

    @pytest.mark.parametrize("argv", [["fetch", "--classes"], ["fetch"]])
    def test_missing_classes_prompt_validates_names(
        self, argv, fake_home, project_dir, monkeypatch, capsys
    ):
        """The prompt's answer goes through the filesystem-safe class-name rules.

        Both shapes reach the same prompt: a trailing ``--classes``
        (``BadOptionUsage``, redirected by the handler) and ``--classes`` absent
        entirely (resolved in the command body).
        """
        monkeypatch.setattr("optica.cli.main.is_interactive", lambda: True)
        monkeypatch.setattr("optica.utils.prompts.is_interactive", lambda: True)
        monkeypatch.setattr("typer.prompt", lambda *a, **k: "--yes,dog")
        assert app.invoke_guarded(argv) == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "No class names given" in err
        assert "'--yes' begins with '-'" in err

    def test_classes_bound_to_a_flag_spelling_is_refused_as_a_name(
        self, fake_home, project_dir, capsys
    ):
        # `optica fetch --classes --yes` parses cleanly with classes == ["--yes"];
        # amended class-name rule 1 is what stops a folder called --yes.
        assert app.invoke_guarded(["fetch", "--classes", "--yes"]) == ExitCode.ERROR
        assert "begins with '-'" in capsys.readouterr().err
        assert not (fake_home / ".optica" / "staging").exists()

    def test_correctable_abort_prints_the_corrected_command(
        self, fake_home, project_dir, capsys
    ):
        """Plan: output the full corrected command, other flags preserved.

        Only where reconstruction is unambiguous; where the fix needs judgment,
        explain the problem instead of guessing a command.
        """
        argv = ["run", "--mode", "curate", "--folder", "./images", "-c", "cat,dog"]
        assert app.invoke_guarded(argv) == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "requires fetched input" in err
        assert "optica run --folder ./images -c cat,dog" in err

    @pytest.mark.skip(reason="stub - pass 5")
    def test_all_invalid_flag_values_are_reported_at_once(self):
        """Plan: never fail on the first invalid value only."""
