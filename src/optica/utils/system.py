"""GPU, virtual-environment and OS detection.

Implements the `utils/system.py` slot in plan § "Code Structure".

**Nothing here imports torch.** Detection has to work before `optica setup` has
installed anything, and ``optica --version`` must work with no torch present, so
the GPU probe reads the driver rather than a framework. Pass 5's setup flow is
the main consumer.

Plan § "Error handling and prompt conventions" also applies to everything this
module returns: output reports **actual detected values**, never internal
registry keys — ``CUDA-capable GPU (NVIDIA RTX 3080)``, not ``gpu``. The
dataclasses below therefore carry a human-readable description alongside the
machine-readable fields, so a caller never has to invent one.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "Accelerator",
    "GPUInfo",
    "SystemInfo",
    "detect_gpu",
    "detect_system",
    "running_in_venv",
    "venv_path",
]


class Accelerator:
    """The accelerator families V1 knows about.

    Plain string constants rather than an enum: these values are compared
    against detection output and written into reports, never parsed from user
    input.
    """

    CUDA = "cuda"
    MPS = "mps"
    CPU = "cpu"


@dataclass(frozen=True)
class GPUInfo:
    """What the machine offers for training.

    Attributes:
        accelerator: One of :class:`Accelerator`'s values.
        name: The adapter's own name, or None where there is no adapter.
        driver_version: The driver's version string, where one is readable.
        cuda_version: The CUDA version the *driver* supports, which is what
            decides the wheel index — not the CUDA a framework was built with.
        description: A sentence fit to print. Reports detected values, never a
            registry key.
    """

    accelerator: str
    name: str | None = None
    driver_version: str | None = None
    cuda_version: str | None = None
    description: str = "CPU only"


@dataclass(frozen=True)
class SystemInfo:
    """The machine Optica is running on.

    Attributes:
        os_name: ``Windows``, ``Darwin`` or ``Linux``.
        os_version: The platform's own release string.
        machine: The processor architecture, e.g. ``AMD64`` or ``arm64``.
        python_version: ``major.minor.patch`` of the running interpreter.
        in_venv: Whether the interpreter is inside a virtual environment.
        venv: The environment's root, or None.
        gpu: The result of :func:`detect_gpu`.
    """

    os_name: str
    os_version: str
    machine: str
    python_version: str
    in_venv: bool
    venv: Path | None
    gpu: GPUInfo


def running_in_venv() -> bool:
    """Whether the running interpreter is inside a virtual environment."""
    return sys.prefix != sys.base_prefix or "VIRTUAL_ENV" in os.environ


def venv_path() -> Path | None:
    """Return the active virtual environment's root, or None.

    ``sys.prefix`` is preferred over ``VIRTUAL_ENV``: the variable says which
    environment was *activated*, while the prefix says which one is actually
    executing, and setup's hard error is about the second.
    """
    if sys.prefix != sys.base_prefix:
        return Path(sys.prefix)
    declared = os.environ.get("VIRTUAL_ENV")
    return Path(declared) if declared else None


def _nvidia_smi_query() -> str | None:
    """Return one CSV line from ``nvidia-smi``, or None if it is not usable.

    Kept separate so tests can replace it without a GPU present.
    """
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return None
    try:
        completed = subprocess.run(  # fixed executable, never a shell
            [
                executable,
                "--query-gpu=name,driver_version",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    first = completed.stdout.strip().splitlines()
    return first[0] if first else None


def _driver_cuda_version() -> str | None:
    """Return the CUDA version the installed driver supports.

    This is the number that decides which wheel index is correct. A driver
    reporting 13.1 selects the ``cu130`` index, because ``cu131`` was never
    published — so a caller must **never** build an index name by string-joining
    the major and minor it gets back from here.
    """
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return None
    try:
        completed = subprocess.run(  # fixed executable, never a shell
            [executable, "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    # The CUDA version lives in `nvidia-smi`'s banner rather than in --query-gpu,
    # so it is parsed from the plain invocation.
    try:
        banner = subprocess.run(  # fixed executable, never a shell
            [executable],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for line in banner.stdout.splitlines():
        if "CUDA Version" in line:
            _, _, tail = line.partition("CUDA Version:")
            return tail.strip().split()[0].rstrip("|").strip() or None
    return None


def detect_gpu() -> GPUInfo:
    """Detect the machine's accelerator without importing torch.

    Returns:
        A :class:`GPUInfo`. Apple silicon reports MPS on the architecture alone,
        since there is no driver to query; anything else with no NVIDIA adapter
        reports CPU.
    """
    line = _nvidia_smi_query()
    if line:
        parts = [part.strip() for part in line.split(",")]
        name = parts[0] if parts else None
        driver = parts[1] if len(parts) > 1 else None
        cuda = _driver_cuda_version()
        suffix = f", driver {driver}" if driver else ""
        cuda_suffix = f", CUDA {cuda}" if cuda else ""
        return GPUInfo(
            accelerator=Accelerator.CUDA,
            name=name,
            driver_version=driver,
            cuda_version=cuda,
            description=f"CUDA-capable GPU ({name}{suffix}{cuda_suffix})",
        )

    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return GPUInfo(
            accelerator=Accelerator.MPS,
            name="Apple silicon",
            description="Apple silicon GPU (Metal Performance Shaders)",
        )

    return GPUInfo(accelerator=Accelerator.CPU, description="CPU only")


def detect_system() -> SystemInfo:
    """Describe the machine Optica is running on."""
    return SystemInfo(
        os_name=platform.system(),
        os_version=platform.release(),
        machine=platform.machine(),
        python_version=platform.python_version(),
        in_venv=running_in_venv(),
        venv=venv_path(),
        gpu=detect_gpu(),
    )
