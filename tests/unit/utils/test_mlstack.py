"""Runtime helpers for the torch stack.

Covers plan § "Exceptions" → *Lazy imports* (a missing stack is
``OpticaTorchError`` with the capability-named message) for the helper shared by
``input/clip.py`` and ``training/``, the device order CUDA → MPS → CPU, and the
Hub output handling measured in pass 4 (``notes/verified.md``).
"""

from __future__ import annotations

import logging
import sys

import pytest

from optica.exceptions import OpticaTorchError
from optica.utils import mlstack


class TestImportTorchStack:
    @pytest.mark.parametrize("missing", ["torch", "timm"])
    def test_a_missing_package_is_the_ml_stack_error(self, monkeypatch, missing):
        # Constructed: a None entry makes the import raise ImportError whether or
        # not this machine has the package.
        monkeypatch.setitem(sys.modules, missing, None)
        with pytest.raises(OpticaTorchError) as info:
            mlstack.import_torch_stack()
        assert "optica setup" in info.value.message


class TestPrepareHub:
    def test_hub_records_stop_propagating_and_the_symlink_warning_is_off(
        self, monkeypatch
    ):
        monkeypatch.delenv("HF_HUB_DISABLE_SYMLINKS_WARNING", raising=False)
        hub = logging.getLogger("huggingface_hub")
        monkeypatch.setattr(hub, "propagate", True)
        mlstack.prepare_hub()
        assert hub.propagate is False
        import os

        assert os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] == "1"

    def test_a_server_warning_prints_once_not_twice(self, monkeypatch, capsys):
        # The double print measured live: the Hub's own handler plus the root
        # handler Optica configures. Both handlers are constructed here.
        hub = logging.getLogger("huggingface_hub")
        monkeypatch.setattr(hub, "propagate", True)
        monkeypatch.setattr(hub, "handlers", [logging.StreamHandler(sys.stderr)])
        # The level too: an earlier test's --quiet leaves the root at ERROR, and a
        # hub logger at NOTSET would inherit it and emit nothing at all.
        monkeypatch.setattr(hub, "level", logging.WARNING)
        # And the root's handlers are replaced, not added to: earlier tests leave
        # handlers on closed capture streams behind.
        root = logging.getLogger()
        root_handler = logging.StreamHandler(sys.stderr)
        root_handler.setFormatter(logging.Formatter("ROOT %(message)s"))
        monkeypatch.setattr(root, "handlers", [root_handler])
        hub.warning("server says hello")
        assert capsys.readouterr().err.count("server says hello") == 2
        mlstack.prepare_hub()
        hub.warning("server says hello")
        assert capsys.readouterr().err.count("server says hello") == 1


@pytest.mark.slow
class TestDevice:
    def test_cuda_is_chosen_when_available(self, monkeypatch):
        import torch

        monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
        assert mlstack.select_device().type == "cuda"

    def test_cpu_when_neither_accelerator_is_available(self, monkeypatch):
        import torch

        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
        monkeypatch.setattr(torch.backends.mps, "is_available", lambda: False)
        assert mlstack.select_device().type == "cpu"

    def test_mps_when_only_mps_is_available(self, monkeypatch):
        # Constructs the condition; no tensor is ever placed on MPS here.
        import torch

        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
        monkeypatch.setattr(torch.backends.mps, "is_available", lambda: True)
        assert mlstack.select_device().type == "mps"
