"""The exception hierarchy and the exit-code table.

Covers plan § "Exceptions" — the hierarchy, the per-extra messages, and the
exit codes.

Every value asserted here is transcribed from the plan rather than from the
implementation.
"""

from __future__ import annotations

import pytest

from optica.exceptions import (
    ExitCode,
    OpticaBrowserServerError,
    OpticaCLIPError,
    OpticaCLIPLoadError,
    OpticaConfigError,
    OpticaCurationError,
    OpticaError,
    OpticaExportError,
    OpticaFetchError,
    OpticaLabelingError,
    OpticaMissingExtraError,
    OpticaSetupError,
    OpticaTorchError,
    OpticaTrainingError,
    OpticaValidationError,
    OpticaWarning,
    OpticaWebError,
)


class TestHierarchy:
    """V1 is a flat hierarchy with exactly one documented nested branch."""

    @pytest.mark.parametrize(
        "cls",
        [
            OpticaMissingExtraError,
            OpticaCLIPLoadError,
            OpticaConfigError,
            OpticaTrainingError,
            OpticaExportError,
            OpticaFetchError,
            OpticaValidationError,
            OpticaSetupError,
            OpticaBrowserServerError,
            OpticaLabelingError,
            OpticaCurationError,
        ],
    )
    def test_every_class_descends_from_optica_error(self, cls):
        assert issubclass(cls, OpticaError)

    @pytest.mark.parametrize(
        "cls", [OpticaTorchError, OpticaWebError, OpticaCLIPError]
    )
    def test_missing_extra_has_exactly_three_children(self, cls):
        assert issubclass(cls, OpticaMissingExtraError)

    def test_missing_extra_branch_is_the_only_nesting(self):
        # Everything else parents directly to OpticaError, so that the one
        # nested branch stays the catch-any-missing-extra point.
        flat = [
            OpticaCLIPLoadError,
            OpticaConfigError,
            OpticaTrainingError,
            OpticaExportError,
            OpticaFetchError,
            OpticaValidationError,
            OpticaSetupError,
            OpticaBrowserServerError,
            OpticaLabelingError,
            OpticaCurationError,
        ]
        for cls in flat:
            assert cls.__bases__ == (OpticaError,)

    def test_clip_load_error_is_not_a_fetch_error(self):
        # CLIP weights load during training and inference too, so filing it
        # under fetch would misclassify most occurrences.
        assert not issubclass(OpticaCLIPLoadError, OpticaFetchError)

    def test_warning_is_not_an_error(self):
        assert issubclass(OpticaWarning, UserWarning)
        assert not issubclass(OpticaWarning, OpticaError)


class TestMessages:
    """The three per-dependency messages, transcribed from the plan's table."""

    def test_torch_message(self):
        assert (
            OpticaTorchError().message
            == "This operation requires the Optica ML stack. Run: optica setup"
        )

    def test_web_message(self):
        assert OpticaWebError().message == (
            "This operation requires the web extras. "
            "Run: optica setup or pip install optica[web]"
        )

    def test_clip_message(self):
        assert OpticaCLIPError().message == (
            "CLIP filtering requires the clip extra. "
            "Run: optica setup --include-extras clip or pip install optica[clip]"
        )

    @pytest.mark.parametrize(
        "cls", [OpticaTorchError, OpticaWebError, OpticaCLIPError]
    )
    def test_messages_name_the_capability_not_the_caller(self, cls):
        # The same error is raised by the CLI and by the API, so no message may
        # name a command, a flag that requested it, or a Python function.
        message = cls().message
        for forbidden in ("optica fetch", "optica label", "optica curate", "--mode"):
            assert forbidden not in message


class TestErrorStructure:
    """Plan § "Coding Style": what went wrong / why / how to fix."""

    def test_parts_are_kept_separately(self):
        exc = OpticaError(
            "No dataset found at ./dataset",
            why="Optica expects class subfolders inside this directory.",
            fix="Run: optica label --folder ./my-images -c cat,dog",
        )
        assert exc.message == "No dataset found at ./dataset"
        assert exc.why == "Optica expects class subfolders inside this directory."
        assert exc.fix == ["Run: optica label --folder ./my-images -c cat,dog"]

    def test_fix_accepts_several_lines(self):
        exc = OpticaError("x", fix=["Run: a", "Or: b"])
        assert exc.fix == ["Run: a", "Or: b"]

    def test_fixed_value_flag_errors_carry_options_and_default(self):
        exc = OpticaConfigError(
            "Unknown source 'flikr'",
            options=["flickr", "open-datasets"],
            default="open-datasets",
        )
        assert exc.options == ["flickr", "open-datasets"]
        assert exc.default == "open-datasets"


class TestExitCodes:
    """The plan's exit-code table, value by value."""

    def test_table(self):
        assert ExitCode.SUCCESS.value == 0
        assert ExitCode.ERROR.value == 1
        assert ExitCode.USAGE.value == 2
        assert ExitCode.ABORTED.value == 3
        assert ExitCode.INTERRUPTED.value == 130

    def test_codes_are_ints_for_sys_exit(self):
        assert isinstance(ExitCode.ABORTED, int)

    def test_aborted_is_distinct_from_error_and_usage(self):
        # A declined prompt is neither a broken config nor a parser error; a CI
        # script has to be able to tell the three apart.
        assert len({ExitCode.ERROR, ExitCode.USAGE, ExitCode.ABORTED}) == 3
