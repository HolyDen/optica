"""The task and extras registries, and the resolution `optica setup` runs on.

Implements plan § "`optica setup` — Machine Initializer" → *Registry and
resolution* and *`--include-extras` / `--exclude-extras` parsing*, and the
`TASK_REGISTRY`/`EXTRAS_REGISTRY` slot that § "Code Structure" leaves without a
home ("both should be placed when the API namespace and setup registry are
built" — this is that placement; see ``notes/build-log.md``).

Top-level rather than inside ``cli/``, because both registries are data two
layers read: ``cli/setup.py`` resolves an extras selection from them, and the
API's task namespace is described by ``TASK_REGISTRY``'s ``api_namespace`` and
``tier5_class``. A home under ``cli/`` would have ``api/`` importing the CLI.

**Nothing here prompts, installs, or detects hardware.** Prompts live in the CLI
layer; this module answers what the registry says, given answers it is handed.
Setup is data-driven by design: adding a future extra is a registry entry, not
an edit in several places.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Final, NotRequired, TypedDict

from optica.exceptions import OpticaValidationError

__all__ = [
    "CPU_INDEX",
    "CUDA_INDEXES",
    "EXTRAS_REGISTRY",
    "INDEXED_PACKAGES",
    "PYPI_PACKAGES",
    "SETUP_PACKAGES",
    "TASK_REGISTRY",
    "TORCH_GROUP",
    "ExtraEntry",
    "ExtraSelector",
    "SetupArgs",
    "SizeRange",
    "TaskEntry",
    "TaskSelector",
    "collapse_groups",
    "cuda_index_url",
    "download_total",
    "expand_excludes",
    "group_members",
    "parse_size_estimate",
    "prompt_order",
    "resolve_setup",
    "size_breakdown",
    "validate_extras_selection",
]


class TaskEntry(TypedDict):
    """One task type. V1 has exactly one, and the shape is what makes a second cheap.

    Attributes:
        task_id: The key ``--tasks`` would take; also the config surface's name.
        display_name: The human-readable name, for the task-selection prompt.
        cli_group: The Typer sub-app the task's commands live in.
        api_namespace: The canonical, task-namespaced API surface.
        tier5_class: The Tier 5 class the namespace exposes.
        relevant_extras: Extras this task can use. **Never the torch variants**
            — those are ``universal`` and reach every task without being listed.
        task_group_extra: An extra covering the whole task, where one exists.
    """

    task_id: str
    display_name: str
    cli_group: str
    api_namespace: str
    tier5_class: str
    relevant_extras: list[str]
    task_group_extra: str | None


class ExtraEntry(TypedDict):
    """One installable extra.

    Schema, per the plan: ``display_name``, ``default``, ``size_estimate`` and
    ``enables`` are required for every entry; ``pip_extra`` XOR ``index_url``;
    ``group`` and ``universal`` are optional. The XOR is what separates a Tier 2
    pip extra from a Tier 3 platform-dependent install.

    Attributes:
        display_name: The name shown in prompts, the Review and messages.
        default: Whether the entry is selected by default.
        size_estimate: The download figure the Review sums. A display string —
            :func:`parse_size_estimate` is what reads it back.
        enables: Commands the entry unlocks. One field, two renderings: the
            completion message's *used by* and the incomplete message's
            *Affected:*.
        pip_extra: The pip requirement that installs it. Excludes ``index_url``.
        index_url: The wheel index the torch stack installs from. ``None`` for
            ``torch-auto``, which resolves in the do phase from the decide
            phase's hardware scan. Excludes ``pip_extra``.
        group: A mutually-exclusive group this entry is a member of.
        universal: Whether every task needs it, regardless of task selection.
    """

    display_name: str
    default: bool
    size_estimate: str
    enables: list[str]
    pip_extra: NotRequired[str]
    index_url: NotRequired[str | None]
    group: NotRequired[str]
    universal: NotRequired[bool]


TASK_REGISTRY: Final[list[TaskEntry]] = [
    {
        "task_id": "classify",
        "display_name": "Image Classification",
        "cli_group": "classify",
        "api_namespace": "optica.classify",
        "tier5_class": "Classifier",
        "relevant_extras": ["web", "clip"],
        "task_group_extra": None,
    },
]

TaskSelector = Callable[[list[TaskEntry]], Sequence[str]]
"""The task-selection prompt. Unreachable in V1: one task selects itself."""

ExtraSelector = Callable[[list[str]], Sequence[str]]
"""The extras-selection prompt, handed the relevant keys in prompt order."""

CPU_INDEX: Final = "https://download.pytorch.org/whl/cpu"
"""The CPU wheel index. ``torch-auto`` resolves here when no CUDA GPU is found."""

EXTRAS_REGISTRY: Final[dict[str, ExtraEntry]] = {
    "web": {
        "display_name": "Browser UI",
        "default": True,
        "pip_extra": "optica[web]",
        "size_estimate": "~5MB",
        "enables": [
            "optica label",
            "optica curate",
            "optica run (label/curate modes)",
        ],
    },
    "clip": {
        "display_name": "CLIP filtering",
        "default": False,
        "pip_extra": "optica[clip]",
        "size_estimate": "~600MB",
        "enables": ["optica fetch --mode clip", "optica run --mode clip"],
    },
    # The torch variants: universal (every task's train/export needs them) and
    # mutually exclusive within group "torch".
    "torch-auto": {
        "display_name": "PyTorch stack (auto-detect)",
        "default": True,
        "group": "torch",
        "universal": True,
        "size_estimate": "~250MB–2.5GB",
        "index_url": None,  # resolved in the do phase from the decide-phase scan
        "enables": ["optica train", "optica export", "optica run"],
    },
    "torch-cpu": {
        "display_name": "PyTorch stack (CPU only)",
        "default": False,
        "group": "torch",
        "universal": True,
        "size_estimate": "~250MB",
        "index_url": CPU_INDEX,
        "enables": ["optica train", "optica export", "optica run"],
    },
    "torch-gpu": {
        "display_name": "PyTorch stack (GPU)",
        "default": False,
        "group": "torch",
        "universal": True,
        "size_estimate": "~2–2.5GB",
        # `cu130`, pinned at the pre-implementation gate: `notes/verified.md`
        # § "Which CUDA indexes exist on `download.pytorch.org`" (2026-09-12).
        # `cu131` was never published, so a driver reporting 13.1 takes `cu130`.
        "index_url": "https://download.pytorch.org/whl/cu130",
        "enables": ["optica train", "optica export", "optica run"],
    },
}

TORCH_GROUP: Final = "torch"
"""The one mutually-exclusive group in V1. A group name, never a registry key."""

SETUP_PACKAGES: Final = ("torch", "torchvision", "timm", "scikit-learn")
"""The four platform-dependent packages ``optica setup`` installs."""

INDEXED_PACKAGES: Final = ("torch", "torchvision")
"""The two a variant's ``index_url`` actually serves."""

PYPI_PACKAGES: Final = ("timm", "scikit-learn")
"""The two it does not.

Measured 2026-09-12 (`notes/verified.md` § "`timm` and `scikit-learn` are not on
the PyTorch index"): both return *No matching distribution found* against a
``cu130`` index. ``--index-url`` **replaces** PyPI rather than supplementing it,
so one command carrying one ``--index-url`` cannot install all four. The
partition lives here; ``cli/setup.py`` builds the commands from it.
"""

CUDA_INDEXES: Final[tuple[tuple[tuple[int, int], str], ...]] = (
    ((12, 6), "https://download.pytorch.org/whl/cu126"),
    ((12, 8), "https://download.pytorch.org/whl/cu128"),
    ((12, 9), "https://download.pytorch.org/whl/cu129"),
    ((13, 0), "https://download.pytorch.org/whl/cu130"),
    ((13, 2), "https://download.pytorch.org/whl/cu132"),
)
"""Every CUDA wheel index that exists, ascending. Checked 2026-09-12 by HTTP
status against ``download.pytorch.org``; ``cu131`` returns 403 and has never
been published, which is why this is a table and not a format string."""


def cuda_index_url(driver_cuda: str | None) -> str:
    """The wheel index for a driver's CUDA version — the highest it can run.

    ``torch-auto``'s do-phase resolution. A driver supports every CUDA release
    at or below its own version, so the answer is the newest published index
    that does not exceed it; a driver reporting 13.1 therefore takes ``cu130``,
    not a string-built ``cu131`` that would 403.

    Args:
        driver_cuda: The CUDA version the driver supports, as
            :attr:`~optica.utils.system.GPUInfo.cuda_version` reports it, or
            None where there is no CUDA GPU.

    Returns:
        A wheel index URL. :data:`CPU_INDEX` where there is no CUDA at all, and
        where the driver predates every published index.
    """
    if not driver_cuda:
        return CPU_INDEX
    try:
        parts = [int(piece) for piece in driver_cuda.split(".")[:2]]
    except ValueError:
        return CPU_INDEX
    version = (parts[0], parts[1] if len(parts) > 1 else 0)
    best = CPU_INDEX
    for published, url in CUDA_INDEXES:
        if published <= version:
            best = url
    return best


# ------------------------------------------------------------------ groups


def group_members(group: str, registry: dict[str, ExtraEntry]) -> set[str]:
    """Every registry key belonging to ``group``."""
    return {key for key, entry in registry.items() if entry.get("group") == group}


def expand_excludes(
    names: list[str] | None, registry: dict[str, ExtraEntry]
) -> set[str]:
    """Expand group names to their members; plain keys pass through.

    Exclude-side only. ``--include-extras`` takes specific variants, and a bare
    group name there is a hard error rather than a silent multi-gigabyte choice
    — enforced at parse, in :func:`validate_extras_selection`.
    """
    out: set[str] = set()
    for name in names or []:
        members = group_members(name, registry)
        out |= members if members else {name}
    return out


def collapse_groups(names: set[str], registry: dict[str, ExtraEntry]) -> set[str]:
    """Reduce each mutually-exclusive group to its default member."""
    out = {name for name in names if registry[name].get("group") is None}
    for group in {registry[name].get("group") for name in names} - {None}:
        assert group is not None
        out |= {key for key in group_members(group, registry) if registry[key]["default"]}
    return out


# -------------------------------------------------------------- resolution


@dataclass(frozen=True)
class SetupArgs:
    """The selection flags ``resolve_setup`` reads.

    ``None`` means *flag absent*; an empty list means *given with no values*,
    which is a silent no-op for the selection but still makes setup
    non-interactive — the distinction ``--include-extras ""`` turns on, and the
    reason these are ``list | None`` rather than ``list``.

    Attributes:
        all_tasks: ``--all-tasks``. Built, not surfaced in V1.
        tasks: ``--tasks``. Built, not surfaced in V1.
        all_extras: ``--all-extras``.
        no_extras: ``--no-extras``.
        include_extras: ``--include-extras``, already comma-split.
        exclude_extras: ``--exclude-extras``, already comma-split.
    """

    all_tasks: bool = False
    tasks: list[str] | None = None
    all_extras: bool = False
    no_extras: bool = False
    include_extras: list[str] | None = None
    exclude_extras: list[str] | None = None

    @property
    def non_interactive(self) -> bool:
        """Whether an extras-selection flag is present.

        *Interactivity is binary*: with none of the four, setup is fully
        interactive; with any, it is fully non-interactive and resolves
        silently. ``--tasks``/``--all-tasks`` are deliberately **not** here —
        they are unregistered in V1, so no user can reach this through them.
        """
        return (
            self.all_extras
            or self.no_extras
            or self.include_extras is not None
            or self.exclude_extras is not None
        )


def resolve_setup(
    args: SetupArgs,
    task_registry: list[TaskEntry] = TASK_REGISTRY,
    extras_registry: dict[str, ExtraEntry] = EXTRAS_REGISTRY,
    *,
    select_tasks: TaskSelector | None = None,
    select_extras: ExtraSelector | None = None,
) -> tuple[set[str], set[str]]:
    """Resolve the task set and the extras selection.

    Modifiers apply in a fixed order — base, then include, then exclude — so
    command-line flag order never changes the outcome. An explicit include
    displaces any other member of its group already in the base, which is why
    ``--all-extras --include-extras torch-cpu`` yields ``torch-cpu`` rather than
    a conflict.

    Args:
        args: The selection flags. Already validated by
            :func:`validate_extras_selection`.
        task_registry: The tasks to resolve against.
        extras_registry: The extras to resolve against.
        select_tasks: The task-selection prompt, reached only when more than one
            task exists and no task flag was given. Unreachable in V1.
        select_extras: The extras-selection prompt, reached only on the fully
            interactive path.

    Returns:
        ``(task_ids, extras_keys)``.
    """
    tasks: set[str]
    if args.all_tasks:
        tasks = {entry["task_id"] for entry in task_registry}
    elif args.tasks is not None:
        tasks = set(args.tasks)
    elif len(task_registry) == 1:
        tasks = {task_registry[0]["task_id"]}
    else:  # pragma: no cover - V1 has one task; the branch is the second one's
        if select_tasks is None:
            raise OpticaValidationError(
                "More than one task is registered and none was selected."
            )
        tasks = set(select_tasks(task_registry))

    task_relevant: set[str] = set()
    for entry in task_registry:
        if entry["task_id"] in tasks:
            task_relevant |= set(entry["relevant_extras"])
    universal = {key for key, e in extras_registry.items() if e.get("universal")}
    # Torch is never task-relevant; it is universal, so a future task reaches it
    # without adding anything.
    relevant = task_relevant | universal

    base: set[str]
    if args.all_extras:
        base = collapse_groups(relevant, extras_registry)
    elif args.no_extras:
        base = set()
    elif (
        args.tasks is not None
        or args.all_tasks
        or args.include_extras is not None
        or args.exclude_extras is not None
    ):
        base = {key for key in relevant if extras_registry[key]["default"]}
    else:
        if select_extras is None:
            raise OpticaValidationError(
                "Interactive extras selection was reached with no prompt to run."
            )
        base = set(select_extras(prompt_order(relevant, extras_registry)))

    include = set(args.include_extras or [])
    exclude = expand_excludes(args.exclude_extras, extras_registry)
    include_groups = {extras_registry[key].get("group") for key in include} - {None}
    base = {
        key
        for key in base
        if extras_registry[key].get("group") not in include_groups
    }
    return tasks, (base | include) - exclude


def prompt_order(
    relevant: set[str], extras_registry: dict[str, ExtraEntry] = EXTRAS_REGISTRY
) -> list[str]:
    """The relevant extras in the order the decide phase asks about them.

    torch → web → clip, per the extras prompt. Registry insertion order puts the
    pip extras first, so the torch group is lifted to the front rather than the
    prompt hardcoding a list that a new entry would silently fall off.
    """
    torch = [key for key in extras_registry if key in relevant and _is_torch(key)]
    rest = [key for key in extras_registry if key in relevant and not _is_torch(key)]
    return torch + rest


def _is_torch(key: str, registry: dict[str, ExtraEntry] = EXTRAS_REGISTRY) -> bool:
    return registry[key].get("group") == TORCH_GROUP


# ----------------------------------------------------------- name validation

_PIP_NAME_HINTS: Final[dict[str, str]] = {
    # The extras table's own contents, so a user who names what pip would
    # install is told the registry key rather than the list of valid keys.
    "optica[web]": "web",
    "fastapi": "web",
    "uvicorn": "web",
    "optica[clip]": "clip",
    "open-clip-torch": "clip",
    "open_clip_torch": "clip",
    "optica[all]": "web",
}

_SIMILARITY_CUTOFF: Final = 0.6
"""``difflib.get_close_matches`` cutoff, per the parsing rules."""


def _suggestion(name: str, valid: list[str]) -> str | None:
    """The registry key ``name`` was probably meant to be, or None."""
    lowered = name.casefold()
    hinted = _PIP_NAME_HINTS.get(lowered)
    if hinted is not None:
        return hinted
    if lowered == TORCH_GROUP:
        # An alias was rejected: `--exclude-extras torch` already means the whole
        # group, so `torch` cannot also mean one variant.
        return "torch-auto"
    close = difflib.get_close_matches(lowered, valid, n=1, cutoff=_SIMILARITY_CUTOFF)
    return close[0] if close else None


def _unknown_name_error(
    bad: list[tuple[str, str | None]], valid: list[str]
) -> OpticaValidationError:
    named = ", ".join(name for name, _ in bad)
    suggestions = [
        f"Did you mean '{hint}'? (for '{name}')" for name, hint in bad if hint
    ]
    return OpticaValidationError(
        f"Not a known extra: {named}",
        why="--include-extras and --exclude-extras take registry keys.",
        fix=suggestions or None,
        options=valid,
    )


def validate_extras_selection(
    args: SetupArgs, extras_registry: dict[str, ExtraEntry] = EXTRAS_REGISTRY
) -> None:
    """Check both extras flags' values before anything is resolved.

    Every invalid value is reported at once, never one per re-run. The two
    directions are deliberately asymmetric: ``--exclude-extras torch`` removes
    every variant, while ``--include-extras`` takes a **specific** variant —
    choosing a multi-gigabyte variant the user did not name is worse than
    refusing.

    Raises:
        OpticaValidationError: An unknown name, a group name on the include
            side, two members of one group included, or the same extra on both
            sides after group expansion.
    """
    valid = sorted(extras_registry)
    groups = {
        entry["group"] for entry in extras_registry.values() if entry.get("group")
    }
    unknown: list[tuple[str, str | None]] = []
    for side, names in (
        ("--include-extras", args.include_extras),
        ("--exclude-extras", args.exclude_extras),
    ):
        for name in names or []:
            if name in extras_registry:
                continue
            if name in groups and side == "--exclude-extras":
                continue
            unknown.append((name, _suggestion(name, valid)))
    if unknown:
        raise _unknown_name_error(unknown, valid)

    include = list(args.include_extras or [])
    by_group: dict[str, list[str]] = {}
    for name in include:
        group = extras_registry[name].get("group")
        if group is not None:
            by_group.setdefault(group, []).append(name)
    clashing = {group: names for group, names in by_group.items() if len(names) > 1}
    if clashing:
        detail = "; ".join(
            f"{group}: {', '.join(names)}" for group, names in sorted(clashing.items())
        )
        raise OpticaValidationError(
            f"--include-extras names more than one member of a group ({detail}).",
            why="Entries within a group are mutually exclusive.",
            fix="Name exactly one variant.",
        )

    # Compared after expansion, so `--include-extras torch-cpu --exclude-extras
    # torch` is the same error as naming torch-cpu on both sides.
    both = set(include) & expand_excludes(args.exclude_extras, extras_registry)
    if both:
        raise OpticaValidationError(
            f"{', '.join(sorted(both))} is in both --include-extras and "
            "--exclude-extras.",
            why="A single run cannot both install and skip the same extra.",
            fix="Remove it from one of the two flags.",
        )


# --------------------------------------------------------------- sizes

_SIZE = re.compile(
    r"^~?\s*(?:(?P<low>[\d.]+)\s*(?P<low_unit>MB|GB)?\s*[–-]\s*)?"
    r"(?P<high>[\d.]+)\s*(?P<high_unit>MB|GB)$"
)
_PER_GB: Final = 1000
"""Decimal GB, which is what the plan's own figures are in: 250 + 5 + 600 MB
reads as 0.9GB, not 0.8."""


@dataclass(frozen=True)
class SizeRange:
    """A download estimate in megabytes.

    Attributes:
        low: The bottom of the range.
        high: The top. Equal to ``low`` for a single-valued estimate.
    """

    low: float
    high: float

    def __add__(self, other: SizeRange) -> SizeRange:
        """Sum two estimates end to end."""
        return SizeRange(self.low + other.low, self.high + other.high)


def parse_size_estimate(estimate: str) -> SizeRange:
    """Read a registry ``size_estimate`` back into megabytes.

    Accepts the three shapes the registry uses: a single value (``~250MB``), a
    range with both units (``~250MB–2.5GB``) and a range whose low side inherits
    the high side's unit (``~2–2.5GB``).

    Raises:
        ValueError: When the string is not one of those shapes — a registry
            entry with an unreadable estimate is a defect, not a user input.
    """
    match = _SIZE.match(estimate.strip())
    if match is None:
        raise ValueError(f"unreadable size_estimate: {estimate!r}")
    high_unit = match.group("high_unit")
    high = float(match.group("high")) * (_PER_GB if high_unit == "GB" else 1)
    raw_low = match.group("low")
    if raw_low is None:
        return SizeRange(high, high)
    low_unit = match.group("low_unit") or high_unit
    return SizeRange(float(raw_low) * (_PER_GB if low_unit == "GB" else 1), high)


def _render(value_mb: float, unit: str) -> str:
    if unit == "GB":
        quantized = Decimal(value_mb / _PER_GB).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )
        return f"{quantized.normalize():f}"
    return f"{Decimal(value_mb).quantize(Decimal('1'), rounding=ROUND_HALF_UP):f}"


def _format(total: SizeRange) -> str:
    # One unit for the whole figure, chosen by the top of the range: a total
    # reading `855MB–3.1GB` would make the two ends incomparable at a glance.
    unit = "GB" if total.high >= _PER_GB else "MB"
    low = _render(total.low, unit)
    high = _render(total.high, unit)
    return f"~{high}{unit}" if low == high else f"~{low}–{high}{unit}"


def size_breakdown(
    keys: set[str] | list[str], extras_registry: dict[str, ExtraEntry] = EXTRAS_REGISTRY
) -> list[tuple[str, str]]:
    """``(display_name, size_estimate)`` per selected extra, in prompt order.

    The Review prints these rows and :func:`download_total` beneath them. A
    total with no breakdown is what lets a wrong figure look plausible.
    """
    selected = set(keys)
    return [
        (extras_registry[key]["display_name"], extras_registry[key]["size_estimate"])
        for key in prompt_order(selected, extras_registry)
    ]


def download_total(
    keys: set[str] | list[str], extras_registry: dict[str, ExtraEntry] = EXTRAS_REGISTRY
) -> str:
    """The Review's download total: a straight sum of what was selected.

    The torch stack ``open-clip-torch`` pulls transitively is **not** in it —
    the Review shows that as its own line, so the sum stays a sum of what the
    user chose. Returns ``"none selected"`` for an empty selection, which is
    what that section of the Review shows.
    """
    rows = [parse_size_estimate(e) for _, e in size_breakdown(keys, extras_registry)]
    if not rows:
        return "none selected"
    total = rows[0]
    for row in rows[1:]:
        total = total + row
    return _format(total)
