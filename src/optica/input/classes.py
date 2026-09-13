"""Class-name rules, the blocklist, and the class-resolution sequence.

Implements plan § "CLI Layer & Conventions" → *Class-name rules*, and § "Input &
Acquisition" → *Class-count validation* and *Undefinable classes in auto modes*.

Every class name becomes a folder, so the two class-name rules apply on every
surface that accepts one — ``-c``, a manifest's ``class`` column, and the
sub-terms the blocklist flow collects. They are enforced here, once, rather than
per surface.

The blocklist flow asks the user questions, and prompts live in the CLI only;
the API raises instead. The flow is therefore written against a
:class:`ClassPrompter` the caller supplies, and this module holds the sequence
and the arithmetic but never reads stdin.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Final, Protocol

from optica.exceptions import OpticaValidationError

__all__ = [
    "BLOCKLIST",
    "MAX_CLASS_NAME_LENGTH",
    "MIN_CLASSES",
    "MIN_IMAGES_PER_SUB_TERM",
    "ClassPrompter",
    "Overlap",
    "ResolvedClass",
    "class_name_problem",
    "find_overlaps",
    "is_blocklisted",
    "list_names",
    "normalize_class_names",
    "require_min_classes",
    "resolve_auto_classes",
    "sub_term_count",
]

MAX_CLASS_NAME_LENGTH: Final = 50
MIN_CLASSES: Final = 2
MIN_IMAGES_PER_SUB_TERM: Final = 10
LIST_TRUNCATE: Final = 10
"""Name lists in errors truncate past this many, as the class-subset exclude
list does."""

_FORBIDDEN_CHARS: Final = '/\\,?*:|"<>'
_RESERVED_NAMES: Final[frozenset[str]] = frozenset(
    {"con", "aux", "nul", "prn"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)

BLOCKLIST: Final[frozenset[str]] = frozenset(
    {
        # The plan's seed list, verbatim.
        "other",
        "unknown",
        "misc",
        "miscellaneous",
        "none",
        "undefined",
        "various",
        "else",
        "rest",
        "good",
        "bad",
        "normal",
        "abnormal",
        "defective",
        "damaged",
        "broken",
        "working",
        "faulty",
        "mine",
        "yours",
        "safe",
        "unsafe",
        "valid",
        "invalid",
        "correct",
        "incorrect",
        "positive",
        "negative",
        # Extensions within the plan's named categories. Implementation Note 10:
        # the seed is a starting point, and adding a term is one line here.
        "others",
        "etc",
        "stuff",
        "things",
        "random",
        "general",
        "generic",
        "ok",
        "okay",
        "fine",
        "fail",
        "pass",
        "custom",
        "personal",
        "ours",
        "theirs",
        "true",
        "false",
        "yes",
        "no",
        "not",
        "non",
    }
)
"""Terms that are not concrete, searchable, visual class names.

Matched case-insensitively against the **whole** name, with ``_`` and ``-`` read
as spaces. Negated names and placeholder labels are caught by pattern below, not
by listing every spelling.
"""

_NEGATION: Final = re.compile(r"^(not|non|no)(\s|$)")
_PLACEHOLDER: Final = re.compile(r"^(class|label|category|group|type)\s?([a-z]|\d+)$")
_SINGLE_OR_NUMBER: Final = re.compile(r"^(.|\d+)$")


# --------------------------------------------------------------- name rules


def class_name_problem(name: str) -> str | None:
    """Return why ``name`` cannot be a class folder, or None if it can.

    Rule 1 of plan § *Class-name rules*: non-empty; not ``.``, ``..`` or any
    all-dots name; no path separator; no comma; none of ``? * : | " < >``; at
    most 50 characters; not beginning with ``-``; and not a reserved Windows
    device name.

    The leading-``-`` clause is the amended one. The parser binds the token after
    ``--classes`` as its value whatever it looks like, so
    ``optica fetch --classes --yes`` arrives here as a class called ``--yes``;
    this is the only layer that can tell it is wrong.
    """
    if not name:
        return "is empty"
    if set(name) == {"."}:
        return "is made only of dots, which is a path component rather than a name"
    if "/" in name or "\\" in name:
        return "contains a path separator"
    if "," in name:
        return "contains a comma, which separates values"
    bad = sorted({char for char in name if char in _FORBIDDEN_CHARS})
    if bad:
        return f"contains {' '.join(bad)}, which Windows rejects in folder names"
    if len(name) > MAX_CLASS_NAME_LENGTH:
        return f"is longer than {MAX_CLASS_NAME_LENGTH} characters"
    if name.startswith("-"):
        return "begins with '-', which is a flag spelling rather than a name"
    # Windows reserves the device names with any extension as well: `con.jpg`
    # is as unusable as `con`.
    if name.split(".", 1)[0].casefold() in _RESERVED_NAMES:
        return "is a reserved operating-system file name"
    return None


def list_names(names: Sequence[str], limit: int = LIST_TRUNCATE) -> str:
    """Render a list of names as prose, truncating past ``limit``."""
    shown = ", ".join(names[:limit])
    extra = len(names) - limit
    return f"{shown} (and {extra} more)" if extra > 0 else shown


def normalize_class_names(
    names: Iterable[str], *, surface: str = "--classes"
) -> list[str]:
    """Apply both class-name rules to a whole list at once.

    Rule 1 (filesystem-safe) and rule 2 (case-insensitive duplicates), in the
    whole-list form the plan gives for ``-c`` and a manifest's ``class`` column:
    a case-variant is a hard error naming both names, and an exact duplicate
    collapses silently. **Every** failing name is reported in one error rather
    than the first only, and no name is rewritten to make it pass.

    Args:
        names: The names, already split on commas and trimmed.
        surface: Where they came from, in the user's vocabulary.

    Returns:
        The resolved list, first occurrence order, exact duplicates removed.

    Raises:
        OpticaValidationError: Naming every invalid name and every case clash.
    """
    resolved: list[str] = []
    seen: dict[str, str] = {}
    invalid: list[str] = []
    clashes: list[str] = []
    for name in names:
        problem = class_name_problem(name)
        if problem is not None:
            invalid.append(f"{name!r} {problem}")
            continue
        folded = name.casefold()
        if folded in seen:
            if seen[folded] != name:
                clash = f"{seen[folded]!r} and {name!r}"
                if clash not in clashes:
                    clashes.append(clash)
            continue
        seen[folded] = name
        resolved.append(name)

    if not invalid and not clashes:
        return resolved

    lines: list[str] = []
    if invalid:
        lines.extend(_truncate_lines(invalid))
    if clashes:
        lines.extend(
            f"{clash} differ only in case, and would be one folder on Windows and macOS"
            for clash in _truncate_lines(clashes)
        )
    count = len(invalid) + len(clashes)
    raise OpticaValidationError(
        f"{count} class name{'s' if count != 1 else ''} from {surface} cannot be used.",
        why="Every class name becomes a folder, so it must be one safe path component.",
        fix=[*lines, "Rename them and try again."],
    )


def _truncate_lines(lines: list[str]) -> list[str]:
    if len(lines) <= LIST_TRUNCATE:
        return lines
    return [*lines[:LIST_TRUNCATE], f"(and {len(lines) - LIST_TRUNCATE} more)"]


def require_min_classes(classes: Sequence[str], *, flag: str = "--classes") -> None:
    """Refuse fewer than two resolved classes.

    Plan § *Class-count validation*: one collapsed check, 0 and 1 invalid
    identically, fired as early as possible — at fetch time, not deferred to
    train.

    Raises:
        OpticaValidationError: ``--classes requires at least 2 class names.``
    """
    if len(classes) >= MIN_CLASSES:
        return
    got = ", ".join(classes) if classes else "(none)"
    raise OpticaValidationError(
        f"{flag} requires at least {MIN_CLASSES} class names. Got: {got}",
        why="Training on fewer than 2 classes is meaningless.",
    )


# ----------------------------------------------------------------- blocklist


def _as_words(name: str) -> str:
    return re.sub(r"[\s_\-]+", " ", name.casefold()).strip()


def is_blocklisted(name: str) -> bool:
    """Whether ``name`` is an undefinable class name in an auto mode.

    Case-insensitive. Catches the seed list and its extensions, negated terms
    (``not_cat``, ``non-defective``, ``no dog``), placeholder labels
    (``class_a``, ``label_1``) and single characters or lone numbers.

    False positives are expected — ``positive``/``negative`` in medical imaging —
    which is why a match triggers a definition prompt rather than a hard block.
    """
    words = _as_words(name)
    return bool(
        words in BLOCKLIST
        or _NEGATION.match(words)
        or _PLACEHOLDER.match(words)
        or _SINGLE_OR_NUMBER.match(words)
    )


def sub_term_count(images_per_class: int, sub_terms: int) -> int:
    """Images to fetch per sub-term.

    ``images_per_class`` divided across the sub-terms by floor division,
    **minimum 10, and the minimum wins** — so a group's total may exceed
    ``images_per_class``, which the plan intends.
    """
    if sub_terms <= 0:
        raise ValueError("sub_terms must be positive")
    return max(MIN_IMAGES_PER_SUB_TERM, images_per_class // sub_terms)


@dataclass(frozen=True)
class Overlap:
    """Two resolved names where one contains the other.

    Attributes:
        inner: The shorter name, found inside ``outer``.
        outer: The longer name.
    """

    inner: str
    outer: str


def find_overlaps(names: Sequence[str]) -> list[Overlap]:
    """Substring overlaps between resolved names, case-insensitively.

    ``cat`` and ``wildcat`` overlap: a search for one returns the other, so the
    two classes would fetch into each other.
    """
    found: list[Overlap] = []
    words = [(name, _as_words(name)) for name in names]
    for i, (a, wa) in enumerate(words):
        for b, wb in words[i + 1 :]:
            if wa == wb:
                continue
            if wa in wb:
                found.append(Overlap(inner=a, outer=b))
            elif wb in wa:
                found.append(Overlap(inner=b, outer=a))
    return found


@dataclass
class ResolvedClass:
    """One class as the fetch will run it.

    Attributes:
        name: The folder name.
        queries: What to search for. One query for an ordinary class; the
            sub-terms, for a blocklisted name the user chose to group.
        per_query: Images to fetch for each query.
        defined_from: The blocklisted name this class came from, if any.
        grouped: Whether the queries are pooled into this one class.
    """

    name: str
    queries: list[str]
    per_query: int
    defined_from: str | None = None
    grouped: bool = False

    @property
    def target(self) -> int:
        """Total images this class aims for."""
        return self.per_query * len(self.queries)


class ClassPrompter(Protocol):
    """The questions the class-resolution sequence may ask.

    The CLI supplies a terminal implementation. A caller that cannot prompt
    supplies one that raises, which is the API's disposition.
    """

    def define(self, name: str) -> list[str]:
        """Return the concrete sub-terms for a blocklisted ``name``.

        The sequence's one **non-defaultable** step: ``--yes`` cannot answer it,
        and where no prompt can fire it raises ``OpticaValidationError``.
        """
        ...

    def group_or_separate(self, name: str, sub_terms: list[str]) -> bool:
        """Return True to pool ``sub_terms`` into one class. ``--yes``: group."""
        ...

    def accept_overlaps(self, overlaps: list[Overlap]) -> bool:
        """Return True to continue past overlapping names. ``--yes``: Y."""
        ...

    def redefine_classes(self, current: list[str]) -> list[str]:
        """Re-open the class-list prompt, returning the corrected top-level list."""
        ...

    def confirm(self, classes: list[ResolvedClass], *, clean: bool) -> bool:
        """Show the final resolved list before any fetch.

        ``--yes`` skips it for **clean** cases only; with a blocklisted name it
        still fires.
        """
        ...


@dataclass
class _Definition:
    sub_terms: list[str]
    grouped: bool


@dataclass
class _State:
    top_level: list[str]
    definitions: dict[str, _Definition] = field(default_factory=dict)


def resolve_auto_classes(
    names: Sequence[str],
    images_per_class: int,
    prompter: ClassPrompter,
) -> list[ResolvedClass]:
    """Run the auto-mode class sequence and return what the fetch will run.

    Plan § *Undefinable classes in auto modes*: **blocklist check** →
    **user-definition prompt** for each blocklisted name → **group or separate**
    → **image count** per sub-term → **overlap warning** → **confirmation**.

    An overlap declined with N re-opens *the step that produced the overlapping
    names* — the definition prompt for a sub-term, the class-list prompt for a
    top-level name — and every other answer is kept, including group-or-separate
    and the counts. The sequence then resumes at the overlap check rather than
    restarting.

    Args:
        names: The class names, already through :func:`normalize_class_names`.
        images_per_class: The resolved ``images_per_class``.
        prompter: Answers the questions.

    Returns:
        The resolved classes, in order — or an empty list when the final
        confirmation is declined, which the caller turns into exit code 3.

    Raises:
        OpticaValidationError: When a name is invalid, a case clash appears
            after definition, fewer than two classes result, or the prompter
            refuses a definition.
    """
    state = _State(top_level=list(names))
    blocklisted_any = False

    while True:
        for name in state.top_level:
            if name in state.definitions or not is_blocklisted(name):
                continue
            blocklisted_any = True
            state.definitions[name] = _define(name, prompter)

        resolved = _build(state, images_per_class)
        overlaps = find_overlaps(
            [cls.name for cls in resolved] + _grouped_terms(resolved)
        )
        if not overlaps or prompter.accept_overlaps(overlaps):
            break
        _reopen(state, overlaps, prompter)

    require_min_classes([cls.name for cls in resolved])
    clean = not blocklisted_any
    if not prompter.confirm(resolved, clean=clean):
        return []
    return resolved


def _define(name: str, prompter: ClassPrompter) -> _Definition:
    terms = normalize_class_names(
        prompter.define(name), surface=f"the definition of {name!r}"
    )
    if not terms:
        raise OpticaValidationError(
            f"{name!r} needs a concrete definition before anything is fetched.",
            why="It names no searchable, visual thing.",
            fix="Give one or more concrete sub-terms, e.g. cracked_screen,dented_case",
        )
    grouped = prompter.group_or_separate(name, terms) if len(terms) > 1 else True
    return _Definition(sub_terms=terms, grouped=grouped)


def _build(state: _State, images_per_class: int) -> list[ResolvedClass]:
    resolved: list[ResolvedClass] = []
    for name in state.top_level:
        definition = state.definitions.get(name)
        if definition is None:
            resolved.append(ResolvedClass(name, [name], images_per_class))
            continue
        count = sub_term_count(images_per_class, len(definition.sub_terms))
        if definition.grouped:
            resolved.append(
                ResolvedClass(
                    name,
                    list(definition.sub_terms),
                    count,
                    defined_from=name,
                    grouped=True,
                )
            )
        else:
            resolved.extend(
                ResolvedClass(term, [term], count, defined_from=name)
                for term in definition.sub_terms
            )
    # Separating sub-terms can reintroduce a case clash with a top-level name.
    normalize_class_names(
        [cls.name for cls in resolved], surface="the resolved class list"
    )
    return resolved


def _grouped_terms(resolved: list[ResolvedClass]) -> list[str]:
    return [term for cls in resolved if cls.grouped for term in cls.queries]


def _reopen(state: _State, overlaps: list[Overlap], prompter: ClassPrompter) -> None:
    """Re-open whichever step produced each overlapping name, keeping the rest.

    A name that is a sub-term re-opens its parent's definition prompt, with the
    group-or-separate answer kept. An overlap between two top-level names
    re-opens the class-list prompt, and the definitions of names that survive it
    are kept. An overlap between a top-level name and a sub-term re-opens only
    the definition — the sub-term is the later answer, and the plan names no
    rule for the mixed pair (``notes/build-log.md``).
    """
    sub_terms = {term for d in state.definitions.values() for term in d.sub_terms}
    via_definition: set[str] = set()
    via_class_list = False
    for overlap in overlaps:
        members = {overlap.inner, overlap.outer}
        if members & sub_terms:
            via_definition |= members & sub_terms
        else:
            via_class_list = True

    for parent, kept in list(state.definitions.items()):
        if not via_definition & set(kept.sub_terms):
            continue
        terms = normalize_class_names(
            prompter.define(parent), surface=f"the definition of {parent!r}"
        )
        state.definitions[parent] = _Definition(
            sub_terms=terms or kept.sub_terms, grouped=kept.grouped
        )

    if via_class_list:
        new_top = normalize_class_names(prompter.redefine_classes(list(state.top_level)))
        state.definitions = {
            name: kept for name, kept in state.definitions.items() if name in new_top
        }
        state.top_level = new_top
