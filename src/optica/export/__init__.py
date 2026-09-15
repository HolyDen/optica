"""Export: a trained checkpoint to a self-describing folder.

Implements plan § "Export". Nothing in this package imports torch at module
level; ``export/pytorch.py`` imports it where ``model.pt`` is written.
"""

from __future__ import annotations
