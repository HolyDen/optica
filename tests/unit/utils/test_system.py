"""GPU, virtual-environment and OS detection.

Covers the `utils/system.py` slot in plan § "Code Structure", and the standing
rule that output reports actual detected values rather than internal registry
keys.
"""

from __future__ import annotations

import sys
from pathlib import Path

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


def _pretend_venv(monkeypatch, *, prefix: str, base: str) -> None:
    """Put the interpreter in, or out of, a virtual environment."""
    monkeypatch.setattr(sys, "prefix", prefix)
    monkeypatch.setattr(sys, "base_prefix", base)


class TestVenv:
    """Both branches are stubbed rather than inherited from the environment.

    The originals asserted that the test run itself was inside a venv, which is
    an ambient fact and a false one on all three CI runners: `setup-python`
    installs into a hosted toolcache, not a venv. What is worth testing is the
    resolution logic, and stubbing is what makes both of its branches reachable
    on every runner.
    """

    def test_differing_prefixes_mean_a_venv(self, monkeypatch):
        _pretend_venv(monkeypatch, prefix="/proj/.venv", base="/usr")
        assert system.running_in_venv() is True

    def test_equal_prefixes_mean_no_venv(self, monkeypatch):
        _pretend_venv(monkeypatch, prefix="/usr", base="/usr")
        assert system.running_in_venv() is False

    def test_an_activated_variable_alone_is_not_a_venv(self, monkeypatch):
        # A shell can carry a stale VIRTUAL_ENV while the system interpreter
        # runs. Counting it would hide the mismatch pass 5 has to report.
        _pretend_venv(monkeypatch, prefix="/usr", base="/usr")
        monkeypatch.setenv("VIRTUAL_ENV", "/proj/.venv")
        assert system.running_in_venv() is False

    def test_venv_path_is_the_executing_prefix(self, monkeypatch):
        _pretend_venv(monkeypatch, prefix="/proj/.venv", base="/usr")
        monkeypatch.setenv("VIRTUAL_ENV", "/somewhere/else")
        assert system.venv_path() == Path("/proj/.venv")

    def test_venv_path_is_none_outside_a_venv(self, monkeypatch):
        _pretend_venv(monkeypatch, prefix="/usr", base="/usr")
        monkeypatch.setenv("VIRTUAL_ENV", "/somewhere/else")
        assert system.venv_path() is None

    def test_declared_venv_reports_the_variable(self, monkeypatch):
        monkeypatch.setenv("VIRTUAL_ENV", "/proj/.venv")
        assert system.declared_venv() == Path("/proj/.venv")

    def test_declared_venv_is_none_when_unset(self, monkeypatch):
        monkeypatch.delenv("VIRTUAL_ENV", raising=False)
        assert system.declared_venv() is None

    def test_the_mismatch_is_visible_to_a_caller(self, monkeypatch):
        # Activated one environment, executing another: plan § "optica setup"
        # makes this a hard error, so the two values must stay distinguishable.
        _pretend_venv(monkeypatch, prefix="/proj/.venv", base="/usr")
        monkeypatch.setenv("VIRTUAL_ENV", "/other/.venv")
        info = system.detect_system()
        assert info.venv != info.declared_venv

    def test_no_venv_is_a_supported_state_not_an_error(self, monkeypatch):
        # CI's actual state on all three runners.
        toolcache = "/opt/hostedtoolcache/Python"
        _pretend_venv(monkeypatch, prefix=toolcache, base=toolcache)
        monkeypatch.delenv("VIRTUAL_ENV", raising=False)
        info = system.detect_system()
        assert info.in_venv is False
        assert info.venv is None


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
