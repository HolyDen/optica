"""The Config Manager: priority resolution, reading, and writing.

Implements plan § "Configuration".

Priority, highest to lowest::

    CLI flags > project-local .optica.toml > env vars > ~/.optica/config.toml
    > built-in defaults

A ``.env`` file sits **at** the env-var tier rather than beside it:
``python-dotenv`` loads it into the environment, so its values inherit env-var
precedence instead of forming a sixth tier.

Writing is line-oriented rather than a serialise-the-whole-document round trip,
because ``config --init`` emits a file of **commented** keys and a round trip
would discard every one of them.
"""

from __future__ import annotations

import difflib
import tomllib
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from optica.config.defaults import (
    API_KEYS,
    CONFIG_KEYS,
    DEFAULTS,
    KEY_HELP,
    env_var_for,
)
from optica.config.schema import EnvConfig, OpticaConfig, _coerce, validate_values
from optica.exceptions import OpticaConfigError

__all__ = ["ConfigManager", "ResolvedConfig", "Source", "ViewRow"]

_MASK = "••••••••"
_INIT_HEADER = """# Optica project configuration.
#
# Committed deliberately, like pyproject.toml: teammates and CI share the same
# Optica settings. API keys are never stored here -- they live in
# ~/.optica/config.toml or in the environment.
#
# Every key below is commented out, so nothing here is set; uncomment what you
# want to override. Values shown are Optica's built-in defaults.
"""


class Source(StrEnum):
    """Where a resolved value came from."""

    FLAG = "flag"
    PROJECT = "project config"
    ENV = "env"
    GLOBAL = "global config"
    DEFAULT = "default"

    @property
    def coarse(self) -> str:
        """The label error messages use.

        Plan § "Configuration" annotates its split-sum example with ``config``
        and ``default`` only, so the two file tiers and the environment collapse
        to ``config`` in an error. ``--view`` keeps the precise label, because
        *"is Optica using the key from my environment or the stale one in my
        global config?"* is the question people actually hit.
        """
        if self is Source.DEFAULT:
            return "default"
        if self is Source.FLAG:
            return "flag"
        return "config"


@dataclass(frozen=True)
class ViewRow:
    """One line of ``optica config --view``.

    Attributes:
        key: The config key.
        value: The value, already masked if it is an API key.
        source: Which tier supplied it.
        at_default: Whether the key was never explicitly set anywhere.
        is_set: False only for an API key that is set nowhere, which renders as
            ``(not set)`` — absent and defaulted are different states, and only
            these keys can be absent.
    """

    key: str
    value: str
    source: Source
    at_default: bool
    is_set: bool = True


@dataclass(frozen=True)
class ResolvedConfig:
    """A validated configuration, with the provenance of every key.

    Attributes:
        config: The typed, validated values.
        sources: Which tier supplied each key.
        flag_names: For keys set by a flag, the flag's spelling — so a range
            error can name the flag that set the value rather than "config".
    """

    config: OpticaConfig
    sources: dict[str, Source]
    flag_names: dict[str, str] = field(default_factory=dict)

    def source_label(self, key: str) -> str:
        """Return the label an error message should use for ``key``."""
        source = self.sources.get(key, Source.DEFAULT)
        if source is Source.FLAG and key in self.flag_names:
            return self.flag_names[key]
        return source.coarse


class ConfigManager:
    """Reads, resolves and writes Optica's two config files.

    Args:
        project_dir: The directory holding ``.optica.toml`` and ``.env``.
            Defaults to the current working directory.
        home: The directory holding ``.optica/``. Defaults to the user's home.
    """

    def __init__(
        self, project_dir: Path | None = None, home: Path | None = None
    ) -> None:
        self.project_dir = Path(project_dir) if project_dir else Path.cwd()
        self.home = Path(home) if home else Path.home()

    @property
    def project_path(self) -> Path:
        """The project-local config file. Committed, not gitignored."""
        return self.project_dir / ".optica.toml"

    @property
    def global_path(self) -> Path:
        """The global config file. Holds defaults and API keys."""
        return self.home / ".optica" / "config.toml"

    @property
    def dotenv_path(self) -> Path:
        """The project's ``.env``. Gitignored -- it is where keys live."""
        return self.project_dir / ".env"

    # ------------------------------------------------------------------ read

    def _read_toml(self, path: Path, tier: str) -> dict[str, Any]:
        """Parse one config file, or return an empty mapping if absent."""
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            return {}
        except OSError as exc:
            raise OpticaConfigError(
                f"Could not read {path}",
                why=f"{type(exc).__name__}: {exc}",
                fix="Check the file's permissions, or delete it to start over.",
            ) from exc

        try:
            parsed = tomllib.loads(raw.decode("utf-8"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
            raise OpticaConfigError(
                f"{path} is not valid TOML",
                why=f"{exc}",
                fix=[
                    "Fix the syntax, or delete the file to fall back to defaults.",
                    "Run: optica config --view to see what Optica resolves without it.",
                ],
            ) from exc

        self._reject_unknown_keys(parsed, path)
        if tier == "project":
            self._reject_api_keys_in_project(parsed, path)
        return parsed

    @staticmethod
    def _reject_unknown_keys(parsed: dict[str, Any], path: Path) -> None:
        """Reject any key Optica does not define, with a suggestion if close.

        Nested tables are rejected too: all V1 config keys are flat.
        """
        problems: list[str] = []
        for key, value in parsed.items():
            if isinstance(value, dict):
                problems.append(
                    f"[{key}] is a table; all Optica config keys are flat in V1."
                )
                continue
            if key in DEFAULTS:
                continue
            close = difflib.get_close_matches(key, CONFIG_KEYS, n=1, cutoff=0.6)
            if close:
                problems.append(
                    f"{key!r} is not a config key. Did you mean {close[0]!r}?"
                )
            else:
                problems.append(f"{key!r} is not a config key.")
        if problems:
            raise OpticaConfigError(
                f"Unknown config key in {path}",
                why=" ".join(problems),
                fix="Run: optica config --view to see every valid key.",
            )

    @staticmethod
    def _reject_api_keys_in_project(parsed: dict[str, Any], path: Path) -> None:
        """Refuse an API key found in the project-local file.

        The file is committed by design, so a key that merely *worked* there
        would reach version control with no signal. Enforced at both ends:
        ``--init`` never emits the key, and this rejects one that was added by
        hand.
        """
        found = [key for key in parsed if key in API_KEYS]
        if not found:
            return
        raise OpticaConfigError(
            f"API key found in {path}",
            why=(
                f"{', '.join(sorted(found))} must never be stored in a "
                "committed file."
            ),
            fix=[
                f"Remove {found[0]} from {path.name}.",
                f"Run: optica config --set {found[0]} <value>"
                "  (writes to the global config)",
                f"Or export {env_var_for(found[0])} in your environment.",
            ],
        )

    def _env_values(self) -> dict[str, Any]:
        """Return the environment tier, with ``.env`` folded into it."""
        if self.dotenv_path.exists():
            # `override=False`: a real environment variable still wins over the
            # file, which is what keeps `.env` *at* the env tier rather than
            # above it.
            load_dotenv(self.dotenv_path, override=False)
        return EnvConfig().explicit()

    def resolve(
        self,
        overrides: dict[str, Any] | None = None,
        flag_names: dict[str, str] | None = None,
    ) -> ResolvedConfig:
        """Resolve the full configuration, validating every value.

        Args:
            overrides: Values supplied by CLI flags, highest priority.
            flag_names: For each overridden key, the flag that set it, so an
                error can name the flag rather than "config".

        Returns:
            The resolved configuration and the provenance of every key.

        Raises:
            OpticaConfigError: On an unknown key, an API key in the
                project-local file, a bad type, an out-of-range value, or a
                split-sum mismatch. Range and type problems are collected and
                reported together rather than one at a time.
        """
        tiers: list[tuple[Source, dict[str, Any]]] = [
            (Source.FLAG, {k: v for k, v in (overrides or {}).items() if v is not None}),
            (Source.PROJECT, self._read_toml(self.project_path, "project")),
            (Source.ENV, self._env_values()),
            (Source.GLOBAL, self._read_toml(self.global_path, "global")),
        ]

        values: dict[str, Any] = dict(DEFAULTS)
        sources: dict[str, Source] = dict.fromkeys(DEFAULTS, Source.DEFAULT)
        labels: dict[str, str] = {}

        # Lowest priority first, so a higher tier simply overwrites.
        for source, tier in reversed(tiers):
            for key, value in tier.items():
                if key not in DEFAULTS:
                    continue
                values[key] = value
                sources[key] = source

        problems: list[str] = []
        for key in CONFIG_KEYS:
            label = sources[key].coarse
            if sources[key] is Source.FLAG and flag_names and key in flag_names:
                label = flag_names[key]
            labels[key] = label
            if sources[key] is Source.DEFAULT:
                continue
            try:
                values[key] = _coerce(key, values[key], label)
            except OpticaConfigError as exc:
                problems.append(f"{exc.message}. {exc.why}")

        problems.extend(validate_values(values, labels))
        if problems:
            raise OpticaConfigError(
                "Invalid configuration"
                if len(problems) > 1
                else problems[0].split(".")[0],
                why=problems[0] if len(problems) == 1 else None,
                fix=problems if len(problems) > 1 else [],
            )

        return ResolvedConfig(
            config=OpticaConfig(**values),
            sources=sources,
            flag_names=dict(flag_names or {}),
        )

    # ----------------------------------------------------------------- write

    def validate_key(self, key: str) -> None:
        """Reject an unknown key **at write time**, not at the next load.

        Writing through would let ``optica config --set epocs 20`` report
        success and break the *next* command instead, at a distance from the
        typo. A close match gives a suggestion; no close match lists the keys.
        """
        if key in DEFAULTS:
            return
        close = difflib.get_close_matches(key, CONFIG_KEYS, n=1, cutoff=0.6)
        if close:
            raise OpticaConfigError(
                f"Unknown config key: {key}",
                why=f"Did you mean {close[0]}?",
                fix=f"Run: optica config --set {close[0]} <value>",
            )
        raise OpticaConfigError(
            f"Unknown config key: {key}",
            why="Optica has no setting by that name.",
            fix="Run: optica config --view to see every valid key.",
            options=list(CONFIG_KEYS),
        )

    def parse_value(self, key: str, raw: str) -> Any:
        """Convert a command-line string to the key's declared type.

        Raises:
            OpticaConfigError: When the text is not a value of that type, or
                when the value is outside the key's domain. The domain check runs
                here as well as at load, so ``--set`` cannot store a value the
                next command would reject.
        """
        default = DEFAULTS[key]
        value: Any
        if key in API_KEYS:
            value = raw
        elif isinstance(default, bool):
            lowered = raw.strip().lower()
            if lowered not in {"true", "false"}:
                raise OpticaConfigError(
                    f"{key} must be true or false",
                    why=f"Got: {raw!r}",
                    fix=f"Run: optica config --set {key} true",
                )
            value = lowered == "true"
        elif isinstance(default, int):
            try:
                value = int(raw)
            except ValueError as exc:
                raise OpticaConfigError(
                    f"{key} must be a whole number",
                    why=f"Got: {raw!r}",
                    fix=f"Run: optica config --set {key} {default}",
                ) from exc
        elif isinstance(default, float):
            try:
                value = float(raw)
            except ValueError as exc:
                raise OpticaConfigError(
                    f"{key} must be a number",
                    why=f"Got: {raw!r}",
                    fix=f"Run: optica config --set {key} {default}",
                ) from exc
        else:
            value = raw

        problems = validate_values({key: value}, {key: "flag"})
        # The split-sum check reads all three keys, so it can fire on a value
        # this call did not set; only this key's own problems belong here.
        mine = [problem for problem in problems if problem.startswith(f"{key} ")]
        if mine:
            raise OpticaConfigError(
                f"Invalid value for {key}",
                why=mine[0],
                fix=f"Run: optica config --set {key} {default}",
            )
        return value

    def target_for_set(self, *, use_global: bool = False) -> Path:
        """Return the file ``--set`` writes to.

        Project-local if it exists, global otherwise; ``--global`` forces
        global. API keys always go to the global file — ``--global`` is implied
        for them and need not be passed.
        """
        if use_global or not self.project_path.exists():
            return self.global_path
        return self.project_path

    def set_key(
        self, key: str, raw: str, *, use_global: bool = False
    ) -> tuple[Path, Any]:
        """Write one config key, creating the target file if needed.

        Returns:
            The file written to, and the parsed value. The path is returned so
            the caller can report it: a file the user did not know appeared is
            the outcome this reporting exists to prevent.

        Raises:
            OpticaConfigError: On an unknown key or an invalid value.
        """
        self.validate_key(key)
        value = self.parse_value(key, raw)
        target = (
            self.global_path
            if key in API_KEYS
            else self.target_for_set(use_global=use_global)
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_key(target, key, value)
        return target, value

    def init_project(self) -> Path:
        """Write ``.optica.toml`` with every key present but commented out.

        Discoverable — a user sees the whole surface and uncomments what they
        want — while nothing is *set*, so ``--view``'s still-at-default
        annotation keeps working for projects created this way.
        ``flickr_api_key`` is never emitted: the file is committed, so a
        commented credential there is an invitation to uncomment one into
        version control.
        """
        lines = [_INIT_HEADER]
        for key in CONFIG_KEYS:
            if key in API_KEYS:
                continue
            help_text = KEY_HELP.get(key)
            if help_text:
                lines.append(f"# {help_text}")
            lines.append(f"# {key} = {_format_value(DEFAULTS[key])}")
            lines.append("")
        self.project_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        return self.project_path

    # ------------------------------------------------------------------ view

    def view(self, resolved: ResolvedConfig | None = None) -> list[ViewRow]:
        """Return the resolved config with source annotations.

        API keys render masked but keep their normal source annotation — the
        annotation is the point, and it is answerable without disclosing a
        character. A key set nowhere renders as ``(not set)``.
        """
        resolution = resolved or self.resolve()
        values = resolution.config.model_dump()
        rows: list[ViewRow] = []
        for key in CONFIG_KEYS:
            source = resolution.sources.get(key, Source.DEFAULT)
            value = values[key]
            if key in API_KEYS:
                if value is None:
                    rows.append(
                        ViewRow(key, "(not set)", source, at_default=False, is_set=False)
                    )
                    continue
                rows.append(ViewRow(key, _MASK, source, at_default=False))
                continue
            rows.append(
                ViewRow(
                    key,
                    _format_value(value),
                    source,
                    at_default=source is Source.DEFAULT,
                )
            )
        return rows


def _format_value(value: Any) -> str:
    """Render a value as TOML."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f'"{value}"'
    if value is None:
        return '""'
    return str(value)


def _write_key(path: Path, key: str, value: Any) -> None:
    """Set ``key`` in a TOML file, replacing a commented line if one exists.

    Line-oriented on purpose: ``config --init`` writes a file of commented keys,
    and re-serialising the parsed document would delete every comment in it —
    including the ones that make the file discoverable.
    """
    rendered = f"{key} = {_format_value(value)}"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = []

    for index, line in enumerate(lines):
        stripped = line.strip()
        without_comment = stripped.lstrip("#").strip()
        if without_comment.startswith(f"{key} ") or without_comment.startswith(f"{key}="):
            lines[index] = rendered
            break
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(rendered)

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
