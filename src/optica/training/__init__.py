"""Training: backbones, splits, transforms, the engine, checkpoints and logs.

Implements plan § "Training". Nothing in this package imports torch at module
level; every torch import is lazy, so ``optica --version`` never loads it.
"""

from __future__ import annotations
