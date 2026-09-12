"""The package's public surface.

Mirrors ``src/optica/__init__.py``. Until pass 5 adds the Simple API, that
surface is ``__version__`` alone.
"""

from __future__ import annotations

import subprocess
import sys
from importlib import metadata

import optica


class TestVersion:
    def test_it_matches_the_installed_distribution(self):
        assert optica.__version__ == metadata.version("optica")

    def test_it_is_not_a_literal_in_the_source(self):
        # `pyproject.toml` is the single source of truth for the version; a
        # literal here would be a second one, free to drift.
        probe = "import optica, inspect; print(inspect.getsource(optica))"
        source = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert optica.__version__ not in source

    def test_it_is_what_the_cli_prints(self, capsys):
        from optica.cli.main import app

        app.invoke_guarded(["--version"])
        assert optica.__version__ in capsys.readouterr().out

    def test_importing_the_package_does_not_import_torch(self):
        # `pip install optica` followed by `optica --version` must work with no
        # torch present, which starts with the package import itself.
        result = subprocess.run(
            [sys.executable, "-c", "import optica, sys; print('torch' in sys.modules)"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == "False"

    def test_the_public_surface_is_declared(self):
        assert optica.__all__ == ["__version__"]
