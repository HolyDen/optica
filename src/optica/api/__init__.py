"""The Python API package: Tier 3/4 functions, the result types, Tier 5.

Implements the `api/` slot in plan § "Code Structure". Everything the plan's own
examples import from ``optica.api`` — ``FetchConfig``, ``TrainConfig``,
``ExportConfig`` — is bound here, alongside the result types a caller reads off
a return value and the `Classifier` class.

**The import binds the full public surface eagerly.** The lazy boundary is at
the dependency level, never the symbol level, so type checkers and IDE
completion see the whole surface with no stub file and ``import optica``
succeeds with no extras installed.
"""

from __future__ import annotations

from optica.api.classifier import Classifier, EpochRecord, Status
from optica.api.simple import (
    ExportConfig,
    ExportResult,
    FetchConfig,
    FetchResult,
    OpticaResult,
    RunResult,
    TrainConfig,
    TrainResult,
    WarningCode,
    WarningEntry,
    curate,
    export,
    fetch,
    label,
    run,
    train,
)

__all__ = [
    "Classifier",
    "EpochRecord",
    "ExportConfig",
    "ExportResult",
    "FetchConfig",
    "FetchResult",
    "OpticaResult",
    "RunResult",
    "Status",
    "TrainConfig",
    "TrainResult",
    "WarningCode",
    "WarningEntry",
    "curate",
    "export",
    "fetch",
    "label",
    "run",
    "train",
]
