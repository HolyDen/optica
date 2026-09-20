"""Optica — image classification by transfer learning.

The Simple API (Tier 3), the Python API (Tier 4) and the `Classifier` class
(Tier 5), bound here as plan § "Python API" → *Import-time contract* requires.

**`import optica` succeeds with no extras installed** — it is the precondition
of ``pip install optica`` followed by ``optica --version`` working, and of
``from optica import Classifier`` and ``from optica.api import ...`` resolving
at all. The import binds the **full public surface eagerly**: the flat aliases,
the `optica.classify` namespace, `Classifier` and the `optica.api` config
objects are real attributes the moment it returns. The lazy boundary is at the
**dependency** level, never the symbol level, so type checkers and IDE
completion see the whole surface with no stub file.

Nothing is resolved through a module-level ``__getattr__`` — that would trade a
few milliseconds of import time for a surface no tooling can see — and nothing
warns at import when setup has not run: a library that prints on import cannot
honour ``verbose=False``, the user having called nothing yet.

``__version__`` is read from the installed distribution metadata rather than
written as a literal, so ``pyproject.toml`` stays the single source of truth.
"""

from __future__ import annotations

from importlib import metadata

from optica import classify
from optica.api import (
    Classifier,
    EpochRecord,
    ExportConfig,
    ExportResult,
    FetchConfig,
    FetchResult,
    OpticaResult,
    RunResult,
    Status,
    TrainConfig,
    TrainResult,
    WarningCode,
    WarningEntry,
)
from optica.config.defaults import DEFAULT_TASK
from optica.exceptions import OpticaWarning

# The flat forms are permanent aliases, never deprecated or removed, and they
# resolve through `DEFAULT_TASK` rather than hardcoding "classify" — exactly as
# the CLI's flat aliases do, so a post-V1 task slots in without restructuring.
_TASKS = {DEFAULT_TASK: classify}
_task = _TASKS[DEFAULT_TASK]

curate = _task.curate
export = _task.export
fetch = _task.fetch
label = _task.label
run = _task.run
train = _task.train

__all__ = [
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

try:
    __version__ = metadata.version("optica")
except metadata.PackageNotFoundError:  # running from a source tree, uninstalled
    __version__ = "unknown"
