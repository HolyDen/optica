"""Rich output, verbosity, and error rendering.

Covers plan § "Coding Style" → *Logging* and *Error handling*, and
Implementation Note 19 (verbosity governs progress and status output only).
"""

from __future__ import annotations

import io

import pytest

from optica.exceptions import OpticaCLIPError, OpticaError, OpticaWebError
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


class TestIncomplete:
    """``✗ X incomplete — reason``: the completion line an exit 3 carries."""

    def test_goes_to_stderr_with_the_fail_marker(self, capsys):
        olog.incomplete("Labeling incomplete — interrupted")
        captured = capsys.readouterr()
        assert captured.out == ""
        marks = olog.markers_for(olog.err_console)
        assert f"{marks.fail} Labeling incomplete — interrupted" in captured.err

    def test_is_not_silenced_by_quiet(self, capsys):
        olog.set_verbosity(olog.Verbosity.QUIET)
        olog.incomplete("Labeling incomplete — timed out")
        assert "Labeling incomplete — timed out" in capsys.readouterr().err


class TestBracketedTextSurvivesRendering:
    """A bracketed token in caller text reaches the screen intact.

    Covers plan § "Lazy imports" — the per-dependency message table at
    l.1536-1537, which spells the install commands ``pip install optica[web]``
    and ``pip install optica[clip]``.

    Rich reads ``[web]`` as a style tag and drops it, with no error and no
    warning, so the rendered line read ``pip install optica`` — a command that
    installs the package the user already has. ``str(exc)`` was correct
    throughout; only the rendering lost the extra, which is why every assertion
    here is made against captured output rather than against a message string.

    Uppercase tags are not markup, so ``[R]``/``[C]``/``[F]`` were never
    affected and the defect was invisible on the prompts that use them.
    """

    @pytest.mark.parametrize(
        ("exc", "extra"),
        [
            (OpticaWebError(), "pip install optica[web]"),
            (OpticaCLIPError(), "pip install optica[clip]"),
        ],
        ids=["web", "clip"],
    )
    def test_the_missing_extra_messages_keep_the_extra(self, exc, extra, capsys):
        olog.render_error(exc)
        assert extra in capsys.readouterr().err

    @pytest.mark.parametrize(
        ("exc", "extra"),
        [
            (OpticaWebError(), "optica[web]"),
            (OpticaCLIPError(), "optica[clip]"),
        ],
        ids=["web", "clip"],
    )
    def test_the_message_itself_was_never_wrong(self, exc, extra):
        # The escape belongs at render time. An escape written into the literal
        # would fix the screen and corrupt `str(exc)`, which the Python API
        # surfaces to a caller who never goes near Rich.
        assert extra in str(exc)
        assert "\\" not in str(exc)

    def test_every_renderer_carries_a_bracketed_token(self, capsys):
        olog.set_verbosity(olog.Verbosity.VERBOSE)
        olog.status("status optica[web]")
        olog.detail("detail optica[web]")
        olog.success("success optica[web]")
        captured = capsys.readouterr()
        for line in ("status optica[web]", "detail optica[web]", "success optica[web]"):
            assert line in captured.out

        olog.incomplete("incomplete optica[clip]")
        olog.warn("warn optica[clip]", why="why optica[clip]", fix="fix optica[clip]")
        err = capsys.readouterr().err
        for line in (
            "incomplete optica[clip]",
            "warn optica[clip]",
            "why optica[clip]",
            "fix optica[clip]",
        ):
            assert line in err

    def test_every_render_error_field_carries_one(self, capsys):
        olog.render_error(
            OpticaError(
                "message optica[web]",
                why="why optica[web]",
                fix=["fix optica[web]"],
                options=["mode[a]", "mode[b]"],
                default="default[x]",
            )
        )
        err = capsys.readouterr().err
        for line in (
            "message optica[web]",
            "why optica[web]",
            "fix optica[web]",
            "mode[a], mode[b]",
            "default[x]",
        ):
            assert line in err

    def test_the_escape_is_not_printed(self, capsys):
        # The mechanism is a backslash Rich consumes. If it ever reaches the
        # screen the user gets ``optica\[web]``, which is as uncopyable as the
        # truncation it replaced.
        olog.render_error(OpticaWebError())
        assert r"\[web]" not in capsys.readouterr().err

    def test_the_style_tags_are_still_markup(self, capsys):
        # The fix escapes caller text only. Escaping the whole formatted line
        # would make every status glyph print its tag literally.
        olog.success("done")
        out = capsys.readouterr().out
        assert "[bold green]" not in out
        assert olog.markers_for(olog.out_console).ok in out

