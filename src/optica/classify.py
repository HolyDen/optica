"""``optica.classify`` — the canonical, task-namespaced API surface.

Implements plan § "Python API" → *Canonical surface — task-namespaced from V1*,
and places the namespace § "Code Structure" flags as having no dedicated module.

The canonical surface is `optica.classify.run()`, `optica.classify.train()`, and
so on; the flat forms bound on `optica` are **convenience aliases** that route
through ``DEFAULT_TASK``. The namespace ships in V1 even though only
classification exists — a small structural cost for a foundation a second task
extends without breaking the first, mirroring the CLI's own alias pattern.

*(The `task=` parameter alternative was rejected: task-specific steps like a
future ``annotate`` make a unified surface hollow.)*
"""

from __future__ import annotations

from optica.api.classifier import Classifier, EpochRecord, Status
from optica.api.simple import (
    ExportConfig,
    ExportResult,
    FetchConfig,
    FetchResult,
    RunResult,
    TrainConfig,
    TrainResult,
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
    "RunResult",
    "Status",
    "TrainConfig",
    "TrainResult",
    "WarningEntry",
    "curate",
    "export",
    "fetch",
    "label",
    "run",
    "train",
]
