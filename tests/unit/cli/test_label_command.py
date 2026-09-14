"""``optica label``, from the command line to ``dataset/``.

Covers plan § "Input & Acquisition" → *`optica run` resumption and
preconditions* (label needs a folder or manifest and resolves ``-c`` first),
*`--manifest`* (a fully labeled manifest is refused; the manifest is never
rewritten), *Unreadable images — pre-flight verification*, *Post-deduplication
floor re-check*, and *`dataset/` conflict* (the prompt fires before the browser;
``--yes`` and ``--force`` never answer it; ``--overwrite`` does; replace, never
merge); § "Labeling & Curation" → *Terminal-side completion for browser steps*
(``✓``/``✗`` lines and exit codes 0, 3, 130) and *Staging shapes* (the session
file: resume, adopt the new list, start fresh; written through, then removed on
completion); § "Exceptions" (``OpticaWebError`` from a missing extra).

The browser is not opened: ``serve`` is replaced by a stand-in that drives the
real page controller the command built, the way the page's requests would. The
real server is tested in ``tests/unit/server/test_app.py`` and the integration
tests.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from PIL import Image

from optica.cli.main import app
from optica.exceptions import ExitCode
from optica.input.sessions import LabelingSession, SourceType, labeling_dir
from optica.server.app import BrowserSession, Outcome
from optica.server.labeling import LabelingController

Drive = Callable[[LabelingController], None]


@pytest.fixture(autouse=True)
def _isolated(fake_home, project_dir):
    return project_dir


@pytest.fixture(autouse=True)
def _web_present(monkeypatch):
    # The extra is checked for real in TestPreconditions; elsewhere its absence
    # (as in CI) must not stop the command before the part under test.
    monkeypatch.setattr("optica.cli.classify.load_web", lambda: None)


def _make_images(folder: Path, count: int, *, start: int = 0) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(start, start + count):
        path = folder / f"IMG_{i:04d}.jpg"
        # Distinct colours, so no two are byte-identical duplicates.
        Image.new(
            "RGB", (160, 140), ((i * 37) % 256, (i * 91) % 256, (i * 53) % 256)
        ).save(path, "JPEG")
        paths.append(path)
    return paths


class FakeServe:
    """Stands in for ``serve``: records the call, drives the controller, returns."""

    def __init__(
        self, drive: Drive | None = None, outcome: Outcome = Outcome.FINISHED
    ) -> None:
        self.drive = drive
        self.outcome = outcome
        self.sessions: list[BrowserSession] = []

    def __call__(self, browser: BrowserSession, **kwargs: object) -> Outcome:
        self.sessions.append(browser)
        controller = browser.controller
        assert isinstance(controller, LabelingController)
        if self.drive is not None:
            self.drive(controller)
        return self.outcome

    @property
    def controller(self) -> LabelingController:
        controller = self.sessions[-1].controller
        assert isinstance(controller, LabelingController)
        return controller


def _label_split(cat: int, dog: int) -> Drive:
    def drive(controller: LabelingController) -> None:
        for i in range(cat):
            controller.assign(i, "cat")
        for i in range(cat, cat + dog):
            controller.assign(i, "dog")
        result = controller.finish(confirmed=True)
        assert result["status"] == "finished", result

    return drive


def _serve(
    monkeypatch, drive: Drive | None = None, outcome=Outcome.FINISHED
) -> FakeServe:
    fake = FakeServe(drive, outcome)
    monkeypatch.setattr("optica.cli.classify.serve", fake)
    return fake


def _dataset_counts(root: Path) -> dict[str, int]:
    return {d.name: len(list(d.iterdir())) for d in sorted(root.iterdir()) if d.is_dir()}


def _session_files(home: Path) -> list[Path]:
    folder = labeling_dir(home)
    return sorted(folder.glob("*.json")) if folder.is_dir() else []


@pytest.fixture
def interactive(monkeypatch):
    monkeypatch.setattr("optica.utils.prompts.is_interactive", lambda: True)


# ------------------------------------------------------------ preconditions


class TestPreconditions:
    def test_needs_a_folder_or_a_manifest(self, capsys):
        assert app.invoke_guarded(["label", "-c", "cat,dog"]) == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "optica label needs a flat folder or a manifest" in err
        assert "optica label --folder ./images -c cat,dog" in err

    def test_a_missing_web_extra_is_reported_before_any_prompt(
        self, monkeypatch, project_dir, capsys
    ):
        from optica.server import app as server_app

        # Put the real check back over the autouse stand-in. Not
        # monkeypatch.undo(): that would also undo the fake home and chdir.
        monkeypatch.setattr("optica.cli.classify.load_web", server_app.load_web)
        monkeypatch.setitem(sys.modules, "uvicorn", None)
        _make_images(project_dir / "images", 2)
        # No -c and no terminal: without the extra check first, the class
        # error would be what printed.
        assert app.invoke_guarded(["label", "--folder", "images"]) == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "This operation requires the web extras." in err
        assert "--classes is required" not in err

    def test_classes_are_required_where_no_prompt_can_fire(self, project_dir, capsys):
        _make_images(project_dir / "images", 2)
        assert app.invoke_guarded(["label", "--folder", "images"]) == ExitCode.ERROR
        assert "--classes is required for label — nothing to label with." in (
            capsys.readouterr().err
        )

    def test_fewer_than_two_classes_is_refused_before_the_browser(
        self, monkeypatch, project_dir, capsys
    ):
        fake = _serve(monkeypatch)
        _make_images(project_dir / "images", 2)
        assert app.invoke_guarded(["label", "--folder", "images", "-c", "cat"]) == 1
        assert (
            "--classes requires at least 2 class names. Got: cat"
            in capsys.readouterr().err
        )
        assert fake.sessions == []

    def test_an_organized_folder_is_refused(self, project_dir, capsys):
        _make_images(project_dir / "images" / "cat", 1)
        code = app.invoke_guarded(["label", "--folder", "images", "-c", "cat,dog"])
        assert code == ExitCode.ERROR
        assert "appears to already be organized into subfolders: cat/" in (
            capsys.readouterr().err
        )

    def test_a_fully_labeled_manifest_is_refused(self, project_dir, capsys):
        _make_images(project_dir / "images", 2)
        manifest = project_dir / "m.csv"
        manifest.write_text(
            "path,class\nimages/IMG_0000.jpg,cat\nimages/IMG_0001.jpg,dog\n",
            encoding="utf-8",
        )
        code = app.invoke_guarded(["label", "--manifest", "m.csv", "-c", "cat,dog"])
        assert code == ExitCode.ERROR
        assert "is already fully labeled" in capsys.readouterr().err

    def test_zero_readable_images_stops_before_the_browser(
        self, monkeypatch, project_dir, capsys
    ):
        fake = _serve(monkeypatch)
        (project_dir / "images").mkdir()
        (project_dir / "images" / "empty.jpg").write_bytes(b"")
        code = app.invoke_guarded(["label", "--folder", "images", "-c", "cat,dog"])
        assert code == ExitCode.ERROR
        assert "None of the 1 files could be read as images." in capsys.readouterr().err
        assert fake.sessions == []


# --------------------------------------------------------------- completion


class TestFinish:
    def test_labels_are_copied_into_dataset_and_the_session_is_cleared(
        self, monkeypatch, project_dir, fake_home, capsys
    ):
        _make_images(project_dir / "images", 12)
        fake = _serve(monkeypatch, _label_split(5, 6))
        code = app.invoke_guarded(["label", "--folder", "images", "-c", "cat,dog"])
        out = capsys.readouterr().out
        assert code == ExitCode.SUCCESS
        assert _dataset_counts(project_dir / "dataset") == {"cat": 5, "dog": 6}
        assert "Labeling complete — 11 images labeled across 2 classes" in out
        assert "Copying 11 images" in out
        assert "originals untouched" in out
        assert len(fake.sessions) == 1
        assert _session_files(fake_home) == []
        assert not (project_dir / ".dataset.partial").exists()

    def test_originals_are_untouched(self, monkeypatch, project_dir):
        originals = _make_images(project_dir / "images", 10)
        before = {p: p.read_bytes() for p in originals}
        _serve(monkeypatch, _label_split(5, 5))
        assert app.invoke_guarded(["label", "--folder", "images", "-c", "cat,dog"]) == 0
        assert {p: p.read_bytes() for p in originals} == before

    def test_the_headline_counts_readable_images(self, monkeypatch, project_dir):
        _make_images(project_dir / "images", 10)
        (project_dir / "images" / "zero.jpg").write_bytes(b"")
        seen: dict[str, object] = {}

        def spy(browser: BrowserSession, **kwargs: object) -> Outcome:
            seen.update(kwargs)
            return Outcome.INTERRUPTED

        monkeypatch.setattr("optica.cli.classify.serve", spy)
        app.invoke_guarded(["label", "--folder", "images", "-c", "cat,dog"])
        assert seen["headline"] == "Labeling 10 images"
        assert seen["configured_port"] == 8765

    def test_unreadable_files_are_listed_and_counted_in_the_completion_line(
        self, monkeypatch, project_dir, capsys
    ):
        _make_images(project_dir / "images", 10)
        (project_dir / "images" / "zero.jpg").write_bytes(b"")
        _serve(monkeypatch, _label_split(5, 5))
        assert app.invoke_guarded(["label", "--folder", "images", "-c", "cat,dog"]) == 0
        captured = capsys.readouterr()
        assert "1 file could not be read before labeling" in captured.err
        assert f"{project_dir / 'images' / 'zero.jpg'}: zero bytes" in captured.err
        assert (
            "Labeling complete — 10 images labeled across 2 classes "
            "(1 unreadable file left out)"
        ) in captured.out

    def test_the_manifest_is_never_rewritten(self, monkeypatch, project_dir, fake_home):
        _make_images(project_dir / "images", 10)
        manifest = project_dir / "m.csv"
        rows = "".join(f"images/IMG_{i:04d}.jpg\n" for i in range(10))
        manifest.write_text("path\n" + rows, encoding="utf-8")
        before = manifest.read_bytes()
        seen: list[Path] = []

        def drive(controller: LabelingController) -> None:
            seen.append(controller.session.path)
            _label_split(5, 5)(controller)

        _serve(monkeypatch, drive)
        assert app.invoke_guarded(["label", "--manifest", "m.csv", "-c", "cat,dog"]) == 0
        assert manifest.read_bytes() == before
        assert _dataset_counts(project_dir / "dataset") == {"cat": 5, "dog": 5}
        # The session the page wrote through is the one keyed by path + content hash.
        import hashlib

        expected = LabelingSession.new(
            fake_home,
            manifest,
            SourceType.MANIFEST,
            ["cat", "dog"],
            hashlib.sha256(before).hexdigest(),
        ).path
        assert seen == [expected]


class TestIncomplete:
    def test_a_timeout_exits_three_and_keeps_progress(
        self, monkeypatch, project_dir, fake_home, capsys
    ):
        _make_images(project_dir / "images", 10)

        def drive(controller: LabelingController) -> None:
            controller.assign(0, "cat")

        _serve(monkeypatch, drive, Outcome.TIMED_OUT)
        code = app.invoke_guarded(["label", "--folder", "images", "-c", "cat,dog"])
        assert code == ExitCode.ABORTED
        err = capsys.readouterr().err
        assert "Labeling incomplete — the session closed after 60 minutes" in err
        assert "progress is saved" in err
        [stored] = _session_files(fake_home)
        assert len(json.loads(stored.read_text(encoding="utf-8"))["entries"]) == 1
        assert not (project_dir / "dataset").exists()

    def test_ctrl_c_exits_130_and_keeps_progress(
        self, monkeypatch, project_dir, fake_home, capsys
    ):
        _make_images(project_dir / "images", 10)
        def drive(controller: LabelingController) -> None:
            controller.next(0)

        _serve(monkeypatch, drive, Outcome.INTERRUPTED)
        code = app.invoke_guarded(["label", "--folder", "images", "-c", "cat,dog"])
        assert code == ExitCode.INTERRUPTED
        assert "Labeling incomplete — interrupted; progress is saved." in (
            capsys.readouterr().err
        )
        assert len(_session_files(fake_home)) == 1

    def test_the_lock_is_released_after_the_browser_stage(self, monkeypatch, project_dir):
        from optica.utils.lockfile import lock_path

        _make_images(project_dir / "images", 10)
        _serve(monkeypatch, None, Outcome.INTERRUPTED)
        app.invoke_guarded(["label", "--folder", "images", "-c", "cat,dog"])
        assert not lock_path().exists()


class TestFloorAfterCopy:
    def test_a_duplicate_that_drops_a_class_below_five_leaves_the_old_dataset(
        self, monkeypatch, project_dir, fake_home, capsys
    ):
        images = _make_images(project_dir / "images", 10)
        # IMG_0004 becomes a byte-identical copy of IMG_0000: cat has 5 labels,
        # 4 unique images.
        images[4].write_bytes(images[0].read_bytes())
        old = project_dir / "dataset" / "old"
        old.mkdir(parents=True)
        (old / "keep.jpg").write_bytes(b"old")
        _serve(monkeypatch, _label_split(5, 5))
        code = app.invoke_guarded(
            ["label", "--folder", "images", "-c", "cat,dog", "--overwrite"]
        )
        assert code == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "cat fell below the 5-image minimum after duplicate removal." in err
        assert "cat: 5 images → 4 unique (1 duplicate removed)" in err
        assert "re-run the same command to resume it" in err
        assert (old / "keep.jpg").read_bytes() == b"old"
        assert not (project_dir / ".dataset.partial").exists()
        assert len(_session_files(fake_home)) == 1

    def test_a_truncated_jpeg_that_passed_pre_flight_is_caught_at_copy(
        self, monkeypatch, project_dir, fake_home, capsys
    ):
        from optica.input.validation import inspect_in_place

        images = _make_images(project_dir / "images", 10)
        # Constructed: half of a noisy JPEG passes the header-only pre-flight
        # (build-log, pass 2) and fails only when fully decoded. Half of a
        # small flat-colour JPEG does not pass it, so the content matters.
        noisy = Image.effect_noise((300, 300), 64).convert("RGB")
        noisy.save(images[2], "JPEG")
        data = images[2].read_bytes()
        images[2].write_bytes(data[: len(data) // 2])
        assert inspect_in_place(images[2]).readable  # the control
        _serve(monkeypatch, _label_split(5, 5))
        code = app.invoke_guarded(["label", "--folder", "images", "-c", "cat,dog"])
        assert code == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "1 file could not be read while copying" in err
        assert f"{images[2]}: truncated file" in err
        assert "cat has fewer than 5 images." in err
        assert not (project_dir / "dataset").exists()
        assert len(_session_files(fake_home)) == 1


# ----------------------------------------------------------------- dataset/


def _populated_dataset(project_dir: Path) -> Path:
    for name, count in (("cat", 3), ("dog", 2)):
        folder = project_dir / "dataset" / name
        folder.mkdir(parents=True)
        for i in range(count):
            (folder / f"old{i}.jpg").write_bytes(b"old")
    return project_dir / "dataset"


class TestOverwritePrompt:
    def test_unattended_without_overwrite_is_refused_before_the_browser(
        self, monkeypatch, project_dir, capsys
    ):
        dataset = _populated_dataset(project_dir)
        _make_images(project_dir / "images", 10)
        fake = _serve(monkeypatch, _label_split(5, 5))
        code = app.invoke_guarded(
            ["label", "--folder", "images", "-c", "cat,dog", "--yes"]
        )
        assert code == ExitCode.ERROR
        assert "already exists and is not empty" in capsys.readouterr().err
        assert fake.sessions == []
        assert _dataset_counts(dataset) == {"cat": 3, "dog": 2}

    def test_overwrite_replaces_rather_than_merges(
        self, monkeypatch, project_dir, capsys
    ):
        dataset = _populated_dataset(project_dir)
        _make_images(project_dir / "images", 10)
        _serve(monkeypatch, _label_split(5, 5))
        code = app.invoke_guarded(
            ["label", "--folder", "images", "-c", "cat,dog", "--overwrite"]
        )
        assert code == ExitCode.SUCCESS
        assert _dataset_counts(dataset) == {"cat": 5, "dog": 5}
        assert not list(dataset.rglob("old*.jpg"))

    def test_the_prompt_names_what_is_there_and_n_exits_three(
        self, monkeypatch, project_dir, interactive, capsys
    ):
        _populated_dataset(project_dir)
        _make_images(project_dir / "images", 10)
        fake = _serve(monkeypatch, _label_split(5, 5))
        asked: list[tuple[str, bool]] = []

        def confirm(question: str, default: bool = True, **kwargs: object) -> bool:
            asked.append((question, default))
            return False

        monkeypatch.setattr("typer.confirm", confirm)
        code = app.invoke_guarded(["label", "--folder", "images", "-c", "cat,dog"])
        assert code == ExitCode.ABORTED
        err = capsys.readouterr().err
        assert (
            "dataset/ already exists and will be replaced with new labels from --folder:"
            in err
        )
        assert "  cat: 3 images" in err
        assert "  dog: 2 images" in err
        assert asked == [("Continue? (n to exit)", False)]  # a destructive prompt: N
        assert "Aborted." in err
        assert "optica label --folder images -c cat,dog --dataset ./new-dataset" in err
        assert fake.sessions == []

    def test_yes_does_not_answer_it(self, monkeypatch, project_dir, interactive):
        _populated_dataset(project_dir)
        _make_images(project_dir / "images", 10)
        _serve(monkeypatch, _label_split(5, 5))
        asked: list[str] = []
        def confirm(question: str, **kwargs: object) -> bool:
            asked.append(question)
            return False

        monkeypatch.setattr("typer.confirm", confirm)
        code = app.invoke_guarded(
            ["label", "--folder", "images", "-c", "cat,dog", "--yes", "--force"]
        )
        assert code == ExitCode.ABORTED
        assert asked == ["Continue? (n to exit)"]

    def test_y_replaces_it_after_labeling(self, monkeypatch, project_dir, interactive):
        dataset = _populated_dataset(project_dir)
        _make_images(project_dir / "images", 10)
        _serve(monkeypatch, _label_split(5, 5))
        monkeypatch.setattr("typer.confirm", lambda *a, **k: True)
        assert app.invoke_guarded(["label", "--folder", "images", "-c", "cat,dog"]) == 0
        assert _dataset_counts(dataset) == {"cat": 5, "dog": 5}

    def test_nothing_is_deleted_when_labeling_does_not_finish(
        self, monkeypatch, project_dir, interactive
    ):
        dataset = _populated_dataset(project_dir)
        _make_images(project_dir / "images", 10)
        _serve(monkeypatch, None, Outcome.INTERRUPTED)
        monkeypatch.setattr("typer.confirm", lambda *a, **k: True)
        app.invoke_guarded(["label", "--folder", "images", "-c", "cat,dog"])
        assert _dataset_counts(dataset) == {"cat": 3, "dog": 2}

    def test_a_different_dataset_path_is_the_destination_checked(
        self, monkeypatch, project_dir
    ):
        _populated_dataset(project_dir)
        _make_images(project_dir / "images", 10)
        _serve(monkeypatch, _label_split(5, 5))
        code = app.invoke_guarded(
            ["label", "--folder", "images", "-c", "cat,dog", "--dataset", "new"]
        )
        assert code == ExitCode.SUCCESS
        assert _dataset_counts(project_dir / "new") == {"cat": 5, "dog": 5}
        assert _dataset_counts(project_dir / "dataset") == {"cat": 3, "dog": 2}


# ------------------------------------------------------------------ resume


def _interrupted_session(monkeypatch, project_dir: Path, fake_home: Path) -> Path:
    _make_images(project_dir / "images", 12)

    def drive(controller: LabelingController) -> None:
        controller.assign(0, "cat")
        controller.assign(1, "dog")
        controller.next(2)

    _serve(monkeypatch, drive, Outcome.INTERRUPTED)
    app.invoke_guarded(["label", "--folder", "images", "-c", "cat,dog"])
    [stored] = _session_files(fake_home)
    return stored


class TestResume:
    def test_unattended_without_yes_is_a_hard_error(
        self, monkeypatch, project_dir, fake_home, capsys
    ):
        _interrupted_session(monkeypatch, project_dir, fake_home)
        capsys.readouterr()
        code = app.invoke_guarded(["label", "--folder", "images", "-c", "cat,dog"])
        assert code == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "A labeling session for" in err
        assert "2 labeled, 1 skipped" in err
        assert "Re-run with --yes to resume it." in err

    def test_yes_resumes_where_it_left_off(self, monkeypatch, project_dir, fake_home):
        _interrupted_session(monkeypatch, project_dir, fake_home)
        fake = _serve(monkeypatch, None, Outcome.INTERRUPTED)
        app.invoke_guarded(["label", "--folder", "images", "-c", "cat,dog", "--yes"])
        controller = fake.controller
        assert controller.counts() == {"cat": 1, "dog": 1}
        assert controller.index == 3

    def test_a_corrupt_session_file_is_a_hard_error(
        self, monkeypatch, project_dir, fake_home, capsys
    ):
        stored = _interrupted_session(monkeypatch, project_dir, fake_home)
        stored.write_text("{not json", encoding="utf-8")
        capsys.readouterr()
        code = app.invoke_guarded(
            ["label", "--folder", "images", "-c", "cat,dog", "--yes"]
        )
        assert code == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "is corrupt" in err
        assert "Delete" in err

    def test_start_fresh_discards_the_session(
        self, monkeypatch, project_dir, fake_home, interactive
    ):
        _interrupted_session(monkeypatch, project_dir, fake_home)
        monkeypatch.setattr("typer.prompt", lambda *a, **k: "S")
        fake = _serve(monkeypatch, None, Outcome.INTERRUPTED)
        app.invoke_guarded(["label", "--folder", "images", "-c", "cat,dog"])
        assert fake.controller.session.entries == {}
        assert fake.controller.index == 0

    def test_a_different_class_list_offers_adopt_and_adopting_requeues(
        self, monkeypatch, project_dir, fake_home, interactive, capsys
    ):
        _interrupted_session(monkeypatch, project_dir, fake_home)
        capsys.readouterr()
        menus: list[str] = []

        def prompt(text: str, **kwargs: object) -> str:
            menus.append(text)
            return "A"

        monkeypatch.setattr("typer.prompt", prompt)
        fake = _serve(monkeypatch, None, Outcome.INTERRUPTED)
        app.invoke_guarded(["label", "--folder", "images", "-c", "cat,bird"])
        assert "[A] Adopt cat, bird" in menus[0]
        session = fake.controller.session
        assert session.classes == ["cat", "bird"]
        # The dog label departed and its image is back in the queue.
        assert fake.controller.counts() == {"cat": 1, "bird": 0}
        assert "1 label for removed classes returned to the queue." in (
            capsys.readouterr().out
        )

    def test_yes_never_adopts(self, monkeypatch, project_dir, fake_home):
        _interrupted_session(monkeypatch, project_dir, fake_home)
        fake = _serve(monkeypatch, None, Outcome.INTERRUPTED)
        app.invoke_guarded(["label", "--folder", "images", "-c", "cat,bird", "--yes"])
        assert fake.controller.session.classes == ["cat", "dog"]
