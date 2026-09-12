"""Shared fixtures.

Synthetic ``pretrained=False`` model fixtures arrive with pass 4, when
``training/`` is built; CI never installs the torch stack, so anything importing
torch carries ``@pytest.mark.slow`` and runs locally only.

What lives here in pass 1 is the isolation every later pass needs: a home
directory and a working directory that are never the developer's own, since
Optica writes ``~/.optica/`` and ``./dataset/``.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from optica.utils import logging as olog


@pytest.fixture(autouse=True)
def _reset_verbosity() -> Iterator[None]:
    """Keep one test's ``--verbose`` out of the next test's output level."""
    olog.set_verbosity(olog.Verbosity.NORMAL)
    yield
    olog.set_verbosity(olog.Verbosity.NORMAL)


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
