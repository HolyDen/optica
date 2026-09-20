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
from importlib import metadata
from pathlib import Path

__all__ = [
    "Accelerator",
    "GPUInfo",
    "SystemInfo",
    "activation_command",
    "conda_prefix",
    "declared_venv",
    "detect_gpu",
    "detect_system",
    "discover_venvs",
    "installed_version",
    "is_venv",
    "pairing_problem",
    "running_in_conda",
    "running_in_venv",
    "venv_path",
    "venv_python",
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
        in_venv: Whether the interpreter is **executing** inside a virtual
            environment.
        venv: The environment being executed from, or None.
        declared_venv: The environment ``VIRTUAL_ENV`` names, or None. Held
            separately from ``venv`` because the two disagreeing is itself the
            condition pass 5's setup must report — an activated environment
            Optica is not running from.
        gpu: The result of :func:`detect_gpu`.
    """

    os_name: str
    os_version: str
    machine: str
    python_version: str
    in_venv: bool
    venv: Path | None
    declared_venv: Path | None
    gpu: GPUInfo


def running_in_venv() -> bool:
    """Whether the interpreter is **executing** inside a virtual environment.

    Decided by the prefixes alone. ``VIRTUAL_ENV`` deliberately does not count:
    the variable says which environment was *activated*, and a shell can carry a
    stale one while the system interpreter runs. Treating that as "in a venv"
    would hide exactly the mismatch pass 5's setup has to report.

    Running outside a venv is a supported state, not an error — GitHub Actions'
    ``setup-python`` installs into a hosted toolcache, so CI is always in it.
    """
    return sys.prefix != sys.base_prefix


def venv_path() -> Path | None:
    """Return the virtual environment being executed from, or None.

    ``sys.prefix`` rather than ``VIRTUAL_ENV``, for the reason in
    :func:`running_in_venv`. Use :func:`declared_venv` for what was activated.
    """
    return Path(sys.prefix) if running_in_venv() else None


def declared_venv() -> Path | None:
    """Return the environment ``VIRTUAL_ENV`` names, or None.

    Reported alongside :func:`venv_path` rather than merged into it: when the
    two differ, the user activated one environment and is running another, which
    plan § "`optica setup`" makes a hard error rather than something to resolve
    silently.
    """
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
        declared_venv=declared_venv(),
        gpu=detect_gpu(),
    )


# ------------------------------------------------------- environments


def conda_prefix() -> Path | None:
    """The environment ``CONDA_PREFIX`` names, or None.

    A conda environment carries its own Python, so ``sys.prefix`` and
    ``sys.base_prefix`` match and no ``pyvenv.cfg`` exists — neither venv signal
    sees one, which is why the variable is read directly.
    """
    declared = os.environ.get("CONDA_PREFIX")
    return Path(declared) if declared else None


def running_in_conda() -> bool:
    """Whether Optica is **executing** inside the active conda environment."""
    prefix = conda_prefix()
    if prefix is None:
        return False
    try:
        return Path(sys.prefix).resolve().is_relative_to(prefix.resolve())
    except OSError:  # pragma: no cover - an unreadable prefix is not ours
        return False


def is_venv(path: Path) -> bool:
    """Whether ``path`` is a virtual environment, by its ``pyvenv.cfg``.

    The marker the ecosystem agrees on. Name-agnostic on purpose: setup's scan
    must find ``env/`` and ``.venv311/`` as readily as ``.venv/``.
    """
    return (path / "pyvenv.cfg").is_file()


def discover_venvs(root: Path) -> list[Path]:
    """Virtual environments **one level** inside ``root``, name-sorted.

    Rooted at the current working directory — the same place the create prompt
    writes ``.venv`` — which is what decides which environments the *exactly one
    found* and *more than one found* cases can ever see. One level only: a scan
    that descended would find environments belonging to unrelated projects.
    """
    if not root.is_dir():
        return []
    try:
        entries = sorted(root.iterdir())
    except OSError:  # pragma: no cover - an unreadable cwd is not ours to fix
        return []
    return [entry for entry in entries if entry.is_dir() and is_venv(entry)]


def venv_python(path: Path) -> Path:
    """The interpreter inside a virtual environment.

    ``Scripts/`` on Windows, ``bin/`` everywhere else — the difference
    ``CLAUDE.md`` names, kept in one place so no caller hardcodes either.
    """
    if platform.system() == "Windows":
        return path / "Scripts" / "python.exe"
    return path / "bin" / "python"


def activation_command(path: Path, shell: str | None = None) -> str:
    """The command that activates ``path``, for the shell this OS implies.

    Reported whenever the resolved environment is not the active one: without
    it setup reports success, the next command raises ``OpticaTorchError``
    saying *"Run: optica setup"*, and the user is sent back to the command they
    just finished.
    """
    if (shell or platform.system()) == "Windows":
        return f"{path}\\Scripts\\activate"
    return f"source {path}/bin/activate"


# ------------------------------------------------------- installed packages


def installed_version(package: str) -> str | None:
    """The installed version of ``package``, or None when it is absent.

    Read from distribution **metadata**, so nothing is imported: setup asks this
    about torch while deciding whether to install torch.
    """
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


def _public(version: str) -> str:
    """A PEP 440 version without its local label: ``2.14.0+cu130`` → ``2.14.0``."""
    return version.split("+", 1)[0]


def pairing_problem() -> str | None:
    """Why the installed torch and torchvision do not pair, or None.

    The **pairing rule** is the constraint that actually exists: the four setup
    packages are deliberately unpinned, so there is no version floor to compare
    against. ``torchvision`` declares an exact ``torch==`` pin, and it declares
    the **public** version on the CUDA index as well as on PyPI — measured
    2026-09-12 — so the same comparison works on both paths.

    Read through ``importlib.metadata``, which parses the metadata as RFC 822
    headers: the CUDA wheel's ``METADATA`` uses CRLF, so a hand-rolled line
    split yields a trailing carriage return on every value.
    """
    torch_version = installed_version("torch")
    vision_version = installed_version("torchvision")
    if torch_version is None or vision_version is None:
        return None
    required = None
    for requirement in metadata.requires("torchvision") or []:
        name, _, rest = requirement.partition(" ")
        if name.strip() == "torch" and "==" in rest:
            required = rest.strip(" ()").removeprefix("==").strip()
            break
    if required is None or _public(torch_version) == _public(required):
        return None
    return (
        f"torchvision {vision_version} requires torch {required}, "
        f"but torch {torch_version} is installed"
    )
