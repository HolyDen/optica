"""``optica.api`` — what the plan's own examples import from it.

Covers plan § "Python API" → *Classifier (Tier 5)* (the example's
``from optica.api import FetchConfig, TrainConfig, ExportConfig`` line) and the
import-time contract's *full public surface bound eagerly*.
"""

from __future__ import annotations

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
