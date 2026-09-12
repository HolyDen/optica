"""Optica — image classification by transfer learning.

The Simple API (Tier 3) and the flat aliases are added in pass 5; until then this
module exposes the package version only.

``__version__`` is read from the installed distribution metadata rather than
written as a literal, so ``pyproject.toml`` stays the single source of truth and
the two cannot drift apart.
"""

from __future__ import annotations

from importlib import metadata

__all__ = ["__version__"]

try:
    __version__ = metadata.version("optica")
except metadata.PackageNotFoundError:  # running from a source tree, uninstalled
    __version__ = "unknown"
