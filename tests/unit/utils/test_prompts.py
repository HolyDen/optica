"""Prompts, and the flags that answer or suppress them.

Covers plan § "Global flags" (``--yes``, ``--force``) and the settled point that
a declined prompt exits ``3`` while ``click.Abort`` exits ``130``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import typer

from optica.exceptions import ExitCode, OpticaConfigError, OpticaValidationError
from optica.utils.prompts import PromptCategory, confirm, confirm_or_abort

if TYPE_CHECKING:
    from optica.cli.classify import TerminalClassPrompter


@pytest.fixture
def interactive(monkeypatch):
    monkeypatch.setattr("optica.utils.prompts.is_interactive", lambda: True)


def _record(monkeypatch, *, answer: bool) -> list[str]:
    """Capture the questions actually put to the user, and answer them."""
    asked: list[str] = []

    def fake_confirm(question, **kwargs):
        asked.append(question)
        return answer

    monkeypatch.setattr("typer.confirm", fake_confirm)
    return asked


class TestYesFlag:
    """``--yes`` answers **Y** -- it is not "accepts defaults"."""

    def test_answers_y_even_where_the_default_is_n(self, interactive, monkeypatch):
        monkeypatch.setattr("typer.confirm", lambda *a, **k: pytest.fail("prompted"))
        assert confirm("Continue?", default=False, assume_yes=True) is True

    def test_answers_safety_prompts(self, interactive, monkeypatch):
        monkeypatch.setattr("typer.confirm", lambda *a, **k: pytest.fail("prompted"))
        assert (
            confirm(
                "Batch size 32 on CPU. Continue?",
                category=PromptCategory.SAFETY,
                assume_yes=True,
            )
            is True
        )

    def test_never_touches_destructive_prompts(self, interactive, monkeypatch):
        # A destructive auto-confirm requires its own dedicated flag -- for the
        # `dataset/` overwrite that is `--overwrite`, never `--yes`.
        asked = _record(monkeypatch, answer=False)
        confirm(
            "Overwrite dataset/?",
            category=PromptCategory.DESTRUCTIVE,
            assume_yes=True,
        )
        assert asked == ["Overwrite dataset/?"]


class TestForceFlag:
    """``--force`` *suppresses* safety prompts rather than answering them."""

    def test_suppresses_safety_prompts(self, interactive, monkeypatch):
        monkeypatch.setattr("typer.confirm", lambda *a, **k: pytest.fail("prompted"))
        assert (
            confirm("Mismatch. Continue?", category=PromptCategory.SAFETY, force=True)
            is True
        )

    def test_does_not_reach_choice_prompts(self, interactive, monkeypatch):
        asked = _record(monkeypatch, answer=True)
        confirm("Group the sub-terms?", category=PromptCategory.CHOICE, force=True)
        assert asked == ["Group the sub-terms?"]

    def test_does_not_reach_destructive_prompts(self, interactive, monkeypatch):
        asked = _record(monkeypatch, answer=False)
        confirm("Overwrite dataset/?", category=PromptCategory.DESTRUCTIVE, force=True)
        assert asked == ["Overwrite dataset/?"]


class TestDeclineExitsThree:
    """The whole reason ``confirm(..., abort=True)`` is banned."""

    def test_declined_prompt_raises_exit_three(self, interactive, monkeypatch):
        monkeypatch.setattr("typer.confirm", lambda *a, **k: False)
        with pytest.raises(typer.Exit) as caught:
            confirm_or_abort("Create .optica.toml in the current directory?")
        assert caught.value.exit_code == ExitCode.ABORTED

    def test_accepted_prompt_returns_quietly(self, interactive, monkeypatch):
        monkeypatch.setattr("typer.confirm", lambda *a, **k: True)
        confirm_or_abort("Create .optica.toml?")  # must not raise

    def test_decline_does_not_raise_abort(self, interactive, monkeypatch):
        # Abort would exit 130 and make a declined prompt indistinguishable from
        # an interrupt.
        monkeypatch.setattr("typer.confirm", lambda *a, **k: False)
        with pytest.raises(typer.Exit):
            confirm_or_abort("Continue?")


class TestIsInteractive:
    """What counts as a terminal — measured, not assumed.

    Pass 2 found that on Windows ``isatty()`` is True for the ``NUL`` device, so
    ``optica fetch -c cat,dog </dev/null`` prompted, read end-of-file and exited
    130 instead of raising the non-prompting error (``notes/build-log.md``).
    These run a real child process, so the stdin under test is a real one.
    """

    @staticmethod
    def _child(stdin: int | None) -> str:
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from optica.utils.prompts import is_interactive; "
                "print(is_interactive())",
            ],
            stdin=stdin,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def test_devnull_is_not_interactive(self):
        import subprocess

        assert self._child(subprocess.DEVNULL) == "False"

    def test_a_pipe_is_not_interactive(self):
        import subprocess

        assert self._child(subprocess.PIPE) == "False"


class TestNonPromptingContext:
    """A prompt that cannot fire raises a hard error rather than blocking."""

    def test_raises_validation_error_by_default(self, monkeypatch):
        monkeypatch.setattr("optica.utils.prompts.is_interactive", lambda: False)
        with pytest.raises(OpticaValidationError):
            confirm("Define the sub-terms for 'beautiful'.")

    def test_caller_supplies_its_own_subsystem_class(self, monkeypatch):
        # A hard error's class is the subsystem whose contract it violates.
        monkeypatch.setattr("optica.utils.prompts.is_interactive", lambda: False)
        with pytest.raises(OpticaConfigError):
            confirm("Create .optica.toml?", non_interactive_error=OpticaConfigError)

    def test_yes_still_answers_without_a_terminal(self, monkeypatch):
        monkeypatch.setattr("optica.utils.prompts.is_interactive", lambda: False)
        assert confirm("Continue?", assume_yes=True) is True

    def test_force_still_suppresses_without_a_terminal(self, monkeypatch):
        monkeypatch.setattr("optica.utils.prompts.is_interactive", lambda: False)
        assert confirm("Continue?", category=PromptCategory.SAFETY, force=True) is True


class TestPlanValuesStillToImplement:
    """The ``--yes`` table's rows, each owned by a later pass."""

    # Built in pass 2 as the terminal side of the blocklist sequence,
    # optica.cli.classify.TerminalClassPrompter, which asks through this module.

    @staticmethod
    def _prompter(*, yes: bool) -> TerminalClassPrompter:
        from optica.cli import GlobalState
        from optica.cli.classify import TerminalClassPrompter as Prompter

        return Prompter(GlobalState(yes=yes))

    def test_overlap_warning_yes_picks_continue(self, monkeypatch):
        """`--yes` picks: Y — continue."""
        from optica.input.classes import Overlap

        monkeypatch.setattr("optica.utils.prompts.is_interactive", lambda: False)
        monkeypatch.setattr("typer.confirm", lambda *a, **k: pytest.fail("prompted"))
        overlaps = [Overlap(inner="cat", outer="wildcat")]
        assert self._prompter(yes=True).accept_overlaps(overlaps) is True

    def test_group_or_separate_yes_picks_group(self, monkeypatch):
        """`--yes` picks: Group."""
        monkeypatch.setattr("optica.utils.prompts.is_interactive", lambda: False)
        monkeypatch.setattr("typer.confirm", lambda *a, **k: pytest.fail("prompted"))
        prompter = self._prompter(yes=True)
        assert prompter.group_or_separate("defective", ["cracked", "dented"]) is True

    def test_blocklist_definition_prompt_is_absent_from_the_yes_table(self, monkeypatch):
        """No answer can be defaulted.

        In a non-prompting context it raises OpticaValidationError rather than
        blocking.
        """
        monkeypatch.setattr("optica.utils.prompts.is_interactive", lambda: False)
        with pytest.raises(OpticaValidationError, match="'defective'"):
            self._prompter(yes=True).define("defective")

    def test_under_yes_the_definition_prompt_still_fires_in_a_terminal(self, monkeypatch):
        monkeypatch.setattr("optica.utils.prompts.is_interactive", lambda: True)
        monkeypatch.setattr("typer.prompt", lambda *a, **k: "cracked_screen, dented_case")
        answer = self._prompter(yes=True).define("defective")
        assert answer == ["cracked_screen", "dented_case"]

    @pytest.mark.skip(reason="stub - pass 4")
    def test_checkpoint_prompt_offers_four_options_and_yes_picks_keep(self):
        """K/A/D/S, not three options; `--yes` picks K — keep."""

    @pytest.mark.skip(reason="stub - pass 4")
    def test_cpu_batch_size_prompt_is_a_safety_prompt(self):
        """`--yes` picks Y — continue; `--force` suppresses it."""

    @pytest.mark.skip(reason="stub - pass 5")
    def test_yes_never_drives_optica_setup(self):
        """Setup's interactivity is binary and driven by its own flags."""
