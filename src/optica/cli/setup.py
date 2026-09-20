"""The ``optica setup`` command — the Machine Initializer.

Implements plan § "`optica setup` — Machine Initializer": the flags, the
**decide-then-do** structural model, environment resolution and its five cases,
the extras prompt, the API-key prompt, the hardware safety prompts, the Review
step, idempotence, and the completion and incomplete messages.

Always global, never per-project — per-project configuration is
``optica config --init``.

Three rules shape this module:

* **Interactivity is binary.** With none of ``--all-extras``/``--no-extras``/
  ``--include-extras``/``--exclude-extras``, setup is fully interactive; with
  any of them it is fully non-interactive and resolves silently. ``--yes`` has
  no role here at all.
* **`--ci` shares no code path with environment detection.** It performs config
  initialization only: no installation, no environment detection, and **no
  prompt of any kind**, which is what lets it run on a CI runner where a prompt
  would be a hard exit 1.
* **Decide, then do.** Every question comes first; the do phase then runs every
  install and write with no further input, so the user can walk away.

The registry is the data — :mod:`optica.registries` — and this module asks the
questions and runs the commands.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Final

import typer

from optica.cli import GlobalState, get_state, split_values
from optica.config.defaults import API_KEYS
from optica.config.manager import ConfigManager
from optica.exceptions import ExitCode, OpticaSetupError, OpticaValidationError
from optica.registries import (
    EXTRAS_REGISTRY,
    INDEXED_PACKAGES,
    PYPI_PACKAGES,
    SETUP_PACKAGES,
    TORCH_GROUP,
    SetupArgs,
    cuda_index_url,
    download_total,
    prompt_order,
    resolve_setup,
    size_breakdown,
    validate_extras_selection,
)
from optica.utils import logging as olog
from optica.utils import prompts
from optica.utils import system as sysinfo
from optica.utils.lockfile import acquire_lock
from optica.utils.mlstack import stack_import_problem

__all__ = ["setup"]

_FLICKR_NOTE: Final = (
    "A key is only needed for `--source flickr`, and requesting one requires a "
    "Flickr Pro subscription. Press Enter to skip if using open-datasets only."
)
_RULE: Final = "─" * 41


# --------------------------------------------------------------- environment


class EnvKind(StrEnum):
    """What the resolved environment is. Decides the Review's label."""

    VENV = "venv"
    CONDA = "conda"
    SYSTEM = "system"


@dataclass(frozen=True)
class Environment:
    """The one environment everything installs into.

    Attributes:
        kind: venv, conda, or system Python.
        path: The environment's prefix, or None for system Python.
        state: ``active``, ``detected (not active)``, ``created``, or
            ``none — installing into system Python``.
        active: Whether this is the environment the shell has activated.
    """

    kind: EnvKind
    path: Path | None
    state: str
    active: bool = False

    @property
    def line(self) -> str:
        """The Review's Environment line. Reports where packages will land."""
        if self.kind is EnvKind.SYSTEM:
            return self.state
        label = "Venv" if self.kind is EnvKind.VENV else "Conda"
        return f"{label}: {self.path} ({self.state})"

    @property
    def python(self) -> Path:
        """The interpreter to install with."""
        if self.path is None or self.active:
            return Path(sys.executable)
        if self.kind is EnvKind.CONDA:  # pragma: no cover - never built here
            return self.path / "python.exe"
        return sysinfo.venv_python(self.path)


_SYSTEM_ENV: Final = Environment(
    EnvKind.SYSTEM, None, "none — installing into system Python"
)


def _active_environment() -> Environment | None:
    """Case 1: an isolated environment is active and Optica runs from it.

    It wins outright, and any venv found on disk is ignored without a prompt.
    Activating an environment is an explicit act; a directory sitting in the
    working folder is not.
    """
    if sysinfo.running_in_conda():
        return Environment(EnvKind.CONDA, sysinfo.conda_prefix(), "active", active=True)
    if sysinfo.running_in_venv():
        return Environment(EnvKind.VENV, sysinfo.venv_path(), "active", active=True)
    return None


def _check_mismatch() -> None:
    """Case 2: an environment is active but Optica is not in it. Hard error.

    Interactive and not. Proceeding is what produces the loop — packages install
    where Optica does not run, setup reports success, the next command says
    *"Run: optica setup"*, and the user is back where they started.
    """
    declared = sysinfo.declared_venv() or sysinfo.conda_prefix()
    if declared is None:
        return
    running = Path(sys.prefix)
    try:
        if running.resolve() == declared.resolve() or running.resolve().is_relative_to(
            declared.resolve()
        ):
            return
    except OSError:  # pragma: no cover - an unreadable prefix
        return
    raise OpticaSetupError(
        "An environment is active, but Optica is not installed in it.",
        why=f"Active: {declared}. Optica runs from: {running}.",
        fix=[
            "Install Optica into the active environment, then run setup again:",
            "pip install optica",
        ],
    )


def _resolve_environment(state: GlobalState, *, interactive: bool) -> Environment:
    """The pre-phase. Runs first, unconditionally; ``--ci`` never reaches it.

    Raises:
        OpticaSetupError: A mismatch on any path, or — non-interactively — no
            environment found, or more than one.
    """
    active = _active_environment()
    if active is not None:
        # Case 1 wins outright: Optica runs from an isolated environment, so
        # there is no mismatch to find and no venv on disk to ask about.
        return active
    _check_mismatch()
    found = sysinfo.discover_venvs(Path.cwd())
    if not interactive:
        # Silent resolution. None found, or more than one, is a hard error: this
        # is the only signal an unattended build receives, so it must be loud
        # rather than a warning nothing will read.
        if len(found) == 1:
            return Environment(EnvKind.VENV, found[0], "detected (not active)")
        found_text = (
            "No virtual environment found"
            if not found
            else f"{len(found)} virtual environments found"
        )
        raise OpticaSetupError(
            f"{found_text} in {Path.cwd()}.",
            why="A non-interactive setup resolves the environment silently, and "
            "neither absence nor ambiguity has a safe answer.",
            fix=[
                "Create and activate one, then run setup again:",
                "python -m venv .venv",
            ],
        )
    if len(found) == 1:
        if prompts.confirm(
            f"Found {found[0]} — not currently active. Install into it?",
            default=True,
        ):
            return Environment(EnvKind.VENV, found[0], "detected (not active)")
    elif found:
        options = {str(i): str(path) for i, path in enumerate(found, start=1)}
        options["N"] = "None of these"
        choice = prompts.choose(
            f"{len(found)} virtual environments found. Which should Optica use?",
            options,
            default="1",
        )
        if choice != "N":
            picked = found[int(choice) - 1]
            return Environment(EnvKind.VENV, picked, "detected (not active)")
    return _create_skip_or_abort(state)


def _create_skip_or_abort(state: GlobalState) -> Environment:
    """Case 5: Y (create) / S (skip, warn) / A (abort)."""
    choice = prompts.choose(
        "No virtual environment found. Create one?",
        {
            "Y": "Create a new environment",
            "S": "Skip — install into system Python",
            "A": "Abort",
        },
        default="Y",
    )
    if choice == "A":
        raise typer.Exit(code=ExitCode.ABORTED)
    if choice == "S":
        olog.warn(
            "Installing into system Python.",
            why="Packages will be visible to every project on this machine.",
        )
        return _SYSTEM_ENV
    return _create_venv()


def _create_venv() -> Environment:
    """The create prompt, with its name collision rule.

    The default is ``.venv`` unconditionally — it encodes the convention and
    does not bend to anticipate a collision. A name that already exists as a
    directory is rejected and re-asked; Optica never creates a venv into an
    existing directory, and ``--force`` does not bypass this, there being no
    proceed-anyway branch to bypass.
    """
    while True:
        name = prompts.ask("Name for the new environment", default=".venv")
        target = Path.cwd() / name
        if not target.exists():
            break
        olog.err_console.print(
            f"{name}/ already exists but is not a virtual environment. Choose a "
            "different name, or remove it and re-run."
        )
    olog.status(f"Creating {target} …")
    completed = subprocess.run(  # fixed executable, never a shell
        [sys.executable, "-m", "venv", str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise OpticaSetupError(
            f"Could not create a virtual environment at {target}.",
            why=completed.stderr.strip().splitlines()[-1] if completed.stderr else "",
            fix=f"Create it by hand: python -m venv {name}",
        )
    return Environment(EnvKind.VENV, target, "created")


# ------------------------------------------------------------ decide phase


def _select_extras(relevant: list[str]) -> list[str]:
    """The interactive extras prompt: torch → web → clip.

    Typed input throughout — universally compatible with SSH, CI and editor
    terminals. Torch asks twice, because its size is knowable only once a
    variant is chosen.
    """
    chosen: list[str] = []
    torch_keys = [key for key in relevant if _is_torch(key)]
    if torch_keys and prompts.confirm("Install PyTorch stack?", default=True):
        olog.err_console.print("  Enables: optica train, optica export, optica run")
        olog.err_console.print("  Which variant?")
        for key, label in (
            ("torch-auto", "auto  — hardware-detected"),
            ("torch-cpu", "cpu   — CPU only"),
            ("torch-gpu", "gpu   — GPU/CUDA"),
        ):
            if key in torch_keys:
                size = EXTRAS_REGISTRY[key]["size_estimate"]
                olog.err_console.print(f"    {label} ({size})")
        variant = prompts.choose(
            "[auto/cpu/gpu]",
            {"A": "auto", "C": "cpu", "G": "gpu"},
            default="A",
        )
        chosen.append({"A": "torch-auto", "C": "torch-cpu", "G": "torch-gpu"}[variant])
    for key in relevant:
        if _is_torch(key):
            continue
        entry = EXTRAS_REGISTRY[key]
        olog.err_console.print(
            f"{entry['display_name']} — {', '.join(entry['enables'])}. "
            f"({entry['size_estimate']})"
        )
        if prompts.confirm(f"Install {entry['display_name']}?", default=entry["default"]):
            chosen.append(key)
    return chosen


def _is_torch(key: str) -> bool:
    return EXTRAS_REGISTRY[key].get("group") == TORCH_GROUP


def _api_key(state: GlobalState, *, skip: bool) -> dict[str, str]:
    """Step 3. Skippable with Enter; skipped entirely under ``--skip-keys``."""
    if skip or not prompts.is_interactive():
        return {}
    olog.err_console.print(_FLICKR_NOTE)
    value = prompts.ask("FLICKR_API_KEY", default="").strip()
    return {"flickr_api_key": value} if value else {}


@dataclass(frozen=True)
class Hardware:
    """The decide phase's hardware scan, and what it implies.

    Attributes:
        gpu: What the machine reports.
        index_url: The wheel index the selected variant will install from.
    """

    gpu: sysinfo.GPUInfo
    index_url: str | None


def _scan_hardware(state: GlobalState, selected: set[str]) -> Hardware | None:
    """Step 4. Runs whenever a torch stack is in play; the prompt does not.

    A mismatch is possible only for ``torch-cpu`` and ``torch-gpu``, since
    ``torch-auto`` resolves to whatever the machine has — so only those two can
    fire the safety prompt, and it fires **here**, in the decide phase, so the
    do phase keeps its no-input guarantee.
    """
    variant = next((key for key in selected if _is_torch(key)), None)
    installed = sysinfo.installed_version("torch") is not None
    if variant is None and not installed:
        return None
    gpu = sysinfo.detect_gpu()
    has_cuda = gpu.accelerator == sysinfo.Accelerator.CUDA
    if variant == "torch-cpu" and has_cuda:
        _safety_prompt(
            state,
            f"Your system has a {gpu.description}.",
            "You requested torch-cpu — this may limit performance.",
            "Proceed with CPU?",
            "optica setup --include-extras torch-auto",
        )
    elif variant == "torch-gpu" and not has_cuda:
        _safety_prompt(
            state,
            "No CUDA-capable GPU detected on your system.",
            "You requested torch-gpu — CUDA-dependent operations will fail at "
            "runtime.",
            "Proceed with the GPU build anyway?",
            "optica setup --include-extras torch-cpu",
        )
    index = None
    if variant is not None:
        declared = EXTRAS_REGISTRY[variant].get("index_url")
        index = declared if declared else cuda_index_url(gpu.cuda_version)
    return Hardware(gpu, index)


def _safety_prompt(
    state: GlobalState, headline: str, consequence: str, question: str, corrected: str
) -> None:
    """A hardware-mismatch safety prompt: answered, suppressed, or an abort.

    With nobody at the terminal it cannot be answered, so it **auto-aborts** —
    the unanswerable prompt's outcome, not an independent hard error, which is
    why ``--force`` removes it along with the prompt. ``--yes`` has no role in
    setup and does not reach here.
    """
    if state.force:
        return
    olog.err_console.print(headline)
    olog.err_console.print(consequence)
    if not prompts.is_interactive():
        raise OpticaSetupError(
            headline,
            why=consequence,
            fix=["The invocation that would work:", corrected],
        )
    answered = prompts.confirm(
        question, default=False, category=prompts.PromptCategory.SAFETY
    )
    if not answered:
        raise typer.Exit(code=ExitCode.ABORTED)


# ------------------------------------------------------------- install state


class PackageState(StrEnum):
    """The Review's per-package states.

    The plan writes the skip state as ``already installed ✓``, and the glyph is
    added at render time rather than stored here: it is one of the four status
    glyphs :class:`~optica.utils.logging.Markers` resolves against the target
    stream, so on a non-UTF-8 Windows console it becomes ``+`` instead of the
    backslash-escape a raw glyph in a data string degrades to. Measured live —
    the escape is what the first Review printed.
    """

    WILL_INSTALL = "will install"
    INSTALLED = "already installed"
    UPGRADE = "already installed — upgrade available"
    REPAIR = "already installed — incompatible, repair"


@dataclass
class Plan:
    """What the do phase will run. Every question already answered.

    Attributes:
        environment: Where everything installs.
        extras: The resolved extras selection.
        packages: Per setup package, its Review state.
        hardware: The scan's result, when a torch stack is in play.
        keys: API keys collected this run.
        repair: Why the installed stack is incompatible, when it is.
        upgrade: Whether this is an ``--upgrade`` run.
    """

    environment: Environment
    extras: set[str]
    packages: dict[str, PackageState] = field(default_factory=dict)
    hardware: Hardware | None = None
    keys: dict[str, str] = field(default_factory=dict)
    repair: str | None = None
    upgrade: bool = False

    @property
    def installs(self) -> list[str]:
        """The extras whose packages are not all present."""
        return [key for key in prompt_order(self.extras) if self._needed(key)]

    def _needed(self, key: str) -> bool:
        if _is_torch(key):
            return any(
                state is not PackageState.INSTALLED for state in self.packages.values()
            )
        return sysinfo.installed_version(_distribution(key)) is None


def _distribution(key: str) -> str:
    """The distribution whose presence decides whether a pip extra is installed."""
    return {"web": "fastapi", "clip": "open-clip-torch"}[key]


def _package_states(selected: set[str], *, upgrade: bool) -> dict[str, PackageState]:
    """The four setup packages' Review states.

    Skip is the default: an already-installed compatible version is skipped
    silently, so re-running setup does not reinstall multi-gigabyte packages.
    """
    if not any(_is_torch(key) for key in selected):
        return {}
    problem = sysinfo.pairing_problem() or stack_import_problem()
    states: dict[str, PackageState] = {}
    for package in SETUP_PACKAGES:
        present = sysinfo.installed_version(_dist_name(package)) is not None
        if not present:
            states[package] = PackageState.WILL_INSTALL
        elif problem is not None:
            states[package] = PackageState.REPAIR
        elif upgrade:
            states[package] = PackageState.UPGRADE
        else:
            states[package] = PackageState.INSTALLED
    return states


def _dist_name(package: str) -> str:
    """``scikit-learn`` is imported as ``sklearn``; metadata uses the pip name."""
    return package


# ------------------------------------------------------------------ review


def _review(state: GlobalState, plan: Plan, *, interactive: bool) -> None:
    """The Review step, printed before anything is installed or written.

    Under a non-interactive invocation it is still printed and its
    ``Proceed with installation?`` prompt is omitted — skipping it entirely
    would remove the only stated catch for a wrong environment target on exactly
    the path where a wrong target costs most.
    """
    out = olog.err_console.print
    out(_RULE)
    out("  Optica Setup — Review")
    out(_RULE)
    out("")
    out("  Environment")
    out(f"    {plan.environment.line}")
    out("")
    out("  Extras")
    rows = size_breakdown(plan.extras)
    if not rows:
        out("    none selected")
    for name, size in rows:
        out(f"    {name:<42}{size}")
    marks = olog.markers_for(olog.err_console)
    for package, package_state in plan.packages.items():
        shown = package_state.value
        if package_state is PackageState.INSTALLED:
            shown = f"{shown} {marks.ok}"
        out(f"      {package:<40}{shown}")
    if plan.hardware is not None:
        out(f"    Detected hardware: {plan.hardware.gpu.description}")
    out("")
    out("  API keys")
    for key in API_KEYS:
        value = "provided" if key in plan.keys else "skipped"
        out(f"    {key.removesuffix('_api_key').title():<15}— {value}")
    out("")
    out(f"  Total download: {download_total(plan.extras)}")
    if _transitive_torch(plan):
        out(
            "  Plus the torch stack open-clip-torch pulls in: "
            f"{EXTRAS_REGISTRY['torch-auto']['size_estimate']}"
        )
    out("")
    out(_RULE)
    if interactive and not prompts.confirm("Proceed with installation?", default=True):
        raise typer.Exit(code=ExitCode.ABORTED)


def _transitive_torch(plan: Plan) -> bool:
    """Whether the Review shows the stack ``open-clip-torch`` pulls in.

    Only when clip is selected, no torch variant is, and no stack is present —
    shown as its own line so the total stays a sum of what was selected.
    """
    return (
        "clip" in plan.extras
        and not any(_is_torch(key) for key in plan.extras)
        and sysinfo.installed_version("torch") is None
    )


# -------------------------------------------------------------- do phase


def _pip_commands(plan: Plan, key: str) -> list[list[str]]:
    """The pip invocations one extra needs.

    The torch group takes **two commands, not one**: ``timm`` and
    ``scikit-learn`` are absent from ``download.pytorch.org`` (measured
    2026-09-12) and ``--index-url`` *replaces* PyPI rather than supplementing
    it, so a single command carrying the variant's index cannot install all
    four. ``--extra-index-url`` was rejected: it lets pip choose per package and
    can silently pull a PyPI torch over the variant's build.
    """
    python = str(plan.environment.python)
    base = [python, "-m", "pip", "install"]
    if plan.upgrade:
        base.append("--upgrade")
    if not _is_torch(key):
        return [[*base, EXTRAS_REGISTRY[key]["pip_extra"]]]
    index = plan.hardware.index_url if plan.hardware else None
    indexed = [*base, *(["--index-url", index] if index else []), *INDEXED_PACKAGES]
    return [indexed, [*base, *PYPI_PACKAGES]]


def _install(plan: Plan) -> list[str]:
    """Run every selected extra's commands. Returns the extras that failed."""
    failed: list[str] = []
    for key in plan.installs:
        name = EXTRAS_REGISTRY[key]["display_name"]
        olog.status(f"Installing {name} …")
        for command in _pip_commands(plan, key):
            completed = subprocess.run(command, check=False)  # fixed executable
            if completed.returncode != 0:
                failed.append(key)
                break
    return failed


def _write_config(plan: Plan) -> Path:
    """The global config file: created if absent, merged into if present.

    Values collected this run are written and values not collected are left
    untouched — so a prompt skipped with Enter **preserves** an existing value
    rather than clearing it, and a key supplied on a re-run is written even
    though the file already exists.
    """
    manager = ConfigManager()
    target = manager.global_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text("# Optica global configuration\n", encoding="utf-8")
    for key, value in plan.keys.items():
        manager.set_key(key, value, use_global=True)
    return target


def _completion(plan: Plan, failed: list[str], installed: list[str]) -> None:
    """The do phase's outcome: the state line, then feature availability."""
    if failed:
        _incomplete(plan, failed)
        return
    if installed:
        present = len(plan.extras) - len(installed)
        detail = f"{len(installed)} extras installed"
        if present:
            detail += f", {present} already present"
        olog.success(f"Setup complete — {detail}.")
    elif plan.repair:
        olog.success("Setup complete — torch stack repaired.")
    elif plan.extras:
        olog.success("Setup complete — all packages already up to date.")
    else:
        olog.success("Setup complete.")
    _features(plan)


def _features(plan: Plan) -> None:
    """Feature availability, not a binary ready-for-X: partial installs are normal."""
    if not plan.environment.active and plan.environment.path is not None:
        olog.status("Activate the environment before using Optica:")
        olog.status(f"  {sysinfo.activation_command(plan.environment.path)}")
    olog.status("Core pipeline:")
    torch_version = sysinfo.installed_version("torch")
    if torch_version is None:
        olog.status("  PyTorch stack: not installed — optica train, optica export")
    elif any(_is_torch(key) for key in plan.extras):
        olog.status(f"  PyTorch stack: {torch_version}")
    else:
        olog.status(
            f"  PyTorch stack: {torch_version} — present, not installed by setup"
        )
    for key in ("web", "clip"):
        entry = EXTRAS_REGISTRY[key]
        present = sysinfo.installed_version(_distribution(key)) is not None
        mark = "yes" if present else "no"
        olog.status(f"  {entry['display_name']}: {mark} — used by "
                    f"{', '.join(entry['enables'])}")


def _incomplete(plan: Plan, failed: list[str]) -> None:
    """What failed → affected commands → retry command → the upgrade note.

    The headline counts **extras, not packages**: an extra may hold more than
    one package, and every other line in the message is per-extra.
    """
    olog.incomplete(f"Setup incomplete — {len(failed)} extra"
                    f"{'s' if len(failed) != 1 else ''} failed.")
    for key in failed:
        entry = EXTRAS_REGISTRY[key]
        olog.err_console.print(f"  {entry['display_name']} failed to install.")
        olog.err_console.print(f"  Affected: {', '.join(entry['enables'])}")
    olog.err_console.print(
        f"  Run `optica setup --include-extras {','.join(failed)}` to retry."
    )
    raise typer.Exit(code=ExitCode.ERROR)


# -------------------------------------------------------------------- --ci


def _ci_init() -> None:
    """``--ci``: config initialization only.

    No package installation, no environment detection, no prompts of any kind.
    Packages reach a CI environment through ``pip install optica[test]`` before
    setup runs, so there is nothing for setup to install — which is why ``--ci``
    installs no torch build, CPU or otherwise. **No Review is shown**: the
    Review confirms an environment target and an install selection, and ``--ci``
    produces neither.
    """
    manager = ConfigManager()
    target = manager.global_path
    target.parent.mkdir(parents=True, exist_ok=True)
    created = not target.exists()
    if created:
        target.write_text("# Optica global configuration\n", encoding="utf-8")
    olog.success(
        f"Setup complete — configuration {'created' if created else 'already present'} "
        f"at {target}."
    )


# ----------------------------------------------------------------- command


def _check_flags(args: SetupArgs, *, upgrade: bool, ci: bool) -> None:
    """Every impossible combination, before anything runs.

    A flag asking for something **already true** is a silent no-op; one asking
    for something **impossible in the resolved mode** is an error. That line is
    what separates ``--skip-keys`` alongside an extras flag, which is accepted
    in silence, from ``--upgrade`` and ``--ci``, which are not.
    """
    if args.all_extras and args.no_extras:
        raise OpticaValidationError(
            "--all-extras and --no-extras cannot be combined.",
            why="The pair is impossible in any resolved mode.",
            fix="Pass one of them.",
        )
    if not args.non_interactive:
        return
    for flag, given in (("--upgrade", upgrade), ("--ci", ci)):
        if given:
            raise OpticaValidationError(
                f"{flag} cannot be combined with an extras-selection flag.",
                why="An extras flag resolves the selection non-interactively, and "
                + (
                    "--upgrade's only function is to raise per-package prompts."
                    if flag == "--upgrade"
                    else "--ci performs no installation at all."
                ),
                fix=f"Run {flag} on its own.",
            )


def setup(
    ctx: typer.Context,
    include_extras: list[str] | None = typer.Option(
        None, "--include-extras", help="Extras to add, comma-separated."
    ),
    exclude_extras: list[str] | None = typer.Option(
        None, "--exclude-extras", help="Extras to skip, comma-separated."
    ),
    all_extras: bool = typer.Option(False, "--all-extras", help="Select every extra."),
    no_extras: bool = typer.Option(False, "--no-extras", help="Select none."),
    upgrade: bool = typer.Option(
        False, "--upgrade", help="Offer newer compatible versions, per package."
    ),
    ci: bool = typer.Option(
        False, "--ci", help="Config initialization only: no install, no prompts."
    ),
    skip_keys: bool = typer.Option(
        False, "--skip-keys", help="Skip the API-key prompts."
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Add detail to output."),
    quiet: bool = typer.Option(False, "--quiet", help="Suppress status output."),
    force: bool = typer.Option(False, "--force", "-f", help="Bypass safety prompts."),
) -> None:
    """Initialize this machine: environment, packages and configuration."""
    state = get_state(ctx).merge(verbose=verbose, quiet=quiet, force=force)
    args = SetupArgs(
        all_extras=all_extras,
        no_extras=no_extras,
        include_extras=split_values(include_extras)
        if include_extras is not None
        else None,
        exclude_extras=split_values(exclude_extras)
        if exclude_extras is not None
        else None,
    )
    _check_flags(args, upgrade=upgrade, ci=ci)
    validate_extras_selection(args)
    if ci:
        # Shares no code path with environment detection, by construction: it
        # returns before the pre-phase exists.
        with acquire_lock("optica setup"):
            _ci_init()
        return
    interactive = not args.non_interactive
    with acquire_lock("optica setup"):
        environment = _resolve_environment(state, interactive=interactive)
        _, extras = resolve_setup(args, select_extras=_select_extras)
        keys = _api_key(state, skip=skip_keys or not interactive)
        hardware = _scan_hardware(state, extras)
        plan = Plan(
            environment=environment,
            extras=extras,
            packages=_package_states(extras, upgrade=upgrade),
            hardware=hardware,
            keys=keys,
            repair=sysinfo.pairing_problem() or stack_import_problem(),
            upgrade=upgrade,
        )
        _review(state, plan, interactive=interactive)
        installed = plan.installs
        failed = _install(plan)
        _write_config(plan)
        _completion(plan, failed, [key for key in installed if key not in failed])


def register(app: typer.Typer) -> None:
    """Register ``optica setup`` on the root app.

    Beside the task groups rather than inside one: setup initializes the
    machine, which is Optica's business and not classification's.
    """
    app.command(name="setup")(setup)
