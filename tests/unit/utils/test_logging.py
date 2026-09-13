"""Rich output, verbosity, and error rendering.

Covers plan § "Coding Style" → *Logging* and *Error handling*, and
Implementation Note 19 (verbosity governs progress and status output only).
"""

from __future__ import annotations

import io

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


class TestUnencodableUserText:
    """Text with no ASCII equivalent degrades to an escape instead of raising.

    A different problem from ``TestMarkers``: a status glyph has an ASCII
    stand-in and keeps it, but a class name such as 猫 has none. The stream is
    built here with ``encoding="ascii"`` so the condition is the same on every
    runner, whatever its code page. See ``notes/build-log.md`` § "Unencodable
    user text on stdout".
    """

    @staticmethod
    def _strict_ascii() -> tuple[io.BytesIO, io.TextIOWrapper]:
        raw = io.BytesIO()
        return raw, io.TextIOWrapper(raw, encoding="ascii", errors="strict", newline="\n")

    def test_the_unprotected_stream_raises(self):
        # The control: proves the stream really cannot encode it, so the test
        # below is not passing vacuously.
        _, stream = self._strict_ascii()
        with pytest.raises(UnicodeEncodeError):
            stream.write("Classes: 猫, dog\n")
            stream.flush()

    def test_protected_streams_escape_instead_of_raising(self):
        raw_out, out = self._strict_ascii()
        raw_err, err = self._strict_ascii()
        olog.protect_streams(out, err)
        for stream in (out, err):
            stream.write("Classes: 猫, dog → café\n")
            stream.flush()
        expected = b"Classes: \\u732b, dog \\u2192 caf\\xe9\n"
        assert raw_out.getvalue() == expected
        assert raw_err.getvalue() == expected

    def test_encodable_text_is_untouched(self):
        raw, stream = self._strict_ascii()
        olog.protect_streams(stream)
        stream.write("cat: 10 images\n")
        stream.flush()
        assert raw.getvalue() == b"cat: 10 images\n"

    def test_the_encoding_is_not_changed(self):
        _, stream = self._strict_ascii()
        olog.protect_streams(stream)
        assert stream.encoding == "ascii"
        assert stream.errors == "backslashreplace"

    def test_a_stream_that_cannot_be_reconfigured_is_left_alone(self):
        class Plain:
            def write(self, text: str) -> int:
                return len(text)

        olog.protect_streams(Plain())  # must not raise

    def test_the_status_glyph_fallback_is_unchanged(self):
        # Both mechanisms coexist: the glyphs still resolve to their ASCII
        # stand-ins before the stream ever sees them.
        marks = olog.Markers("ascii")
        assert (marks.error, marks.fail, marks.ok, marks.warn) == ("X", "x", "+", "!")


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


class TestLongTokensAreNotFolded:
    """Paths and commands must survive whole, at any length.

    Rich word-wraps at an assumed 79 columns whenever the stream is not a
    terminal, and folds a token longer than the remaining width by inserting a
    newline *inside* it. That broke `optica config --set`'s reported path on CI:
    a path split mid-token is not copyable, and plan § "Error handling and
    prompt conventions" requires the opposite.

    Whether the fold lands mid-token depends on the length of the path, so the
    original failure was reproducible only at certain lengths. These assert the
    property directly instead, at several lengths and on both streams.
    """

    @pytest.mark.parametrize("depth", [1, 3, 6, 12, 40])
    def test_a_long_path_stays_on_one_line(self, depth, capsys):
        path = "/" + "/".join(f"directory-number-{n}" for n in range(depth))
        path += "/.optica/config.toml"
        olog.success(f"epochs = 20  ->  {path}")
        out = capsys.readouterr().out
        assert path in out
        assert "config.toml" in out

    @pytest.mark.parametrize("depth", [1, 3, 6, 12, 40])
    def test_a_long_path_survives_in_an_error(self, depth, capsys):
        path = "C:\\" + "\\".join(f"directory-number-{n}" for n in range(depth))
        olog.render_error(
            OpticaError(
                "Could not read the config",
                fix=f"Run: optica config --view {path}",
            )
        )
        assert path in capsys.readouterr().err

    def test_a_copy_paste_command_is_not_broken(self, capsys):
        command = (
            "optica run -c golden_retriever,german_shepherd,border_collie "
            "--source open-datasets --images-per-class 200 --model efficientnet-large"
        )
        olog.render_error(OpticaError("Something went wrong", fix=f"Run: {command}"))
        assert command in capsys.readouterr().err

    def test_the_console_width_is_not_what_makes_this_work(self):
        # Soft wrapping, not a wide terminal: CI logs report 79 columns.
        assert olog.out_console.soft_wrap is True
        assert olog.err_console.soft_wrap is True


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
