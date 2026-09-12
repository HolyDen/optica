"""GPU, virtual-environment and OS detection.

Covers the `utils/system.py` slot in plan § "Code Structure", and the standing
rule that output reports actual detected values rather than internal registry
keys.
"""

from __future__ import annotations

import sys

import pytest

from optica.utils import system


class TestNoTorch:
    """Detection must work before ``optica setup`` has installed anything."""

    def test_importing_the_module_does_not_import_torch(self):
        assert "torch" not in sys.modules

    def test_detecting_does_not_import_torch(self, monkeypatch):
        monkeypatch.setattr(system, "_nvidia_smi_query", lambda: None)
        system.detect_gpu()
        assert "torch" not in sys.modules


class TestGPUDetection:
    def test_cuda_is_reported_with_the_adapter_name(self, monkeypatch):
        monkeypatch.setattr(
            system, "_nvidia_smi_query", lambda: "NVIDIA GeForce RTX 4070 Ti, 591.86"
        )
        monkeypatch.setattr(system, "_driver_cuda_version", lambda: "13.1")
        gpu = system.detect_gpu()
        assert gpu.accelerator == system.Accelerator.CUDA
        assert gpu.name == "NVIDIA GeForce RTX 4070 Ti"
        assert gpu.driver_version == "591.86"
        assert gpu.cuda_version == "13.1"

    def test_the_description_names_detected_values_not_registry_keys(self, monkeypatch):
        monkeypatch.setattr(
            system, "_nvidia_smi_query", lambda: "NVIDIA GeForce RTX 3080, 550.00"
        )
        monkeypatch.setattr(system, "_driver_cuda_version", lambda: "12.4")
        description = system.detect_gpu().description
        assert "NVIDIA GeForce RTX 3080" in description
        # Never `gpu`, `torch-gpu`, or a `cu<XXX>` index name.
        assert "torch-gpu" not in description
        assert "cu12" not in description

    def test_no_adapter_reports_cpu(self, monkeypatch):
        monkeypatch.setattr(system, "_nvidia_smi_query", lambda: None)
        monkeypatch.setattr("platform.system", lambda: "Linux")
        gpu = system.detect_gpu()
        assert gpu.accelerator == system.Accelerator.CPU
        assert gpu.description == "CPU only"

    def test_apple_silicon_reports_mps(self, monkeypatch):
        monkeypatch.setattr(system, "_nvidia_smi_query", lambda: None)
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        monkeypatch.setattr("platform.machine", lambda: "arm64")
        gpu = system.detect_gpu()
        assert gpu.accelerator == system.Accelerator.MPS
        assert "Metal" in gpu.description

    def test_intel_mac_reports_cpu(self, monkeypatch):
        monkeypatch.setattr(system, "_nvidia_smi_query", lambda: None)
        monkeypatch.setattr("platform.system", lambda: "Darwin")
        monkeypatch.setattr("platform.machine", lambda: "x86_64")
        assert system.detect_gpu().accelerator == system.Accelerator.CPU


class TestVenv:
    def test_the_test_run_is_inside_a_venv(self):
        # The build and CI both run from `.venv`; if this ever fails, the
        # environment is not the one the milestone was checked against.
        assert system.running_in_venv() is True

    def test_venv_path_prefers_the_executing_prefix(self, monkeypatch):
        monkeypatch.setenv("VIRTUAL_ENV", "/somewhere/else")
        assert str(system.venv_path()) == sys.prefix


class TestSystemInfo:
    def test_reports_the_running_interpreter(self):
        info = system.detect_system()
        assert info.python_version.startswith("3.")
        assert info.os_name in {"Windows", "Darwin", "Linux"}


class TestPlanValuesStillToImplement:
    @pytest.mark.skip(reason="stub - pass 5")
    def test_driver_cuda_version_maps_to_a_published_index(self):
        """A driver reporting 13.1 selects `cu130`.

        `cu131` was never published, so no code may build an index name by
        joining major and minor.
        """

    @pytest.mark.skip(reason="stub - pass 5")
    def test_mps_path_is_written_but_never_run_on_this_machine(self):
        """The MPS branch has no local coverage.

        The build machine has an NVIDIA GPU; recorded in notes/build-log.md.
        """
