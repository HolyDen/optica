"""``optica.api`` — what the plan's own examples import from it.

Covers plan § "Python API" → *Classifier (Tier 5)* (the example's
``from optica.api import FetchConfig, TrainConfig, ExportConfig`` line) and the
import-time contract's *full public surface bound eagerly*.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

import optica
from optica import api


class TestSurface:
    def test_the_config_objects_the_tier_5_example_imports(self):
        from optica.api import ExportConfig, FetchConfig, TrainConfig

        assert (FetchConfig, TrainConfig, ExportConfig) == (
            api.FetchConfig,
            api.TrainConfig,
            api.ExportConfig,
        )

    def test_the_result_types_a_caller_reads_off_a_return_value(self):
        for name in (
            "OpticaResult",
            "FetchResult",
            "TrainResult",
            "ExportResult",
            "RunResult",
            "WarningEntry",
            "WarningCode",
        ):
            assert getattr(api, name) is getattr(optica, name)

    def test_the_functions_are_the_same_objects_as_the_flat_aliases(self):
        for name in ("run", "fetch", "label", "curate", "train", "export"):
            assert getattr(api, name) is getattr(optica, name)

    def test_everything_declared_is_bound(self):
        for name in api.__all__:
            assert hasattr(api, name), name


def _probe(code: str) -> str:
    """Run a fresh interpreter, so import order is the test's own."""
    return subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout.strip()


class TestExportNameCollision:
    """``optica.export`` is both a Tier 3 alias and a subpackage path.

    The plan fixes both names (§ "Python API" and § "Code Structure") and only
    one attribute can exist on the package object. The function wins. Its
    stability rests on **one invariant**: ``optica.export`` must already be in
    ``sys.modules`` when ``optica/__init__.py`` binds the alias, because the
    import machinery sets the attribute on the parent package only on a
    submodule's **first** load. Today ``optica.api.simple`` imports
    ``optica.export`` eagerly, so the first load happens inside the package
    import and the alias, bound afterwards, is never overwritten. Make that
    import lazy and a user's own ``import optica.export`` rebinds the attribute
    to the module in their process. These tests pin the invariant and both
    import orders.
    """

    def test_the_subpackage_is_loaded_before_the_alias_is_bound(self):
        # The invariant. If this fails, the two tests below fail with it.
        assert "optica.export" in sys.modules

    @pytest.mark.parametrize(
        "order",
        [
            "import optica.export",
            "import optica; import optica.export",
            "import optica; import optica.export.pytorch",
            "import optica.export.pytorch; import optica",
            "from optica import export",
        ],
    )
    def test_the_alias_survives_every_import_order(self, order):
        probe = "; ".join([order, "import optica", "print(callable(optica.export))"])
        assert _probe(probe) == "True"

    def test_the_module_is_still_reachable_by_import(self):
        probe = "; ".join(
            [
                "import optica, sys",
                "from optica.export import manager",
                "print(sys.modules['optica.export'].manager is manager)",
            ]
        )
        assert _probe(probe) == "True"
