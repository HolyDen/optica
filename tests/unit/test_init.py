"""The package's public surface.

Mirrors ``src/optica/__init__.py``. Pass 5 added the Simple API, so the surface
is the flat aliases, the `optica.classify` namespace, `Classifier`, the config
objects and the result types — plus ``__version__``.

Covers plan § "Python API" → *Import-time contract*: the full surface is bound
eagerly, no extra is imported, and nothing resolves through ``__getattr__``.
"""

from __future__ import annotations

import subprocess
import sys
from importlib import metadata
from pathlib import Path

import optica


class TestVersion:
    def test_it_matches_the_installed_distribution(self):
        assert optica.__version__ == metadata.version("optica")

    def test_it_is_not_a_literal_in_the_source(self):
        # `pyproject.toml` is the single source of truth for the version; a
        # literal here would be a second one, free to drift.
        source = Path(optica.__file__).read_text(encoding="utf-8")
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
        assert optica.__all__ == [
            "Classifier",
            "EpochRecord",
            "ExportConfig",
            "ExportResult",
            "FetchConfig",
            "FetchResult",
            "OpticaResult",
            "OpticaWarning",
            "RunResult",
            "Status",
            "TrainConfig",
            "TrainResult",
            "WarningCode",
            "WarningEntry",
            "__version__",
            "classify",
            "curate",
            "export",
            "fetch",
            "label",
            "run",
            "train",
        ]

    def test_importing_the_package_imports_no_extra_at_all(self):
        # The lazy boundary is at the dependency level, never the symbol level.
        probe = (
            "import optica, sys; "
            "print([m for m in ('torch','torchvision','timm','sklearn',"
            "'open_clip','fastapi','uvicorn') if m in sys.modules])"
        )
        result = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, text=True, check=True
        )
        assert result.stdout.strip() == "[]"
