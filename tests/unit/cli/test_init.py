"""Shared CLI state and the value-separator helper.

Mirrors ``src/optica/cli/__init__.py``. Covers plan § *Value separator — comma,
everywhere* and § "Global flags".

``split_values`` is the implementation of the convention checked against Click's
real behaviour in ``notes/verified.md`` § "Click's restriction of variable-length
``nargs``": the parser hands back ``["cat", "dog,bird"]`` untouched, so every
part of the convention — the splitting, the trimming, the composition of a
repeated flag with a comma-separated one — happens here and nowhere else.
"""

from __future__ import annotations

import typer

from optica.cli import GlobalState, get_state, split_values
from optica.utils import logging as olog


class TestSplitValues:
    """The convention, clause by clause."""

    def test_comma_separated(self):
        assert split_values(["cat,dog"]) == ["cat", "dog"]

    def test_repeated_flag(self):
        assert split_values(["cat", "dog"]) == ["cat", "dog"]

    def test_the_two_compose(self):
        # The plan's own example: -c cat -c dog,bird yields three classes.
        assert split_values(["cat", "dog,bird"]) == ["cat", "dog", "bird"]

    def test_a_single_value(self):
        assert split_values(["cat"]) == ["cat"]

    def test_absent_flag_gives_an_empty_list(self):
        assert split_values(None) == []

    def test_an_empty_list_gives_an_empty_list(self):
        assert split_values([]) == []


class TestSplitValuesTrimming:
    """Values are trimmed of surrounding whitespace."""

    def test_spaces_around_values(self):
        assert split_values([" cat , dog "]) == ["cat", "dog"]

    def test_tabs_and_newlines(self):
        assert split_values(["\tcat\n,\tdog\n"]) == ["cat", "dog"]

    def test_interior_spaces_survive(self):
        # Multi-word values quote per value: --classes "orange cat",dog
        assert split_values(["orange cat,dog"]) == ["orange cat", "dog"]

    def test_a_multi_word_value_keeps_one_interior_space(self):
        assert split_values([" orange  cat "]) == ["orange  cat"]


class TestSplitValuesEmptySegments:
    """A comma with nothing beside it is not a value."""

    def test_trailing_comma(self):
        assert split_values(["cat,dog,"]) == ["cat", "dog"]

    def test_leading_comma(self):
        assert split_values([",cat,dog"]) == ["cat", "dog"]

    def test_doubled_comma(self):
        assert split_values(["cat,,dog"]) == ["cat", "dog"]

    def test_a_lone_comma(self):
        assert split_values([","]) == []

    def test_an_empty_string(self):
        assert split_values([""]) == []

    def test_whitespace_only(self):
        assert split_values(["   "]) == []


class TestSplitValuesDoesNotOverreach:
    """It splits and trims. Everything else belongs to the rules that consume it."""

    def test_order_is_preserved(self):
        assert split_values(["c,a", "b"]) == ["c", "a", "b"]

    def test_duplicates_are_preserved(self):
        # Collapsing `cat,cat` is the class-name rule's job (pass 2), and it is
        # a rule about class names rather than about flag syntax -- the same
        # splitter serves --checkpoint-rank and --include-extras.
        assert split_values(["cat,cat"]) == ["cat", "cat"]

    def test_case_is_preserved(self):
        # Case-insensitive duplicate blocking is likewise pass 2's rule.
        assert split_values(["Cat,cat"]) == ["Cat", "cat"]

    def test_non_class_values_split_the_same_way(self):
        assert split_values(["1,2,3"]) == ["1", "2", "3"]


class TestGlobalStateDefaults:
    def test_everything_is_off(self):
        state = GlobalState()
        assert (state.verbose, state.quiet, state.yes, state.force, state.dry_run) == (
            False,
            False,
            False,
            False,
            False,
        )

    def test_argv_defaults_to_empty(self):
        assert GlobalState().argv == []


class TestGlobalStateMerge:
    """A flag seen in either position applies to the whole run."""

    def test_merge_is_sticky(self):
        state = GlobalState()
        state.merge(verbose=True)
        state.merge(quiet=False)
        assert state.verbose is True

    def test_a_later_false_never_unsets(self):
        state = GlobalState(yes=True)
        state.merge(yes=False)
        assert state.yes is True

    def test_merge_returns_the_same_state(self):
        state = GlobalState()
        assert state.merge(force=True) is state

    def test_each_flag_merges_independently(self):
        state = GlobalState()
        state.merge(verbose=True)
        state.merge(force=True)
        assert state.verbose is True
        assert state.force is True


class TestGlobalStateApply:
    def test_verbose_wins_over_quiet(self):
        # --verbose adds detail rather than unlocking messages --quiet withheld,
        # so the louder of the two is never the surprising choice.
        GlobalState(verbose=True, quiet=True).apply()
        assert olog.get_verbosity() is olog.Verbosity.VERBOSE

    def test_quiet_alone_lowers_the_level(self):
        GlobalState(quiet=True).apply()
        assert olog.get_verbosity() is olog.Verbosity.QUIET

    def test_neither_is_normal(self):
        GlobalState().apply()
        assert olog.get_verbosity() is olog.Verbosity.NORMAL

    def test_merge_applies_immediately(self):
        GlobalState().merge(verbose=True)
        assert olog.get_verbosity() is olog.Verbosity.VERBOSE


class TestGlobalStateConfig:
    """Config resolves once per run, before the command acts."""

    def test_resolution_is_cached(self, fake_home, project_dir):
        state = GlobalState()
        assert state.config() is state.config()

    def test_overrides_force_a_re_resolution(self, fake_home, project_dir):
        state = GlobalState()
        first = state.config()
        second = state.config(overrides={"epochs": 42})
        assert first is not second
        assert second.config.epochs == 42


class TestGetState:
    """One state object per run, reached from any depth of subcommand."""

    def test_a_command_gets_a_state(self, fake_home, project_dir):
        seen: list[GlobalState] = []
        app = typer.Typer()

        @app.command()
        def probe(ctx: typer.Context) -> None:
            seen.append(get_state(ctx))

        @app.command()
        def other() -> None:
            pass

        typer.main.get_command(app).main(
            args=["probe"], prog_name="optica", standalone_mode=False
        )
        assert isinstance(seen[0], GlobalState)

    def test_the_root_callback_and_a_subcommand_share_one_state(
        self, fake_home, project_dir
    ):
        seen: list[GlobalState] = []
        app = typer.Typer()
        group = typer.Typer()

        @app.callback()
        def root(ctx: typer.Context) -> None:
            seen.append(get_state(ctx))

        @group.command()
        def probe(ctx: typer.Context) -> None:
            seen.append(get_state(ctx))

        app.add_typer(group, name="classify")
        typer.main.get_command(app).main(
            args=["classify", "probe"], prog_name="optica", standalone_mode=False
        )
        # A flag given before the subcommand must reach the subcommand, which
        # only works if both see the same object.
        assert len(seen) == 2
        assert seen[0] is seen[1]
