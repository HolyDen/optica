"""``optica fetch``, end to end through the real command.

Covers plan § "Input & Acquisition" as it reaches the terminal: *Class-count
validation* (the prompt where one can fire, the hard error where one cannot),
*Fetch sources* (Open Datasets with no key; Flickr requiring one; the soft cap
before the fetch begins), *Undefinable classes in auto modes* (the entry check
for CLIP), *Staging shapes* (``.partial`` resume belongs to fetch), and the
``--yes`` table rows for the class-name confirmation, the soft-cap warning and
the interrupted-fetch resume prompt.

Every request goes to an in-memory Open Images and image CDN; the autouse
``_no_network`` guard makes any real request fail the test.

``tests/unit/test_tree.py`` pairs this file with nothing: the command lives in
``cli/classify.py`` and its flag-surface tests are in ``test_classify.py``. The
end-to-end fetch tests are split out only because they carry their own fake
world.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from PIL import Image

from optica.cli.main import app
from optica.exceptions import ExitCode, OpticaCLIPLoadError
from optica.input import openimages as oi
from tests.unit.input.test_openimages import LABEL_MAP, FakeGCS, _dataset


def _jpeg_for(url: str) -> bytes:
    digest = hashlib.sha256(url.encode()).digest()
    buffer = io.BytesIO()
    Image.new("RGB", (160 + digest[0] % 50, 160), tuple(digest[1:4])).save(buffer, "JPEG")
    return buffer.getvalue()


class World:
    """Open Images on GCS, plus the Flickr CDN its URLs point at."""

    def __init__(self) -> None:
        labels, metadata, self.truth, _ = _dataset(images=300)
        self.gcs = FakeGCS(
            files={
                oi.LABEL_MAP_URL: LABEL_MAP,
                oi.LABELS_URL: labels,
                oi.METADATA_URL: metadata,
            }
        )
        self.image_requests: list[str] = []
        self.dead: set[str] = set()

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://storage.googleapis.com/"):
            return self.gcs.handler(request)
        self.image_requests.append(url)
        if url in self.dead:
            return httpx.Response(404)
        return httpx.Response(
            200, content=_jpeg_for(url), headers={"content-type": "image/jpeg"}
        )

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))


@pytest.fixture
def world(monkeypatch, fake_home, project_dir):
    world = World()
    monkeypatch.setattr("optica.cli.classify.make_client", world.client)
    # Small reads keep the fake files' request count sensible.
    original = oi.OpenImagesIndex.__init__

    def small(self, client, home=None, report=None, *, chunk_bytes=4096, stripes=4):
        original(self, client, home, report, chunk_bytes=chunk_bytes, stripes=stripes)

    monkeypatch.setattr(oi.OpenImagesIndex, "__init__", small)
    return world


@pytest.fixture
def interactive(monkeypatch):
    monkeypatch.setattr("optica.utils.prompts.is_interactive", lambda: True)
    monkeypatch.setattr("optica.cli.main.is_interactive", lambda: True)


def _staging(fake_home: Path) -> Path:
    return fake_home / ".optica" / "staging"


def _images(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.glob("0*.*"))


class TestUnattendedFetch:
    def test_yes_fetches_every_class_into_staging(self, world, fake_home, capsys):
        code = app.invoke_guarded(["fetch", "-c", "cat,dog", "-i", "5", "--yes"])
        captured = capsys.readouterr()
        assert code == ExitCode.SUCCESS, captured.err
        staging = _staging(fake_home)
        assert _images(staging / "cat") == [f"{i:04d}.jpg" for i in range(1, 6)]
        assert len(_images(staging / "dog")) == 5
        assert not list(staging.glob("*.partial"))
        assert "Mode: curate (default)" in captured.out
        assert "Source: Open Images" in captured.out
        assert "Fetch complete — 10 images across 2 classes" in captured.out

    def test_the_lock_is_released_afterwards(self, world, fake_home):
        from optica.utils.lockfile import lock_path

        app.invoke_guarded(["fetch", "-c", "cat,dog", "-i", "2", "--yes"])
        assert not lock_path().exists()

    def test_dead_urls_are_filled_past(self, world, fake_home, capsys):
        cat_ids = world.truth["/m/01yrx"]
        world.dead = {f"https://c1.staticflickr.com/1/{i}_z.jpg" for i in cat_ids}
        code = app.invoke_guarded(
            ["fetch", "-c", "cat,dog", "-i", "5", "--yes", "--verbose"]
        )
        captured = capsys.readouterr()
        assert code == ExitCode.SUCCESS, captured.err
        # Every Cat thumbnail is dead; the class still fills from the rows whose
        # thumbnail value is empty and so are fetched from OriginalURL.
        assert len(_images(_staging(fake_home) / "cat")) == 5
        dead_tried = [url for url in world.image_requests if url in world.dead]
        assert dead_tried
        assert f"Skipped {len(dead_tried)} dead links" in captured.out

    def test_without_a_terminal_and_without_yes_it_refuses_at_the_confirmation(
        self, world, fake_home, monkeypatch, capsys
    ):
        monkeypatch.setattr("optica.utils.prompts.is_interactive", lambda: False)
        code = app.invoke_guarded(["fetch", "-c", "cat,dog", "-i", "2"])
        assert code == ExitCode.ERROR
        assert "--yes" in capsys.readouterr().err
        assert world.image_requests == []


class TestEntryChecks:
    def test_missing_classes_without_a_terminal_is_the_plan_error(self, world, capsys):
        assert app.invoke_guarded(["fetch"]) == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "--classes is required for fetch — nothing to search for." in err
        assert "Example: optica fetch --classes cat,dog" in err

    def test_missing_classes_under_yes_errors_rather_than_prompting(
        self, world, interactive, monkeypatch
    ):
        monkeypatch.setattr("typer.prompt", lambda *a, **k: pytest.fail("prompted"))
        assert app.invoke_guarded(["fetch", "--yes"]) == ExitCode.ERROR

    def test_one_class_is_refused_before_any_request(self, world, capsys):
        assert app.invoke_guarded(["fetch", "-c", "cat", "--yes"]) == ExitCode.ERROR
        assert (
            "--classes requires at least 2 class names. Got: cat"
            in capsys.readouterr().err
        )
        assert world.gcs.requests == []

    def test_unknown_open_images_class_is_named_before_any_download(
        self, world, fake_home, capsys
    ):
        code = app.invoke_guarded(["fetch", "-c", "cat,unicorn", "--yes"])
        assert code == ExitCode.ERROR
        assert "Open Images has no class named: unicorn" in capsys.readouterr().err
        assert world.image_requests == []
        assert not (_staging(fake_home) / "cat").exists()

    def test_a_blocklisted_name_under_curate_checks_for_clip_at_entry(
        self, world, monkeypatch, capsys
    ):
        monkeypatch.setattr("optica.input.manager.clip_available", lambda: False)
        code = app.invoke_guarded(["fetch", "-c", "cat,defective", "--yes"])
        assert code == ExitCode.ERROR
        assert "CLIP filtering requires the clip extra" in capsys.readouterr().err
        assert world.gcs.requests == []

    def test_clip_mode_checks_the_threshold_and_the_extra_at_entry(
        self, world, monkeypatch, capsys
    ):
        monkeypatch.setattr("optica.input.manager.clip_available", lambda: False)
        code = app.invoke_guarded(["fetch", "-c", "cat,dog", "--mode", "clip", "--yes"])
        assert code == ExitCode.ERROR
        assert "CLIP filtering requires the clip extra" in capsys.readouterr().err

    def test_clip_threshold_zero_is_the_plan_error(self, world, capsys):
        code = app.invoke_guarded(
            [
                "fetch",
                "-c",
                "cat,dog",
                "--mode",
                "clip",
                "--clip-threshold",
                "0.0",
                "--yes",
            ]
        )
        assert code == ExitCode.ERROR
        err = capsys.readouterr().err
        # The plan's own wording, not config load's generic range error.
        assert "--clip-threshold 0.0 disables CLIP filtering entirely." in err
        assert "clip mode requires a threshold greater than 0.0." in err
        assert "To skip filtering, use --mode curate instead." in err

    def test_flickr_without_a_key_names_the_keyless_route(self, world, capsys):
        code = app.invoke_guarded(
            ["fetch", "-c", "cat,dog", "--source", "flickr", "--yes"]
        )
        assert code == ExitCode.ERROR
        err = capsys.readouterr().err
        assert "Flickr needs an API key" in err
        assert "--source open-datasets" in err

    def test_dry_run_touches_neither_network_nor_disk(self, world, fake_home, capsys):
        code = app.invoke_guarded(["fetch", "-c", "cat,dog", "--dry-run"])
        assert code == ExitCode.SUCCESS
        assert "nothing was fetched" in capsys.readouterr().out
        assert world.gcs.requests == []
        assert not _staging(fake_home).exists()


class TestPrompts:
    def test_absent_classes_prompts_then_confirms_then_fetches(
        self, world, fake_home, interactive, monkeypatch
    ):
        monkeypatch.setattr("typer.prompt", lambda *a, **k: "cat, dog")
        asked: list[str] = []

        def confirm(question, **kwargs):
            asked.append(question)
            return True

        monkeypatch.setattr("typer.confirm", confirm)
        assert app.invoke_guarded(["fetch", "-i", "2"]) == ExitCode.SUCCESS
        assert asked == ["Fetch these classes?"]
        assert len(_images(_staging(fake_home) / "dog")) == 2

    def test_declining_the_class_confirmation_exits_three_and_fetches_nothing(
        self, world, fake_home, interactive, monkeypatch
    ):
        monkeypatch.setattr("typer.confirm", lambda *a, **k: False)
        assert (
            app.invoke_guarded(["fetch", "-c", "cat,dog", "-i", "2"]) == ExitCode.ABORTED
        )
        assert world.image_requests == []

    def test_soft_cap_warns_and_yes_continues(
        self, world, fake_home, monkeypatch, capsys
    ):
        monkeypatch.setenv("OPTICA_MAX_OPEN_DATASETS_PER_CLASS", "3")
        code = app.invoke_guarded(["fetch", "-c", "cat,dog", "-i", "4", "--yes"])
        assert code == ExitCode.SUCCESS
        assert "courtesy limit of 3" in capsys.readouterr().err

    def test_soft_cap_declined_exits_three_before_fetching(
        self, world, interactive, monkeypatch
    ):
        monkeypatch.setenv("OPTICA_MAX_OPEN_DATASETS_PER_CLASS", "3")
        monkeypatch.setattr("typer.confirm", lambda *a, **k: False)
        assert (
            app.invoke_guarded(["fetch", "-c", "cat,dog", "-i", "4"]) == ExitCode.ABORTED
        )
        assert world.image_requests == []


class TestResume:
    def _interrupted(self, fake_home) -> None:
        partial = _staging(fake_home) / "cat.partial"
        partial.mkdir(parents=True)
        for i in (1, 2):
            (partial / f"{i:04d}.jpg").write_bytes(_jpeg_for(f"old-{i}"))

    def test_yes_resumes_an_interrupted_fetch(self, world, fake_home):
        self._interrupted(fake_home)
        assert app.invoke_guarded(["fetch", "-c", "cat,dog", "-i", "4", "--yes"]) == 0
        cat = _staging(fake_home) / "cat"
        assert _images(cat) == ["0001.jpg", "0002.jpg", "0003.jpg", "0004.jpg"]

    def test_declining_resume_starts_fresh_for_that_class(
        self, world, fake_home, interactive, monkeypatch
    ):
        self._interrupted(fake_home)
        answers = {"Resume it? (n starts fresh for these classes)": False}
        monkeypatch.setattr("typer.confirm", lambda q, **k: answers.get(q, True))
        assert app.invoke_guarded(["fetch", "-c", "cat,dog", "-i", "3"]) == 0
        cat = _staging(fake_home) / "cat"
        # The two old images were deleted with the .partial; numbering restarts.
        assert _images(cat) == ["0001.jpg", "0002.jpg", "0003.jpg"]
        assert _jpeg_for("old-1") not in {p.read_bytes() for p in cat.glob("0*.jpg")}

    def test_other_staged_classes_are_named(self, world, fake_home, capsys):
        other = _staging(fake_home) / "bird"
        other.mkdir(parents=True)
        (other / "0001.jpg").write_bytes(b"x")
        app.invoke_guarded(["fetch", "-c", "cat,dog", "-i", "2", "--yes"])
        assert "Staging also holds images for bird" in capsys.readouterr().err


# --- CLIP: clip mode, and the grouped path under curate ------------------------


def _score_of(data: bytes) -> float:
    """A deterministic pseudo-score in [0, 1) from an image's bytes."""
    return int.from_bytes(hashlib.md5(data).digest()[:2], "big") / 65536


class FakeScorer:
    """Stands in for the CLIP model: scores by bytes, records every call."""

    def __init__(self) -> None:
        self.score_fn: Callable[[str, bytes], float] = lambda folder, data: _score_of(
            data
        )
        self.interrupt_on: str | None = None
        self.loads: list[bool] = []
        # (class folder name, prompts, [(file name, bytes, score)])
        self.calls: list[tuple[str, list[str], list[tuple[str, bytes, float]]]] = []

    def score(self, images, prompts, *, on_image=None):
        folder = images[0].parent.name if images else ""
        if folder == self.interrupt_on:
            raise KeyboardInterrupt
        rows = []
        for path in images:
            data = path.read_bytes()
            rows.append((path.name, data, self.score_fn(folder, data)))
            if on_image is not None:
                on_image()
        self.calls.append((folder, list(prompts), rows))
        return [score for _, _, score in rows]


@pytest.fixture
def clip_installed(monkeypatch):
    """The clip extra is present — constructed, so CI (which never has it) agrees."""
    monkeypatch.setattr("optica.input.manager.clip_available", lambda: True)


@pytest.fixture
def scorer(monkeypatch, clip_installed):
    fake = FakeScorer()

    def load_clip(*, report, device=None, quiet=False):
        fake.loads.append(quiet)
        return fake

    monkeypatch.setattr("optica.input.clip.load_clip", load_clip)
    return fake


def _expected_kept(rows, threshold: float, keep: int) -> set[bytes]:
    passing = sorted(
        (row for row in rows if row[2] >= threshold), key=lambda r: (-r[2], r[0])
    )
    return {data for _, data, _ in passing[:keep]}


def _dataset_bytes(folder: Path) -> set[bytes]:
    return {p.read_bytes() for p in folder.iterdir() if p.is_file()}


_CLIP = ["fetch", "-c", "cat,dog", "--mode", "clip", "--yes"]


class TestClipMode:
    """Plan § "CLIP Adapter (clip mode)", end to end with a fake model."""

    def test_fetches_twice_the_target_and_keeps_the_best_passing(
        self, world, fake_home, project_dir, scorer, capsys
    ):
        code = app.invoke_guarded([*_CLIP, "-i", "5"])
        captured = capsys.readouterr()
        assert code == ExitCode.SUCCESS, captured.err
        assert [call[0] for call in scorer.calls] == ["cat", "dog"]
        for name, prompts, rows in scorer.calls:
            assert prompts == [f"a photo of a {name}"]
            assert len(rows) == 10  # images_per_class x 2
            kept = _dataset_bytes(project_dir / "dataset" / name)
            assert kept == _expected_kept(rows, 0.25, 5)
            passed = sum(1 for row in rows if row[2] >= 0.25)
            assert f"{name}: 10 scored, {passed} at or above 0.25, 5 kept" in captured.out
        # Consumed staging is gone; nothing partial is left beside the dataset.
        assert not (_staging(fake_home) / "cat").exists()
        assert not (project_dir / ".dataset.partial").exists()
        assert "Fetch complete — 10 images kept across 2 classes" in captured.out
        assert scorer.loads == [False]

    def test_a_shortfall_is_reported_and_is_not_an_error(
        self, world, project_dir, scorer, capsys
    ):
        scorer.score_fn = lambda folder, data: 0.0 if folder == "dog" else 0.9
        code = app.invoke_guarded([*_CLIP, "-i", "5"])
        captured = capsys.readouterr()
        assert code == ExitCode.SUCCESS, captured.err
        dog = project_dir / "dataset" / "dog"
        assert dog.is_dir()  # present by name, so training's floor check names it
        assert not any(dog.iterdir())
        assert len(list((project_dir / "dataset" / "cat").iterdir())) == 5
        assert "Fewer images than requested passed CLIP filtering" in captured.err
        assert "dog kept 0 of 5" in captured.err

    def test_a_populated_dataset_refuses_unattended_before_anything_runs(
        self, world, project_dir, scorer, monkeypatch, capsys
    ):
        old = project_dir / "dataset" / "bird"
        old.mkdir(parents=True)
        (old / "keep.jpg").write_bytes(b"old")
        monkeypatch.setattr("optica.utils.prompts.is_interactive", lambda: False)
        assert app.invoke_guarded([*_CLIP, "-i", "5"]) == ExitCode.ERROR
        assert "--overwrite" in capsys.readouterr().err
        assert world.gcs.requests == []
        assert world.image_requests == []
        assert scorer.loads == []
        assert (old / "keep.jpg").read_bytes() == b"old"

    def test_overwrite_replaces_rather_than_merges(self, world, project_dir, scorer):
        old = project_dir / "dataset" / "bird"
        old.mkdir(parents=True)
        (old / "keep.jpg").write_bytes(b"old")
        code = app.invoke_guarded([*_CLIP, "-i", "3", "--overwrite"])
        assert code == ExitCode.SUCCESS
        names = sorted(p.name for p in (project_dir / "dataset").iterdir())
        assert names == ["cat", "dog"]

    def test_an_interrupt_while_scoring_leaves_the_old_dataset_and_the_staging(
        self, world, fake_home, project_dir, scorer
    ):
        old = project_dir / "dataset" / "bird"
        old.mkdir(parents=True)
        (old / "keep.jpg").write_bytes(b"old")
        scorer.interrupt_on = "dog"
        code = app.invoke_guarded([*_CLIP, "-i", "3", "--overwrite"])
        assert code == ExitCode.INTERRUPTED
        assert (old / "keep.jpg").read_bytes() == b"old"
        assert not (project_dir / "dataset" / "cat").exists()
        assert not (project_dir / ".dataset.partial").exists()
        # The fetched candidates survive for a re-run.
        assert len(_images(_staging(fake_home) / "cat")) == 6
        assert len(_images(_staging(fake_home) / "dog")) == 6

    def test_the_model_loads_before_any_image_is_fetched(
        self, world, project_dir, clip_installed, monkeypatch, capsys
    ):
        def broken(**kwargs):
            raise OpticaCLIPLoadError("The CLIP weights failed to load.")

        monkeypatch.setattr("optica.input.clip.load_clip", broken)
        assert app.invoke_guarded([*_CLIP, "-i", "3"]) == ExitCode.ERROR
        assert "The CLIP weights failed to load." in capsys.readouterr().err
        assert world.image_requests == []

    def test_dry_run_names_the_dataset_and_the_over_fetch(
        self, world, fake_home, project_dir, scorer, capsys
    ):
        code = app.invoke_guarded(
            ["fetch", "-c", "cat,dog", "-i", "5", "--mode", "clip", "--dry-run"]
        )
        out = capsys.readouterr().out
        assert code == ExitCode.SUCCESS
        assert "Candidates per class: 5 x 2, filtered at clip_threshold 0.25" in out
        assert "Destination: dataset" in out
        assert scorer.loads == []
        assert world.image_requests == []


class TestGroupedUnderCurate:
    """Plan § "Undefinable classes in auto modes": CLIP runs after the fetch."""

    def test_a_grouped_class_is_scored_against_every_sub_term_in_staging(
        self, world, fake_home, project_dir, scorer, interactive, monkeypatch, capsys
    ):
        monkeypatch.setattr("typer.prompt", lambda *a, **k: "cat,dog")
        monkeypatch.setattr("typer.confirm", lambda *a, **k: True)
        code = app.invoke_guarded(["fetch", "-c", "screwdriver,defective", "-i", "20"])
        captured = capsys.readouterr()
        assert code == ExitCode.SUCCESS, captured.err
        # Only the grouped class is scored, and against both sub-terms.
        [(name, prompts, rows)] = scorer.calls
        assert (name, prompts) == ("defective", ["a photo of a cat", "a photo of a dog"])
        assert len(rows) == 20  # 10 per sub-term: no over-fetch outside clip mode
        folder = _staging(fake_home) / "defective"
        remaining = {p.read_bytes() for p in folder.glob("0*")}
        assert remaining == {data for _, data, score in rows if score >= 0.25}
        assert 0 < len(remaining) < 20  # the filter did something, both ways
        assert not (project_dir / "dataset").exists()
        passed = len(remaining)
        assert (
            f"defective: 20 scored, {passed} at or above 0.25, {passed} kept"
            in captured.out
        )
        total = passed + len(_images(_staging(fake_home) / "screwdriver"))
        assert f"Fetch complete — {total} images across 2 classes" in captured.out

    def test_no_grouped_class_means_no_model_load(self, world, scorer):
        assert app.invoke_guarded(["fetch", "-c", "cat,dog", "-i", "2", "--yes"]) == 0
        assert scorer.loads == []
