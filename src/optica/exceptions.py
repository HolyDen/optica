"""All Optica exception classes, and the process exit codes they map to.

Implements plan § "Exceptions". One file, universal ``Optica*`` prefix, a flat
hierarchy with exactly one nested branch (``OpticaMissingExtraError``).
``OpticaWarning`` lives here too despite subclassing :class:`UserWarning` rather
than :class:`OpticaError` — a module holding one warning class is the split this
consolidation exists to avoid.

``ExitCode`` lives here rather than in the CLI layer because the plan states the
exit-code table inside § "Exceptions" itself, directly after the table mapping
error families to classes: the two are one contract, and the CLI is specified as
a thin entry point holding no business logic.
"""

from __future__ import annotations

from enum import IntEnum

__all__ = [
    "ExitCode",
    "OpticaBrowserServerError",
    "OpticaCLIPError",
    "OpticaCLIPLoadError",
    "OpticaConfigError",
    "OpticaCurationError",
    "OpticaError",
    "OpticaExportError",
    "OpticaFetchError",
    "OpticaLabelingError",
    "OpticaMissingExtraError",
    "OpticaSetupError",
    "OpticaTorchError",
    "OpticaTrainingError",
    "OpticaValidationError",
    "OpticaWarning",
    "OpticaWebError",
]


class ExitCode(IntEnum):
    """Process exit codes, per plan § "Exceptions" → *Exit codes*.

    V1 is designed to be scripted, so the exit code is what a CI job or a
    container build actually branches on. Codes are deliberately **not** per
    exception class: the class is available to a Python caller through
    ``except``, and post-V1 subclass families would churn any code-to-class
    mapping a CI script came to depend on.
    """

    SUCCESS = 0
    """Success."""

    ERROR = 1
    """Any :class:`OpticaError`."""

    USAGE = 2
    """A malformed invocation. This code is Click's own — every parser error it
    raises is a ``UsageError``, whose ``exit_code`` is already ``2`` — and Optica
    matches it rather than contending for it."""

    ABORTED = 3
    """User abort: a declined prompt, or an incomplete-completion message.

    Distinct from :attr:`ERROR` because under ``--yes`` a prompt should never
    have appeared, and distinct from :attr:`USAGE` because a declined prompt is
    not a parser error — collapsing the two would leave a CI script unable to
    tell a malformed command line from a prompt it could not answer.
    """

    INTERRUPTED = 130
    """Interrupted (SIGINT), per shell convention. Also ``click.Abort``."""


class OpticaError(Exception):
    """Base class for every Optica error.

    Carries the three-part error structure plan § "Coding Style" requires —
    what went wrong / why, in one sentence / how to fix, as a specific command —
    as data rather than as a pre-formatted string, so that the one renderer in
    :mod:`optica.utils.logging` decides how it reaches the terminal and the API
    can read the parts back off the exception.

    Raised directly only where no subsystem's contract is the one violated,
    which is a signal the hierarchy is missing a class rather than a licence to
    use the base class routinely.

    Args:
        message: What went wrong. One line, no trailing period needed.
        why: One sentence of explanation. Optional.
        fix: How to fix it — a specific command wherever one exists. Accepts a
            single string or several, rendered one per line.
        options: Valid values, for fixed-value flags. Plan § "Error handling and
            prompt conventions" requires these in every such error.
        default: The default value for a fixed-value flag, rendered as
            ``Default: X`` where applicable.
    """

    def __init__(
        self,
        message: str,
        *,
        why: str | None = None,
        fix: str | list[str] | None = None,
        options: list[str] | None = None,
        default: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.why = why
        self.fix: list[str] = [fix] if isinstance(fix, str) else list(fix or [])
        self.options = list(options or [])
        self.default = default


class OpticaMissingExtraError(OpticaError):
    """A required extra is not installed.

    The one nested branch in the V1 hierarchy: it lets a caller catch any
    missing-extra condition at a single point. Its subclasses each carry the
    install instruction for their own extra, so a raw :class:`ImportError`
    traceback never reaches the user.

    Messages name the **capability**, never the command or flag that requested
    it — the same error is raised from the CLI and from the Python API, and a
    message written in either surface's vocabulary is wrong on the other.
    """

    default_message: str = "This operation requires an extra that is not installed."

    def __init__(self, message: str | None = None, **kwargs: object) -> None:
        super().__init__(message or self.default_message, **kwargs)  # type: ignore[arg-type]


class OpticaTorchError(OpticaMissingExtraError):
    """The torch stack is missing."""

    default_message = "This operation requires the Optica ML stack. Run: optica setup"


class OpticaWebError(OpticaMissingExtraError):
    """``optica[web]`` is missing."""

    default_message = (
        "This operation requires the web extras. "
        "Run: optica setup or pip install optica[web]"
    )


class OpticaCLIPError(OpticaMissingExtraError):
    """``optica[clip]`` is missing.

    Means only that the extra is absent, consistent with its siblings. A CLIP
    **model-load** failure is :class:`OpticaCLIPLoadError`: the two need
    different messages, and one message cannot serve both.
    """

    default_message = (
        "CLIP filtering requires the clip extra. "
        "Run: optica setup --include-extras clip or pip install optica[clip]"
    )


class OpticaCLIPLoadError(OpticaError):
    """CLIP model load failure — corrupt or interrupted weights.

    Parented to :class:`OpticaError` rather than to :class:`OpticaFetchError`
    because CLIP weights load during training and inference too, so filing it
    under fetch would misclassify most occurrences. It is also the one class the
    "a hard error's class is the subsystem whose contract it violates" rule does
    not reach, for the same reason.
    """


class OpticaConfigError(OpticaError):
    """Invalid config values or missing required keys.

    Covers the split-sum mismatch, numeric range violations, a ``clip_threshold``
    out of range, and an unknown config key.
    """


class OpticaTrainingError(OpticaError):
    """Training failure, bad dataset, or OOM."""


class OpticaExportError(OpticaError):
    """Export failure."""


class OpticaFetchError(OpticaError):
    """Missing API key, rate limit, or network failure."""


class OpticaValidationError(OpticaError):
    """Inputs, or destination state, that the caller must resolve.

    The input contract specifically — which is what makes it broad without being
    a catch-all: it is bounded by the other classes, not by a list. Covers image
    validation rejecting everything or falling below the hard floor, class-count
    and manifest-shape violations, mutually exclusive input flags, a refused
    ``dataset/`` overwrite, and the blocklist prompt in a non-prompting context.
    """


class OpticaSetupError(OpticaError):
    """Setup failure.

    Covers environment resolution and mismatch, hardware detection, and install
    failure.

    Setup is a subsystem rather than a caller, so it gets a descriptively named
    class of its own — without it, setup's hard errors fit nothing in the
    hierarchy.
    """


class OpticaBrowserServerError(OpticaError):
    """Browser server (label and curate): port unavailable, browser launch failure.

    Named for the subsystem rather than for a caller: ``optica label`` and
    ``optica curate`` share one server, so a caller-named class would misreport
    half its failures. The qualifier separates it from ``OpticaWebError``, whose
    "web" names the missing extra.
    """


class OpticaLabelingError(OpticaError):
    """A labeling session file is unreadable, corrupt, or an unrecognized version."""


class OpticaCurationError(OpticaError):
    """``curation.json`` is unreadable, corrupt, or an unrecognized version."""


class OpticaWarning(UserWarning):
    """Optica's warning category for the Python API.

    Deliberately **not** an :class:`OpticaError` — it subclasses
    :class:`UserWarning` so that callers can filter it with the standard
    :mod:`warnings` machinery.
    """
