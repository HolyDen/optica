"""Shared fixtures.

Synthetic ``pretrained=False`` fixtures arrived with pass 4: ``image_dataset``
writes a small ``ImageFolder``-shaped dataset with Pillow alone, and
``timm_model`` builds a backbone with ``pretrained=False`` — no weights are ever
downloaded, and the network guard below would fail a test that tried. CI never
installs the torch stack, so anything using ``timm_model`` carries
``@pytest.mark.slow`` and runs locally only.

What lives here in pass 1 is the isolation every later pass needs: a home
directory and a working directory that are never the developer's own, since
Optica writes ``~/.optica/`` and ``./dataset/``.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

# The tests assert what Optica prints to a captured, non-terminal stream: plain
# text. Rich decides whether to style output from the environment, and two
# variables override that decision — measured against Rich 15.0.0, FORCE_COLOR
# and TTY_COMPATIBLE each fail the same 31 tests when set, and nothing else Rich
# reads does. Honouring them is correct *product* behaviour; asserting their
# absence would be the test asserting an ambient fact, the failure mode that made
# pass 1's first CI run fail on every runner. So the harness removes them.
#
# This must run before `optica.utils.logging` is imported: its consoles are
# module-level, and Rich fixes the colour system once, when a console is built.
# Child processes spawned by integration tests inherit the scrubbed environment.
for _ambient in ("FORCE_COLOR", "TTY_COMPATIBLE"):
    os.environ.pop(_ambient, None)

import optica.utils.logging as olog  # noqa: E402 - after the scrub, deliberately


@pytest.fixture(autouse=True)
def _reset_verbosity() -> Iterator[None]:
    """Keep one test's ``--verbose`` out of the next test's output level."""
    olog.set_verbosity(olog.Verbosity.NORMAL)
    yield
    olog.set_verbosity(olog.Verbosity.NORMAL)


@pytest.fixture
def clip_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ``optica[clip]`` extra is present — constructed, never inherited.

    Here rather than in one test module because the machine's answer differs
    from CI's: the build ``.venv`` has the extra and no CI runner does, so a
    test that reads ``clip_available()`` off the environment asserts a
    different thing on each. Pass 4 met this and fixed it with a fixture local
    to ``tests/unit/cli/test_fetch_command.py``; pass 5 met it again in
    ``tests/unit/api/``, which could not see that fixture because a
    module-level fixture is not shared. One definition, in ``conftest.py``, is
    what stops it recurring a third time.
    """
    monkeypatch.setattr("optica.input.manager.clip_available", lambda: True)


@pytest.fixture
def clip_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ``optica[clip]`` extra is missing — the state every CI runner is in."""
    monkeypatch.setattr("optica.input.manager.clip_available", lambda: False)


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``Path.home()`` at a temporary directory.

    ``~/.optica/`` holds the global config, the lock file and staging, so a test
    that touches any of them must never see the developer's real home.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


@pytest.fixture
def project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Chdir into an empty project directory for the duration of a test."""
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    return project


@pytest.fixture(autouse=True)
def _clear_optica_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop any ``OPTICA_*`` variable the developer happens to have exported.

    Env vars sit in the config priority chain, so one left in the shell would
    change a test's resolved config without appearing anywhere in the test.
    """
    for key in list(os.environ):
        if key.startswith("OPTICA_") or key == "FLICKR_API_KEY":
            monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any real HTTP request in a test fail loudly.

    From pass 2 the fetch path talks to Open Images and Flickr. A test that
    reached them by accident would be slow, flaky, and a load on public
    infrastructure, and would pass or fail with the network rather than the code.
    ``httpx.MockTransport`` is unaffected, so tests that need HTTP build a client
    over one.
    """
    real = httpx.HTTPTransport.handle_request

    def refuse(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        # From pass 3 the integration tests talk to Optica's own browser server
        # on the loopback address. That is not the network this guard protects.
        if request.url.host in _LOOPBACK:
            return real(self, request)
        raise RuntimeError(f"test attempted real network access: {request.url}")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)


_LOOPBACK = frozenset({"127.0.0.1", "localhost"})


@pytest.fixture(autouse=True)
def _no_real_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any attempt to launch a real web browser fail the test at once.

    From pass 3, ``optica label`` and ``optica curate`` start a server and open
    the user's browser. A test that reached that path without a stand-in opened
    a tab on the developer's desktop and then waited on a 60-minute idle timer —
    it happened, once, while pass 3 was being built. Raising here also ends the
    server the test started, since ``serve`` stops it on any exception.
    """
    import webbrowser

    def refuse(url: str, *args: object, **kwargs: object) -> bool:
        raise RuntimeError(f"test attempted to open a real browser: {url}")

    monkeypatch.setattr(webbrowser, "open", refuse)


@pytest.fixture
def image_dataset(tmp_path: Path) -> Callable[..., Path]:
    """Write ``root/<class>/<n>.png`` for each class. No torch needed.

    Each image is distinct (so deduplication keeps it) and each class has its
    own colour family (so a model can learn the split in an epoch or two).
    """
    from PIL import Image

    palette = [(220, 40, 40), (40, 40, 220), (40, 200, 40), (200, 200, 40)]

    def make(counts: dict[str, int], root: Path | None = None, size: int = 64) -> Path:
        root = root or tmp_path / "dataset"
        for index, (name, count) in enumerate(counts.items()):
            folder = root / name
            folder.mkdir(parents=True, exist_ok=True)
            base = palette[index % len(palette)]
            for i in range(count):
                shade = (i * 7) % 30
                colour = tuple(max(0, min(255, c + shade)) for c in base)
                image = Image.new("RGB", (size, size), colour)
                image.putpixel((i % size, (i * 3) % size), (255 - shade, shade, 128))
                image.save(folder / f"{i:04d}.png")
        return root

    return make


@pytest.fixture
def timm_model() -> Callable[..., Any]:
    """Build a timm backbone with ``pretrained=False``. Slow tests only."""

    def make(name: str, **kwargs: Any) -> Any:
        import timm

        return timm.create_model(name, pretrained=False, **kwargs)

    return make
