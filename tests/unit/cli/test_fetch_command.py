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
from pathlib import Path

import httpx
import pytest
from PIL import Image

from optica.cli.main import app
from optica.exceptions import ExitCode
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
