"""``optica curate``, from auto-fetch staging to ``dataset/``.

Covers plan § "Labeling & Curation" → *Deletion, staging, and interruption*
(mass rejection after Confirm: two triggers, F / C / A, C's own confirmation
defaulting to N, ``--yes`` picking C then Y; auto-fetched images deleted when
rejected; the curation resume prompt), *Staging shapes* (``curation.json``:
resume or start fresh; standalone curate reports an incomplete fetch and
proceeds), *Terminal-side completion for browser steps* (``✓``/``✗`` and exit
codes 0, 3, 130); § "Input & Acquisition" → *`dataset/` conflict* (checked at
command start; replace, never merge; ``--overwrite`` the only unattended route)
and *Post-deduplication floor re-check*; ``--classes`` warned and ignored.

Curate has no manifest; the session file is ``curation.json`` and nothing else.

``serve`` is replaced by a stand-in that drives the real page controller the
command built, the way the page's requests would.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from PIL import Image

from optica.cli.main import app
from optica.exceptions import ExitCode
from optica.input.fetch import ClassFetchReport
from optica.server.app import BrowserSession, Outcome
from optica.server.curation import CurationController

Drive = Callable[[CurationController], None]


@pytest.fixture(autouse=True)
def _isolated(fake_home, project_dir, monkeypatch):
    # The extra's absence (as in CI) must not stop the command before the part
    # under test; the real check is tested with `optica label`.
    monkeypatch.setattr("optica.cli.classify.load_web", lambda: None)
    return project_dir


def _staging(home: Path) -> Path:
    return home / ".optica" / "staging"


def _stage(home: Path, name: str, count: int, *, start: int = 1) -> list[Path]:
    folder = _staging(home) / name
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(start, start + count):
        path = folder / f"{i:04d}.jpg"
        shade = (sum(map(ord, name)) + i * 29) % 256
        Image.new("RGB", (140, 140), (shade, (i * 71) % 256, (i * 13) % 256)).save(
            path, "JPEG"
        )
        paths.append(path)
    return paths


class FakeServe:
    """Stands in for ``serve``, once per opening of the page."""

    def __init__(
        self, drives: list[Drive | None], outcome: Outcome = Outcome.FINISHED
    ) -> None:
        self.drives = list(drives)
        self.outcome = outcome
        self.controllers: list[CurationController] = []

    def __call__(self, browser: BrowserSession, **kwargs: object) -> Outcome:
        controller = browser.controller
        assert isinstance(controller, CurationController)
        self.controllers.append(controller)
        drive = self.drives.pop(0) if self.drives else None
        if drive is not None:
            drive(controller)
        if self.outcome is Outcome.FINISHED:
            assert controller.confirm()["status"] == "finished"
        return self.outcome


def _serve(monkeypatch, *drives: Drive | None, outcome=Outcome.FINISHED) -> FakeServe:
    fake = FakeServe(list(drives), outcome)
    monkeypatch.setattr("optica.cli.classify.serve", fake)
    return fake


def _deselect(name: str, count: int) -> Drive:
    def drive(controller: CurationController) -> None:
        index = controller.names.index(name)
        for image in range(count):
            controller.toggle(index, image, selected=False)

    return drive


def _counts(root: Path) -> dict[str, int]:
    return {d.name: len(list(d.iterdir())) for d in sorted(root.iterdir()) if d.is_dir()}


@pytest.fixture
def interactive(monkeypatch):
    monkeypatch.setattr("optica.utils.prompts.is_interactive", lambda: True)


# ---------------------------------------------------------------- confirm


class TestConfirm:
    def test_the_selection_is_written_and_rejected_images_leave_staging(
        self, monkeypatch, fake_home, project_dir, capsys
    ):
        _stage(fake_home, "cat", 12)
        _stage(fake_home, "dog", 12)
        _serve(monkeypatch, _deselect("cat", 2))
        assert app.invoke_guarded(["curate"]) == ExitCode.SUCCESS
        out = capsys.readouterr().out
        assert _counts(project_dir / "dataset") == {"cat": 10, "dog": 12}
        assert "Curation complete — 22 images selected across 2 classes" in out
        # Rejected auto-fetched images are deleted; selected ones stay staged.
        assert len(list((_staging(fake_home) / "cat").glob("*.jpg"))) == 10
        assert not (_staging(fake_home) / "curation.json").exists()
        assert not (project_dir / ".dataset.partial").exists()

    def test_classes_is_warned_and_ignored(self, monkeypatch, fake_home, capsys):
        _stage(fake_home, "cat", 12)
        _stage(fake_home, "dog", 12)
        fake = _serve(monkeypatch, None)
        assert app.invoke_guarded(["curate", "-c", "bird"]) == ExitCode.SUCCESS
        assert "--classes is ignored by optica curate." in capsys.readouterr().err
        assert fake.controllers[0].names == ["cat", "dog"]

    def test_the_headline_counts_staged_images(self, monkeypatch, fake_home):
        _stage(fake_home, "cat", 12)
        _stage(fake_home, "dog", 11)
        seen: dict[str, object] = {}

        def spy(browser: BrowserSession, **kwargs: object) -> Outcome:
            seen.update(kwargs)
            return Outcome.INTERRUPTED

        monkeypatch.setattr("optica.cli.classify.serve", spy)
        app.invoke_guarded(["curate"])
        assert seen["headline"] == "Curating 23 images across 2 classes"

    def test_a_duplicate_that_drops_a_class_below_five_keeps_everything(
        self, monkeypatch, fake_home, project_dir, capsys
    ):
        cats = _stage(fake_home, "cat", 12)
        _stage(fake_home, "dog", 12)
        cats[1].write_bytes(cats[0].read_bytes())
        # Selected: 0001-0005, two of them byte-identical → 4 unique.
        def keep_first_five(controller: CurationController) -> None:
            for image in range(5, 12):
                controller.toggle(0, image, selected=False)

        _serve(monkeypatch, keep_first_five)
        code = app.invoke_guarded(["curate", "--yes"])
        assert code == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "cat fell below the 5-image minimum after duplicate removal." in err
        assert "cat: 5 images → 4 unique (1 duplicate removed)" in err
        assert not (project_dir / "dataset").exists()
        assert not (project_dir / ".dataset.partial").exists()
        assert len(list((_staging(fake_home) / "cat").glob("*.jpg"))) == 12
        assert (_staging(fake_home) / "curation.json").exists()

    def test_a_class_already_below_five_by_choice_is_not_a_floor_error(
        self, monkeypatch, fake_home, project_dir
    ):
        _stage(fake_home, "cat", 12)
        _stage(fake_home, "dog", 12)
        _serve(monkeypatch, _deselect("cat", 9))
        # 3 selected trips mass rejection; --yes continues past it.
        assert app.invoke_guarded(["curate", "--yes"]) == ExitCode.SUCCESS
        assert _counts(project_dir / "dataset") == {"cat": 3, "dog": 12}


class TestIncomplete:
    def test_timeout_exits_three_and_keeps_selections(
        self, monkeypatch, fake_home, project_dir, capsys
    ):
        _stage(fake_home, "cat", 12)
        _stage(fake_home, "dog", 12)
        _serve(monkeypatch, _deselect("dog", 1), outcome=Outcome.TIMED_OUT)
        assert app.invoke_guarded(["curate"]) == ExitCode.ABORTED
        err = capsys.readouterr().err
        assert "Curation incomplete — the session closed after 60 minutes" in err
        stored = json.loads((_staging(fake_home) / "curation.json").read_text("utf-8"))
        assert len(stored["deselected"]["dog"]) == 1
        assert not (project_dir / "dataset").exists()
        assert len(list((_staging(fake_home) / "dog").glob("*.jpg"))) == 12

    def test_ctrl_c_exits_130(self, monkeypatch, fake_home, capsys):
        _stage(fake_home, "cat", 12)
        _stage(fake_home, "dog", 12)
        _serve(monkeypatch, None, outcome=Outcome.INTERRUPTED)
        assert app.invoke_guarded(["curate"]) == ExitCode.INTERRUPTED
        assert "Curation incomplete — interrupted; selections are saved." in (
            capsys.readouterr().err
        )

    def test_nothing_staged_is_a_precondition_error(self, monkeypatch, capsys):
        fake = _serve(monkeypatch, None)
        assert app.invoke_guarded(["curate"]) == ExitCode.ERROR
        assert "No fetched images are staged for curation." in capsys.readouterr().err
        assert fake.controllers == []


# ------------------------------------------------------------ mass rejection


class TestMassRejection:
    def _two_classes(self, home: Path) -> None:
        _stage(home, "cat", 12)
        _stage(home, "dog", 12)

    def test_each_trigger_prints_its_own_message(
        self, monkeypatch, fake_home, interactive, capsys
    ):
        self._two_classes(fake_home)
        _serve(monkeypatch, _deselect("cat", 9))
        monkeypatch.setattr("typer.prompt", lambda *a, **k: "A")
        assert app.invoke_guarded(["curate"]) == ExitCode.ABORTED
        err = capsys.readouterr().err
        assert "cat: only 3 of 12 fetched images selected (25%, below 30%)" in err
        assert "cat: only 3 images selected (fewer than 10)" in err

    def test_abort_exits_three_and_preserves_staging(
        self, monkeypatch, fake_home, project_dir, interactive, capsys
    ):
        self._two_classes(fake_home)
        _serve(monkeypatch, _deselect("cat", 9))
        menus: list[str] = []

        def prompt(text: str, **kwargs: object) -> str:
            menus.append(text)
            return "A"

        monkeypatch.setattr("typer.prompt", prompt)
        assert app.invoke_guarded(["curate"]) == ExitCode.ABORTED
        assert "[F] Fetch more   [C] Continue anyway   [A] Abort" in menus[0]
        assert "Curation incomplete — aborted" in capsys.readouterr().err
        assert not (project_dir / "dataset").exists()
        assert len(list((_staging(fake_home) / "cat").glob("*.jpg"))) == 12
        assert (_staging(fake_home) / "curation.json").exists()

    def test_c_asks_again_defaulting_to_n_and_n_returns_to_the_prompt(
        self, monkeypatch, fake_home, project_dir, interactive
    ):
        self._two_classes(fake_home)
        _serve(monkeypatch, _deselect("cat", 9))
        letters = iter(["C", "C"])
        monkeypatch.setattr("typer.prompt", lambda *a, **k: next(letters))
        asked: list[tuple[str, bool]] = []
        answers = iter([False, True])

        def confirm(question: str, default: bool = True, **kwargs: object) -> bool:
            asked.append((question, default))
            return next(answers)

        monkeypatch.setattr("typer.confirm", confirm)
        assert app.invoke_guarded(["curate"]) == ExitCode.SUCCESS
        assert asked == [
            ("Continue with the current selection?", False),
            ("Continue with the current selection?", False),
        ]
        assert _counts(project_dir / "dataset") == {"cat": 3, "dog": 12}

    def test_yes_picks_continue_then_confirms(self, monkeypatch, fake_home, project_dir):
        self._two_classes(fake_home)
        _serve(monkeypatch, _deselect("cat", 9))
        monkeypatch.setattr("typer.prompt", lambda *a, **k: pytest.fail("prompted"))
        monkeypatch.setattr("typer.confirm", lambda *a, **k: pytest.fail("prompted"))
        assert app.invoke_guarded(["curate", "--yes"]) == ExitCode.SUCCESS
        assert _counts(project_dir / "dataset") == {"cat": 3, "dog": 12}

    def test_unattended_without_yes_is_a_hard_error(self, monkeypatch, fake_home, capsys):
        self._two_classes(fake_home)
        _serve(monkeypatch, _deselect("cat", 9))
        assert app.invoke_guarded(["curate"]) == ExitCode.ERROR
        assert "Re-run with --yes to continue with the selection." in (
            capsys.readouterr().err
        )

    def test_f_fetches_the_shortfall_and_reopens_curation(
        self, monkeypatch, fake_home, project_dir, interactive
    ):
        self._two_classes(fake_home)
        requested: list[dict[str, int]] = []

        def fake_fetch(config, requests, **kwargs):
            requested.append(dict(requests))
            reports = []
            for name, count in requests.items():
                _stage(fake_home, name, count, start=13)
                reports.append(ClassFetchReport(name, count, delivered=count))
            return reports

        monkeypatch.setattr("optica.cli.classify._run_fetch_more", fake_fetch)
        fake = _serve(monkeypatch, _deselect("cat", 9), None)
        monkeypatch.setattr("typer.prompt", lambda *a, **k: "F")
        assert app.invoke_guarded(["curate"]) == ExitCode.SUCCESS
        # 3 selected, images_per_class 50: request 47. Then curation reopens.
        assert requested == [{"cat": 47}]
        assert len(fake.controllers) == 2
        assert fake.controllers[1].view.fetched == {"cat": 59, "dog": 12}
        assert _counts(project_dir / "dataset") == {"cat": 50, "dog": 12}

    def test_a_fetch_that_yields_nothing_returns_without_f(
        self, monkeypatch, fake_home, interactive, capsys
    ):
        self._two_classes(fake_home)
        monkeypatch.setattr(
            "optica.cli.classify._run_fetch_more",
            lambda config, requests, **k: [ClassFetchReport("cat", 47)],
        )
        _serve(monkeypatch, _deselect("cat", 9))
        menus: list[str] = []
        letters = iter(["F", "A"])

        def prompt(text: str, **kwargs: object) -> str:
            menus.append(text)
            return next(letters)

        monkeypatch.setattr("typer.prompt", prompt)
        assert app.invoke_guarded(["curate"]) == ExitCode.ABORTED
        assert "[F]" in menus[0]
        assert "[F]" not in menus[1]
        assert "The source had no more images for those classes." in (
            capsys.readouterr().err
        )


# ----------------------------------------------------------------- session


class TestResume:
    def _interrupted(self, monkeypatch, home: Path) -> None:
        _stage(home, "cat", 12)
        _stage(home, "dog", 12)
        _serve(monkeypatch, _deselect("dog", 2), outcome=Outcome.INTERRUPTED)
        app.invoke_guarded(["curate"])

    def test_yes_resumes_the_deselections(self, monkeypatch, fake_home):
        self._interrupted(monkeypatch, fake_home)
        fake = _serve(monkeypatch, None, outcome=Outcome.INTERRUPTED)
        app.invoke_guarded(["curate", "--yes"])
        assert fake.controllers[0].selected() == {"cat": 12, "dog": 10}

    def test_unattended_without_yes_is_a_curation_error(
        self, monkeypatch, fake_home, capsys
    ):
        self._interrupted(monkeypatch, fake_home)
        capsys.readouterr()
        assert app.invoke_guarded(["curate"]) == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "A curation session was found: 2 images deselected" in err
        assert "Re-run with --yes to resume it." in err

    def test_start_fresh_discards_selections_not_images(
        self, monkeypatch, fake_home, interactive
    ):
        self._interrupted(monkeypatch, fake_home)
        monkeypatch.setattr("typer.prompt", lambda *a, **k: "S")
        fake = _serve(monkeypatch, None, outcome=Outcome.INTERRUPTED)
        app.invoke_guarded(["curate"])
        assert fake.controllers[0].selected() == {"cat": 12, "dog": 12}
        assert len(list((_staging(fake_home) / "dog").glob("*.jpg"))) == 12

    def test_a_corrupt_curation_json_is_a_hard_error(
        self, monkeypatch, fake_home, capsys
    ):
        self._interrupted(monkeypatch, fake_home)
        (_staging(fake_home) / "curation.json").write_text("[", encoding="utf-8")
        capsys.readouterr()
        assert app.invoke_guarded(["curate", "--yes"]) == ExitCode.ERROR
        assert "curation session file" in capsys.readouterr().err


# ---------------------------------------------------------------- dataset/


class TestOverwrite:
    def _populated(self, project_dir: Path) -> Path:
        folder = project_dir / "dataset" / "old"
        folder.mkdir(parents=True)
        (folder / "a.jpg").write_bytes(b"old")
        return project_dir / "dataset"

    def test_unattended_is_refused_before_the_browser(
        self, monkeypatch, fake_home, project_dir, capsys
    ):
        dataset = self._populated(project_dir)
        _stage(fake_home, "cat", 12)
        _stage(fake_home, "dog", 12)
        fake = _serve(monkeypatch, None)
        assert app.invoke_guarded(["curate", "--yes"]) == ExitCode.ERROR
        assert "already exists and is not empty" in capsys.readouterr().err
        assert fake.controllers == []
        assert (dataset / "old" / "a.jpg").exists()

    def test_the_prompt_names_curation_as_the_replacement(
        self, monkeypatch, fake_home, project_dir, interactive, capsys
    ):
        self._populated(project_dir)
        _stage(fake_home, "cat", 12)
        _stage(fake_home, "dog", 12)
        _serve(monkeypatch, None)
        monkeypatch.setattr("typer.confirm", lambda *a, **k: False)
        assert app.invoke_guarded(["curate"]) == ExitCode.ABORTED
        err = capsys.readouterr().err
        assert (
            "dataset/ already exists and will be replaced with new images selected "
            "in curation:"
        ) in err
        assert "optica curate --dataset ./new-dataset" in err

    def test_overwrite_replaces_rather_than_merges(
        self, monkeypatch, fake_home, project_dir
    ):
        dataset = self._populated(project_dir)
        _stage(fake_home, "cat", 12)
        _stage(fake_home, "dog", 12)
        _serve(monkeypatch, None)
        assert app.invoke_guarded(["curate", "--overwrite"]) == ExitCode.SUCCESS
        assert _counts(dataset) == {"cat": 12, "dog": 12}
