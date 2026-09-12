"""Rich output, verbosity, and error rendering.

Covers plan § "Coding Style" → *Logging* and *Error handling*, and
Implementation Note 19 (verbosity governs progress and status output only).
"""

from __future__ import annotations

import pytest

from optica.exceptions import OpticaError
from optica.utils import logging as olog


class TestMarkers:
    """The four status glyphs, with an ASCII fallback.

    Used where the stream cannot encode them. See ``notes/verified.md``
    § "Non-ASCII status glyphs crash on a non-UTF-8 Windows stdout".
    """

    def test_utf8_keeps_the_glyphs(self):
        marks = olog.Markers("utf-8")
        assert marks.error == "✕"
        assert marks.fail == "✗"
        assert marks.ok == "✓"
        assert marks.warn == "⚠"

    @pytest.mark.parametrize("encoding", ["ascii", "cp1252", "cp1255"])
    def test_narrow_encodings_fall_back_to_ascii(self, encoding):
        marks = olog.Markers(encoding)
        assert (marks.error, marks.fail, marks.ok, marks.warn) == ("X", "x", "+", "!")

    def test_unknown_encoding_falls_back_rather_than_raising(self):
        assert olog.Markers("not-a-codec").error == "X"

    def test_missing_encoding_falls_back(self):
        assert olog.Markers(None).error == "X"


class TestVerbosity:
    """``--verbose``/``--quiet`` govern progress and status output only."""

    def test_status_is_silenced_by_quiet(self, capsys):
        olog.set_verbosity(olog.Verbosity.QUIET)
        olog.status("fetching")
        assert capsys.readouterr().out == ""

    def test_status_shows_at_normal(self, capsys):
        olog.status("fetching")
        assert "fetching" in capsys.readouterr().out

    def test_detail_needs_verbose(self, capsys):
        olog.detail("resolved 12 URLs")
        assert capsys.readouterr().out == ""
        olog.set_verbosity(olog.Verbosity.VERBOSE)
        olog.detail("resolved 12 URLs")
        assert "resolved 12 URLs" in capsys.readouterr().out

    @pytest.mark.parametrize(
        "level", [olog.Verbosity.QUIET, olog.Verbosity.NORMAL, olog.Verbosity.VERBOSE]
    )
    def test_warnings_display_at_every_level(self, level, capsys):
        # Nothing about verbosity suppresses a warning (Implementation Note 19).
        olog.set_verbosity(level)
        olog.warn("Class 'cat' has 12 images; 'dog' has 95.")
        assert "cat" in capsys.readouterr().err

    @pytest.mark.parametrize(
        "level", [olog.Verbosity.QUIET, olog.Verbosity.NORMAL, olog.Verbosity.VERBOSE]
    )
    def test_errors_display_at_every_level(self, level, capsys):
        olog.set_verbosity(level)
        olog.render_error(OpticaError("No dataset found at ./dataset"))
        assert "No dataset found" in capsys.readouterr().err


class TestRenderError:
    """The three-line structure, plus the fixed-value-flag additions."""

    def test_full_shape(self, capsys):
        olog.render_error(
            OpticaError(
                "No dataset found at ./dataset",
                why="Optica expects class subfolders inside this directory.",
                fix=[
                    "Run: optica label --folder ./my-images -c cat,dog",
                    "Or create subfolders manually: dataset/cat/, dataset/dog/",
                ],
            )
        )
        err = capsys.readouterr().err
        assert "No dataset found at ./dataset" in err
        assert "Optica expects class subfolders" in err
        assert "optica label --folder ./my-images -c cat,dog" in err
        assert "dataset/cat/" in err

    def test_errors_go_to_stderr_not_stdout(self, capsys):
        olog.render_error(OpticaError("boom"))
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "boom" in captured.err
