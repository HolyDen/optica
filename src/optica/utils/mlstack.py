"""Runtime helpers for the torch stack, shared by CLIP scoring and training.

Not in plan § "Code Structure"'s tree; added in pass 4 (``notes/build-log.md``).
``input/clip.py`` and ``training/`` both need the same device choice and the
same handling of the Hugging Face Hub, and neither should import the other.

**Nothing here imports torch at module level**, so this module is as importable
without the stack as ``utils/system.py`` is. Each helper imports lazily and
turns a missing package into the capability-named error.
"""

from __future__ import annotations

import logging
import os
from types import ModuleType
from typing import TYPE_CHECKING

from optica.exceptions import OpticaTorchError

if TYPE_CHECKING:
    import torch

__all__ = [
    "import_torch_stack",
    "prepare_hub",
    "select_device",
    "stack_import_problem",
]


def import_torch_stack() -> tuple[ModuleType, ModuleType]:
    """Import ``torch`` and ``timm``, or raise the ML-stack error.

    Returns:
        ``(torch, timm)``.

    Raises:
        OpticaTorchError: Either is missing — ``optica setup`` installs both.
    """
    # timm imports the Hub, and the Hub reads its warning switch at import.
    prepare_hub()
    try:
        import timm
        import torch
    except ImportError as exc:
        raise OpticaTorchError() from exc
    return torch, timm


def select_device() -> torch.device:
    """CUDA if available, then MPS, then CPU.

    The MPS branch is written and has never been run: the build machine has an
    NVIDIA GPU and no Apple silicon (``notes/build-log.md``).
    """
    import torch

    if torch.cuda.is_available():
        return torch.device("cuda")
    mps = getattr(torch.backends, "mps", None)
    if mps is not None and mps.is_available():  # TODO(test): MPS never exercised
        return torch.device("mps")
    return torch.device("cpu")


def prepare_hub() -> None:
    """Quiet the Hugging Face Hub's duplicate and non-actionable output.

    Call before the Hub is first used. Two things, both measured on the build
    machine (``notes/verified.md``):

    - On Windows without Developer Mode the Hub warns about symlinks on every
      download; the user cannot act on it.
    - Server-sent warnings (the ``X-HF-Warning`` header) are logged by the Hub's
      own handler **and** propagate to the root handler Optica configures, so
      each printed twice. Propagation is turned off: the message still prints,
      once, because a server-sent warning may matter.
    """
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    logging.getLogger("huggingface_hub").propagate = False


def stack_import_problem() -> str | None:
    """Why an installed torch stack will not import, or None.

    The second half of *compatible*: the pairing rule, then "imports
    successfully". A package that is installed but will not import is a
    different failure from a version mismatch — it comes from a broken driver or
    a corrupt wheel, which reinstalling the pairing may not fix — and `optica
    setup`'s repair message says which of the two it found.

    Imports only what is already installed, and never raises: the caller is
    deciding whether to repair, not trying to use the stack.
    """
    import importlib

    for package in ("torch", "torchvision", "timm", "sklearn"):
        try:
            importlib.import_module(package)
        except ImportError:
            continue  # absent, not broken: that is the installer's business
        except Exception as exc:  # noqa: BLE001 - any failure is the answer
            return f"{package} is installed but will not import: {exc}"
    return None
